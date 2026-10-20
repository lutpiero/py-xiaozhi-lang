"""Unified application scanner entrance.

Automatically select the corresponding scanner according to the current system to implement
"""
import asyncio
import json
from typing import Any, Dict

from src.i18n import t
from src.logging import get_logger

from .utils import get_system_scanner

logger = get_logger()


async def scan_installed_applications(args: Dict[str, Any]) -> str:
    """Scan Scan all installed applications in the system.

    Args:
        args: Dictionary containing scan parameters
            - force_refresh: Whether to force rescan (optional, default False)

    Returns:
        str: List of applications in JSON format
    """
    try:
        force_refresh = args.get("force_refresh", False)
        logger.info(t('[AppScanner] 开始扫描已安装应用程序，强制刷新: {value1}', value1=force_refresh))

        # Get the scanner corresponding to the system
        scanner = get_system_scanner()
        if not scanner:
            error_msg = t("不支持的操作系统")
            logger.error(t("[AppScanner] {message}", message=error_msg))
            return json.dumps(
                {
                    "success": False,
                    "total_count": 0,
                    "applications": [],
                    "message": error_msg,
                },
                ensure_ascii=False,
            )

        # Uses a thread pool to perform scans to avoid blocking the event loop
        apps = await asyncio.to_thread(scanner.scan_installed_applications)

        result = {
            "success": True,
            "total_count": len(apps),
            "applications": apps,
            "message": t('成功扫描到 {value1} 个已安装应用程序', value1=len(apps)),
        }

        logger.info(t('[AppScanner] 扫描完成，找到 {value1} 个应用程序', value1=len(apps)))
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        error_msg = t("扫描应用程序失败: {error}", error=str(e))
        logger.error(t("[AppScanner] {message}", message=error_msg), exc_info=True)
        return json.dumps(
            {
                "success": False,
                "total_count": 0,
                "applications": [],
                "message": error_msg,
            },
            ensure_ascii=False,
        )


async def list_running_applications(args: Dict[str, Any]) -> str:
    """Lists running applications on the system.

    Args:
        args: Dictionary containing filter parameters
            - filter_name: Apply name filter conditions (optional)

    Returns:
        str: List of running applications in JSON format
    """
    try:
        filter_name = args.get("filter_name", "")
        logger.info(t('[AppScanner] 开始列出正在运行的应用程序，过滤条件: {value1}', value1=filter_name))

        # Get the scanner corresponding to the system
        scanner = get_system_scanner()
        if not scanner:
            error_msg = t("不支持的操作系统")
            logger.error(t("[AppScanner] {message}", message=error_msg))
            return json.dumps(
                {
                    "success": False,
                    "total_count": 0,
                    "applications": [],
                    "message": error_msg,
                },
                ensure_ascii=False,
            )

        # Uses a thread pool to perform scans to avoid blocking the event loop
        apps = await asyncio.to_thread(scanner.scan_running_applications)

        # Apply filters
        if filter_name:
            filter_lower = filter_name.lower()
            filtered_apps = []
            for app in apps:
                if (
                    filter_lower in app.get("name", "").lower()
                    or filter_lower in app.get("display_name", "").lower()
                    or filter_lower in app.get("command", "").lower()
                ):
                    filtered_apps.append(app)
            apps = filtered_apps

        result = {
            "success": True,
            "total_count": len(apps),
            "applications": apps,
            "message": t('找到 {value1} 个正在运行的应用程序', value1=len(apps)),
        }

        logger.info(t('[AppScanner] 列出完成，找到 {value1} 个正在运行的应用程序', value1=len(apps)))
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        error_msg = t("列出运行应用程序失败: {error}", error=str(e))
        logger.error(t("[AppScanner] {message}", message=error_msg), exc_info=True)
        return json.dumps(
            {
                "success": False,
                "total_count": 0,
                "applications": [],
                "message": error_msg,
            },
            ensure_ascii=False,
        )
