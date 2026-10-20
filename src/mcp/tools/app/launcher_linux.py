"""Linux system application launcher.

provides application startup function under Linux platform.
All subprocess calls use list form, do not use shell=True.
"""
import os
import subprocess

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


def launch_application(app_name: str) -> bool:
    """Start the application on Linux.

    Args:
        app_name: Application name

    Returns:
        bool: Whether the startup was successful
    """
    try:
        logger.info(t('[LinuxLauncher] 启动应用程序: {value1}', value1=app_name))

        # Method 1: Use the application name directly
        try:
            subprocess.Popen(
                [app_name],
                start_new_session=True,
            )
            logger.info(t('[LinuxLauncher] 直接启动成功: {value1}', value1=app_name))
            return True
        except (OSError, subprocess.SubprocessError):
            logger.debug(t('[LinuxLauncher] 直接启动失败: {value1}', value1=app_name))

        # Method 2: Use which to find the application path
        try:
            result = subprocess.run(
                ["which", app_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                app_path = result.stdout.strip()
                subprocess.Popen(
                    [app_path],
                    start_new_session=True,
                )
                logger.info(t('[LinuxLauncher] 通过which启动成功: {value1}', value1=app_name))
                return True
        except (OSError, subprocess.SubprocessError):
            logger.debug(t('[LinuxLauncher] which启动失败: {value1}', value1=app_name))

        # Method 3: Use xdg-open (for desktop environments)
        try:
            subprocess.Popen(
                ["xdg-open", app_name],
                start_new_session=True,
            )
            logger.info(t('[LinuxLauncher] 使用xdg-open启动成功: {value1}', value1=app_name))
            return True
        except (OSError, subprocess.SubprocessError):
            logger.debug(t('[LinuxLauncher] xdg-open启动失败: {value1}', value1=app_name))

        # Method 4: Try common application paths
        common_paths = [
            f"/usr/bin/{app_name}",
            f"/usr/local/bin/{app_name}",
            f"/opt/{app_name}/{app_name}",
            f"/snap/bin/{app_name}",
        ]

        for path in common_paths:
            if os.path.exists(path):
                subprocess.Popen(
                    [path],
                    start_new_session=True,
                )
                logger.info(
                    t('[LinuxLauncher] 通过常见路径启动成功: {value1} ({value3})', value1=app_name, value3=path)
                )
                return True

        # Method 5: Try .desktop file to launch
        desktop_dirs = [
            "/usr/share/applications",
            "/usr/local/share/applications",
            os.path.expanduser("~/.local/share/applications"),
        ]

        for desktop_dir in desktop_dirs:
            desktop_file = os.path.join(desktop_dir, f"{app_name}.desktop")
            if os.path.exists(desktop_file):
                subprocess.Popen(
                    ["gtk-launch", f"{app_name}.desktop"],
                    start_new_session=True,
                )
                logger.info(t('[LinuxLauncher] 通过desktop文件启动成功: {value1}', value1=app_name))
                return True

        logger.warning(t('[LinuxLauncher] 所有Linux启动方法都失败了: {value1}', value1=app_name))
        return False

    except Exception as e:
        logger.error(t('[LinuxLauncher] Linux启动失败: {value1}', value1=e), exc_info=True)
        return False
