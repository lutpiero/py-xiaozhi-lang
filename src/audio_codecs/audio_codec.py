import asyncio
import threading
import time
from collections.abc import Callable
from typing import Protocol

import numpy as np

from src.audio_codecs.audio_buffer import PcmFifo
from src.audio_codecs.audio_converter import AudioConverter
from src.audio_codecs.opus_codec import OpusCodec, parse_opus_toc
from src.audio_codecs.stream_manager import AudioStreamManager
from src.constants.constants import AudioConfig
from src.i18n import t
from src.logging import get_logger
from src.utils.audio_device import AudioDeviceManager, DeviceConfig
from src.utils.config_manager import get_config

logger = get_logger()

# TTS The mixing gain (dodge) of the music when it exists, and its retention time (number of 20ms blocks)
_MUSIC_DUCK_GAIN = 0.35
_DUCK_HOLD_CHUNKS = 10
# Music writing end water level back pressure target (seconds): The smaller the pause/interruption, the more follow-up, the larger the stronger the anti-jitter
_MUSIC_BACKLOG_TARGET_S = 0.30
# TTS / music FIFO capacity (seconds), the oldest
_TTS_FIFO_MAX_S = 10.0
_MUSIC_FIFO_MAX_S = 2.0


class AudioListener(Protocol):
    """Audio listener protocol"""

    def on_audio_data(self, audio_data: np.ndarray) -> None:
        """Receive audio data

        Args:
            audio_data: float32 audio data
        """
        ...


class AudioCodec:
    """Audio codec - coordinator mode

    Combines various components to coordinate data flow

    Data stream:
    - Input: Device(float32) → Downmix Resample(float32) → Opus encoding(float32→bytes) → network
    - Output: network → Opus decoding(bytes→float32) → resampling upmix(float32) → device(float32)
    """

    def __init__(self):
        """Initialize audio codec"""
        # Refresh protocol configuration (support Settings UI modification to take effect)
        AudioConfig.reload()

        # Component (dependency injection)
        self.device_manager = AudioDeviceManager(get_config())
        self.opus_codec = OpusCodec(
            input_sample_rate=AudioConfig.INPUT_SAMPLE_RATE,
            output_sample_rate=AudioConfig.OUTPUT_SAMPLE_RATE,
            channels=AudioConfig.CHANNELS,
        )
        self.converter = AudioConverter()
        self.stream_manager = None

        # TTS is discarded when the limit is exceeded and music diversion: each FIFO, mixing in the output callback (no queue blocking)
        self._tts_fifo = PcmFifo(
            int(AudioConfig.OUTPUT_SAMPLE_RATE * _TTS_FIFO_MAX_S)
        )
        self._music_fifo = PcmFifo(
            int(AudioConfig.OUTPUT_SAMPLE_RATE * _MUSIC_FIFO_MAX_S)
        )
        self._mix_chunk = int(AudioConfig.OUTPUT_SAMPLE_RATE * 0.02)  # 20ms
        self._duck_hold = 0

        # Listener (thread safe)
        self._encoded_callback: Callable | None = None
        self._audio_listeners: list[AudioListener] = []
        self._listeners_lock = threading.Lock()

        # device configuration (populated after initialization)
        self.device_config: DeviceConfig | None = None

        # AEC (Self far: the final PCM of the playback callback is used as a reference), created according to the configuration when initializing
        self._aec = None

        # Status flag
        self._is_closing = False
        self._closed = False
        self._server_opus_logged = False
        self._last_output_status_log = 0.0

    async def initialize(self):
        """Initialize all components

        Process:
        1. Load/detect device
        2. Refresh the protocol configuration and initialize Opus
        3. Configure format conversion pipeline
        4. Create audio stream
        5. Start audio stream
        """
        try:
            # 1. Load/detect device
            self.device_config = self.device_manager.load_or_detect_devices()

            # 2. Refresh the protocol configuration and initialize Opus
            AudioConfig.reload()
            self.opus_codec.close()
            self.opus_codec = OpusCodec(
                input_sample_rate=AudioConfig.INPUT_SAMPLE_RATE,
                output_sample_rate=AudioConfig.OUTPUT_SAMPLE_RATE,
                channels=AudioConfig.CHANNELS,
            )
            self.opus_codec.initialize()

            # 3. Configure format conversion pipeline
            self._configure_pipeline()

            # 4. Create AEC as configured (Self far), automatic bypass on failure
            self._setup_aec()

            # 5. Create audio stream
            self.stream_manager = AudioStreamManager(self.device_config)
            self.stream_manager.create_streams(
                input_callback=self._input_callback,
                output_callback=self._output_callback,
            )

            # 6. Start the audio stream
            self.stream_manager.start()

            logger.info(t("AudioCodec 初始化完成"))

        except Exception as e:
            logger.error(t('初始化音频设备失败: {value1}', value1=e), exc_info=True)
            await self.close()
            raise

    def _input_callback(self, indata, frames, time_info, status):
        """Input callback: device → encoding → send

        Data stream: Multi-channel/high sample rate → Downmix → Resampling → Opus encoding → Network

        Args:
            indata: float32 audio data, shape (frames, channels)
            frames: frame number
            time_info: time information
            status: status flag
        """
        if status and "overflow" not in str(status).lower():
            logger.warning(t('输入流状态: {value1}', value1=status))

        if self._is_closing:
            return

        try:
            # 1. Format conversion (downmix resampling)
            # retained indata The (frames, channels) shape allows downmix_to_mono to correctly downmix
            audio_converted = self.converter.convert_input(
                indata, AudioConfig.INPUT_FRAME_SIZE
            )
            if audio_converted is None:
                return  # Insufficient data, waiting for next frame

            # 1.5 AEC: far extracted with playback callback Refer to echo cancellation (returned unchanged during bypass)
            if self._aec is not None and self._aec.active:
                audio_converted = self._aec.process_near(audio_converted)

            # 2. Opus encoding (float32 input)
            if self._encoded_callback:
                try:
                    opus_data = self.opus_codec.encode(
                        audio_converted, AudioConfig.INPUT_FRAME_SIZE
                    )
                    self._encoded_callback(opus_data)
                except Exception as e:
                    logger.warning(t('编码失败: {value1}', value1=e), exc_info=True)

            # 3. Notify listener (thread safe)
            with self._listeners_lock:
                for listener in self._audio_listeners:
                    try:
                        listener.on_audio_data(audio_converted.copy())
                    except Exception as e:
                        logger.warning(t('监听器处理失败: {value1}', value1=e), exc_info=True)

        except Exception as e:
            logger.error(t('输入回调错误: {value1}', value1=e), exc_info=True)

    def _output_callback(self, outdata, frames, time_info, status):
        """Output callback: decode → convert → play

        Data stream: Queue → Resampling → Upmix → Device

        Loops to take chunks from the queue and feed them to convert_output until resampler
        The internal buffer has enough frames or the queue is exhausted. Solve the problem of non-divisible sampling rate
        (such as 16kHz→44100Hz) or the lagging problem when the server frame duration does not match.

        Args:
            outdata: float32 output buffer, shape (frames, channels)
            frames: frame number
            time_info: time information
            status: status flag
        """
        if status:
            # Current limiting: writing logs (file IO) within the callback itself will aggravate underload, 2 Maximum one per second
            now = time.monotonic()
            if now - self._last_output_status_log > 2.0:
                self._last_output_status_log = now
                logger.warning(t('输出流状态: {value1}', value1=status))

        try:
            audio_converted = None

            while audio_converted is None:
                audio_data = self._pull_mixed(self._mix_chunk)
                if audio_data is None:
                    break
                audio_converted = self.converter.convert_output(audio_data, frames)

            if audio_converted is None:
                audio_converted = self.converter.drain_output_buffer(frames)

            if audio_converted is None or len(audio_converted) < frames:
                outdata.fill(0.0)
                if audio_converted is not None and len(audio_converted) > 0:
                    outdata[: len(audio_converted)] = audio_converted
            else:
                outdata[:] = audio_converted[:frames]

            # AEC far: the final PCM actually written by the device (TTS music mixing, including silence to keep continuous)
            if self._aec is not None and self._aec.active:
                self._aec.feed_far(outdata)

        except Exception as e:
            logger.error(t('输出回调错误: {value1}', value1=e), exc_info=True)
            outdata.fill(0.0)

    def _configure_pipeline(self):
        """Configure the format conversion pipeline (device ↔ protocol).

        sets the input/output conversion chain according to the device's native parameters and protocol required parameters.
        Input: device (f32, device_rate, device_ch) → protocol (f32, 16kHz, 1ch)
        Output: protocol(f32, opus_out_rate, 1ch) → device(f32, device_rate, device_ch)
        """
        self.converter.setup_input_converter(
            from_rate=self.device_config.input_sample_rate,
            to_rate=AudioConfig.INPUT_SAMPLE_RATE,
            from_channels=self.device_config.input_channels,
            to_channels=1,
        )
        self.converter.setup_output_converter(
            from_rate=AudioConfig.OUTPUT_SAMPLE_RATE,
            to_rate=self.device_config.output_sample_rate,
            from_channels=1,
            to_channels=self.device_config.output_channels,
        )

        # The protocol output sampling rate may change with configuration hot reload, and the FIFO/mixing block will be rebuilt accordingly
        # (audio streaming has stopped at this time, no concurrent reading)
        self._tts_fifo = PcmFifo(
            int(AudioConfig.OUTPUT_SAMPLE_RATE * _TTS_FIFO_MAX_S)
        )
        self._music_fifo = PcmFifo(
            int(AudioConfig.OUTPUT_SAMPLE_RATE * _MUSIC_FIFO_MAX_S)
        )
        self._mix_chunk = int(AudioConfig.OUTPUT_SAMPLE_RATE * 0.02)
        self._duck_hold = 0

    def _pull_mixed(self, n: int) -> np.ndarray | None:
        """Output callback thread: n each from TTS/Music FIFO Sample and mix.

        Rules:
        - Both paths are empty → None (upper layer goes to silent/underrun path)
        - Music pressed _MUSIC_DUCK_GAIN ducks when TTS is present, and when TTS
          frame gaps to keep several blocks (to avoid dodge gain jitter)
        """
        tts = self._tts_fifo.pull(n)
        music = self._music_fifo.pull(n)

        if tts is None and music is None:
            return None

        if tts is not None:
            self._duck_hold = _DUCK_HOLD_CHUNKS
        elif self._duck_hold > 0:
            self._duck_hold -= 1

        if music is None:
            return tts
        if tts is None:
            if self._duck_hold > 0:
                music *= _MUSIC_DUCK_GAIN
            return music
        return np.clip(tts + music * _MUSIC_DUCK_GAIN, -1.0, 1.0)

    def _setup_aec(self):
        """press AEC_OPTIONS.ENABLED to create/rebuild the AEC engine (Self far).

        The far sampling rate may change after device hot reload and must be changed with device_config Rebuild;
        , which will not be thrown, and the engine itself will be bypassed (active=False).
        """
        if self._aec is not None:
            self._aec.close()
            self._aec = None

        try:
            config = get_config()
            if not bool(config.get_config("AEC_OPTIONS.ENABLED", False)):
                logger.info(t("AEC 未启用（AEC_OPTIONS.ENABLED=false）"))
                return

            from src.audio_processing.aec_engine import AecEngine

            frame_delay = config.get_config("AEC_OPTIONS.FRAME_DELAY", 3)
            self._aec = AecEngine(
                near_rate=AudioConfig.INPUT_SAMPLE_RATE,
                far_rate=self.device_config.output_sample_rate,
                # FRAME_DELAY takes the protocol frame as the unit, converts to milliseconds and then superimposes the basic output delay
                delay_ms=40 + int(frame_delay) * AudioConfig.FRAME_DURATION,
                enable_preprocess=bool(
                    config.get_config("AEC_OPTIONS.ENABLE_PREPROCESS", True)
                ),
            )
        except Exception as e:
            logger.warning(t('创建 AEC 引擎失败，已旁路: {value1}', value1=e), exc_info=True)
            self._aec = None

    # === External interface (maintain compatibility) ===

    @property
    def aec_active(self) -> bool:
        """AEC engine is in place and working (music parallel strategy, etc. rely on this judgment)."""
        aec = self._aec
        return bool(aec is not None and aec.active)

    def set_encoded_callback(self, callback: Callable[[bytes], None]):
        """Set encoding callback

        Args:
            callback: callback function, receiving Opus Encoded data
        """
        self._encoded_callback = callback
        if callback:
            logger.info(t("已设置编码音频回调"))
        else:
            logger.info(t("已清除编码音频回调"))

    def add_audio_listener(self, listener: AudioListener):
        """Add audio listener (thread-safe)

        Args:
            listener: implements AudioListener The listener object of the protocol
        """
        with self._listeners_lock:
            if listener not in self._audio_listeners:
                self._audio_listeners.append(listener)
                logger.info(t('已添加音频监听器: {value1}', value1=listener.__class__.__name__))

    def remove_audio_listener(self, listener: AudioListener):
        """Remove audio listener (thread safe)

        Args:
            listener: The listener object to be removed
        """
        with self._listeners_lock:
            if listener in self._audio_listeners:
                self._audio_listeners.remove(listener)
                logger.info(t('已移除音频监听器: {value1}', value1=listener.__class__.__name__))

    async def write_audio(self, opus_data: bytes):
        """Decode and play audio (Opus → Speaker)

        Automatically detects frame duration from Opus TOC bytes without relying on client configuration.

        Args:
            opus_data: Opus encoding data
        """
        try:
            toc_info = parse_opus_toc(opus_data)
            if toc_info is None:
                return

            if not self._server_opus_logged:
                self._server_opus_logged = True
                logger.info(
                    t('服务端 Opus 参数: {value1} {value3} | 帧时长 {value5}ms ({value7}ms×{value9})', value1=toc_info['mode'], value3=toc_info['bandwidth_hz'], value5=toc_info['duration_ms'], value7=toc_info['frame_ms'], value9=toc_info['num_frames'])
                )

            frame_size = int(
                AudioConfig.OUTPUT_SAMPLE_RATE * toc_info["duration_ms"] / 1000
            )
            audio_float32 = self.opus_codec.decode(opus_data, frame_size)

            self._tts_fifo.push(audio_float32)

        except Exception as e:
            logger.warning(t('音频写入失败: {value1}', value1=e), exc_info=True)

    async def write_pcm_direct(self, pcm_float32: np.ndarray):
        """written to music PCM (float32, used by MusicPlayer), with water level back pressure.

        After writing, if the music buffer exceeds the target water level, it will wait for playback consumption - this is the creation failure of the music link
        is the only source of beats (the decoder clock will be inaccurate after pause and cannot be used as a basis).
        The upper limit of back pressure is 2 seconds to exit, and the FIFO capacity is guaranteed not to expand infinitely.
        """
        self._music_fifo.push(pcm_float32)

        target = int(AudioConfig.OUTPUT_SAMPLE_RATE * _MUSIC_BACKLOG_TARGET_S)
        for _ in range(100):
            if self._is_closing or self._music_fifo.size <= target:
                break
            await asyncio.sleep(0.02)

    async def clear_audio_queue(self):
        """Clear the TTS play queue (used when interrupting/aborting; the music queue is not affected)."""
        self._server_opus_logged = False
        self.converter.clear_output_buffer()
        count = self._tts_fifo.clear()
        if count > 0:
            logger.info(t('清空 TTS 队列，丢弃 {value1} 样本', value1=count))

    async def clear_music_queue(self):
        """Clear the music playback queue (used when stopping/jumping; TTS The queue is not affected)."""
        count = self._music_fifo.clear()
        if count > 0:
            logger.info(t('清空音乐队列，丢弃 {value1} 样本', value1=count))

    async def reinitialize_stream(self, is_input: bool = True):
        """Rebuild the audio stream (supports hot swapping)

        Args:
            is_input: True=input stream, False=output stream

        Returns:
            bool: whether it is successful
        """
        if not self.stream_manager:
            return False

        if is_input:
            return self.stream_manager.reinitialize_stream(
                is_input=True, input_callback=self._input_callback
            )
        else:
            return self.stream_manager.reinitialize_stream(
                is_input=False, output_callback=self._output_callback
            )

    def stop_streams_for_enumeration(self) -> None:
        """Stop the sounddevice stream occupied by this codec and call it before hot plug enumeration.

        must be called again ``reload_devices()`` or ``create_streams`` by yourself, otherwise there will be no collection/playback.
        """
        if self.stream_manager:
            self.stream_manager.stop()
            logger.info(t("AudioCodec: 已停止音频流（供设备枚举）"))

    async def reload_devices(self, *, reenumerate: bool = True):
        """Hot reload audio device configuration

        Process:
        1. Stop current audio stream
        2. (Optional) Reinitialize PortAudio and re-enumerate (favorable for subsequent Bluetooth connections)
        3. Reload device configuration protocol configuration
        4. Rebuild format converter Opus codec
        5. Recreate and start the audio stream

        Args:
            reenumerate: whether to force refresh the PortAudio device table after stopping the flow

        Returns:
            bool: whether it is successful
        """
        logger.info(t("AudioCodec: 开始热重载音频设备..."))

        try:
            # 1. Stop the current stream (must be before PortAudio reinit)
            if self.stream_manager:
                self.stream_manager.stop()
                logger.debug(t("AudioCodec: 已停止当前音频流"))

            # 2. Hot plug: Rebuild the PortAudio context and then match by name
            if reenumerate:
                from src.utils.audio_utils import refresh_portaudio_devices

                refresh_portaudio_devices(reinitialize=True)

            # 3. Reload device configuration
            self.device_manager.config.reload_config()
            self.device_config = self.device_manager.load_or_detect_devices()
            logger.info(
                t('AudioCodec: 新设备配置 - 输入ID: {value1}, 输出ID: {value3}', value1=self.device_config.input_device_id, value3=self.device_config.output_device_id)
            )

            # 4. Refresh protocol configuration and rebuild Opus codec
            AudioConfig.reload()
            self.opus_codec.close()
            self.opus_codec = OpusCodec(
                input_sample_rate=AudioConfig.INPUT_SAMPLE_RATE,
                output_sample_rate=AudioConfig.OUTPUT_SAMPLE_RATE,
                channels=AudioConfig.CHANNELS,
            )
            self.opus_codec.initialize()

            # 5. Rebuild the format converter
            self.converter.clear_buffers()
            self._configure_pipeline()

            # 5.5 Rebuild AEC (far sample rate follows new output device, filter status cleared)
            self._setup_aec()

            # 6. Recreate the audio stream
            self.stream_manager = AudioStreamManager(self.device_config)
            self.stream_manager.create_streams(
                input_callback=self._input_callback,
                output_callback=self._output_callback,
            )

            # 7. Start the audio stream
            self.stream_manager.start()

            logger.info(t("AudioCodec: 音频设备热重载完成"))
            return True

        except Exception as e:
            logger.error(t('AudioCodec: 热重载音频设备失败: {value1}', value1=e), exc_info=True)
            return False

    async def close(self):
        """Turn off the audio codec"""
        self._is_closing = True

        try:
            # 1. Stop audio stream
            if self.stream_manager:
                self.stream_manager.stop()

            # 2. Clear the queue
            await self.clear_audio_queue()
            await self.clear_music_queue()

            # 2.5 Release AEC (must be after the stream is stopped)
            if self._aec is not None:
                self._aec.close()
                self._aec = None

            # 3. Release converter (with soxr resampler)
            self.converter.close()

            # 4. Release Opus
            self.opus_codec.close()

            # 5. Clean up listener
            with self._listeners_lock:
                self._audio_listeners.clear()

            logger.info(t("AudioCodec 已关闭"))
            self._closed = True

        except Exception as e:
            logger.error(t('关闭音频编解码器失败: {value1}', value1=e), exc_info=True)
        finally:
            self._is_closing = False

    def __del__(self):
        """destructor - performs synchronous cleanup"""
        # If it has been closed correctly or is being closed, skip
        if getattr(self, "_closed", False) or getattr(self, "_is_closing", False):
            return

        logger.warning(t("AudioCodec 未正确关闭，执行紧急清理（建议使用 async close()）"))

        try:
            # 1. Stop audio stream (synchronous)
            if self.stream_manager:
                self.stream_manager.stop()

            # 2. Clear the queue (synchronous version)
            count = self._tts_fifo.clear() + self._music_fifo.clear()
            if count > 0:
                logger.debug(t('析构函数清空了 {value1} 样本音频', value1=count))

            # 3. Release converter (synchronous, with soxr resampler)
            if self.converter:
                self.converter.close()

            # 4. Release Opus (synchronous)
            if self.opus_codec:
                self.opus_codec.close()

            # 5. Clean up listener (synchronized)
            try:
                with self._listeners_lock:
                    self._audio_listeners.clear()
            except Exception as e:
                logger.warning(
                    t('清理音频监听器失败（锁可能已损坏）: {value1}', value1=e), exc_info=True
                )

            logger.debug(t("AudioCodec 析构清理完成"))

        except Exception as e:
            logger.error(t('析构函数清理失败: {value1}', value1=e), exc_info=True)
