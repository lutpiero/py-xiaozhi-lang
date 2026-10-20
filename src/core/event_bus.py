"""event bus.

provides a decoupled communication mechanism between components.
"""
import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


# Predefined event name
class Events:
    """
    Predefined event constants.
    """

    # Device Status
    DEVICE_STATE_CHANGED = "device_state_changed"

    # Protocol related
    PROTOCOL_CONNECTED = "protocol_connected"
    PROTOCOL_DISCONNECTED = "protocol_disconnected"
    INCOMING_JSON = "incoming_json"
    INCOMING_AUDIO = "incoming_audio"

    # Network Error
    NETWORK_ERROR = "network_error"

    # Audio channel
    AUDIO_CHANNEL_OPENED = "audio_channel_opened"
    AUDIO_CHANNEL_CLOSED = "audio_channel_closed"
    # AudioCodec life cycle (AudioPlugin → MusicPlayer and other subscribers, avoid direct connection set)
    AUDIO_CODEC_CHANGED = "audio_codec_changed"
    # requests to re-enumerate the audio device (refresh the settings page; you need to stop the flow first and then PortAudio reinit)
    # payload: Optional asyncio.Future, when completed set_result(list|dict|None)
    AUDIO_DEVICES_REFRESH_REQUEST = "audio_devices_refresh_request"

    # Application life cycle
    APP_SHUTDOWN = "app_shutdown"
    # System-level prompts (downgrade mode banners, etc., payload: str)
    SYSTEM_NOTICE = "system_notice"

    # Music player event
    MUSIC_STATE_CHANGED = "music_state_changed"  # Playback status changes
    MUSIC_LYRICS_UPDATE = "music_lyrics_update"  # Lyrics update
    MUSIC_PROGRESS_UPDATE = "music_progress_update"  # Progress update

    # Music control command (controlled externally) MusicPlayer)
    MUSIC_PAUSE_REQUEST = "music_pause_request"  # Request Pause (e.g. TTS)
    MUSIC_RESUME_REQUEST = "music_resume_request"  # Request Resume

    # UI operation (interface → Plug-in)
    UI_BUTTON_PRESS = "ui_button_press"  # Manual: Press
    UI_BUTTON_RELEASE = "ui_button_release"  # Manual: Release
    UI_MANUAL_TOGGLE = "ui_manual_toggle"  # Manual: Click to start/end recording
    UI_AUTO_TOGGLE = "ui_auto_toggle"  # switches to automatic/manual
    UI_AUTO_START = "ui_auto_start"  # Automatic: Start/Stop Dialogue
    UI_ABORT_REQUEST = "ui_abort_request"  # Interrupt
    UI_SEND_TEXT = "ui_send_text"  # Send text
    UI_QUIT_REQUEST = "ui_quit_request"  # Exit
    UI_OPEN_SETTINGS = "ui_open_settings"  # Open settings
    UI_TOGGLE_WINDOW = "ui_toggle_window"  # Show and hide the main window (GUI)

    # Configuration change event
    CONFIG_CHANGED = "config_changed"  # Configuration changed (requires hot reload)
    # MCP After tool exposure changes: Disconnect and reconnect the protocol to make the server re-tools/list
    PROTOCOL_RECONNECT_REQUEST = "protocol_reconnect_request"


# A collection of known event names: hit warning (debug) in on/emit when spelling mistakes Friendly)
_KNOWN_EVENTS: frozenset[str] = frozenset(
    v for k, v in vars(Events).items() if not k.startswith("_") and isinstance(v, str)
)


class EventBus:
    """Event bus.

    Supports asynchronous event processing and loosely coupled communication
    between components.

    Usage:
        bus = EventBus()
        bus.on(Events.DEVICE_STATE_CHANGED, on_state_changed)
        await bus.emit(Events.DEVICE_STATE_CHANGED, DeviceState.LISTENING)
        bus.off(Events.DEVICE_STATE_CHANGED, on_state_changed)
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable[..., Awaitable[None]]]] = defaultdict(
            list
        )

    @staticmethod
    def _warn_if_unknown(event: str, action: str) -> None:
        if event not in _KNOWN_EVENTS:
            logger.warning(
                t('EventBus: {value1} 未知事件名 {value3!r}（可能是拼写错误；请使用 Events.* 常量）', value1=action, value3=event)
            )

    def on(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        """registers event handlers.

        Args:
            event: event name
            handler: asynchronous processing function
        """
        self._warn_if_unknown(event, t("注册"))
        if handler not in self._handlers[event]:
            self._handlers[event].append(handler)
            logger.debug(t('EventBus: 注册处理器 {value1} -> {value3}', value1=handler.__name__, value3=event))

    def off(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        """Removes the event handler.

        Args:
            event: event name
            handler: handler function to be removed
        """
        if handler in self._handlers[event]:
            self._handlers[event].remove(handler)
            logger.debug(t('EventBus: 移除处理器 {value1} <- {value3}', value1=handler.__name__, value3=event))

    def clear(self, event: str = None) -> None:
        """Clear the event handler.

        Args:
            event: event name, clear all when None
        """
        if event is None:
            self._handlers.clear()
            logger.debug(t("EventBus: 清除所有处理器"))
        elif event in self._handlers:
            self._handlers[event].clear()
            logger.debug(t('EventBus: 清除事件 {value1} 的所有处理器', value1=event))

    async def emit(self, event: str, data: Any = None) -> None:
        """Triggers the event.

        calls all registered processors in parallel.

        Args:
            event: event name
            data: event data
        """
        handlers = list(self._handlers.get(event, []))
        if not handlers:
            # An unknown event name is still prompted when there are no subscribers to avoid silent loss of spelling errors
            self._warn_if_unknown(event, t("触发"))
            return

        logger.debug(t('EventBus: 触发事件 {value1}, {value3} 个处理器', value1=event, value3=len(handlers)))

        # executes all processors in parallel
        tasks = []
        for handler in handlers:
            try:
                tasks.append(self._safe_call(handler, data))
            except Exception as e:
                logger.error(
                    t('EventBus: 创建任务失败 {value1}: {value3}', value1=handler.__name__, value3=e),
                    exc_info=True,
                )

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def emit_sequential(self, event: str, data: Any = None) -> None:
        """Sequentially triggered events.

        Call the processors in sequence in the registration order.

        Args:
            event: event name
            data: event data
        """
        handlers = list(self._handlers.get(event, []))
        for handler in handlers:
            await self._safe_call(handler, data)

    async def _safe_call(
        self, handler: Callable[..., Awaitable[None]], data: Any
    ) -> None:
        """
        Safely call the processor and catch exceptions.
        """
        try:
            if data is None:
                await handler()
            else:
                await handler(data)
        except Exception as e:
            logger.error(
                t('EventBus: 处理器 {value1} 执行异常: {value3}', value1=handler.__name__, value3=e),
                exc_info=True,
            )

    def has_handlers(self, event: str) -> bool:
        """
        Check whether the event has a handler.
        """
        return bool(self._handlers.get(event))

    def handler_count(self, event: str) -> int:
        """
        Get the number of handlers for the event.
        """
        return len(self._handlers.get(event, []))
