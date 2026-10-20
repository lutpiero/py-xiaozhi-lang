"""Linux application scanner.

Specially used for application scanning and management of Linux systems
"""
import platform
import subprocess
from pathlib import Path
from typing import Dict, List

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


def scan_installed_applications() -> List[Dict[str, str]]:
    """Scans installed applications in Linux systems.

    Returns:
        List[Dict[str, str]]: Application list
    """
    if platform.system() != "Linux":
        return []

    apps = []

    # Scans .desktop files
    desktop_dirs = [
        "/usr/share/applications",
        "/usr/local/share/applications",
        Path.home() / ".local/share/applications",
    ]

    for desktop_dir in desktop_dirs:
        desktop_path = Path(desktop_dir)
        if desktop_path.exists():
            for desktop_file in desktop_path.glob("*.desktop"):
                try:
                    app_info = _parse_desktop_file(desktop_file)
                    if app_info and _should_include_app(app_info["display_name"]):
                        apps.append(app_info)
                except Exception as e:
                    logger.debug(
                        t('[LinuxScanner] 解析desktop文件失败 {value1}: {value3}', value1=desktop_file, value3=e)
                    )

    # Add common Linux system applications
    system_apps = [
        {
            "name": "gedit",
            "display_name": "文本编辑器",
            "path": "gedit",
            "type": "system",
        },
        {
            "name": "firefox",
            "display_name": "Firefox浏览器",
            "path": "firefox",
            "type": "system",
        },
        {
            "name": "gnome-calculator",
            "display_name": "计算器",
            "path": "gnome-calculator",
            "type": "system",
        },
        {
            "name": "nautilus",
            "display_name": "文件管理器",
            "path": "nautilus",
            "type": "system",
        },
        {
            "name": "gnome-terminal",
            "display_name": "终端",
            "path": "gnome-terminal",
            "type": "system",
        },
        {
            "name": "gnome-control-center",
            "display_name": "设置",
            "path": "gnome-control-center",
            "type": "system",
        },
    ]
    apps.extend(system_apps)

    logger.info(t('[LinuxScanner] 扫描完成，找到 {value1} 个应用程序', value1=len(apps)))
    return apps


def scan_running_applications() -> List[Dict[str, str]]:
    """Scans running applications in Linux systems.

    Returns:
        List[Dict[str, str]]: Running application list
    """
    if platform.system() != "Linux":
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

        logger.info(t('[LinuxScanner] 找到 {value1} 个正在运行的应用程序', value1=len(apps)))
        return apps

    except Exception as e:
        logger.error(t('[LinuxScanner] 扫描运行应用失败: {value1}', value1=e), exc_info=True)
        return []


def _parse_desktop_file(desktop_file: Path) -> Dict[str, str]:
    """Parse .desktop file .

    Args:
        desktop_file: .desktop file path

    Returns:
        Dict[str, str]: Application information
    """
    try:
        with open(desktop_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse .desktop file
        name = ""
        display_name = ""
        exec_cmd = ""

        for line in content.split("\n"):
            if line.startswith("Name="):
                display_name = line.split("=", 1)[1]
            elif line.startswith("Name[zh_CN]="):
                display_name = line.split("=", 1)[1]  # Prefer using Chinese name
            elif line.startswith("Exec="):
                exec_cmd = line.split("=", 1)[1].split()[0]  # takes the first command

        if display_name and exec_cmd:
            name = clean_app_name(display_name)
            return {
                "name": name,
                "display_name": display_name,
                "path": exec_cmd,
                "type": "desktop",
            }

        return None

    except Exception:
        return None


def _should_include_app(display_name: str) -> bool:
    """determine whether the application should be included.

    Args:
        display_name: application display name

    Returns:
        bool: Whether to include
    """
    if not display_name:
        return False

    # Exclude application mode
    exclude_patterns = [
        # System components
        "gnome-",
        "kde-",
        "xfce-",
        "unity-",
        # Development Tools Component
        "gdb",
        "valgrind",
        "strace",
        "ltrace",
        # System tools
        "dconf",
        "gsettings",
        "xdg-",
        "desktop-file-",
        # Other system components
        "help",
        "about",
        "preferences",
        "settings",
    ]

    display_lower = display_name.lower()

    # Check exclusion mode
    for pattern in exclude_patterns:
        if pattern in display_lower:
            return False

    return True


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
        # The kernel and core processes
        "kthreadd",
        "ksoftirqd",
        "migration",
        "rcu_",
        "watchdog",
        "systemd",
        "init",
        "kernel",
        "kworker",
        "kcompactd",
        # System services
        "dbus",
        "networkd",
        "resolved",
        "logind",
        "udevd",
        "cron",
        "rsyslog",
        "ssh",
        "avahi",
        "cups",
        # Desktop environment services
        "gnome-",
        "kde-",
        "xfce-",
        "unity-",
        "compiz",
        "pulseaudio",
        "pipewire",
        "wireplumber",
        # X11/Wayland
        "Xorg",
        "wayland",
        "weston",
        "mutter",
        "kwin",
    }

    # Check whether it is a system process
    comm_lower = comm.lower()
    command_lower = command.lower()

    # Exclude empty name or system processes
    if not comm or any(proc in comm_lower for proc in system_processes):
        return False

    # Exclude processes under the system path
    if any(
        path in command_lower
        for path in [
            "/usr/libexec/",
            "/usr/lib/",
            "/lib/",
            "/sbin/",
            "/usr/sbin/",
            "/bin/systemd",
            "/usr/bin/dbus",
        ]
    ):
        return False

    # Exclude obvious system services
    if any(
        keyword in command_lower
        for keyword in ["daemon", "service", "helper", "agent", "monitor"]
    ):
        return False

    # contains only user applications
    user_app_indicators = [
        "/usr/bin/",
        "/usr/local/bin/",
        "/opt/",
        "/home/",
        "/snap/",
        "/flatpak/",
    ]

    return any(indicator in command_lower for indicator in user_app_indicators)


def _extract_app_name(comm: str, command: str) -> str:
    """Extract application name from process information.

    Args:
        comm: process name
        command: complete command

    Returns:
        str: Application name
    """
    # attempts to extract the application name from the command path
    if "/" in command:
        try:
            # Get executable file name
            exec_path = command.split()[0]
            app_name = Path(exec_path).name

            # Remove common suffix
            if app_name.endswith(".py"):
                app_name = app_name[:-3]
            elif app_name.endswith(".sh"):
                app_name = app_name[:-3]

            return app_name
        except (IndexError, AttributeError):
            pass

    # Use process name
    return comm if comm else "Unknown"


from .utils import clean_app_name
