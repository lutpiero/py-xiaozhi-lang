"""Shortcut key backend abstract base class."""
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


@dataclass
class ShortcutConfig:
    """Shortcut key configuration."""

    modifier: str  # ctrl, alt, shift, cmd
    key: str  # Button
    description: str = ""


class ShortcutBackend(ABC):
    """Shortcut key backend abstract base class.

    defines the interface that all shortcut key backends must implement.
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        self._loop = loop
        self._running = False
        self._shortcuts: Dict[str, ShortcutConfig] = {}
        self._callbacks: Dict[str, Callable] = {}

    @abstractmethod
    async def start(self) -> bool:
        """starts shortcut key monitoring.

        Returns:
            Whether it is started successfully
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """stops shortcut key monitoring."""
        pass

    @abstractmethod
    def register(self, name: str, config: ShortcutConfig, callback: Callable) -> bool:
        """to register the shortcut key.

        Args:
            name: The shortcut key name
            config: shortcut key configuration
            callback: callback function (no parameters)

        Returns:
            Whether it is registered successfully
        """
        pass

    @abstractmethod
    def unregister(self, name: str) -> bool:
        """logout the shortcut key.

        Args:
            name: The shortcut key name

        Returns:
            Whether the logout is successful
        """
        pass

    def unregister_all(self) -> None:
        """Unregisters all shortcut keys."""
        for name in list(self._shortcuts.keys()):
            self.unregister(name)

    @property
    def is_running(self) -> bool:
        """Is it running."""
        return self._running

    def _run_callback(self, name: str) -> None:
        """Runs the callback function (thread safe).

        Args:
            name: The shortcut key name
        """
        if name not in self._callbacks:
            return

        callback = self._callbacks[name]
        if self._loop and self._loop.is_running():
            if asyncio.iscoroutinefunction(callback):
                asyncio.run_coroutine_threadsafe(callback(), self._loop)
            else:
                self._loop.call_soon_threadsafe(callback)
        else:
            # has no event loop and directly calls
            if asyncio.iscoroutinefunction(callback):
                logger.warning(t('无法调用异步回调 {value1}，没有事件循环', value1=name))
            else:
                try:
                    callback()
                except Exception as e:
                    logger.error(t('快捷键回调 {value1} 执行失败: {value3}', value1=name, value3=e), exc_info=True)
