from collections import deque

import numpy as np
import soxr

from src.i18n import t
from src.logging import get_logger
from src.utils.audio_utils import downmix_to_mono, upmix_mono_to_channels

logger = get_logger()


class AudioConverter:
    """Audio format converter

    is responsible for sample rate conversion and channel conversion, and internally maintains the buffer to make up the target frame size.
    """

    def __init__(self):
        """Initialize the converter"""
        self.input_resampler = None
        self.output_resampler = None
        self._input_buffer = deque()
        self._output_buffer = deque()
        self.needs_input_downmix = False
        self.needs_output_upmix = False
        self.input_channels = 1
        self.output_channels = 1

    def setup_input_converter(
        self, from_rate: int, to_rate: int, from_channels: int, to_channels: int = 1
    ):
        """Configure the input conversion chain (device → protocol)

        Args:
            from_rate: Device sampling rate
            to_rate: Protocol sampling rate (usually 16kHz)
            from_channels: Number of device channels
            to_channels: Number of protocol channels (usually 1)
        """
        self.input_channels = from_channels
        self.needs_input_downmix = from_channels > to_channels

        if self.needs_input_downmix:
            logger.info(t('输入声道下混: {value1}ch → {value3}ch', value1=from_channels, value3=to_channels))

        if from_rate != to_rate:
            self.input_resampler = soxr.ResampleStream(
                from_rate,
                to_rate,
                num_channels=to_channels,  # The number of channels after downmixing
                dtype="float32",
                quality="QQ",  # Fast quality (suitable for real-time processing)
            )
            logger.info(t('输入重采样: {value1}Hz → {value3}Hz', value1=from_rate, value3=to_rate))

    def setup_output_converter(
        self, from_rate: int, to_rate: int, from_channels: int = 1, to_channels: int = 2
    ):
        """Configure the output conversion chain (protocol → device)

        Args:
            from_rate: Protocol sampling rate (usually 24kHz)
            to_rate: device sampling rate
            from_channels: Number of protocol channels (usually 1)
            to_channels: Number of device channels
        """
        self.output_channels = to_channels
        self.needs_output_upmix = to_channels > from_channels

        if from_rate != to_rate:
            self.output_resampler = soxr.ResampleStream(
                from_rate,
                to_rate,
                num_channels=from_channels,  # The number of channels before upmixing
                dtype="float32",
                quality="QQ",
            )
            logger.info(t('输出重采样: {value1}Hz → {value3}Hz', value1=from_rate, value3=to_rate))

        if self.needs_output_upmix:
            logger.info(t('输出声道上混: {value1}ch → {value3}ch', value1=from_channels, value3=to_channels))

    def convert_input(
        self, audio: np.ndarray, target_size: int
    ) -> np.ndarray | None:
        """Input conversion: multichannel/high sample rate → mono/16kHz

        Args:
            audio: float32 Audio data
            target_size: Target number of samples

        Returns:
            Converted float32 data, or None (insufficient data)
        """
        # 1. Downmix (using audio_utils)
        if self.needs_input_downmix:
            audio = downmix_to_mono(audio, keepdims=False)
        else:
            audio = audio.flatten()

        # 2. Resampling
        if self.input_resampler:
            resampled = self.input_resampler.resample_chunk(audio, last=False)
            if len(resampled) > 0:
                self._input_buffer.extend(resampled)

            # accumulates to the target size
            if len(self._input_buffer) < target_size:
                return None

            # Get out one frame
            frame_data = [self._input_buffer.popleft() for _ in range(target_size)]
            return np.array(frame_data, dtype=np.float32)

        return audio

    def convert_output(
        self, audio: np.ndarray, target_frames: int
    ) -> np.ndarray | None:
        """Output conversion: mono/24kHz → multichannel/high sample rate

        Args:
            audio: float32 Audio data
            target_frames: Target number of frames

        Returns:
            Converted float32 data
        """
        # 1. Resampling
        if self.output_resampler:
            resampled = self.output_resampler.resample_chunk(audio, last=False)
            if len(resampled) > 0:
                self._output_buffer.extend(resampled)

            # Get out the target frame number
            if len(self._output_buffer) < target_frames:
                return None

            frame_data = [self._output_buffer.popleft() for _ in range(target_frames)]
            audio = np.array(frame_data, dtype=np.float32)

        # 2. Upmixing (using audio_utils)
        if self.needs_output_upmix:
            audio = upmix_mono_to_channels(audio, self.output_channels)
        else:
            audio = audio.reshape(-1, 1)

        return audio

    def drain_output_buffer(self, target_frames: int) -> np.ndarray | None:
        """Drain remaining data in the resampler buffer (with mixing).

        is used to avoid entire frame silence when the queue is exhausted but the buffer is short of a few samples.
        """
        available = min(len(self._output_buffer), target_frames)
        if available == 0:
            return None

        frame_data = [self._output_buffer.popleft() for _ in range(available)]
        audio = np.array(frame_data, dtype=np.float32)

        if self.needs_output_upmix:
            audio = upmix_mono_to_channels(audio, self.output_channels)
        else:
            audio = audio.reshape(-1, 1)

        return audio

    def clear_output_buffer(self):
        """Clear the output buffer only (for TTS Anti-echo when stopped, does not affect the input pipeline)"""
        self._output_buffer.clear()

    def clear_buffers(self):
        """Clear the buffer"""
        self._input_buffer.clear()
        self._output_buffer.clear()
        logger.debug(t("音频转换器缓冲区已清空"))

    def close(self):
        """Release soxr resampler, prevent nanobind C Object leak."""
        self.clear_buffers()
        self.input_resampler = None
        self.output_resampler = None
