"""Cross-platform process management (based on psutil).

Use psutil to replace all platform-specific subprocess process lists and termination logic,
Eliminates command injection risk.
"""
import sys

import psutil

from src.i18n import t
from src.logging import get_logger

from .utils import AppMatcher

logger = get_logger()

# Electron/Chromium child process suffix, these are internal child processes of the main application
_HELPER_SUFFIXES = (
    " helper",
    " helper (gpu)",
    " helper (renderer)",
    " helper (plugin)",
    "_crashpad_handler",
)

# macOS System path prefix, the processes under these paths are system daemons
_MACOS_SYSTEM_PREFIXES = (
    "/usr/libexec/",
    "/usr/sbin/",
    "/System/Library/",
    "/Library/Apple/",
)

# Windows system process name (lowercase, excluding .exe)
_WINDOWS_SYSTEM_NAMES: set[str] = {
    "dwm",
    "winlogon",
    "csrss",
    "smss",
    "wininit",
    "services",
    "lsass",
    "svchost",
    "spoolsv",
    "taskhostw",
    "fontdrvhost",
    "dllhost",
    "ctfmon",
    "audiodg",
    "conhost",
    "sihost",
    "shellexperiencehost",
    "startmenuexperiencehost",
    "runtimebroker",
    "applicationframehost",
    "searchui",
    "lockapp",
    "explorer",
}


def _is_user_application(name: str, exe: str) -> bool:
    """Judgement Whether the process is a user-visible application."""
    name_lower = name.lower()
    exe_lower = exe.lower()

    # Electron/Chromium child processes (Helper, Renderer, GPU) Exclusion
    if any(name_lower.endswith(suffix) for suffix in _HELPER_SUFFIXES):
        return False

    if sys.platform == "darwin":
        # macOS: Only keep the .app main process under /Applications/
        if "/Applications/" in exe and ".app/" in exe:
            # Exclude child .app inside .app (e.g. Framework/Helpers/)
            app_path = exe[: exe.index(".app/") + 5]
            remaining = exe[len(app_path) :]
            if ".app/" in remaining:
                return False
            return True
        # Not /Applications but not the system path (such as Tools under ~/Library/Application Support)
        if any(exe_lower.startswith(p) for p in _MACOS_SYSTEM_PREFIXES):
            return False
        # /Library/Application Support User tools (such as security software, VPN)
        if "/Library/Application Support/" in exe and ".app" not in exe:
            return False
        # Other known system process paths
        if exe_lower.startswith("/system/") or exe_lower.startswith("/library/"):
            return False
        return False

    elif sys.platform == "win32":
        if name_lower.replace(".exe", "") in _WINDOWS_SYSTEM_NAMES:
            return False
        # Windows system directory process exclusion
        if "\\windows\\system32\\" in exe_lower:
            return False
        if "\\windows\\syswow64\\" in exe_lower:
            return False
        return True

    else:
        # Linux: Exclude system daemon process
        if exe_lower.startswith(("/usr/libexec/", "/usr/sbin/")):
            return False
        if exe_lower.startswith("/usr/bin/") and name_lower in {
            "dbus-daemon",
            "dbus-broker",
            "at-spi-bus-launcher",
            "pulseaudio",
            "pipewire",
            "systemd",
        }:
            return False
        return True


def list_running_applications(filter_name: str = "") -> list[dict]:
    """List running user applications.

    Only returns user-visible desktop applications, excluding system daemons and Electron subprocess, etc.

    Args:
        filter_name: Optional name filter keyword, relax filtering when passed in (used for kill matching)
    """
    apps: list[dict] = []
    filter_lower = filter_name.lower() if filter_name else ""

    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline", "status"]):
        try:
            info = proc.info
            name = info.get("name") or ""
            exe = info.get("exe") or ""
            pid = info.get("pid", 0)
            if not name or pid <= 4:
                continue

            # Relax the conditions when there are filter words (used for kill Matching scenarios, need to match child processes)
            if filter_lower:
                name_lower = name.lower()
                exe_lower = exe.lower()
                cmd = " ".join(info.get("cmdline") or [])
                cmd_lower = cmd.lower()
                if (
                    filter_lower not in name_lower
                    and filter_lower not in exe_lower
                    and filter_lower not in cmd_lower
                ):
                    continue
                apps.append(
                    {
                        "pid": pid,
                        "name": name,
                        "display_name": name,
                        "exe": exe,
                        "command": cmd,
                        "type": "application",
                    }
                )
            else:
                # No filter words: Strictly only return user applications
                if not _is_user_application(name, exe):
                    continue
                apps.append(
                    {
                        "pid": pid,
                        "name": name,
                        "display_name": name,
                        "exe": exe,
                        "command": " ".join(info.get("cmdline") or []),
                        "type": "application",
                    }
                )

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # Sort by name to deduplicate
    seen_pids: set[int] = set()
    unique_apps: list[dict] = []
    for app in sorted(apps, key=lambda x: x["name"].lower()):
        if app["pid"] not in seen_pids:
            seen_pids.add(app["pid"])
            unique_apps.append(app)

    return unique_apps


def kill_process(pid: int, force: bool = False) -> bool:
    """Terminate the process with the specified PID.

    Args:
        pid: Process ID
        force: True uses SIGKILL/TerminateProcess, False uses SIGTERM

    Returns:
        Whether it was successfully terminated
    """
    try:
        proc = psutil.Process(pid)
        if force:
            proc.kill()
        else:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                logger.warning(t('[ProcessManager] 进程 {value1} 未在超时内退出，强制终止', value1=pid))
                proc.kill()
        return True
    except psutil.NoSuchProcess:
        logger.warning(t('[ProcessManager] 进程不存在: {value1}', value1=pid))
        return False
    except psutil.AccessDenied as e:
        logger.warning(t('[ProcessManager] 无权终止进程 {value1}: {value3}', value1=pid, value3=e), exc_info=True)
        return False


def find_matching_processes(app_name: str) -> list[dict]:
    """finds running processes that match the application name.

    Use AppMatcher for smart matching (including special mapping, fuzzy matching, etc.).

    Args:
        app_name: Target application name

    Returns:
        Matching process information list, sorted in descending order of matching degree
    """
    all_apps = list_running_applications()
    matched: list[tuple[int, dict]] = []

    for app in all_apps:
        score = AppMatcher.match_application(app_name, app)
        if score >= 50:
            matched.append((score, app))

    matched.sort(key=lambda x: x[0], reverse=True)
    return [app for _, app in matched]


def kill_application_by_name(app_name: str, force: bool = False) -> bool:
    """Kill app by name (match all related processes).

    Args:
        app_name: Application name
        force: whether to force the termination of

    Returns:
        Whether at least one process was terminated
    """
    matched = find_matching_processes(app_name)
    if not matched:
        logger.info(t('[ProcessManager] 未找到匹配的运行进程: {value1}', value1=app_name))
        return False

    logger.info(t('[ProcessManager] 找到 {value1} 个匹配进程: {value3}', value1=len(matched), value3=app_name))

    # Group by process group, try to kill child process before parent process
    success_count = 0
    for app in matched:
        pid = app["pid"]
        try:
            proc = psutil.Process(pid)
            # Terminate the child process first
            children = proc.children(recursive=True)
            for child in children:
                try:
                    if force:
                        child.kill()
                    else:
                        child.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Terminate the main process
            if kill_process(pid, force):
                success_count += 1
                logger.info(t('[ProcessManager] 已终止进程: {value1} (PID={value3})', value1=app['name'], value3=pid))
        except psutil.NoSuchProcess:
            logger.debug(t('[ProcessManager] 进程已退出: PID={value1}', value1=pid))
        except psutil.AccessDenied as e:
            logger.warning(t('[ProcessManager] 无权操作进程 PID={value1}: {value3}', value1=pid, value3=e), exc_info=True)

    logger.info(
        t('[ProcessManager] 终止操作完成，成功 {value1}/{value3} 个进程', value1=success_count, value3=len(matched))
    )
    return success_count > 0
