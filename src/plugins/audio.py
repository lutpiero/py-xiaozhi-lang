"""Audio plug-in.

is responsible for audio collection, encoding, playback and sending.
AudioCodec is published by Events.AUDIO_CODEC_CHANGED and is not directly connected to MusicPlayer.
"""
import asyncio
import os
from typing import TYPE_CHECKING

from src.audio_codecs.audio_codec import AudioCodec
from src.i18n import t
from src.logging import get_logger
from src.plugins.base import Plugin

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext

logger = get_logger()

MAX_CONCURRENT_AUDIO_SENDS = 4


class AudioPlugin(Plugin):
    name = "audio"
    priority = 10  # The highest priority, other plug-ins depend on audio_codec

    def __init__(self) -> None:
        super().__init__()
        self.codec: AudioCodec | None = None
        self._send_sem = asyncio.Semaphore(MAX_CONCURRENT_AUDIO_SENDS)
        self._in_silence_period = False

    async def setup(self, ctx: "PluginContext", cmd: "PluginCommands") -> None:
        await super().setup(ctx, cmd)

        if os.getenv("XIAOZHI_DISABLE_AUDIO") == "1":
            logger.warning(t("XIAOZHI_DISABLE_AUDIO=1，音频插件以禁用模式运行"))
            return

        try:
            self.codec = AudioCodec()
            await self.codec.initialize()
            self.codec.set_encoded_callback(self._on_encoded_audio)

            from src.core.event_bus import Events

            ctx.event_bus.on(Events.CONFIG_CHANGED, self._on_config_changed)
            ctx.event_bus.on(
                Events.AUDIO_DEVICES_REFRESH_REQUEST, self._on_devices_refresh_request
            )
            # codec is published again in start(): MusicPlayer subscribes to EventBus

        except Exception as e:
            logger.error(t('音频插件初始化失败: {value1}', value1=e), exc_info=True)
            self.codec = None
            self.mark_failed()
            raise

    async def start(self) -> None:
        await super().start()
        if self.codec and not self.failed:
            await self._publish_audio_codec(self.codec)

    async def _publish_audio_codec(self, codec) -> None:
        """Publish AudioCodec instance or None to subscribers (such as MusicPlayer)."""
        if not self._ctx or not self._ctx.event_bus:
            logger.warning(
                t("无法发布 AUDIO_CODEC_CHANGED：PluginContext / EventBus 未就绪")
            )
            return
        from src.core.event_bus import Events

        try:
            await self._ctx.event_bus.emit(Events.AUDIO_CODEC_CHANGED, codec)
        except Exception as e:
            logger.warning(t('发布 AUDIO_CODEC_CHANGED 失败: {value1}', value1=e), exc_info=True)

    async def _on_config_changed(self, data=None):
        """Reload the audio device (including PortAudio re-enumeration) when the configuration changes."""
        if self.codec:
            logger.info(t("AudioPlugin: 收到配置变更事件，重新加载音频设备"))
            await self.codec.reload_devices(reenumerate=True)

    async def _on_devices_refresh_request(self, data=None):
        """The setting page requests to refresh the device list: stop flow → re-enumerate → Open the stream again.

        payload in McpPlugin.setup, which can be asyncio.Future, and set_result(list_audio_devices result) after completion.
        """
        from src.utils.audio_utils import list_audio_devices, refresh_portaudio_devices

        future = data if isinstance(data, asyncio.Future) else None
        result = {"input": [], "output": []}
        try:
            if self.codec:
                # It is safe to stop the flow. _terminate PortAudio
                self.codec.stop_streams_for_enumeration()
                refresh_portaudio_devices(reinitialize=True)
                result = list_audio_devices(include_virtual=True)
                # reopens the stream according to the current configuration (name matching may point to a new index)
                ok = await self.codec.reload_devices(reenumerate=False)
                if not ok:
                    logger.error(t("AudioPlugin: 设备刷新后重新打开音频流失败"))
            else:
                # Still try to enumerate when there is no codec (disable audio) for display on the settings page
                refresh_portaudio_devices(reinitialize=True)
                result = list_audio_devices(include_virtual=True)
            logger.info(
                t('AudioPlugin: 设备刷新完成 in={value1} out={value3}', value1=len(result.get('input', [])), value3=len(result.get('output', [])))
            )
        except Exception as e:
            logger.error(t('AudioPlugin: 设备刷新失败: {value1}', value1=e), exc_info=True)
        finally:
            if future is not None and not future.done():
                future.set_result(result)

    async def on_device_state_changed(self, state):
        """
        Process when the device status changes.
        """
        if not self.codec:
            return

        from src.constants.constants import DeviceState

        if state == DeviceState.LISTENING:
            self._in_silence_period = True
            try:
                await asyncio.sleep(0.2)
            finally:
                self._in_silence_period = False

    async def on_incoming_json(self, message) -> None:
        """
        Handle TTS events.
        """
        if not isinstance(message, dict):
            return

        try:
            if message.get("type") == "tts":
                state = message.get("state")
                if state == "start":
                    if self._music_parallel_enabled():
                        logger.debug(t("TTS 开始（并行模式）：音乐继续播放，混音闪避"))
                    else:
                        await self._pause_music_for_tts()
                elif state == "stop":
                    # Parallel mode is also restored: "The song started during TTS is set to tts" Pause"
                    await self._resume_music_after_tts()
        except Exception as e:
            logger.error(t('处理 TTS 事件失败: {value1}', value1=e), exc_info=True)

    def _music_parallel_enabled(self) -> bool:
        """Parallel playback determination: AEC When the engine is in place and the configuration allows, TTS does not pause music.

        Automatically falls back to the pause strategy when the engine is bypassed (library missing/continuous failure self-ban),
        Avoid naked parallel pollution identification without echo cancellation.
        """
        try:
            config = self._ctx.get_config()
            if not bool(config.get_config("AEC_OPTIONS.MUSIC_PARALLEL", True)):
                return False
            return bool(self.codec and self.codec.aec_active)
        except Exception:
            return False

    async def on_incoming_audio(self, data: bytes) -> None:
        """
        Receive and play audio data.
        """
        if self.codec:
            try:
                await self.codec.write_audio(data)
            except Exception as e:
                logger.debug(t('写入音频数据失败: {value1}', value1=e))

    async def _pause_music_for_tts(self):
        """TTS Pauses music at the beginning (TTS/music is mixed in queues without losing frames; the music margin fades out naturally)."""
        try:
            from src.core.event_bus import Events
            from src.mcp.tools.music.events import MusicControlRequest

            logger.info(t("TTS 开始，发送音乐暂停请求"))
            await self._ctx.event_bus.emit(
                Events.MUSIC_PAUSE_REQUEST, MusicControlRequest(source="tts")
            )
        except Exception as e:
            logger.warning(t('发送音乐暂停请求失败: {value1}', value1=e), exc_info=True)

    async def _resume_music_after_tts(self):
        """TTS Resume the music after the end (in parallel mode, there is only a bottom line, most of the time there is no actual pause)."""
        try:
            from src.core.event_bus import Events
            from src.mcp.tools.music.events import MusicControlRequest

            log = logger.debug if self._music_parallel_enabled() else logger.info
            log(t("TTS 播放完成，发送音乐恢复请求"))
            await self._ctx.event_bus.emit(
                Events.MUSIC_RESUME_REQUEST, MusicControlRequest(source="tts")
            )
        except Exception as e:
            logger.error(t('发送音乐恢复请求失败: {value1}', value1=e), exc_info=True)

    def register_resources(self, pool) -> None:
        codec = self.codec
        if codec:

            async def _cleanup():
                """Audio codec complete cleanup: first notify the subscriber to clear the codec, and then close."""
                import gc

                try:
                    # Music will stop on its own when receiving None; complete detach is handled by mcp/container
                    await self._publish_audio_codec(None)
                except Exception as e:
                    logger.debug(t('发布 codec 清除失败: {value1}', value1=e), exc_info=True)
                gc.collect()
                await codec.close()

            pool.register("audio.codec", _cleanup)

    def _on_encoded_audio(self, encoded_data: bytes) -> None:
        """
        Audio encoding callback (called from the audio thread).
        """
        try:
            if not self._cmd:
                return
            self._cmd.schedule_command_nowait(self._send_audio_async, encoded_data)
        except Exception as e:
            logger.error(t('调度音频发送失败: {value1}', value1=e), exc_info=True)

    async def _send_audio_async(self, encoded_data: bytes) -> None:
        """
        sends audio data asynchronously.
        """
        async with self._send_sem:
            try:
                if not self._ctx.is_audio_channel_opened():
                    return
                if self._should_send_microphone_audio():
                    await self._cmd.send_audio(encoded_data)
            except Exception as e:
                logger.error(t('发送音频数据失败: {value1}', value1=e), exc_info=True)

    def _should_send_microphone_audio(self) -> bool:
        """
        Determine whether microphone audio should be sent.
        """
        try:
            if self._in_silence_period:
                return False
            return self._ctx.should_capture_audio()
        except Exception as e:
            logger.warning(
                t('判断是否发送麦克风音频失败，默认不发送: {value1}', value1=e), exc_info=True
            )
            return False
