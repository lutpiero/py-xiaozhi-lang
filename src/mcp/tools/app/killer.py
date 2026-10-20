"""Application termination and running process management.

Pass process_manager (psutil) provides cross-platform process killing and listing capabilities.
"""
import asyncio
import json
from typing import Any

from src.i18n import t
from src.logging import get_logger

from .process_manager import kill_application_by_name
from .process_manager import list_running_applications as _list_apps

logger = get_logger()


async def kill_application(args: dict[str, Any]) -> bool:
    """Close the application.

    Args:
        args: Dictionary of parameters containing application names
            - app_name: application name
            - force: whether to force close (optional, default False)

    Returns:
        Whether the shutdown was successful
    """
    try:
        app_name = args["app_name"]
        force = args.get("force", False)
        logger.info(t('[AppKiller] 尝试关闭应用程序: {value1}, 强制关闭: {value3}', value1=app_name, value3=force))

        success = await asyncio.to_thread(kill_application_by_name, app_name, force)

        if success:
            logger.info(t('[AppKiller] 成功关闭应用程序: {value1}', value1=app_name))
        else:
            logger.warning(t('[AppKiller] 未能关闭应用程序: {value1}', value1=app_name))

        return success

    except Exception as e:
        logger.error(t('[AppKiller] 关闭应用程序时出错: {value1}', value1=e), exc_info=True)
        return False


async def list_running_applications(args: dict[str, Any]) -> str:
    """List all running applications.

    Args:
        args: Dictionary containing listed parameters
            - filter_name: filter application name (optional)

    Returns:
        List of running applications in JSON format
    """
    try:
        filter_name = args.get("filter_name", "")
        logger.info(t('[AppKiller] 开始列出正在运行的应用程序，过滤条件: {value1}', value1=filter_name))

        apps = await asyncio.to_thread(_list_apps, filter_name)

        result = {
            "success": True,
            "total_count": len(apps),
            "applications": apps[:50],
            "message": t('找到 {value1} 个正在运行的应用程序', value1=len(apps)),
        }

        logger.info(t('[AppKiller] 列出完成，找到 {value1} 个正在运行的应用程序', value1=len(apps)))
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        error_msg = t("列出运行中应用程序失败: {error}", error=e)
        logger.error(t("[AppKiller] {message}", message=error_msg), exc_info=True)
        return json.dumps(
            {
                "success": False,
                "total_count": 0,
                "applications": [],
                "message": error_msg,
            },
            ensure_ascii=False,
        )
