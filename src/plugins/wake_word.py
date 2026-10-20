"""Wake word plug-in.

detects the wake word and triggers the conversation.
"""
from typing import TYPE_CHECKING, Optional

from src.constants.constants import AbortReason
from src.i18n import t
from src.logging import get_logger
from src.plugins.base import Plugin

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext

logger = get_logger()


class WakeWordPlugin(Plugin):
    name = "wake_word"
    priority = 30
    requires = ["audio"]

    def __init__(self) -> None:
        super().__init__()
        self.detector = None

    @property
    def _audio_plugin(self):
        """Get the AudioPlugin through dependency injection."""
        return self.get_dep("audio")

    async def setup(self, ctx: "PluginContext", cmd: "PluginCommands") -> None:
        await super().setup(ctx, cmd)
        # Subscribe to configuration change events (lightweight, no model loading)
        from src.core.event_bus import Events
        ctx.event_bus.on(Events.CONFIG_CHANGED, self._on_config_changed)

    async def _on_config_changed(self, data=None):
        """Reload the wake word model when configuration changes."""
        logger.info(t("WakeWordPlugin: 收到配置变更事件，重新加载唤醒词模型"))
        await self.reload_model()

    async def start(self) -> None:
        try:
            # Lazy load the model to the start() stage to avoid setup() with PortAudio DLL Conflict
            if self.detector is None:
                from src.audio_processing.wake_word_detect import WakeWordDetector

                self.detector = WakeWordDetector()
                if not await self.detector.initialize():
                    logger.info(t("唤醒词检测器未启用或初始化失败"))
                    self.detector = None
                    return
                self.detector.on_detected(self._on_detected)
                self.detector.on_error = self._on_error

            if not self._audio_plugin or not self._audio_plugin.codec:
                logger.warning(t("未找到 audio_codec，无法启动唤醒词检测"))
                return
            await self.detector.start(self._audio_plugin.codec)
        except ImportError as e:
            logger.error(t('无法导入唤醒词检测器: {value1}', value1=e), exc_info=True)
            self.detector = None
        except Exception as e:
            logger.error(t('启动唤醒词检测器失败: {value1}', value1=e), exc_info=True)

    async def stop(self) -> None:
        if self.detector:
            try:
                await self.detector.stop()
            except Exception as e:
                logger.warning(t('停止唤醒词检测器失败: {value1}', value1=e), exc_info=True)

    def register_resources(self, pool) -> None:
        detector = self.detector
        if detector:
            pool.register("wake_word.detector", detector.shutdown)

    async def reload_model(self, model_path: Optional[str] = None) -> bool:
        """Hot reload wake word model.

        Args:
            model_path: New model path (such as "models/en"). If None, read from configuration.

        Returns:
            Whether the reload is successful
        """
        if not self.detector:
            logger.warning(t("检测器未初始化，无法热重载"))
            return False

        try:
            return await self.detector.reload(model_path)
        except Exception as e:
            logger.error(t('热重载唤醒词模型失败: {value1}', value1=e), exc_info=True)
            return False

    async def _on_detected(self, wake_word, full_text):
        """
        Wake word detection callback.
        """
        try:
            if self._ctx.is_speaking():
                await self._cmd.abort_speaking(AbortReason.WAKE_WORD_DETECTED)
                if self._audio_plugin and self._audio_plugin.codec:
                    await self._audio_plugin.codec.clear_audio_queue()
            else:
                # Start automatic conversation
                await self._cmd.connect_protocol()
                from src.constants.constants import ListeningMode

                mode = (
                    ListeningMode.REALTIME
                    if self._ctx.get_config().get_config("AEC_OPTIONS.ENABLED", True)
                    else ListeningMode.AUTO_STOP
                )
                await self._cmd.start_listening(mode)
        except Exception as e:
            logger.error(t('处理唤醒词检测失败: {value1}', value1=e), exc_info=True)

    async def _on_error(self, error):
        """
        Wake word detection error callback.
        """
        logger.error(t('唤醒词检测错误: {value1}', value1=error), exc_info=True)
