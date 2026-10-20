"""Windows application scanner.

is specially used for application scanning and management of Windows systems
"""
import json
import os
import platform
import subprocess
from typing import Dict, List, Optional

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


def scan_installed_applications() -> List[Dict[str, str]]:
    """Scans installed applications in Windows systems.

    Returns:
        List[Dict[str, str]]: Application list
    """
    if platform.system() != "Windows":
        return []

    apps = []

    # 1. Scan the start menu for major applications (most direct method)
    try:
        logger.info(t("[WindowsScanner] 开始扫描开始菜单主要应用"))
        start_menu_apps = _scan_main_start_menu_apps()
        apps.extend(start_menu_apps)
        logger.info(
            t('[WindowsScanner] 从开始菜单扫描到 {value1} 个主要应用', value1=len(start_menu_apps))
        )
    except Exception as e:
        logger.warning(t('[WindowsScanner] 开始菜单扫描失败: {value1}', value1=e), exc_info=True)

    # 2. Scan the registry for major third-party applications (filtering system components)
    try:
        logger.info(t("[WindowsScanner] 开始扫描已安装的主要应用程序"))
        registry_apps = _scan_main_registry_apps()
        # Deduplication: Avoid duplication of applications in the start menu
        existing_names = {app["display_name"].lower() for app in apps}
        for app in registry_apps:
            if app["display_name"].lower() not in existing_names:
                apps.append(app)
        logger.info(
            t('[WindowsScanner] 从注册表扫描到 {value1} 个新的主要应用', value1=len([a for a in registry_apps if a['display_name'].lower() not in existing_names]))
        )
    except Exception as e:
        logger.warning(t('[WindowsScanner] 注册表扫描失败: {value1}', value1=e), exc_info=True)

    # 3. Add common system applications (only keep those commonly used by users)
    system_apps = [
        {
            "name": "Calculator",
            "display_name": "计算器",
            "path": "calc",
            "type": "system",
        },
        {
            "name": "Notepad",
            "display_name": "记事本",
            "path": "notepad",
            "type": "system",
        },
        {"name": "Paint", "display_name": "画图", "path": "mspaint", "type": "system"},
        {
            "name": "File Explorer",
            "display_name": "文件资源管理器",
            "path": "explorer",
            "type": "system",
        },
        {
            "name": "Task Manager",
            "display_name": "任务管理器",
            "path": "taskmgr",
            "type": "system",
        },
        {
            "name": "Control Panel",
            "display_name": "控制面板",
            "path": "control",
            "type": "system",
        },
        {
            "name": "Settings",
            "display_name": "设置",
            "path": "ms-settings:",
            "type": "system",
        },
    ]
    apps.extend(system_apps)

    logger.info(
        t('[WindowsScanner] Windows应用扫描完成，总共找到 {value1} 个主要应用程序', value1=len(apps))
    )
    return apps


def scan_running_applications() -> List[Dict[str, str]]:
    """Scans running applications in Windows systems.

    Returns:
        List[Dict[str, str]]: Running application list
    """
    if platform.system() != "Windows":
        return []

    apps = []

    try:
        # Use the tasklist command to obtain process information
        result = subprocess.run(
            ["tasklist", "/fo", "csv", "/v"], capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")[1:]  # Skip header line

            for line in lines:
                try:
                    # Parse CSV format
                    parts = [part.strip('"') for part in line.split('","')]
                    if len(parts) >= 8:
                        image_name = parts[0].strip('"')
                        pid = parts[1]
                        window_title = parts[8] if len(parts) > 8 else ""

                        # Filter out unwanted processes
                        if _should_include_process(image_name, window_title):
                            display_name = _extract_app_name(image_name, window_title)
                            clean_name = clean_app_name(display_name)

                            apps.append(
                                {
                                    "pid": int(pid),
                                    "name": clean_name,
                                    "display_name": display_name,
                                    "command": image_name,
                                    "window_title": window_title,
                                    "type": "application",
                                }
                            )
                except (ValueError, IndexError):
                    continue

        logger.info(t('[WindowsScanner] 找到 {value1} 个正在运行的应用程序', value1=len(apps)))
        return apps

    except Exception as e:
        logger.error(t('[WindowsScanner] 扫描运行应用失败: {value1}', value1=e), exc_info=True)
        return []


def _scan_main_start_menu_apps() -> List[Dict[str, str]]:
    """
    Scans main applications in the Start menu (filtering system components and auxiliary tools).
    """
    apps = []

    # Start menu directory
    start_menu_paths = [
        os.path.join(
            os.environ.get("PROGRAMDATA", ""),
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
        ),
        os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
        ),
    ]

    for start_path in start_menu_paths:
        if os.path.exists(start_path):
            try:
                for root, dirs, files in os.walk(start_path):
                    for file in files:
                        if file.lower().endswith(".lnk"):
                            try:
                                shortcut_path = os.path.join(root, file)
                                display_name = file[:-4]  # Remove .lnk extension

                                # Filter out unwanted applications
                                if _should_include_app(display_name):
                                    clean_name = clean_app_name(display_name)
                                    target_path = _resolve_shortcut_target(
                                        shortcut_path
                                    )

                                    apps.append(
                                        {
                                            "name": clean_name,
                                            "display_name": display_name,
                                            "path": target_path or shortcut_path,
                                            "type": "shortcut",
                                        }
                                    )

                            except Exception as e:
                                logger.debug(
                                    t('[WindowsScanner] 处理快捷方式失败 {value1}: {value3}', value1=file, value3=e)
                                )

            except Exception as e:
                logger.debug(t('[WindowsScanner] 扫描开始菜单失败 {value1}: {value3}', value1=start_path, value3=e))

    return apps


def _scan_main_registry_apps() -> List[Dict[str, str]]:
    """
    Scans the registry for main applications (filtering system components).
    """
    apps = []

    try:
        powershell_cmd = [
            "powershell",
            "-Command",
            "Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | "
            "Select-Object DisplayName, InstallLocation, Publisher | "
            "Where-Object {$_.DisplayName -ne $null} | "
            "ConvertTo-Json",
        ]

        result = subprocess.run(
            powershell_cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout:
            try:
                installed_apps = json.loads(result.stdout)
                if isinstance(installed_apps, dict):
                    installed_apps = [installed_apps]

                for app in installed_apps:
                    display_name = app.get("DisplayName", "")
                    publisher = app.get("Publisher", "")

                    if display_name and _should_include_app(display_name, publisher):
                        clean_name = clean_app_name(display_name)
                        apps.append(
                            {
                                "name": clean_name,
                                "display_name": display_name,
                                "path": app.get("InstallLocation", ""),
                                "type": "installed",
                            }
                        )

            except json.JSONDecodeError:
                logger.warning(t("[WindowsScanner] 无法解析PowerShell输出"))

    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        logger.warning(t('[WindowsScanner] PowerShell扫描失败: {value1}', value1=e), exc_info=True)

    return apps


def _should_include_app(display_name: str, publisher: str = "") -> bool:
    """determine whether the application should be included.

    Args:
        display_name: application display name
        publisher: Published by (optional)

    Returns:
        bool: Should it include
    """
    name_lower = display_name.lower()

    # Explicitly excluded system components and runtime libraries
    exclude_keywords = [
        # Microsoft system components
        "microsoft visual c++",
        "microsoft .net",
        "microsoft office",
        "microsoft edge webview",
        "microsoft visual studio",
        "microsoft redistributable",
        "microsoft windows sdk",
        # System tools and drivers
        "uninstall",
        "卸载",
        "readme",
        "help",
        "帮助",
        "documentation",
        "文档",
        "driver",
        "驱动",
        "update",
        "更新",
        "hotfix",
        "patch",
        "补丁",
        # Development Tools Component
        "development",
        "sdk",
        "runtime",
        "redistributable",
        "framework",
        "python documentation",
        "python test suite",
        "python executables",
        "java update",
        "java development kit",
        # System services
        "service pack",
        "security update",
        "language pack",
        # Useless shortcuts
        "website",
        "web site",
        "网站",
        "online",
        "在线",
        "report",
        "报告",
        "feedback",
        "反馈",
    ]

    # Check whether the excluded keywords are included
    for keyword in exclude_keywords:
        if keyword in name_lower:
            return False

    # Explicitly included well-known applications
    include_keywords = [
        # Browser
        "chrome",
        "firefox",
        "edge",
        "safari",
        "opera",
        "brave",
        # Office software
        "office",
        "word",
        "excel",
        "powerpoint",
        "outlook",
        "onenote",
        "wps",
        "typora",
        "notion",
        "obsidian",
        # Development tools
        "visual studio code",
        "vscode",
        "pycharm",
        "idea",
        "eclipse",
        "git",
        "docker",
        "nodejs",
        "android studio",
        # Communication software
        "qq",
        "微信",
        "wechat",
        "skype",
        "zoom",
        "teams",
        "飞书",
        "feishu",
        "discord",
        "slack",
        "telegram",
        # Media software
        "vlc",
        "potplayer",
        "网易云音乐",
        "spotify",
        "itunes",
        "photoshop",
        "premiere",
        "after effects",
        "illustrator",
        # Game platform
        "steam",
        "epic",
        "origin",
        "uplay",
        "battlenet",
        # Utility tools
        "7-zip",
        "winrar",
        "bandizip",
        "everything",
        "listary",
        "notepad++",
        "sublime",
        "atom",
    ]

    # Check whether the explicitly included keywords are included
    for keyword in include_keywords:
        if keyword in name_lower:
            return True

    # If there is publisher information, exclude Micro System components released by soft
    if publisher:
        publisher_lower = publisher.lower()
        if "microsoft corporation" in publisher_lower and any(
            x in name_lower
            for x in [
                "visual c++",
                ".net",
                "redistributable",
                "runtime",
                "framework",
                "update",
            ]
        ):
            return False

    # Other applications are included by default (assumed to be installed by the user)
    # but exclude obvious systems System component
    system_indicators = ["(x64)", "(x86)", "redistributable", "runtime", "framework"]
    if any(indicator in name_lower for indicator in system_indicators):
        return False

    return True


def _should_include_process(image_name: str, window_title: str) -> bool:
    """determines whether the process should be included.

    Args:
        image_name: Process image name
        window_title: Window title

    Returns:
        bool: Whether to include
    """
    # Exclude system processes
    system_processes = {
        "dwm.exe",
        "winlogon.exe",
        "csrss.exe",
        "smss.exe",
        "lsass.exe",
        "services.exe",
        "svchost.exe",
        "explorer.exe",
        "taskhostw.exe",
        "conhost.exe",
        "dllhost.exe",
        "rundll32.exe",
        "msiexec.exe",
        "wininit.exe",
        "lsm.exe",
        "spoolsv.exe",
        "audiodg.exe",
    }

    image_lower = image_name.lower()

    # Exclude system processes
    if image_lower in system_processes:
        return False

    # Exclude processes without window titles (usually background services)
    if not window_title or window_title == "N/A":
        return False

    # Only contain meaningful window titles
    if len(window_title.strip()) < 3:
        return False

    return True


def _extract_app_name(image_name: str, window_title: str) -> str:
    """Extract application name from process information.

    Args:
        image_name: Process image name
        window_title: Window title

    Returns:
        str: Application name
    """
    # Prioritize the use of window title
    if window_title and window_title != "N/A" and len(window_title.strip()) > 0:
        return window_title.strip()

    # Use the process name (remove the .exe suffix)
    if image_name.lower().endswith(".exe"):
        return image_name[:-4]

    return image_name


def _resolve_shortcut_target(shortcut_path: str) -> Optional[str]:
    """Parse Windo Target path of ws shortcut.

    Args:
        shortcut_path: Shortcut file path

    Returns:
        Target path, if the parsing fails, return None
    """
    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        target_path = shortcut.Targetpath

        if target_path and os.path.exists(target_path):
            return target_path

    except ImportError:
        logger.debug(t("[WindowsScanner] win32com模块不可用，无法解析快捷方式"))
    except Exception as e:
        logger.debug(t('[WindowsScanner] 解析快捷方式失败: {value1}', value1=e))

    return None


from .utils import clean_app_name
