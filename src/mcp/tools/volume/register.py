"""Volume MCP tool: VolumeController is injected by register_volume_tools, no module-level singleton."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from src.i18n import t
from src.logging import get_logger
from src.mcp.tooling import McpTool, Property, PropertyList, PropertyType

from .volume_controller import VolumeController

logger = get_logger()


def create_volume_controller() -> VolumeController | None:
    """creates a volume controller; returns None when there are insufficient dependencies or initialization fails."""
    if not VolumeController.check_dependencies():
        return None
    try:
        return VolumeController()
    except Exception as e:
        logger.error(t('音量控制器初始化失败: {value1}', value1=e), exc_info=True)
        return None


def register_volume_tools(
    add_tool: Callable[[McpTool], None],
    controller: VolumeController | None = None,
) -> None:
    """Registers the volume tool with McpServer (the closure holds the controller and does not write a global singleton).

    controller is None, try create_volume_controller(); if it still fails, register
    , a tool that will return an "unavailable" result to avoid missing the tool list.
    """
    if controller is None:
        controller = create_volume_controller()

    async def set_volume(args: dict[str, Any]) -> bool:
        try:
            volume = args["volume"]
            logger.info(t('[VolumeTools] 设置音量到 {value1}', value1=volume))
            if not (0 <= volume <= 100):
                logger.warning(t('[VolumeTools] 音量值超出范围: {value1}', value1=volume))
                return False
            if controller is None:
                logger.warning(t("[VolumeTools] 音量控制依赖不完整，无法设置音量"))
                return False
            await asyncio.to_thread(controller.set_volume, volume)
            logger.info(t('[VolumeTools] 音量设置成功: {value1}', value1=volume))
            return True
        except KeyError:
            logger.error(t("[VolumeTools] 缺少volume参数"))
            return False
        except Exception as e:
            logger.error(t('[VolumeTools] 设置音量失败: {value1}', value1=e), exc_info=True)
            return False

    async def get_volume(args: dict[str, Any]) -> int:
        try:
            logger.info(t("[VolumeTools] 获取当前音量"))
            if controller is None:
                logger.warning(t("[VolumeTools] 音量控制依赖不完整，返回默认音量"))
                return VolumeController.DEFAULT_VOLUME
            current = await asyncio.to_thread(controller.get_volume)
            logger.info(t('[VolumeTools] 当前音量: {value1}', value1=current))
            return current
        except Exception as e:
            logger.error(t('[VolumeTools] 获取音量失败: {value1}', value1=e), exc_info=True)
            return VolumeController.DEFAULT_VOLUME

    async def get_volume_status(args: dict[str, Any]) -> str:
        try:
            if controller is not None:
                current = await asyncio.to_thread(controller.get_volume)
                status = {
                    "volume": current,
                    "muted": current == 0,
                    "available": True,
                }
            else:
                status = {
                    "volume": 50,
                    "muted": False,
                    "available": False,
                    "reason": "Dependencies not available",
                }
        except Exception as e:
            logger.warning(t('[VolumeTools] 获取音量状态失败: {value1}', value1=e), exc_info=True)
            status = {
                "volume": 50,
                "muted": False,
                "available": False,
                "error": str(e),
            }
        return json.dumps(status, ensure_ascii=False)

    tools: list[McpTool] = [
        McpTool(
            "self.audio_speaker.set_volume",
            (
                t("Set the system speaker volume to an absolute value (0-100).\n"
                "Use when user mentions: volume, sound, louder, quieter, mute, unmute, adjust volume.\n"
                "Examples: 'set volume to 50', 'turn volume up', 'make it louder', 'mute', "
                "'音量设为50', '调大声音', '声音小一点', '静音'.\n"
                "Parameter:\n"
                "- volume: Integer (0-100) representing the target volume level. Set to 0 for mute.")
            ),
            PropertyList(
                [Property("volume", PropertyType.INTEGER, min_value=0, max_value=100)]
            ),
            set_volume,
        ),
        McpTool(
            "self.audio_speaker.get_volume",
            (
                t("Get the current system speaker volume level.\n"
                "Use when user asks about: current volume, volume level, how loud, what's the volume.\n"
                "Examples: 'what is the current volume?', 'how loud is it?', 'check volume level', "
                "'现在音量多少?', '查看音量', '音量是多少'.\n"
                "Returns: Integer (0-100) representing the current volume level.")
            ),
            PropertyList(),
            get_volume,
        ),
        McpTool(
            "self.audio_speaker.get_volume_status",
            (
                "Get detailed speaker volume status including whether audio output is muted and "
                "whether the volume controller dependencies are available. Returns a JSON payload "
                "with fields: volume (0-100), muted (bool), available (bool), reason/error(optional)."
            ),
            PropertyList(),
            get_volume_status,
        ),
    ]

    for tool in tools:
        add_tool(tool)
    logger.info(
        t("已注册 %d 个音量 MCP 工具（注入 VolumeController, available=%s）"),
        len(tools),
        controller is not None,
    )
