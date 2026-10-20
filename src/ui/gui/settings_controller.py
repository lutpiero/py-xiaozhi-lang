"""Settings window: SettingsModel lazy loading and opening settings."""
from src.core.event_bus import EventBus, Events
from src.core.task_manager import TaskManager
from src.i18n import t
from src.logging import get_logger
from src.ui.shared.bridge import EventBridge

logger = get_logger()


class SettingsController:
    """Lazy creation of SettingsModel; when opening settings reload notifies QML."""

    def __init__(
        self,
        event_bus: EventBus,
        tasks: TaskManager,
        bridge: EventBridge,
    ) -> None:
        self._event_bus = event_bus
        self._tasks = tasks
        self._bridge = bridge
        self._settings_model = None

    @property
    def settings_model(self):
        return self.ensure_model()

    def ensure_model(self):
        """Lazy creation of SettingsModel (when first injecting QML/opening settings)."""
        if self._settings_model is None:
            from src.ui.gui.models import SettingsModel

            self._settings_model = SettingsModel(
                event_bus=self._event_bus,
                task_manager=self._tasks,
            )
            self._settings_model.configSaved.connect(self._on_config_saved)
            self._settings_model.mcpToolsNeedReconnect.connect(
                self._on_mcp_tools_need_reconnect
            )
            logger.debug(t("SettingsController: SettingsModel 已懒加载"))
        return self._settings_model

    def _on_config_saved(self) -> None:
        logger.info(t("SettingsController: 配置已保存，触发热重载"))
        self._tasks.spawn(
            self._event_bus.emit(Events.CONFIG_CHANGED), name="ui:config_changed"
        )

    def _on_mcp_tools_need_reconnect(self) -> None:
        """MCP tool blacklist change: request the session layer to disconnect and reconnect to refresh the server tools/list."""
        logger.info(t("SettingsController: MCP 工具列表变更，请求协议重连"))
        self._tasks.spawn(
            self._event_bus.emit(Events.PROTOCOL_RECONNECT_REQUEST),
            name="ui:protocol_reconnect",
        )

    def open_settings(self) -> None:
        """reload the configuration/device list, and then let QML display the settings window."""
        self.ensure_model().reload()
        self._bridge.showSettingsWindow.emit()
        logger.debug(t("SettingsController: 已发送打开设置窗口信号"))
