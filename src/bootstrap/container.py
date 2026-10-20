"""Service Container.

Integrates core services as the central coordinator of the application; sessions/latches/assemblies/adapters have been split into submodules.
"""
from src.bootstrap.adapters import PluginCommandsAdapter, PluginContextAdapter
from src.bootstrap.health import (
    DEGRADED_AUDIO_NOTICE,
    audio_is_fatal,
    check_critical_plugins,
)
from src.bootstrap.plugin_wiring import setup_plugins
from src.bootstrap.protocols import PluginCommands, PluginContext
from src.bootstrap.session import ConversationSession
from src.core.event_bus import EventBus, Events
from src.core.protocol_manager import ProtocolManager
from src.core.resource_pool import ResourcePool
from src.core.state_manager import StateManager
from src.core.task_manager import TaskManager
from src.i18n import t
from src.logging import get_logger
from src.plugins.manager import PluginManager
from src.utils.config_manager import get_config

logger = get_logger()


class ServiceContainer:
    """Service Container.

    holds the core service and ConversationSession, orchestrating the run / shutdown life cycle.
    Session operation goes ``self.session``; latch goes ``health`` module.
    """

    def __init__(self):
        logger.debug(t("初始化 ServiceContainer"))

        self.config = get_config()

        try:
            aec_enabled = bool(self.config.get_config("AEC_OPTIONS.ENABLED", True))
        except Exception:
            aec_enabled = True

        self.event_bus = EventBus()
        self.state = StateManager(self.event_bus, aec_enabled=aec_enabled)
        self.tasks = TaskManager()
        # Protocol Inbound tasks go to TaskManager to avoid fire-and-forget
        self.protocol = ProtocolManager(self.event_bus, task_manager=self.tasks)
        self.plugins = PluginManager()
        self.resource_pool = ResourcePool()

        # The cross-plugin shared service held by the container (bind when starting, unbind when shutting down)
        self.mcp_server = None
        self.music_player = None

        # Session control (listen/speak/interrupt/TTS loopback)
        self.session = ConversationSession(
            state=self.state,
            protocol=self.protocol,
            plugins=self.plugins,
            event_bus=self.event_bus,
        )

        self._plugin_context: PluginContextAdapter | None = None
        self._plugin_commands: PluginCommandsAdapter | None = None

        self._mode: str = "cli"
        self._shutting_down = False
        # audio downgrade operation (XIAOZHI_DEGRADED_AUDIO=1 and audio failed)
        self._degraded_audio = False

    # -------------------------
    # Adapter Creation
    # -------------------------
    def create_plugin_context(self) -> PluginContext:
        if not self._plugin_context:
            self._plugin_context = PluginContextAdapter(self)
        return self._plugin_context

    def create_plugin_commands(self) -> PluginCommands:
        if not self._plugin_commands:
            self._plugin_commands = PluginCommandsAdapter(self)
        return self._plugin_commands

    # -------------------------
    # Life Cycle
    # -------------------------
    async def run(self, *, protocol: str = "websocket", mode: str = "gui") -> int:
        logger.info(t('启动 ServiceContainer, protocol={value1}, mode={value3}', value1=protocol, value3=mode))
        self._mode = mode

        try:
            self.tasks.initialize()
            self.protocol.set_task_manager(self.tasks)
            self.protocol.set_protocol(protocol)

            self.session.bind_events(self.event_bus)

            ctx = self.create_plugin_context()
            cmd = self.create_plugin_commands()

            await setup_plugins(self, mode, ctx, cmd)
            await self.plugins.start_all()

            # Key plug-in health latch: exit on failure, disable silent zombie
            health_error = check_critical_plugins(self.plugins)
            if health_error:
                logger.error(health_error)
                return 1

            # audio failure but allow downgrade: display banner/log and continue running UI
            if self.plugins.is_failed("audio") and not audio_is_fatal():
                logger.warning(DEGRADED_AUDIO_NOTICE)
                self._degraded_audio = True
                try:
                    await self.event_bus.emit(
                        Events.SYSTEM_NOTICE, DEGRADED_AUDIO_NOTICE
                    )
                except Exception as e:
                    logger.debug(t('降级提示事件失败: {value1}', value1=e), exc_info=True)

            await self.plugins.notify_device_state_changed(self.state.device_state)

            await self.tasks.wait_shutdown()
            return 0

        except Exception as e:
            logger.error(t('应用运行失败: {value1}', value1=e), exc_info=True)
            return 1
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Closes the application and releases all resources uniformly through the resource pool in reverse order."""
        if self._shutting_down:
            logger.debug(t("ServiceContainer 已在关闭中，跳过"))
            return
        self._shutting_down = True
        logger.info(t("正在关闭 ServiceContainer..."))

        try:
            await self.resource_pool.shutdown()
            logger.info(t("ServiceContainer 关闭完成"))
        except Exception as e:
            logger.error(t('关闭时出错: {value1}', value1=e), exc_info=True)
        finally:
            if self._mode == "gui":
                try:
                    from PySide6.QtWidgets import QApplication

                    if QApplication.instance():
                        logger.debug(t("退出 Qt 应用"))
                        QApplication.quit()
                except Exception as e:
                    logger.debug(t('退出 Qt 应用时出错: {value1}', value1=e))
