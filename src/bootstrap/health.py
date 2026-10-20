"""Start the health latch and audio degradation strategy.

has nothing to do with the session business: it only determines whether to exit/downgrade based on the plug-in failure set and environment variables.
"""

from __future__ import annotations

import os
from typing import Optional, Protocol

from src.i18n import t

# Exit directly when startup fails to avoid zombie wait_shutdown
CRITICAL_PLUGINS = ("ui",)
# audio default key; when XIAOZHI_DEGRADED_AUDIO=1, failure will only downgrade without exit.
AUDIO_CRITICAL = True

DEGRADED_AUDIO_NOTICE = t(
    "降级：音频不可用（无麦/扬声器）。设置仍可用，修复设备后请重启。"
)


class _PluginHealth(Protocol):
    def is_failed(self, name: str) -> bool: ...


def audio_is_fatal() -> bool:
    """Audio failure should cause the process to exit.

    - XIAOZHI_DISABLE_AUDIO=1: Intentionally disabled, not considered a failure
    - XIAOZHI_DEGRADED_AUDIO=1: Downgrade continues on failure (UI/settings available)
    -Default: audio failure means exit. 1
    """
    if os.getenv("XIAOZHI_DISABLE_AUDIO") == "1":
        return False
    if os.getenv("XIAOZHI_DEGRADED_AUDIO") == "1":
        return False
    return AUDIO_CRITICAL


def check_critical_plugins(plugins: _PluginHealth) -> Optional[str]:
    """Check whether key plug-ins are available.

    Returns:
        Error description; return None when all are healthy
    """
    failed: list[str] = []
    for name in CRITICAL_PLUGINS:
        if plugins.is_failed(name):
            failed.append(name)

    if audio_is_fatal() and plugins.is_failed("audio"):
        failed.append("audio")

    if not failed:
        return None

    hints = []
    if "audio" in failed:
        hints.append(
            t("无音频调试可设 XIAOZHI_DISABLE_AUDIO=1；"
            "或设 XIAOZHI_DEGRADED_AUDIO=1 以无麦模式继续（UI/设置可用）。")
        )
    return (
        t(
            "关键插件启动失败: {failed}。应用将退出以避免空转（zombie）。",
            failed=", ".join(failed),
        )
        + (" " + " ".join(hints) if hints else "")
    )
