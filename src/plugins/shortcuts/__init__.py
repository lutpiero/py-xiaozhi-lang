"""Shortcut key plug-in module.

Provides cross-platform global shortcut key support:
- macOS: use Quartz Event Tap (PyObjC)
- Linux/Windows: use pynput
"""
import asyncio
import sys
from typing import TYPE_CHECKING, Dict, Optional

from src.constants.constants import AbortReason
from src.i18n import t
from src.logging import get_logger
from src.plugins.base import Plugin
from src.utils.config_manager import get_config

from .base import ShortcutBackend, ShortcutConfig

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext

logger = get_logger()

__all__ = ["ShortcutBackend", "ShortcutConfig", "ShortcutsPlugin", "create_backend"]


def create_backend(
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> Optional[ShortcutBackend]:
    """Create a shortcut key backend suitable for the current platform.

    Args:
        loop: asyncio event loop

    Returns:
        Shortcut key backend instance, returned if it cannot be created None
    """
    if sys.platform == "darwin":
        # macOS: use Quartz Event first Tap
        try:
            from .macos_backend import MacOSShortcutBackend

            logger.info(t("使用 macOS Quartz Event Tap 后端"))
            return MacOSShortcutBackend(loop)
        except ImportError as e:
            logger.warning(t('无法加载 macOS 后端: {value1}', value1=e), exc_info=True)
            logger.info(t("回退到 pynput 后端"))
            # Fall back to pynput
            try:
                from .pynput_backend import PynputShortcutBackend

                return PynputShortcutBackend(loop)
            except ImportError as e2:
                logger.error(t('无法加载 pynput 后端: {value1}', value1=e2))
                return None
    else:
        # Linux/Windows: use pynput
        try:
            from .pynput_backend import PynputShortcutBackend

            logger.info(t("使用 pynput 后端"))
            return PynputShortcutBackend(loop)
        except ImportError as e:
            logger.error(t('无法加载 pynput 后端: {value1}', value1=e), exc_info=True)
            return None


class _CmdAdapter:
    """Shortcut key command adapter."""

    def __init__(self, cmd: "PluginCommands", ctx: "PluginContext"):
        self._cmd = cmd
        self._ctx = ctx

    async def toggle_chat_state(self):
        try:
            await self._cmd.connect_protocol()
            from src.constants.constants import ListeningMode

            mode = (
                ListeningMode.REALTIME
                if self._ctx.get_config().get_config("AEC_OPTIONS.ENABLED", True)
                else ListeningMode.AUTO_STOP
            )
            await self._cmd.start_listening(mode)
        except Exception as e:
            logger.error(t('切换对话状态失败: {value1}', value1=e), exc_info=True)

    async def abort_speaking(self, reason):
        try:
            await self._cmd.abort_speaking(reason)
        except Exception as e:
            logger.error(t('中断对话失败: {value1}', value1=e), exc_info=True)


class ShortcutsPlugin(Plugin):
    """Shortcut key plug-in."""

    name = "shortcuts"
    priority = 70  # Lowest priority, dependency UIPlugin

    # Shortcut key name constant
    MANUAL_PRESS = "MANUAL_PRESS"
    AUTO_TOGGLE = "AUTO_TOGGLE"
    ABORT = "ABORT"
    MODE_TOGGLE = "MODE_TOGGLE"
    WINDOW_TOGGLE = "WINDOW_TOGGLE"

    def __init__(self) -> None:
        super().__init__()
        self._backend: Optional[ShortcutBackend] = None
        self._adapter: Optional[_CmdAdapter] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._event_bus = None
        self._config = get_config()
        self._shortcuts_config: Dict = {}
        self._enabled = True

    async def setup(self, ctx: "PluginContext", cmd: "PluginCommands") -> None:
        await super().setup(ctx, cmd)
        self._adapter = _CmdAdapter(cmd, ctx)
        self._loop = asyncio.get_running_loop()
        self._event_bus = ctx.event_bus

        # Load configuration
        self._load_config()

        # Create backend
        self._backend = create_backend(self._loop)
        if not self._backend:
            logger.warning(t("无法创建快捷键后端，快捷键功能将不可用"))

        # Subscribe to configuration change events
        from src.core.event_bus import Events

        ctx.event_bus.on(Events.CONFIG_CHANGED, self._on_config_changed)

    def _load_config(self) -> None:
        """Load shortcut key configuration."""
        self._shortcuts_config = self._config.get_config("SHORTCUTS", {}) or {}
        self._enabled = bool(self._shortcuts_config.get("ENABLED", True))

    async def _on_config_changed(self, data=None) -> None:
        """Reload when configuration changes."""
        logger.info(t("ShortcutsPlugin: 收到配置变更事件，重新加载配置"))
        self.reload_from_config()

    async def start(self) -> None:
        """Start plug-in."""
        if not self._enabled:
            logger.info(t("快捷键功能已禁用"))
            return

        if not self._backend:
            logger.warning(t("快捷键后端不可用"))
            return

        # Register shortcut keys
        self._register_shortcuts()

        # Start backend
        success = await self._backend.start()
        if success:
            logger.info(t("快捷键插件已启动"))
        else:
            logger.error(t("快捷键后端启动失败"))

    def _register_shortcuts(self) -> None:
        """Register all shortcut keys."""
        if not self._backend:
            return

        shortcut_handlers = {
            self.MANUAL_PRESS: self._handle_manual_press,
            self.AUTO_TOGGLE: self._handle_auto_toggle,
            self.ABORT: self._handle_abort,
            self.MODE_TOGGLE: self._handle_mode_toggle,
            self.WINDOW_TOGGLE: self._handle_window_toggle,
        }

        for name, handler in shortcut_handlers.items():
            cfg = self._shortcuts_config.get(name, {}) or {}
            modifier = str(cfg.get("modifier", "ctrl")).lower()
            key = str(cfg.get("key", "")).lower()

            if not key:
                continue

            config = ShortcutConfig(
                modifier=modifier,
                key=key,
                description=cfg.get("description", ""),
            )

            self._backend.register(name, config, handler)

    def _handle_manual_press(self) -> None:
        """handles manual key shortcuts - use UI_MANUAL_TOGGLE Event."""
        if not self._event_bus or not self._loop:
            return

        from src.core.event_bus import Events

        asyncio.run_coroutine_threadsafe(
            self._event_bus.emit(Events.UI_MANUAL_TOGGLE), self._loop
        )

    def _handle_auto_toggle(self) -> None:
        """Handles the automatic dialogue switching shortcut key."""
        if not self._adapter or not self._loop:
            return

        asyncio.run_coroutine_threadsafe(
            self._adapter.toggle_chat_state(), self._loop
        )

    def _handle_abort(self) -> None:
        """handles interrupt shortcut keys."""
        if not self._adapter or not self._loop:
            return

        asyncio.run_coroutine_threadsafe(
            self._adapter.abort_speaking(AbortReason.NONE), self._loop
        )

    def _handle_mode_toggle(self) -> None:
        """Handles the mode switching shortcut key."""
        if not self._event_bus or not self._loop:
            return

        from src.core.event_bus import Events

        asyncio.run_coroutine_threadsafe(
            self._event_bus.emit(Events.UI_AUTO_TOGGLE), self._loop
        )

    def _handle_window_toggle(self) -> None:
        """Handles the window switching shortcut key."""
        if not self._event_bus or not self._loop:
            return

        from src.core.event_bus import Events

        asyncio.run_coroutine_threadsafe(
            self._event_bus.emit(Events.UI_TOGGLE_WINDOW), self._loop
        )

    async def stop(self) -> None:
        """stops the plugin."""
        if self._backend:
            await self._backend.stop()

    def register_resources(self, pool) -> None:
        backend = self._backend
        if backend:
            pool.register("shortcuts.backend", backend.stop)

    def reload_from_config(self) -> None:
        """reloads from configuration."""
        self._load_config()

        if not self._backend:
            return

        # Unregister all shortcut keys
        self._backend.unregister_all()

        if self._enabled:
            # Re-register
            self._register_shortcuts()
            logger.info(t("快捷键配置已重新加载"))
        else:
            logger.info(t("快捷键功能已禁用"))
