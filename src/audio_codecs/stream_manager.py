"""Audio stream manager.

Responsibilities: sounddevice stream creation, life cycle management
"""
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from src.i18n import t
from src.logging import get_logger
from src.utils.audio_device import DeviceConfig
from src.utils.audio_utils import ALSAErrorSuppressor

logger = get_logger()


class AudioStreamManager:
    """Audio stream manager (sounddevice package)

    is responsible for creating and managing the life cycle of audio input/output streams.
    """

    def __init__(self, device_config: DeviceConfig):
        """Initializes the stream manager

        Args:
            device_config: Device configuration
        """
        self.device_config = device_config
        self.input_stream = None
        self.output_stream = None
        self._stopped = False

    def create_streams(
        self, input_callback: Callable, output_callback: Callable
    ) -> None:
        """Creates a duplex audio stream

        Args:
            input_callback: Input callback function
            output_callback: Output callback function

        Raises:
            Exception: Failed to create stream
        """
        # to allow stop() create (hot reload path)
        self._stopped = False
        try:
            # Suppressing ALSA on Linux using ALSAErrorSuppressor Warning
            with ALSAErrorSuppressor():
                # Input stream
                self.input_stream = sd.InputStream(
                    device=self.device_config.input_device_id,
                    samplerate=self.device_config.input_sample_rate,
                    channels=self.device_config.input_channels,
                    dtype=np.float32,  # Unified float32
                    blocksize=self.device_config.input_frame_size,
                    callback=input_callback,
                    latency="low",
                )

                # Output stream
                self.output_stream = sd.OutputStream(
                    device=self.device_config.output_device_id,
                    samplerate=self.device_config.output_sample_rate,
                    channels=self.device_config.output_channels,
                    dtype=np.float32,  # Unified float32
                    blocksize=self.device_config.output_frame_size,
                    callback=output_callback,
                    latency="low",
                )

            logger.info(
                t('音频流已创建 | 输入: {value1}Hz {value3}ch | 输出: {value5}Hz {value7}ch', value1=self.device_config.input_sample_rate, value3=self.device_config.input_channels, value5=self.device_config.output_sample_rate, value7=self.device_config.output_channels)
            )
        except Exception as e:
            logger.error(t('创建音频流失败: {value1}', value1=e), exc_info=True)
            raise

    def start(self) -> None:
        """Starts the audio stream

        Raises:
            Exception: Failed to start
        """
        try:
            if self.input_stream:
                self.input_stream.start()
            if self.output_stream:
                self.output_stream.start()
            logger.info(t("音频流已启动"))
        except Exception as e:
            logger.error(t('启动音频流失败: {value1}', value1=e), exc_info=True)
            raise

    def stop(self) -> None:
        """stops the audio stream, idempotent and can be repeated after calling"""
        if getattr(self, "_stopped", False):
            return
        self._stopped = True

        try:
            if self.input_stream:
                self.input_stream.stop()
                self.input_stream.close()
                self.input_stream = None

            if self.output_stream:
                self.output_stream.stop()
                self.output_stream.close()
                self.output_stream = None

            logger.info(t("音频流已停止"))
        except Exception as e:
            logger.error(t('停止音频流失败: {value1}', value1=e), exc_info=True)

    def is_active(self) -> bool:
        """Whether an unclosed input/output stream is still held."""
        return bool(self.input_stream or self.output_stream)

    def reinitialize_stream(
        self,
        is_input: bool,
        input_callback: Callable = None,
        output_callback: Callable = None,
    ) -> bool:
        """Rebuild the audio stream (supports hot swapping)

        Args:
            is_input: True=input stream, False=output stream
            input_callback: Input callback function (required only when rebuilding the input stream)
            output_callback: Output callback function (required only when rebuilding the output stream)

        Returns:
            bool: whether it is successful
        """
        try:
            # Suppressing ALSA on Linux using ALSAErrorSuppressor Warning
            with ALSAErrorSuppressor():
                if is_input and input_callback:
                    # Reconstruct input stream
                    if self.input_stream:
                        self.input_stream.stop()
                        self.input_stream.close()

                    self.input_stream = sd.InputStream(
                        device=self.device_config.input_device_id,
                        samplerate=self.device_config.input_sample_rate,
                        channels=self.device_config.input_channels,
                        dtype=np.float32,
                        blocksize=self.device_config.input_frame_size,
                        callback=input_callback,
                        latency="low",
                    )
                    self.input_stream.start()
                    logger.info(t("输入流重新初始化成功"))
                    return True

                elif not is_input and output_callback:
                    # Reconstruct output stream
                    if self.output_stream:
                        self.output_stream.stop()
                        self.output_stream.close()

                    self.output_stream = sd.OutputStream(
                        device=self.device_config.output_device_id,
                        samplerate=self.device_config.output_sample_rate,
                        channels=self.device_config.output_channels,
                        dtype=np.float32,
                        blocksize=self.device_config.output_frame_size,
                        callback=output_callback,
                        latency="low",
                    )
                    self.output_stream.start()
                    logger.info(t("输出流重新初始化成功"))
                    return True

            return False

        except Exception as e:
            stream_type = t("输入") if is_input else t("输出")
            logger.error(t('{value0}流重建失败: {value2}', value0=stream_type, value2=e), exc_info=True)
            return False
