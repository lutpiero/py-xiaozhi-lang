"""Universal tool for application management.

Provides unified application matching, lookup, caching and name cleansing capabilities.
"""
import platform
import re
import time
from typing import Any

from src.i18n import t
from src.logging import get_logger

logger = get_logger()

# Global application cache
_cached_applications: list[dict[str, Any]] | None = None
_cache_timestamp: float = 0
_cache_duration = 300  # Cache for 5 minutes


def clean_app_name(name: str) -> str:
    """Cleans the application name, removing version numbers and special characters.

    Args:
        name: Original name

    Returns:
        str: Cleaned name
    """
    if not name:
        return ""

    # Remove common version number patterns
    name = re.sub(r"\s+v?\d+[\.\d]*", "", name)
    name = re.sub(r"\s*\(\d+\)", "", name)
    name = re.sub(r"\s*\[.*?\]", "", name)

    # Remove extra spaces
    name = " ".join(name.split())

    return name.strip()


class AppMatcher:
    """
    Unified application matcher.
    """

    # Special application name mapping - Sort by length, avoid short names matching first
    SPECIAL_MAPPINGS = {
        "qq音乐": ["qqmusic", "qq音乐", "qq music"],
        "qqmusic": ["qqmusic", "qq音乐", "qq music"],
        "qq music": ["qqmusic", "qq音乐", "qq music"],
        "tencent meeting": ["tencent meeting", "腾讯会议", "voovmeeting"],
        "腾讯会议": ["tencent meeting", "腾讯会议", "voovmeeting"],
        "google chrome": ["chrome", "googlechrome", "google chrome"],
        "microsoft edge": ["msedge", "edge", "microsoft edge"],
        "microsoft office": [
            "microsoft office",
            "office",
            "word",
            "excel",
            "powerpoint",
        ],
        "microsoft word": ["microsoft word", "word"],
        "microsoft excel": ["microsoft excel", "excel"],
        "microsoft powerpoint": ["microsoft powerpoint", "powerpoint"],
        "visual studio code": ["code", "vscode", "visual studio code"],
        "wps office": ["wps", "wps office"],
        "qq": ["qq", "qqnt", "tencentqq"],
        "wechat": ["wechat", "weixin", "微信"],
        "dingtalk": ["dingtalk", "钉钉", "ding"],
        "钉钉": ["dingtalk", "钉钉", "ding"],
        "chrome": ["chrome", "googlechrome", "google chrome"],
        "firefox": ["firefox", "mozilla"],
        "edge": ["msedge", "edge", "microsoft edge"],
        "safari": ["safari"],
        "notepad": ["notepad", "notepad++"],
        "calculator": ["calc", "calculator", "calculatorapp"],
        "calc": ["calc", "calculator", "calculatorapp"],
        "feishu": ["feishu", "飞书", "lark"],
        "vscode": ["code", "vscode", "visual studio code"],
        "pycharm": ["pycharm", "pycharm64"],
        "cursor": ["cursor"],
        "typora": ["typora"],
        "wps": ["wps", "wps office"],
        "office": ["microsoft office", "office", "word", "excel", "powerpoint"],
        "word": ["microsoft word", "word"],
        "excel": ["microsoft excel", "excel"],
        "powerpoint": ["microsoft powerpoint", "powerpoint"],
        "finder": ["finder"],
        "terminal": ["terminal", "iterm"],
        "iterm": ["iterm", "iterm2"],
    }

    # Process grouping Mapping (for grouping on shutdown)
    PROCESS_GROUPS = {
        "chrome": "chrome",
        "googlechrome": "chrome",
        "firefox": "firefox",
        "edge": "edge",
        "msedge": "edge",
        "safari": "safari",
        "qq": "qq",
        "qqnt": "qq",
        "tencentqq": "qq",
        "qqmusic": "qqmusic",
        "QQMUSIC": "QQMUSIC",
        "QQ音乐": "QQ音乐",
        "wechat": "wechat",
        "weixin": "wechat",
        "dingtalk": "dingtalk",
        "钉钉": "dingtalk",
        "feishu": "feishu",
        "飞书": "feishu",
        "lark": "feishu",
        "vscode": "vscode",
        "code": "vscode",
        "cursor": "cursor",
        "pycharm": "pycharm",
        "pycharm64": "pycharm",
        "typora": "typora",
        "calculatorapp": "calculator",
        "calc": "calculator",
        "calculator": "calculator",
        "tencent meeting": "tencent_meeting",
        "腾讯会议": "tencent_meeting",
        "voovmeeting": "tencent_meeting",
        "wps": "wps",
        "word": "word",
        "excel": "excel",
        "powerpoint": "powerpoint",
        "finder": "finder",
        "terminal": "terminal",
        "iterm": "iterm",
        "iterm2": "iterm",
    }

    @classmethod
    def normalize_name(cls, name: str) -> str:
        """
        Standardize the application name.
        """
        if not name:
            return ""

        # Remove .exe suffix
        name = name.lower().replace(".exe", "")

        # Remove version numbers and special characters
        name = re.sub(r"\s+v?\d+[\.\d]*", "", name)
        name = re.sub(r"\s*\(\d+\)", "", name)
        name = re.sub(r"\s*\[.*?\]", "", name)
        name = " ".join(name.split())

        return name.strip()

    @classmethod
    def get_process_group(cls, process_name: str) -> str:
        """
        Get the group to which the process belongs.
        """
        normalized = cls.normalize_name(process_name)

        # Checks direct mapping
        if normalized in cls.PROCESS_GROUPS:
            return cls.PROCESS_GROUPS[normalized]

        # Check the inclusion relationship
        for key, group in cls.PROCESS_GROUPS.items():
            if key in normalized or normalized in key:
                return group

        return normalized

    @classmethod
    def match_application(cls, target_name: str, app_info: dict[str, Any]) -> int:
        """Matches applications, returning a match score.

        Args:
            target_name: target application name
            app_info: application information

        Returns:
            int: Matching score (0-100), 0 means no match
        """
        if not target_name or not app_info:
            return 0

        target_lower = target_name.lower()
        app_name = app_info.get("name", "").lower()
        display_name = app_info.get("display_name", "").lower()
        window_title = app_info.get("window_title", "").lower()
        exe_path = app_info.get("command", "").lower()

        # 1. Exact match (100 points)
        if target_lower == app_name or target_lower == display_name:
            return 100

        # 2. Special mapping match (95-98 points) - preferentially match more specific keywords
        best_special_score = 0

        for key in cls.SPECIAL_MAPPINGS:
            if key in target_lower or target_lower == key:
                # Checks if there is a matching alias
                for alias in cls.SPECIAL_MAPPINGS[key]:
                    if alias.lower() in app_name or alias.lower() in display_name:
                        # Calculate the matching degree: more specific matches have higher scores
                        if target_lower == key:
                            score = 98  # Exact Match special map key
                        elif len(key) > len(target_lower) * 0.8:
                            score = 97  # Matches of similar length
                        else:
                            score = 95  # general special mapping match

                        if score > best_special_score:
                            best_special_score = score

        if best_special_score > 0:
            return best_special_score

        # 3. Standardized name match (90 points)
        normalized_target = cls.normalize_name(target_name)
        normalized_app = cls.normalize_name(app_info.get("name", ""))
        normalized_display = cls.normalize_name(app_info.get("display_name", ""))

        if (
            normalized_target == normalized_app
            or normalized_target == normalized_display
        ):
            return 90

        # 4. Included match (70-80 points)
        if target_lower in app_name:
            return 80
        if target_lower in display_name:
            return 75
        if app_name and app_name in target_lower:
            # Avoid short names mismatching long names
            if len(app_name) < len(target_lower) * 0.5:
                return 50  # Reduce score
            return 70

        # 5. Window title matching (60 points)
        if window_title and target_lower in window_title:
            return 60

        # 6. Path matching (50 points)
        if exe_path and target_lower in exe_path:
            return 50

        # 7. Fuzzy matching (30 points)
        if cls._fuzzy_match(target_lower, app_name) or cls._fuzzy_match(
            target_lower, display_name
        ):
            return 30

        return 0

    @classmethod
    def _fuzzy_match(cls, target: str, candidate: str) -> bool:
        """
        Fuzzy match.
        """
        if not target or not candidate:
            return False

        # Remove all non-alphanumeric characters for comparison
        target_clean = re.sub(r"[^a-zA-Z0-9一-鿿]", "", target)
        candidate_clean = re.sub(r"[^a-zA-Z0-9一-鿿]", "", candidate)

        return target_clean in candidate_clean or candidate_clean in target_clean


async def get_cached_applications(force_refresh: bool = False) -> list[dict[str, Any]]:
    """Get cached application list.

    Args:
        force_refresh: Whether to force the cache to be refreshed

    Returns:
        Application list
    """
    global _cached_applications, _cache_timestamp

    current_time = time.time()

    # Checks if cache is valid
    if (
        not force_refresh
        and _cached_applications is not None
        and (current_time - _cache_timestamp) < _cache_duration
    ):
        logger.debug(
            t('[AppUtils] 使用缓存的应用程序列表，缓存时间: {value1}秒前', value1=int(current_time - _cache_timestamp))
        )
        return _cached_applications

    # Rescan application
    try:
        import json

        from .scanner import scan_installed_applications

        logger.info(t("[AppUtils] 刷新应用程序缓存"))
        result_json = await scan_installed_applications(
            {"force_refresh": force_refresh}
        )
        result = json.loads(result_json)

        if result.get("success", False):
            _cached_applications = result.get("applications", [])
            _cache_timestamp = current_time
            logger.info(
                t('[AppUtils] 应用程序缓存已刷新，找到 {value1} 个应用', value1=len(_cached_applications))
            )
            return _cached_applications
        else:
            logger.warning(
                t('[AppUtils] 应用程序扫描失败: {value1}', value1=result.get('message', t('未知错误')))
            )
            return _cached_applications or []

    except Exception as e:
        logger.error(t('[AppUtils] 刷新应用程序缓存失败: {value1}', value1=e), exc_info=True)
        return _cached_applications or []


async def find_best_matching_app(
    app_name: str, app_type: str = "any"
) -> dict[str, Any] | None:
    """Find the best matching application.

    Args:
        app_name: Application name
        app_type: application type filtering ("installed", "running", "any")

    Returns:
        Best matching application information
    """
    try:
        if app_type == "running":
            # Get running applications
            import asyncio

            from .process_manager import list_running_applications as list_running_sync

            applications = await asyncio.to_thread(list_running_sync)
        else:
            # Get installed applications
            applications = await get_cached_applications()

        if not applications:
            return None

        # Calculate the matching degree for all applications
        matches = []
        for app in applications:
            score = AppMatcher.match_application(app_name, app)
            if score > 0:
                matches.append((score, app))

        if not matches:
            return None

        # Sort by score, returning the best match
        matches.sort(key=lambda x: x[0], reverse=True)
        best_score, best_app = matches[0]

        logger.info(
            t('[AppUtils] 找到最佳匹配: {value1} (分数: {value3})', value1=best_app.get('display_name', best_app.get('name', '')), value3=best_score)
        )
        return best_app

    except Exception as e:
        logger.error(t('[AppUtils] 查找匹配应用失败: {value1}', value1=e), exc_info=True)
        return None


def clear_app_cache():
    """Clears the application cache."""
    global _cached_applications, _cache_timestamp

    _cached_applications = None
    _cache_timestamp = 0
    logger.info(t("[AppUtils] 应用程序缓存已清空"))


def get_system_scanner():
    """Get the corresponding scanner module based on the current system."""
    system = platform.system()

    if system == "Darwin":
        from . import scanner_mac

        return scanner_mac
    elif system == "Windows":
        from . import scanner_windows

        return scanner_windows
    elif system == "Linux":
        from . import scanner_linux

        return scanner_linux
    else:
        logger.warning(t('[AppUtils] 不支持的系统: {value1}', value1=system))
        return None


def get_cache_info() -> dict[str, Any]:
    """
    Get cache information.
    """

    current_time = time.time()
    cache_age = current_time - _cache_timestamp if _cache_timestamp > 0 else -1

    return {
        "cached": _cached_applications is not None,
        "count": len(_cached_applications) if _cached_applications else 0,
        "age_seconds": int(cache_age) if cache_age >= 0 else None,
        "valid": cache_age >= 0 and cache_age < _cache_duration,
        "cache_duration": _cache_duration,
    }
