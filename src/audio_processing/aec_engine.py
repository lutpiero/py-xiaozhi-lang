"""AEC engine: real-time encapsulation of libs/webrtc_apm (P0 Self far).

Data stream:
- near: acquisition frame (16kHz mono float32) → ProcessStream → Upstream after echo elimination
- far: the final PCM actually written by the device (TTS music mix, device sample rate/channel)
       → Downmix → Resample to 16kHz → ProcessReverseStream

Thread model (key):
- The output callback thread only does "downmix copy enqueue" (feed_far, microsecond level, no lock);
  Resampling and APM calls are all in the collection thread (the far queue is drained at the beginning of process_near).
  does not share locks between the two real-time callbacks, preventing the output callback from being overwhelmed when the input side lock is stuck by the GIL.

Design constraints:
- Library loading/processing failures will be bypassed (active=False), and the main link of the call will not be affected.
- WebRTC APM is processed in 10ms frames; protocol frames 20/40/60ms are all multiples of it
"""
import ctypes
import sys
import threading
from collections import deque

import numpy as np

from src.i18n import t
from src.logging import get_logger

logger = get_logger()

# Automatically bypass after the number of consecutive processing failures to avoid bad libraries from dragging down the audio callback
_MAX_CONSECUTIVE_FAILURES = 5
# far The upper limit of the pending queue (number of output callback blocks, approx. 20ms/block → 0.5s);
# Prevent accumulation when the collection thread stops, and discard the oldest if it exceeds the limit
_FAR_PENDING_MAX_BLOCKS = 25


def _import_webrtc_apm():
    """Import libs.webrtc_apm, source code running and packaging forms have their own paths."""
    try:
        from libs import webrtc_apm

        return webrtc_apm
    except ImportError:
        from src.utils.resource_finder import get_app_root

        root = str(get_app_root())
        if root not in sys.path:
            sys.path.insert(0, root)
        from libs import webrtc_apm

        return webrtc_apm


class AecEngine:
    """WebRTC APM packaging: AEC optional NS/Qualcomm, near/far dual stream."""

    def __init__(
        self,
        near_rate: int = 16000,
        far_rate: int = 48000,
        delay_ms: int = 60,
        enable_preprocess: bool = True,
    ):
        """initializes and loads APM; on failure, active=False (bypass).

        Args:
            near_rate: acquisition protocol sampling rate (16kHz)
            far_rate: device output sampling rate (far focuses on sampling source)
            delay_ms: Estimated delay from playback to acquisition
            enable_preprocess: Whether to enable Qualcomm at the same time Noise suppression
        """
        self._near_rate = int(near_rate)
        self._far_rate = int(far_rate)
        self._delay_ms = int(delay_ms)
        self._frame = self._near_rate // 100  # 10ms
        self._lock = threading.Lock()
        self._active = False
        self._closed = False
        self._fail_count = 0
        self._near_misaligned_logged = False

        self._apm = None
        self._stream_cfg = None
        # far Two-level buffering: pending is written by the output callback (copy only),
        # buffer 16k sample margin after resampling for acquisition thread
        self._far_pending: deque = deque()
        self._far_buffer = np.empty(0, dtype=np.float32)
        self._far_resampler = None
        self._far_dropped = 0

        # Multiplexed ctypes frame buffer (10ms int16)
        self._near_in = (ctypes.c_short * self._frame)()
        self._near_out = (ctypes.c_short * self._frame)()
        self._far_in = (ctypes.c_short * self._frame)()
        self._far_out = (ctypes.c_short * self._frame)()

        try:
            self._init_apm(enable_preprocess)
            if self._far_rate != self._near_rate:
                import soxr

                self._far_resampler = soxr.ResampleStream(
                    self._far_rate,
                    self._near_rate,
                    num_channels=1,
                    dtype="float32",
                    quality="QQ",
                )
            self._active = True
            logger.info(
                t('AEC 引擎已启用 | near {value1}Hz, far {value3}Hz→{value5}Hz, delay {value7}ms, preprocess={value9}', value1=self._near_rate, value3=self._far_rate, value5=self._near_rate, value7=self._delay_ms, value9=enable_preprocess)
            )
        except Exception as e:
            logger.warning(t('AEC 引擎初始化失败，已旁路: {value1}', value1=e))
            self._release()

    def _init_apm(self, enable_preprocess: bool) -> None:
        """loads dynamic libraries, application configurations, and creates stream configurations."""
        apm_mod = _import_webrtc_apm()

        self._apm = apm_mod.WebRTCAudioProcessing()

        config = apm_mod.create_default_config()
        config.echo.enabled = True
        config.echo.mobile_mode = False
        if enable_preprocess:
            config.high_pass.enabled = True
            config.noise_suppress.enabled = True
            config.noise_suppress.noise_level = apm_mod.NoiseSuppressionLevel.MODERATE

        ret = self._apm.apply_config(config)
        if ret != 0:
            raise RuntimeError(t('apply_config 返回 {value1}', value1=ret))

        # near/far are both 16kHz mono, sharing a stream configuration
        self._stream_cfg = self._apm.create_stream_config(self._near_rate, 1)
        self._apm.set_stream_delay_ms(self._delay_ms)

    @property
    def active(self) -> bool:
        return self._active

    def process_near(self, block: np.ndarray) -> np.ndarray:
        """processes the acquisition frame (16kHz mono float32) and returns the same-length data after echo cancellation.

        Any failure returns the original data; continuous failures are automatically bypassed.
        """
        if not self._active:
            return block

        n = block.shape[0]
        if n % self._frame != 0:
            if not self._near_misaligned_logged:
                self._near_misaligned_logged = True
                logger.warning(t('采集帧长 {value1} 非 10ms 整数倍，AEC 旁路该路径', value1=n))
            return block

        try:
            i16 = self._float_to_i16(block)
            out = np.empty(n, dtype=np.float32)

            with self._lock:
                if not self._active:
                    return block
                # far precedes near: Empty the reference data saved by the output callback, maintain the cause and effect
                self._drain_far_locked()
                self._apm.set_stream_delay_ms(self._delay_ms)
                for off in range(0, n, self._frame):
                    ctypes.memmove(
                        self._near_in,
                        i16[off : off + self._frame].ctypes.data,
                        self._frame * 2,
                    )
                    ret = self._apm.process_stream(
                        self._near_in, self._stream_cfg, self._stream_cfg, self._near_out
                    )
                    if ret != 0:
                        raise RuntimeError(t('process_stream 返回 {value1}', value1=ret))
                    out[off : off + self._frame] = (
                        np.frombuffer(self._near_out, dtype=np.int16).astype(np.float32)
                        / 32768.0
                    )

            self._fail_count = 0
            return out
        except Exception as e:
            self._on_failure("near", e)
            return block

    def feed_far(self, outdata: np.ndarray) -> None:
        """Output callback thread call: only downmix copy and enqueue, no resampling/APM (microsecond return).

        frames containing silence should also be fed to keep the far stream continuous; the heavy work is completed by the collection thread process_near.
        """
        if not self._active:
            return

        try:
            if outdata.ndim > 1 and outdata.shape[1] > 1:
                mono = outdata.mean(axis=1, dtype=np.float32)
            else:
                # PortAudio reuses outdata memory and must be copied
                mono = np.array(outdata, dtype=np.float32).ravel()

            self._far_pending.append(mono)
            # deque operation in GIL Drop atoms; discard the oldest ones if they exceed the limit (to prevent accumulation when the collection thread stops)
            while len(self._far_pending) > _FAR_PENDING_MAX_BLOCKS:
                self._far_pending.popleft()
                self._far_dropped += 1
        except Exception:
            pass  # The output path will never be discarded

    def _drain_far_locked(self) -> None:
        """Collection thread (lock already held): resample the far queue and feed it ProcessReverseStream."""
        while self._far_pending:
            mono = self._far_pending.popleft()
            if self._far_resampler is not None:
                mono = self._far_resampler.resample_chunk(mono, last=False)
            if len(mono):
                self._far_buffer = np.concatenate((self._far_buffer, mono))

        n_frames = len(self._far_buffer) // self._frame
        if n_frames == 0:
            return

        usable = n_frames * self._frame
        i16 = self._float_to_i16(self._far_buffer[:usable])
        self._far_buffer = self._far_buffer[usable:]

        for off in range(0, usable, self._frame):
            ctypes.memmove(
                self._far_in, i16[off : off + self._frame].ctypes.data, self._frame * 2
            )
            ret = self._apm.process_reverse_stream(
                self._far_in, self._stream_cfg, self._stream_cfg, self._far_out
            )
            if ret != 0:
                raise RuntimeError(t('process_reverse_stream 返回 {value1}', value1=ret))

    def set_delay_ms(self, delay_ms: int) -> None:
        self._delay_ms = int(delay_ms)

    def close(self) -> None:
        """releases APM resources; it must be called after the audio stream stops."""
        if self._closed:
            return
        self._closed = True
        with self._lock:
            self._active = False
            self._release()
        logger.info(t("AEC 引擎已关闭"))

    def _release(self) -> None:
        self._active = False
        try:
            if self._apm is not None and self._stream_cfg is not None:
                self._apm.destroy_stream_config(self._stream_cfg)
        except Exception:
            pass
        self._stream_cfg = None
        self._apm = None
        self._far_resampler = None
        self._far_pending.clear()
        self._far_buffer = np.empty(0, dtype=np.float32)
        if self._far_dropped:
            logger.debug(t('AEC far 累计丢弃 {value1} 块', value1=self._far_dropped))

    def _on_failure(self, side: str, err: Exception) -> None:
        self._fail_count += 1
        if self._fail_count >= _MAX_CONSECUTIVE_FAILURES:
            logger.error(
                t('AEC {value1} 连续失败 {value3} 次，自动旁路: {value5}', value1=side, value3=self._fail_count, value5=err),
                exc_info=True,
            )
            with self._lock:
                self._release()
        else:
            logger.debug(t('AEC {value1} 处理失败（{value3}）: {value5}', value1=side, value3=self._fail_count, value5=err))

    @staticmethod
    def _float_to_i16(x: np.ndarray) -> np.ndarray:
        return np.clip(x * 32768.0, -32768.0, 32767.0).astype(np.int16)
