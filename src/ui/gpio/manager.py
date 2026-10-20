# -*- coding: utf-8 -*-
"""GPIO key interface (status logging)."""
import asyncio
from typing import TYPE_CHECKING, Optional

from src.core.event_bus import EventBus, Events
from src.i18n import t
from src.logging import get_logger

from .input import GPIOInput

if TYPE_CHECKING:
    from src.core.task_manager import TaskManager

logger = get_logger()


class GpioViewManager:
    """GPIO interface (ViewPort: same set_* as CLI/GUI)."""

    def __init__(
        self,
        event_bus: EventBus,
        task_manager: Optional["TaskManager"] = None,
    ):
        self._event_bus = event_bus
        self._task_manager = task_manager
        self._gpio_input = GPIOInput()
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Status
        self._auto_mode = False
        self._status = t("待命")
        self._connected = False
        self._chat_text = ""
        self._music_line = ""

    async def start(self, mode: str = "gpio"):
        """Start the GPIO view.

        Args:
            mode: Running mode (GPIO This parameter is ignored in mode)
        """
        logger.info(t("GpioViewManager: 启动 GPIO 界面..."))
        self._running = True
        self._loop = asyncio.get_running_loop()

        # Set the GPIO key callback
        if self._gpio_input.available:
            self._gpio_input.setup(
                on_key1_pressed=self._on_key1,
                on_key2_pressed=self._on_key2,
                on_key3_pressed=self._on_key3,
                on_key4_pressed=self._on_key4,
            )
            logger.info(t("GPIO 按键已就绪"))
            logger.info(t("KEY1: 开始/停止对话"))
            logger.info(t("KEY2: 中断语音"))
            logger.info(t("KEY3: 切换模式"))
            logger.info(t("KEY4: 退出程序"))
        else:
            logger.warning(t("GPIO 不可用，按键功能已禁用"))

        # Keep running (event-driven)
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info(t("GpioViewManager: 任务被取消"))

    async def close(self):
        """Close the GPIO view."""
        logger.info(t("GpioViewManager: 正在关闭..."))
        self._running = False
        self._gpio_input.close()
        logger.info(t("GpioViewManager: 已关闭"))

    # ========== Key callback ==========

    def _on_key1(self):
        """KEY1: Start/stop the conversation."""
        if self._auto_mode:
            self._safe_emit(Events.UI_AUTO_START)
            logger.info(t("[KEY1] 自动模式：切换开始/停止对话"))
        else:
            self._safe_emit(Events.UI_MANUAL_TOGGLE)
            logger.info(t("[KEY1] 手动模式：切换录音"))

    def _on_key2(self):
        """KEY2: Interrupt."""
        self._safe_emit(Events.UI_ABORT_REQUEST)
        logger.info(t("[KEY2] 中断语音"))

    def _on_key3(self):
        """KEY3: Switch to automatic/manual."""
        self._safe_emit(Events.UI_AUTO_TOGGLE)
        logger.info(t("[KEY3] 请求切换对话模式"))

    def _on_key4(self):
        """KEY4: Exit the program."""
        self._safe_emit(Events.UI_QUIT_REQUEST)
        logger.info(t("[KEY4] 退出程序"))

    def _safe_emit(self, event: str, data=None):
        """Send events securely.

        first via TaskManager.schedule_nowait (thread safe and traceable);
        otherwise falls back to run_coroutine_threadsafe.
        """
        def _start_emit():
            if data is None:
                return self._event_bus.emit(event)
            return self._event_bus.emit(event, data)

        if self._task_manager is not None:
            try:
                self._task_manager.schedule_nowait(_start_emit)
                return
            except Exception as e:
                logger.error(
                    t('GpioViewManager 经 TaskManager 调度事件 {value1} 失败: {value3}', value1=event, value3=e),
                    exc_info=True,
                )

        if not self._loop or not self._loop.is_running():
            return
        coro = _start_emit()
        try:
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)

            def _done(f):
                try:
                    exc = f.exception()
                except Exception:
                    return
                if exc:
                    logger.error(
                        t('GpioViewManager 发射事件 {value1} 失败: {value3}', value1=event, value3=exc),
                        exc_info=exc,
                    )

            fut.add_done_callback(_done)
        except Exception as e:
            logger.error(t('GpioViewManager 调度事件 {value1} 失败: {value3}', value1=event, value3=e), exc_info=True)
            if asyncio.iscoroutine(coro):
                coro.close()

    # ========== Public API ==========

    @property
    def is_running(self) -> bool:
        """Is it running."""
        return self._running

    def set_status(self, status: str, connected: bool = True):
        """Set status."""
        self._status = status
        self._connected = connected
        logger.info(t('[状态] {value1}', value1=status))

    def set_chat_text(self, text: str):
        self._chat_text = text
        logger.info(t('[对话] {value1}', value1=text))

    def set_music_line(self, text: str):
        self._music_line = text
        logger.info(t('[音乐] {value1}', value1=text))

    def set_emotion(self, emotion: str):
        logger.debug(t('[表情] {value1}', value1=emotion))

    def set_auto_mode(self, auto_mode: bool):
        # KEY1 The branch will look at this
        self._auto_mode = auto_mode
        mode_text = t("自动") if auto_mode else t("手动")
        logger.info(t('[模式] {value1}', value1=mode_text))

    def set_button_text(self, text: str):
        logger.debug(f"GPIO set_button_text: {text}")

    def is_auto_mode(self) -> bool:
        return bool(self._auto_mode)
