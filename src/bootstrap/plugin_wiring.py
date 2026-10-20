"""Plug-ins and shared services are assembled.

Centralize: create McpServer/MusicPlayer, register plug-in list, resource pool cleanup, audio direct connection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.i18n import t
from src.logging import get_logger

if TYPE_CHECKING:
    from src.bootstrap.container import ServiceContainer
    from src.bootstrap.protocols import PluginCommands, PluginContext

logger = get_logger()


def bind_shared_services(container: "ServiceContainer") -> None:
    """Create cross-plugin shared service (McpServer/ MusicPlayer), only held by the container.

    no longer writes module-level singletons; plug-ins and MCP tools get the same instance through constructor injection/closure.
    """
    from src.mcp.mcp_server import McpServer
    from src.mcp.tools.music.music_player import MusicPlayer

    if container.mcp_server is None:
        container.mcp_server = McpServer()

    if container.music_player is None:
        container.music_player = MusicPlayer()

    logger.debug(t("共享服务已创建: McpServer, MusicPlayer"))


def unbind_shared_services(container: "ServiceContainer") -> None:
    """releases the shared service reference (called in the final stage of the resource pool)."""
    if container.music_player is not None:
        try:
            container.music_player.detach()
        except Exception as e:
            logger.debug(t('detach MusicPlayer 失败: {value1}', value1=e), exc_info=True)
    if container.mcp_server is not None:
        try:
            container.mcp_server.detach()
        except Exception as e:
            logger.debug(t('detach McpServer 失败: {value1}', value1=e), exc_info=True)
    container.music_player = None
    container.mcp_server = None


async def setup_plugins(
    container: "ServiceContainer",
    mode: str,
    ctx: "PluginContext",
    cmd: "PluginCommands",
) -> None:
    """binds the shared service, registers and initializes the plug-in, and hangs resource cleaning and audio direct connection."""
    from src.plugins.audio import AudioPlugin
    from src.plugins.mcp import McpPlugin
    from src.plugins.shortcuts import ShortcutsPlugin
    from src.plugins.ui import UIPlugin
    from src.plugins.wake_word import WakeWordPlugin

    bind_shared_services(container)

    # Create plug-in instance (Audio is released via event codec, MusicPlayer is not injected)
    audio_plugin = AudioPlugin()
    wake_word_plugin = WakeWordPlugin()
    ui_plugin = UIPlugin(mode=mode, task_manager=container.tasks)
    shortcuts_plugin = ShortcutsPlugin()
    mcp_plugin = McpPlugin(
        server=container.mcp_server,
        music_player=container.music_player,
    )

    container.plugins.register(
        mcp_plugin,
        audio_plugin,
        wake_word_plugin,
        ui_plugin,
        shortcuts_plugin,
    )

    await container.plugins.setup_all(ctx, cmd)

    register_cleanup_resources(container)

    # Sets the audio direct connection channel (TTS audio does not go through EventBus, reduce latency)
    if not audio_plugin.failed:
        container.protocol.set_audio_handler(audio_plugin.on_incoming_audio)


def register_cleanup_resources(container: "ServiceContainer") -> None:
    """Register the cleanup functions of all modules to the resource pool (registered first and then released)."""
    pool = container.resource_pool

    # First registered = last released: shared service unbind After the plug-in is cleaned,
    pool.register(
        "shared_services", lambda: unbind_shared_services(container)
    )

    # Event bus is released last (registered first)
    pool.register("event_bus", container.event_bus.clear)

    # Each plug-in registers its own resources
    for plugin in container.plugins._plugins:
        plugin.register_resources(pool)

    # Network connection
    pool.register("protocol", container.protocol.disconnect)

    # Asynchronous tasks
    pool.register("tasks", container.tasks.cancel_all)
