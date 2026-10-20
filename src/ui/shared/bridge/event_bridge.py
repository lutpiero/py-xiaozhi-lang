"""EventBus Bridge - Python Signals to QML Signal bidirectional conversion."""
from PySide6.QtCore import QObject, QTimer, Signal, Slot

from src.core.event_bus import EventBus, Events
from src.i18n import t
from src.logging import get_logger

logger = get_logger()


class EventBridge(QObject):
    """EventBus Bidirectional bridge to QML.

    QML → Python: QML calls slot, slot internal emit EventBus event
    Python → QML: EventBus event triggers Python Signal, QML connects the Signal

    Device activation is handled by the independent GuiActivation window, and the main interface bridge no longer carries the activation signal.
    """

    # ========== Python → QML Signals ==========

    # Window control
    showWindow = Signal()
    hideWindow = Signal()
    showSettingsWindow = Signal()  # Display setting window

    # ========== Construct ==========

    def __init__(self, event_bus: EventBus, task_manager=None, parent: QObject | None = None):
        super().__init__(parent)
        self._event_bus = event_bus
        self._task_manager = task_manager

    def _emit_event(self, event: str, data=None):
        """safely emit EventBus events and schedule them to asyncio in the Qt main thread. loop."""
        if self._task_manager is None:
            logger.error(t("EventBridge: TaskManager 未注入，无法发射事件"))
            return

        def do_emit():
            try:
                task_name = f"bridge:{event.split('.')[-1]}" if '.' in event else f"bridge:{event}"
                self._task_manager.spawn(self._event_bus.emit(event, data), name=task_name)
            except Exception as e:
                logger.warning(
                    t('EventBridge: 发射事件 {value1} 失败: {value3}', value1=event, value3=e),
                    exc_info=True,
                )

        # Use QTimer.singleShot to ensure that Qt Execute
        QTimer.singleShot(0, do_emit)

    # ========== QML → Python (Slots) ==========

    @Slot()
    def onButtonPress(self):
        """Manual mode button pressed."""
        logger.debug(t("EventBridge: 按钮按下"))
        self._emit_event(Events.UI_BUTTON_PRESS)

    @Slot()
    def onButtonRelease(self):
        """Manual mode button released."""
        logger.debug(t("EventBridge: 按钮释放"))
        self._emit_event(Events.UI_BUTTON_RELEASE)

    @Slot()
    def onManualToggle(self):
        """Manual mode recording switch (click start/stop)."""
        logger.debug(t("EventBridge: 手动录音切换"))
        self._emit_event(Events.UI_MANUAL_TOGGLE)

    @Slot()
    def onAutoToggle(self):
        """Automatic mode switching."""
        logger.debug(t("EventBridge: 自动模式切换"))
        self._emit_event(Events.UI_AUTO_TOGGLE)

    @Slot()
    def onAutoStart(self):
        """Automatic mode: start or stop the conversation."""
        logger.debug(t("EventBridge: 自动模式开始/停止对话"))
        self._emit_event(Events.UI_AUTO_START)

    @Slot()
    def onAbort(self):
        """Interrupt request."""
        logger.debug(t("EventBridge: 中断请求"))
        self._emit_event(Events.UI_ABORT_REQUEST)

    @Slot(str)
    def onSendText(self, text: str):
        """to send text in the event loop."""
        if text.strip():
            logger.debug(t('EventBridge: 发送文本: {value1}...', value1=text[:20]))
            from src.ui.shared.events import UISendTextRequest
            self._emit_event(Events.UI_SEND_TEXT, UISendTextRequest(text=text))

    @Slot()
    def onQuitRequest(self):
        """Exit request."""
        logger.info(t("EventBridge: 退出请求"))
        self._emit_event(Events.UI_QUIT_REQUEST)

    @Slot()
    def onOpenSettings(self):
        """Open setting window - transmit signal directly to QML."""
        logger.debug(t("EventBridge: 打开设置窗口"))
        self.showSettingsWindow.emit()
