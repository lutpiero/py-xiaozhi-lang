"""macOS application scanner.

Specialized for application scanning and management of macOS systems
"""
import platform
import subprocess
from pathlib import Path
from typing import Dict, List

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


def scan_installed_applications() -> List[Dict[str, str]]:
    """Scans installed applications in macOS systems.

    Returns:
        List[Dict[str, str]]: Application list
    """
    if platform.system() != "Darwin":
        return []

    apps = []

    # Scan for /Applications Catalog
    applications_dir = Path("/Applications")
    if applications_dir.exists():
        for app_path in applications_dir.glob("*.app"):
            app_name = app_path.stem
            clean_name = clean_app_name(app_name)
            apps.append(
                {
                    "name": clean_name,
                    "display_name": app_name,
                    "path": str(app_path),
                    "type": "application",
                }
            )

    # Scans user applications Directory
    user_apps_dir = Path.home() / "Applications"
    if user_apps_dir.exists():
        for app_path in user_apps_dir.glob("*.app"):
            app_name = app_path.stem
            clean_name = clean_app_name(app_name)
            apps.append(
                {
                    "name": clean_name,
                    "display_name": app_name,
                    "path": str(app_path),
                    "type": "user_application",
                }
            )

    # Add common system applications
    system_apps = [
        {
            "name": "Calculator",
            "display_name": "计算器",
            "path": "Calculator",
            "type": "system",
        },
        {
            "name": "TextEdit",
            "display_name": "文本编辑",
            "path": "TextEdit",
            "type": "system",
        },
        {
            "name": "Preview",
            "display_name": "预览",
            "path": "Preview",
            "type": "system",
        },
        {
            "name": "Safari",
            "display_name": "Safari浏览器",
            "path": "Safari",
            "type": "system",
        },
        {"name": "Finder", "display_name": "访达", "path": "Finder", "type": "system"},
        {
            "name": "Terminal",
            "display_name": "终端",
            "path": "Terminal",
            "type": "system",
        },
        {
            "name": "System Preferences",
            "display_name": "系统偏好设置",
            "path": "System Preferences",
            "type": "system",
        },
    ]
    apps.extend(system_apps)

    logger.info(t('[MacScanner] 扫描完成，找到 {value1} 个应用程序', value1=len(apps)))
    return apps


def scan_running_applications() -> List[Dict[str, str]]:
    """Scans running applications in macOS systems.

    Returns:
        List[Dict[str, str]]: Running application list
    """
    if platform.system() != "Darwin":
        return []

    apps = []

    try:
        # Use ps command to obtain process information
        result = subprocess.run(
            ["ps", "-eo", "pid,ppid,comm,command"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")[1:]  # Skip header line

            for line in lines:
                parts = line.strip().split(None, 3)
                if len(parts) >= 4:
                    pid, ppid, comm, command = parts

                    # Filter out unwanted processes
                    if _should_include_process(comm, command):
                        display_name = _extract_app_name(comm, command)
                        clean_name = clean_app_name(display_name)

                        apps.append(
                            {
                                "pid": int(pid),
                                "ppid": int(ppid),
                                "name": clean_name,
                                "display_name": display_name,
                                "command": command,
                                "type": "application",
                            }
                        )

        logger.info(t('[MacScanner] 找到 {value1} 个正在运行的应用程序', value1=len(apps)))
        return apps

    except Exception as e:
        logger.error(t('[MacScanner] 扫描运行应用失败: {value1}', value1=e), exc_info=True)
        return []


def _should_include_process(comm: str, command: str) -> bool:
    """determines whether the process should be included.

    Args:
        comm: process name
        command: complete command

    Returns:
        bool: Whether to include
    """
    # Exclude system processes and services
    system_processes = {
        # System core process
        "kernel_task",
        "launchd",
        "kextd",
        "UserEventAgent",
        "cfprefsd",
        "loginwindow",
        "WindowServer",
        "SystemUIServer",
        "Dock",
        "Finder",
        "ControlCenter",
        "NotificationCenter",
        "WallpaperAgent",
        "Spotlight",
        "WiFiAgent",
        "CoreLocationAgent",
        "bluetoothd",
        "wirelessproxd",
        # System services
        "com.apple.",
        "suhelperd",
        "softwareupdated",
        "cloudphotod",
        "identityservicesd",
        "imagent",
        "sharingd",
        "remindd",
        "contactsd",
        "accountsd",
        "CallHistorySyncHelper",
        "CallHistoryPluginHelper",
        # Drivers and extensions
        "AppleSpell",
        "coreaudiod",
        "audio",
        "webrtc",
        "chrome_crashpad_handler",
        "crashpad_handler",
        "fsnotifier",
        "mdworker",
        "mds",
        "spotlight",
        # Other system components
        "automountd",
        "autofsd",
        "aslmanager",
        "syslogd",
        "ntpd",
        "mDNSResponder",
        "distnoted",
        "notifyd",
        "powerd",
        "thermalmonitord",
        "watchdogd",
    }

    # Check whether it is a system process
    comm_lower = comm.lower()
    command_lower = command.lower()

    # Exclude empty names or system paths
    if not comm or comm_lower in system_processes:
        return False

    # Exclude processes under the system path
    if any(
        path in command_lower
        for path in [
            "/system/library/",
            "/library/apple/",
            "/usr/libexec/",
            "/system/applications/utilities/",
            "/private/var/",
            "com.apple.",
            ".xpc/",
            ".framework/",
            ".appex/",
            "helper (gpu)",
            "helper (renderer)",
            "helper (plugin)",
            "crashpad_handler",
            "fsnotifier",
        ]
    ):
        return False

    # Exclude obvious system services
    if any(
        keyword in command_lower
        for keyword in [
            "xpcservice",
            "daemon",
            "agent",
            "service",
            "monitor",
            "updater",
            "sync",
            "backup",
            "cache",
            "log",
        ]
    ):
        return False

    # contains only user applications
    user_app_indicators = ["/applications/", "/users/", "~/", ".app/contents/macos/"]

    return any(indicator in command_lower for indicator in user_app_indicators)


def _extract_app_name(comm: str, command: str) -> str:
    """Extract application name from process information.

    Args:
        comm: process name
        command: complete command

    Returns:
        str: Application name
    """
    # Attempts to extract .app name from command path
    if ".app/Contents/MacOS/" in command:
        try:
            app_path = command.split(".app/Contents/MacOS/")[0] + ".app"
            app_name = Path(app_path).name.replace(".app", "")
            return app_name
        except (IndexError, AttributeError):
            pass

    # Attempts to extract from /Applications/ path
    if "/Applications/" in command:
        try:
            parts = command.split("/Applications/")[1].split("/")[0]
            if parts.endswith(".app"):
                return parts.replace(".app", "")
        except (IndexError, AttributeError):
            pass

    # Use process name
    return comm if comm else "Unknown"


from .utils import clean_app_name
