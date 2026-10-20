"""Plug-in python-subprocess runtime: independent process JSON line protocol proxy tool.

The main process does not import plug-in code; only starts worker, bootstrap pull tool schema,
and proxy McpTool callback as a call to the subprocess.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from src.i18n import t
from src.logging import get_logger
from src.mcp.tooling import McpTool, Property, PropertyList, PropertyType
from src.utils.resource_finder import get_app_root

logger = get_logger()

# Single call default timeout (seconds)
DEFAULT_CALL_TIMEOUT = 60.0
BOOTSTRAP_TIMEOUT = 30.0


class PluginSubprocessSession:
    """manages the life cycle and RPC of a plug-in sub-process."""

    def __init__(
        self,
        *,
        plugin_id: str,
        plugin_root: Path,
        entry: str,
        platform_tag: str,
        allow_get: list[str],
        capabilities: dict[str, Any],
        python_executable: str | None = None,
        call_timeout: float = DEFAULT_CALL_TIMEOUT,
    ) -> None:
        self.plugin_id = plugin_id
        self.plugin_root = Path(plugin_root)
        self.entry = entry
        self.platform_tag = platform_tag
        self.allow_get = list(allow_get)
        self.capabilities = dict(capabilities)
        self.python_executable = python_executable or sys.executable
        self.call_timeout = call_timeout
        self._proc: subprocess.Popen[str] | None = None
        self._id = 0
        self._lock = threading.Lock()
        self._tools_meta: list[dict[str, Any]] = []

    @property
    def tools_meta(self) -> list[dict[str, Any]]:
        return list(self._tools_meta)

    def start_and_bootstrap(self) -> list[dict[str, Any]]:
        """Start the process and bootstrap, return to tools schema List."""
        worker = Path(__file__).resolve().parent / "subprocess_worker.py"
        if not worker.is_file():
            raise RuntimeError(t('缺少 worker 脚本: {value1}', value1=worker))

        env = os.environ.copy()
        # to avoid child process inheritance GUI/Qt related interference (optional)
        env.setdefault("PYTHONUNBUFFERED", "1")

        self._proc = subprocess.Popen(
            [self.python_executable, str(worker)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
            cwd=str(self.plugin_root),
        )
        # Read stderr in the background to avoid pipe blocking
        threading.Thread(
            target=self._drain_stderr,
            name=f"mcp-plugin-err:{self.plugin_id}",
            daemon=True,
        ).start()

        app_root = str(get_app_root())
        result = self._request(
            "bootstrap",
            {
                "plugin_root": str(self.plugin_root.resolve()),
                "plugin_id": self.plugin_id,
                "entry": self.entry,
                "platform_tag": self.platform_tag,
                "allow_get": self.allow_get,
                "capabilities": self._json_safe_caps(self.capabilities),
                "app_root": app_root,
            },
            timeout=BOOTSTRAP_TIMEOUT,
        )
        tools = result.get("tools") or []
        if not isinstance(tools, list):
            raise RuntimeError(t("bootstrap 返回 tools 非列表"))
        self._tools_meta = tools
        logger.info(
            t("[MCP插件:%s] subprocess 已启动 pid=%s tools=%d"),
            self.plugin_id,
            self._proc.pid if self._proc else "?",
            len(tools),
        )
        return tools

    def _json_safe_caps(self, caps: dict[str, Any]) -> dict[str, Any]:
        """capabilities must be JSON serializable; object class capabilities cannot be used by sub-processes, only snapshots are passed."""
        out: dict[str, Any] = {}
        for k, v in caps.items():
            if k == "config_readonly":
                # ConfigManager → read-only dict snapshot
                try:
                    if hasattr(v, "get_config") and hasattr(v, "_config"):
                        out[k] = dict(getattr(v, "_config", {}) or {})
                    elif isinstance(v, dict):
                        out[k] = v
                    else:
                        out[k] = {}
                except Exception:
                    out[k] = {}
            elif isinstance(v, (dict, list, str, int, float, bool)) or v is None:
                try:
                    json.dumps(v)
                    out[k] = v
                except Exception:
                    pass
            # music_player and other non-serializable objects: cannot be obtained by the sub-process side (consistent with the isolation target)
        return out

    def _drain_stderr(self) -> None:
        proc = self._proc
        if not proc or not proc.stderr:
            return
        try:
            for line in proc.stderr:
                line = line.rstrip()
                if line:
                    logger.warning(t("[MCP插件:%s:stderr] %s"), self.plugin_id, line)
        except Exception:
            pass

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _request(
        self, method: str, params: dict[str, Any], *, timeout: float
    ) -> dict[str, Any]:
        with self._lock:
            return self._request_locked(method, params, timeout=timeout)

    def _request_locked(
        self, method: str, params: dict[str, Any], *, timeout: float
    ) -> dict[str, Any]:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise RuntimeError(t('插件子进程未运行: {value1}', value1=self.plugin_id))
        if proc.poll() is not None:
            raise RuntimeError(
                t('插件子进程已退出: {value1} code={value3}', value1=self.plugin_id, value3=proc.returncode)
            )

        req_id = self._next_id()
        payload = json.dumps(
            {"id": req_id, "method": method, "params": params},
            ensure_ascii=False,
        )
        try:
            proc.stdin.write(payload + "\n")
            proc.stdin.flush()
        except Exception as e:
            raise RuntimeError(t('写入子进程失败: {value1}', value1=e)) from e

        # Read one line synchronously (with timeout)
        line_holder: list[str | None] = [None]
        err_holder: list[BaseException | None] = [None]

        def _read() -> None:
            try:
                line_holder[0] = proc.stdout.readline()
            except BaseException as e:  # noqa: BLE001
                err_holder[0] = e

        thread = threading.Thread(target=_read, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        if thread.is_alive():
            self.terminate()
            raise TimeoutError(
                t('插件 {value1} 调用 {value3} 超时（{value5}s）', value1=self.plugin_id, value3=method, value5=timeout)
            )
        if err_holder[0]:
            raise RuntimeError(t('读子进程失败: {value1}', value1=err_holder[0])) from err_holder[0]
        line = line_holder[0]
        if not line:
            raise RuntimeError(t('插件子进程无响应: {value1}', value1=self.plugin_id))

        try:
            msg = json.loads(line)
        except Exception as e:
            raise RuntimeError(t('子进程返回非 JSON: {value1}', value1=line[:200])) from e

        if msg.get("id") != req_id:
            raise RuntimeError(
                t('子进程响应 id 不匹配: expect={value1} got={value3}', value1=req_id, value3=msg.get('id'))
            )
        if "error" in msg and msg["error"]:
            err = msg["error"]
            message = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(message or "worker error")
        result = msg.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(t('子进程 result 无效: {value1!r}', value1=result))
        return result

    def call_tool_sync(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self._request(
            "call",
            {"name": name, "arguments": arguments or {}},
            timeout=self.call_timeout,
        )
        return result.get("value")

    def terminate(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin:
                try:
                    req = json.dumps(
                        {"id": self._next_id(), "method": "shutdown", "params": {}}
                    )
                    proc.stdin.write(req + "\n")
                    proc.stdin.flush()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
        except Exception as e:
            logger.debug(
                t("[MCP插件:%s] 结束子进程: %s"), self.plugin_id, e, exc_info=True
            )
            try:
                proc.kill()
            except Exception:
                pass

    def __del__(self) -> None:
        try:
            self.terminate()
        except Exception:
            pass


def _props_from_meta(prop_defs: list[dict[str, Any]] | None) -> PropertyList:
    if not prop_defs:
        return PropertyList()
    type_map = {
        "string": PropertyType.STRING,
        "str": PropertyType.STRING,
        "integer": PropertyType.INTEGER,
        "int": PropertyType.INTEGER,
        "boolean": PropertyType.BOOLEAN,
        "bool": PropertyType.BOOLEAN,
    }
    props: list[Property] = []
    for d in prop_defs:
        raw = str(d.get("type", "string")).lower()
        ptype = type_map.get(raw, PropertyType.STRING)
        props.append(
            Property(
                str(d["name"]),
                ptype,
                default_value=d.get("default", d.get("default_value")),
                min_value=d.get("min", d.get("min_value")),
                max_value=d.get("max", d.get("max_value")),
            )
        )
    return PropertyList(props)


def register_subprocess_plugin_tools(
    add_tool,
    *,
    session: PluginSubprocessSession,
    tool_owner: dict[str, str] | None = None,
    enforce_prefix: bool = False,
    prefix: str | None = None,
) -> list[str]:
    """registers the agent McpTool with the host according to session.tools_meta; returns the tool name list."""
    names: list[str] = []
    for meta in session.tools_meta:
        name = str(meta.get("name") or "").strip()
        if not name:
            continue
        if prefix and enforce_prefix and not name.startswith(str(prefix)):
            raise RuntimeError(t('工具名未使用前缀 {value1}: {value3}', value1=prefix, value3=name))
        if prefix and not name.startswith(str(prefix)):
            logger.warning(
                t("[MCP插件:%s] 工具名未使用前缀 %s: %s"),
                session.plugin_id,
                prefix,
                name,
            )

        desc = str(meta.get("description") or "")
        props = _props_from_meta(meta.get("properties") or [])

        def _make_cb(tool_name: str):
            async def _proxy(arguments: dict[str, Any]):
                return await asyncio.to_thread(
                    session.call_tool_sync, tool_name, arguments or {}
                )

            return _proxy

        add_tool(McpTool(name, desc, props, _make_cb(name)))
        names.append(name)
        if tool_owner is not None:
            tool_owner[name] = session.plugin_id
        logger.info(
            t("[MCP插件:%s] 注册代理工具(subprocess): %s"), session.plugin_id, name
        )
    return names


# In-process session table for uninstallation terminate
_SESSIONS: dict[str, PluginSubprocessSession] = {}


def track_session(plugin_id: str, session: PluginSubprocessSession) -> None:
    old = _SESSIONS.pop(plugin_id, None)
    if old is not None:
        old.terminate()
    _SESSIONS[plugin_id] = session


def drop_session(plugin_id: str) -> None:
    session = _SESSIONS.pop(plugin_id, None)
    if session is not None:
        session.terminate()


def drop_all_sessions() -> None:
    for pid in list(_SESSIONS.keys()):
        drop_session(pid)
