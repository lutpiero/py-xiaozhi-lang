"""Interface Unified interface: gui / cli / gpio All implement this set."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ViewPort(Protocol):
    """A collection of methods for writing the interface."""

    async def start(self, mode: str = "cli") -> None:
        """Start."""
        ...

    async def close(self) -> None:
        """Close."""
        ...

    def set_status(self, status: str, connected: bool = True) -> None:
        """Status bar."""
        ...

    def set_emotion(self, emotion: str) -> None:
        """Expression name, each end of the specific resource parses it by itself."""
        ...

    def set_chat_text(self, text: str) -> None:
        """Conversation content (TTS/ STT)."""
        ...

    def set_music_line(self, text: str) -> None:
        """Music status or lyrics."""
        ...

    def set_button_text(self, text: str) -> None:
        """Main button copy; no button can be implemented empty."""
        ...

    def set_auto_mode(self, auto_mode: bool) -> None:
        """Refresh automatic/manual display (the true state is in Session)."""
        ...

    def is_auto_mode(self) -> bool:
        """The current mode recorded on the interface (for example, the GPIO button branch will be used)."""
        ...
