"""macOS system application launcher.

provides the application launch function under the macOS platform.
All subprocess calls use list form, do not use shell=True.
"""
import os
import subprocess

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


def launch_application(app_name: str) -> bool:
    """launches applications on macOS.

    Args:
        app_name: Application name

    Returns:
        bool: Whether the startup was successful
    """
    try:
        logger.info(t('[MacLauncher] 启动应用程序: {value1}', value1=app_name))

        # Method 1: Use the open -a command (safe list form)
        try:
            subprocess.Popen(
                ["open", "-a", app_name],
                start_new_session=True,
            )
            logger.info(t('[MacLauncher] 使用open -a成功启动: {value1}', value1=app_name))
            return True
        except (OSError, subprocess.SubprocessError):
            logger.debug(t('[MacLauncher] open -a启动失败: {value1}', value1=app_name))

        # Method 2: Use the application name directly
        try:
            subprocess.Popen(
                [app_name],
                start_new_session=True,
            )
            logger.info(t('[MacLauncher] 直接启动成功: {value1}', value1=app_name))
            return True
        except (OSError, subprocess.SubprocessError):
            logger.debug(t('[MacLauncher] 直接启动失败: {value1}', value1=app_name))

        # Method 3: Try the Applications directory
        app_path = f"/Applications/{app_name}.app"
        if os.path.exists(app_path):
            subprocess.Popen(
                ["open", app_path],
                start_new_session=True,
            )
            logger.info(t('[MacLauncher] 通过Applications目录启动成功: {value1}', value1=app_name))
            return True

        # Method 4: Use open -a again (as a final try, without using osascript)
        # used to use osascript f-string splicing to have an AppleScript injection vulnerability, which has been removed.
        try:
            subprocess.Popen(
                ["open", "-a", app_name, "--background"],
                start_new_session=True,
            )
            logger.info(t('[MacLauncher] 使用open -a(后台模式)启动成功: {value1}', value1=app_name))
            return True
        except (OSError, subprocess.SubprocessError):
            logger.debug(t('[MacLauncher] open -a(后台模式)启动失败: {value1}', value1=app_name))

        logger.warning(t('[MacLauncher] 所有macOS启动方法都失败了: {value1}', value1=app_name))
        return False

    except Exception as e:
        logger.error(t('[MacLauncher] macOS启动失败: {value1}', value1=e), exc_info=True)
        return False
