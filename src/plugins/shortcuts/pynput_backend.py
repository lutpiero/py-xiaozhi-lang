"""pynput Shortcut key backend.

is used for Linux and Windows systems.
"""
import asyncio
import time
from typing import Callable, Optional, Set

from src.i18n import t
from src.logging import get_logger

from .base import ShortcutBackend, ShortcutConfig

logger = get_logger()

try:
    from pynput import keyboard
except ImportError as e:
    raise ImportError(
        "pynput is required for keyboard shortcut support. "
        "Install with: pip install pynput"
    ) from e


class PynputShortcutBackend(ShortcutBackend):
    """pynput Shortcut key backend.

    Applicable to Linux and Windows systems.
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        super().__init__(loop)
        self._listener = None
        self._pressed_keys: Set[str] = set()
        self._last_activity_time = 0.0
        self._health_check_task = None
        self._check_interval = 10.0  # Health check interval (seconds)

        # Control character mapping
        self._key_mapping = {
            "\x17": "w", "\x01": "a", "\x13": "s", "\x04": "d",
            "\x05": "e", "\x12": "r", "\x14": "t", "\x06": "f",
            "\x07": "g", "\x08": "h", "\x0a": "j", "\x0b": "k",
            "\x0c": "l", "\x1a": "z", "\x18": "x", "\x03": "c",
            "\x16": "v", "\x02": "b", "\x0e": "n", "\x0d": "m",
            "\x11": "q",
        }

    async def start(self) -> bool:
        """starts shortcut key monitoring."""
        if self._running:
            return True

        try:
            self._listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._listener.start()
            self._running = True
            self._last_activity_time = time.time()

            # starts the health check
            self._start_health_check()

            logger.info(t("pynput 全局快捷键监听已启动"))
            return True
        except Exception as e:
            logger.error(t('启动 pynput 快捷键监听失败: {value1}', value1=e), exc_info=True)
            return False

    async def stop(self) -> None:
        """stops shortcut key monitoring."""
        self._running = False

        # Stop health check
        if self._health_check_task:
            self._health_check_task.cancel()
            # concurrent.futures.Future cannot await directly, special processing is required
            try:
                # waits for the Future to complete (ignoring cancellation exceptions)
                self._health_check_task.result(timeout=1.0)
            except Exception as e:
                logger.debug(t('Pynput 健康检查超时: {value1}', value1=e))
            self._health_check_task = None

        # Stop listener
        if self._listener:
            try:
                self._listener.stop()
            except Exception as e:
                logger.warning(t('停止监听器时出错: {value1}', value1=e), exc_info=True)
            self._listener = None

        self._pressed_keys.clear()
        logger.info(t("pynput 全局快捷键监听已停止"))

    def register(self, name: str, config: ShortcutConfig, callback: Callable) -> bool:
        """to register the shortcut key."""
        self._shortcuts[name] = config
        self._callbacks[name] = callback
        logger.info(t('已注册快捷键: {value1} -> {value3}+{value5}', value1=name, value3=config.modifier, value5=config.key))
        return True

    def unregister(self, name: str) -> bool:
        """logout the shortcut key."""
        if name not in self._shortcuts:
            return False

        del self._shortcuts[name]
        if name in self._callbacks:
            del self._callbacks[name]

        logger.info(t('已注销快捷键: {value1}', value1=name))
        return True

    def _on_key_press(self, key) -> None:
        """Key press callback."""
        if not self._running:
            return

        self._last_activity_time = time.time()
        key_name = self._get_key_name(key)
        if not key_name:
            return

        self._pressed_keys.add(key_name)
        self._check_shortcuts()

    def _on_key_release(self, key) -> None:
        """Key release callback."""
        if not self._running:
            return

        self._last_activity_time = time.time()
        key_name = self._get_key_name(key)
        if not key_name:
            return

        self._pressed_keys.discard(key_name)

    def _get_key_name(self, key) -> Optional[str]:
        """Get the key name."""
        try:
            if hasattr(key, "name"):
                name = key.name
                # Normalized modifier key name
                if name in ("ctrl_l", "ctrl_r"):
                    return "ctrl"
                if name in ("alt_l", "alt_r"):
                    return "alt"
                if name in ("shift_l", "shift_r"):
                    return "shift"
                if name == "cmd":
                    return "cmd"
                if name == "esc":
                    return "escape"
                if name == "enter":
                    return "return"
                return name.lower()
            elif hasattr(key, "char") and key.char:
                char = key.char
                if char == "\n":
                    return "return"
                if char in self._key_mapping:
                    return self._key_mapping[char]
                return char.lower()
        except Exception as e:
            logger.debug(t('按键映射失败: {value1}', value1=e))
        return None

    def _check_shortcuts(self) -> None:
        """Check if the shortcut key is triggered."""
        if not self._shortcuts:
            return

        # Check the modifier key status
        ctrl = any(k in self._pressed_keys for k in ("ctrl", "control"))
        alt = any(k in self._pressed_keys for k in ("alt", "option"))
        shift = "shift" in self._pressed_keys
        cmd = "cmd" in self._pressed_keys

        for name, config in self._shortcuts.items():
            if self._match_shortcut(config, ctrl, alt, shift, cmd):
                logger.debug(t('触发快捷键: {value1}', value1=name))
                self._run_callback(name)

    def _match_shortcut(
        self, config: ShortcutConfig, ctrl: bool, alt: bool, shift: bool, cmd: bool
    ) -> bool:
        """Check if the shortcut key configuration is matched."""
        modifier = config.modifier.lower()

        # Check modifier keys
        if modifier == "ctrl" and not ctrl:
            return False
        if modifier == "alt" and not alt:
            return False
        if modifier == "shift" and not shift:
            return False
        if modifier == "cmd" and not cmd:
            return False

        # Check the primary key
        return config.key.lower() in {k.lower() for k in self._pressed_keys}

    def _start_health_check(self) -> None:
        """starts the health check task."""
        if self._loop:
            self._health_check_task = asyncio.run_coroutine_threadsafe(
                self._health_check_loop(), self._loop
            )

    async def _health_check_loop(self) -> None:
        """Health check loop."""
        while self._running:
            await asyncio.sleep(self._check_interval)

            if not self._running:
                break

            # Check if the listener is still running
            if self._listener and not self._listener.is_alive():
                logger.warning(t("pynput 监听器已停止，尝试重启..."))
                await self._restart_listener()

    async def _restart_listener(self) -> None:
        """Restart the listener."""
        try:
            # Stop old listener
            if self._listener:
                try:
                    self._listener.stop()
                except Exception as e:
                    logger.debug(t('停止 Pynput 监听器失败: {value1}', value1=e))
                self._listener = None

            # short wait
            await asyncio.sleep(0.5)

            # Create new listener
            self._listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._listener.start()
            self._pressed_keys.clear()
            logger.info(t("pynput 监听器重启成功"))
        except Exception as e:
            logger.error(t('重启 pynput 监听器失败: {value1}', value1=e), exc_info=True)
