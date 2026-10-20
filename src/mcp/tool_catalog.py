"""MCP tool directory: grouping and display name for setting UI.

Contract (complied during development)
-----------------
1. **Built-in tools** are placed in ``src/mcp/tools/<pkg>/register.py``, using ``McpTool("name", ...)``
   or ``McpTool(name="name", ...)`` registration; the directory is obtained by scanning these files, **do not hard-code the list/Chinese title**.
2. **Group id / Group title** = package directory name ``<pkg>`` (such as ``music``, ``weather``, ``camera``),
   and disk ``tools/<pkg>`` is consistent, and the package name is directly displayed on the setting page.
3. **Tool display name** = name last paragraph (``music_player.pause`` → ``pause``).
4. **Plug-in**: manifest.tools/source code ``name=`` heuristic; group title = plugin id
   (if the manifest has a ``name`` field, use this field, which is self-describing by the plug-in and not hard-coded by the host).
5. **Disable** configuration: ``MCP_TOOLS.DISABLED`` (tool full name list).

Names that have been registered at runtime but not scanned will be merged into the directory (source=runtime).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Regular: Scan the registration source code
# ---------------------------------------------------------------------------

# McpTool("a.b", ...) or McpTool('a.b',
_MCP_TOOL_POS_NAME = re.compile(
    r"""McpTool\s*\(\s*['"]([a-zA-Z][a-zA-Z0-9_.]*)['"]"""
)
# McpTool(name="a.b"
_MCP_TOOL_KW_NAME = re.compile(
    r"""McpTool\s*\([^)]*?\bname\s*=\s*['"]([a-zA-Z][a-zA-Z0-9_.]*)['"]""",
    re.DOTALL,
)
# Plug-in/General name="..."
_NAME_KWARG_RE = re.compile(
    r"""\bname\s*=\s*['"]([a-zA-Z0-9_.-]+)['"]"""
)
def _tools_package_dir() -> Path:
    return Path(__file__).resolve().parent / "tools"


def tool_group(name: str, *, fallback_pkg: str | None = None) -> str:
    """group id: Priority is given to the package name passed in by the caller; otherwise, the name prefix heuristic is used."""
    if fallback_pkg:
        return fallback_pkg
    if "." in name:
        parts = name.split(".")
        if name.startswith("self.") and len(parts) >= 2:
            return ".".join(parts[:2])  # self.application
        return parts[0]
    return "other"


def tool_label(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def group_label(group_id: str) -> str:
    return group_id


def _extract_mcp_tool_names(text: str) -> list[str]:
    """returns the tool_name list (removing duplication and preserving order)."""
    found: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        found.append(name)

    for m in _MCP_TOOL_POS_NAME.finditer(text):
        add(m.group(1))
    for m in _MCP_TOOL_KW_NAME.finditer(text):
        add(m.group(1))
    return found


def _scan_register_file(path: Path, pkg: str) -> list[dict[str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []

    rows: list[dict[str, str]] = []
    for name in _extract_mcp_tool_names(text):
        rows.append(
            {
                "name": name,
                "group": pkg,
                "groupLabel": pkg,  # without writing Chinese characters, group title = directory name
                "label": tool_label(name),
                "source": "builtin",
            }
        )
    return rows


@lru_cache(maxsize=1)
def discover_builtin_catalog_rows() -> tuple[dict[str, str], ...]:
    """Scan ``src/mcp/tools/*/register.py``, the results are cached (in-process)."""
    root = _tools_package_dir()
    if not root.is_dir():
        return tuple()

    rows: list[dict[str, str]] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        reg = child / "register.py"
        if not reg.is_file():
            continue
        rows.extend(_scan_register_file(reg, child.name))
    # tuple of frozendict-like: use tuple[dict] but dict is variable; cache returns tuple copy using
    return tuple(rows)


def clear_builtin_catalog_cache() -> None:
    discover_builtin_catalog_rows.cache_clear()


def builtin_catalog_rows() -> list[dict[str, str]]:
    """Built-in tool row in the settings page (scan tools package, not hard-coded list)."""
    return [dict(r) for r in discover_builtin_catalog_rows()]


def normalize_disabled(names: Any) -> list[str]:
    if not names:
        return []
    if isinstance(names, str):
        names = [names]
    out: list[str] = []
    seen: set[str] = set()
    for n in names:
        s = str(n).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def is_tool_enabled(name: str, disabled: list[str] | set[str] | None) -> bool:
    if not disabled:
        return True
    return name not in set(disabled)


# is compatible with old calls: dynamic group label table (plug-ins will be written in)
GROUP_LABELS: dict[str, str] = {}


def _plugins_dir_from_config() -> Path | None:
    try:
        from src.utils.config_manager import get_config
        from src.utils.resource_finder import get_user_data_dir

        raw = get_config().get_config("MCP_PLUGINS.DIR", None)
        if raw and str(raw).strip():
            return Path(str(raw).strip()).expanduser()
        return get_user_data_dir() / "mcp_plugins"
    except Exception:
        try:
            from src.utils.resource_finder import get_user_data_dir

            return get_user_data_dir() / "mcp_plugins"
        except Exception:
            return None


def _tools_from_manifest(
    manifest: dict[str, Any], plugin_id: str
) -> list[dict[str, str]]:
    raw = manifest.get("tools")
    if not raw or not isinstance(raw, list):
        return []
    display = str(manifest.get("name") or plugin_id)
    rows: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
            label = tool_label(name)
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            label = str(
                item.get("title") or item.get("label") or tool_label(name)
            )
        else:
            continue
        if not name:
            continue
        rows.append(
            {
                "name": name,
                "group": plugin_id,
                "groupLabel": display,
                "label": label,
                "source": "plugin",
            }
        )
    return rows


def _tools_from_plugin_sources(
    path: Path, plugin_id: str, display: str
) -> list[dict[str, str]]:
    names: list[str] = []
    seen: set[str] = set()
    py_files: list[Path] = []
    if path.is_file() and path.suffix == ".py":
        py_files = [path]
    elif path.is_dir():
        for p in path.rglob("*.py"):
            if p.name.startswith("_"):
                continue
            if "lib" in p.parts or "native" in p.parts:
                continue
            py_files.append(p)
    for pf in py_files[:20]:
        try:
            text = pf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # takes precedence over McpTool(...) format
        for name in _extract_mcp_tool_names(text):
            if name not in seen:
                seen.add(name)
                names.append(name)
        if not names:
            for m in _NAME_KWARG_RE.finditer(text):
                n = m.group(1)
                if "." not in n and len(n) < 4:
                    continue
                if n not in seen:
                    seen.add(n)
                    names.append(n)
    return [
        {
            "name": n,
            "group": plugin_id,
            "groupLabel": display,
            "label": tool_label(n),
            "source": "plugin",
        }
        for n in names
    ]


def discover_plugin_catalog_rows() -> list[dict[str, str]]:
    root = _plugins_dir_from_config()
    if root is None or not root.is_dir():
        return []

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        children = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except Exception:
        return []

    for child in children:
        if child.name.startswith(".") or child.name.startswith("_"):
            continue
        plugin_id = child.stem if child.is_file() else child.name
        display = plugin_id
        manifest: dict[str, Any] = {}

        if child.is_dir():
            mf = child / "manifest.json"
            if mf.is_file():
                try:
                    manifest = json.loads(mf.read_text(encoding="utf-8"))
                    plugin_id = str(manifest.get("id") or plugin_id)
                    display = str(manifest.get("name") or plugin_id)
                except Exception:
                    manifest = {}
            GROUP_LABELS[plugin_id] = display
            found = _tools_from_manifest(manifest, plugin_id)
            if not found:
                found = _tools_from_plugin_sources(child, plugin_id, display)
            for r in found:
                if r["name"] in seen:
                    continue
                seen.add(r["name"])
                rows.append(r)
        elif child.suffix == ".py" and child.is_file():
            GROUP_LABELS[plugin_id] = plugin_id
            for r in _tools_from_plugin_sources(child, plugin_id, plugin_id):
                if r["name"] in seen:
                    continue
                seen.add(r["name"])
                rows.append(r)
    return rows


def full_catalog_rows(
    *,
    runtime_names: list[str] | None = None,
    extra_disabled: list[str] | None = None,
) -> list[dict[str, str]]:
    """built-in (scan tools/) disk plug-in runtime disabled residual."""
    rows = builtin_catalog_rows()
    seen = {r["name"] for r in rows}
    pkg_labels = {r["group"]: r["groupLabel"] for r in rows}

    for r in discover_plugin_catalog_rows():
        if r["name"] in seen:
            continue
        seen.add(r["name"])
        rows.append(r)

    def _append_unknown(name: str, source: str) -> None:
        if name in seen:
            return
        g, label = _runtime_group_for(name, pkg_labels)
        rows.append(
            {
                "name": name,
                "group": g,
                "groupLabel": label,
                "label": tool_label(name),
                "source": source,
            }
        )
        seen.add(name)

    for name in runtime_names or []:
        _append_unknown(name, "runtime")
    for name in normalize_disabled(extra_disabled):
        _append_unknown(name, "external")

    return rows


def _runtime_group_for(
    name: str, pkg_labels: dict[str, str]
) -> tuple[str, str]:
    """Runtime/residual tools: try to belong to the scanned built-in package group."""
    builtins = discover_builtin_catalog_rows()
    for row in builtins:
        if name == row["name"]:
            return row["group"], row["groupLabel"]

    for row in builtins:
        bn = row["name"]
        if "." not in name or "." not in bn:
            continue
        np, bp = name.split("."), bn.split(".")
        if name.startswith("self.") and bn.startswith("self."):
            if len(np) >= 2 and len(bp) >= 2 and np[:2] == bp[:2]:
                return row["group"], row["groupLabel"]
        elif not name.startswith("self.") and np[0] == bp[0]:
            return row["group"], row["groupLabel"]

    g = tool_group(name)
    return g, pkg_labels.get(g, GROUP_LABELS.get(g, g))
