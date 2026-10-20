"""Interface protocol definition.

Define the contract between plug-ins, windows and core services to achieve loose coupling.
"""

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol

if TYPE_CHECKING:
    from src.constants.constants import DeviceState, ListeningMode


class PluginContext(Protocol):
    """Read-only context accessible by the plug-in.

    plug-in obtains the application status through this interface, but cannot modify the status directly. Whether
    """

    def get_device_state(self) -> "DeviceState":
        """
        Gets the current device status.
        """
        ...

    def get_listening_mode(self) -> "ListeningMode":
        """
        Gets the current listening mode.
        """
        ...

    def is_listening(self) -> bool:
        """
        is listening.
        """
        ...

    def is_speaking(self) -> bool:
        """
        is talking.
        """
        ...

    def is_idle(self) -> bool:
        """
        is in idle state.
        """
        ...

    def is_audio_channel_opened(self) -> bool:
        """
        Whether the audio channel is open.
        """
        ...

    def should_capture_audio(self) -> bool:
        """
        should collect audio.
        """
        ...

    def is_keep_listening(self) -> bool:
        """
        maintains continuous monitoring.
        """
        ...

    def get_config(self) -> Any:
        """
        Gets the configuration manager.
        """
        ...


class PluginCommands(Protocol):
    """Commands executable by the plug-in.

    plug-in performs operations through this interface, and the core service implements the specific logic. The
    """

    async def start_listening(self, mode: "ListeningMode") -> None:
        """
        Start listening.
        """
        ...

    async def stop_listening(self) -> None:
        """
        Stop listening.
        """
        ...

    async def abort_speaking(self, reason: str) -> None:
        """
        Abort speech output.
        """
        ...

    async def send_audio(self, data: bytes) -> None:
        """
        Send audio data.
        """
        ...

    async def send_text(self, text: str) -> None:
        """
        Send text message.
        """
        ...

    async def send_wake_word_detected(self, text: str) -> None:
        """
        Send detected text (wake word or user input).
        """
        ...

    async def send_mcp_message(self, payload: str) -> None:
        """
        Send MCP Message (will automatically wrap the format).
        """
        ...

    async def connect_protocol(self) -> bool:
        """
        Connection protocol channel.
        """
        ...

    def spawn(self, coro: Awaitable[Any], name: str) -> Any:
        """
        Create asynchronous task.
        """
        ...

    def schedule_command_nowait(self, fn: Callable, *args, **kwargs) -> None:
        """
        Scheduling command (non-blocking).
        """
        ...

    def request_shutdown(self) -> None:
        """
        Requests to close the application.
        """
        ...


class EventHandler(Protocol):
    """
    Event handler protocol.
    """

    async def __call__(self, data: Any = None) -> None:
        """
        Handle events.
        """
        ...


class EventBusProtocol(Protocol):
    """Event bus protocol.

    is used for decoupled communication between components.
    """

    def on(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        """
        registers event handlers.
        """
        ...

    def off(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        """
        Removes the event handler.
        """
        ...

    async def emit(self, event: str, data: Any = None) -> None:
        """
        Triggers the event.
        """
        ...
