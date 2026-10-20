import asyncio
import os
import re
import sys
from typing import Any

import numpy as np
import sounddevice as sd

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


class ALSAErrorSuppressor:
    """
    ALSA Error output suppressor.

    On Linux systems, the ALSA library will output a lot of warning and error messages to stderr,
    These messages can interfere with terminal output. This context manager temporarily suppresses these outputs.

    Usage:
        with ALSAErrorSuppressor():
            # Perform PyAudio initialization and similar work
            audio = pyaudio.PyAudio()

    Note:
        - Only works on Linux systems
        - No action on Windows/macOS
        - stderr
    """

    def __init__(self):
        self._old_stderr = None
        self._devnull = None
        self._is_linux = sys.platform.startswith("linux")

    def __enter__(self):
        if not self._is_linux:
            return self

        try:
            self._old_stderr = os.dup(2)
            self._devnull = os.open("/dev/null", os.O_WRONLY)
            os.dup2(self._devnull, 2)
        except OSError:
            # Fails silently if the file descriptor cannot be manipulated
            self._old_stderr = None
            self._devnull = None

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._is_linux:
            return False

        if self._old_stderr is not None:
            try:
                os.dup2(self._old_stderr, 2)
                os.close(self._old_stderr)
            except OSError:
                pass

        if self._devnull is not None:
            try:
                os.close(self._devnull)
            except OSError:
                pass

        return False  # Does not suppress exceptions


def suppress_alsa_errors():
    """returns ALSA Error Suppressor Context Manager."""
    return ALSAErrorSuppressor()


# Optional: Block common virtual/aggregated devices (they are not selected by default)
_VIRTUAL_PATTERNS = [
    r"blackhole",
    r"aggregate",
    r"multi[-\s]?output",  # macOS
    r"monitor",
    r"echo[-\s]?cancel",  # Linux Pulse/PipeWire
    r"vb[-\s]?cable",
    r"voicemeeter",
    r"cable (input|output)",  # Windows
    r"loopback",
]


def _is_virtual(name: str) -> bool:
    n = name.casefold()
    return any(re.search(pat, n) for pat in _VIRTUAL_PATTERNS)


def downmix_to_mono(
    pcm: np.ndarray | bytes,
    *,
    keepdims: bool = True,
    dtype: np.dtype | str = np.int16,
    in_channels: int | None = None,
) -> np.ndarray | bytes:
    """Puts any formatted audio Downmix to mono.

    supports two inputs:
    1 is restored when exiting the context. np.ndarray: PCM array of shape (N,) or (N, C)
    2. bytes: PCM byte stream (dtype and in_channels need to be specified)

    Args:
        pcm: Input audio data (ndarray or bytes)
        keepdims: True returns (N,1), False returns (N,) (ndarray input only)
        dtype: PCM data type (only used for bytes input)
        in_channels: number of input channels (only required for bytes input)

    Returns:
        Mono audio data (Same as input type)

    Examples:
        >>>
        >>> stereo = np.random.randint(-32768, 32767, (1000, 2), dtype=np.int16)
        >>> mono = downmix_to_mono(stereo, keepdims=False)

        >>>
        >>> stereo_bytes = b'...'
        >>> mono_bytes = downmix_to_mono(stereo_bytes, dtype=np.int16, in_channels=2)
    """
    # bytes Input: Convert -> Process -> Convert back bytes
    if isinstance(pcm, bytes):
        if in_channels is None:
            raise ValueError(t("bytes 输入必须指定 in_channels 参数"))
        arr = np.frombuffer(pcm, dtype=dtype).reshape(-1, in_channels)
        mono_arr = downmix_to_mono(arr, keepdims=False)  # bytes Output No keepdims required
        return mono_arr.tobytes()

    # ndarray Input: Direct processing
    x = np.asarray(pcm)
    if x.ndim == 1:
        return x[:, None] if keepdims else x

    # Already mono
    if x.shape[1] == 1:
        return x if keepdims else x[:, 0]

    # Multi-channel downmix
    if np.issubdtype(x.dtype, np.integer):
        # First convert to floating point for averaging, then round back to the original integer type to avoid overflow
        y = np.rint(x.astype(np.float32).mean(axis=1))
        info = np.iinfo(x.dtype)
        y = np.clip(y, info.min, info.max).astype(x.dtype)
    else:
        # Floating point: keep the original dtype (such as float32) to avoid defaulting to float64
        y = x.mean(axis=1, dtype=x.dtype)

    return y[:, None] if keepdims else y


def safe_queue_put(
    queue: asyncio.Queue, item: Any, replace_oldest: bool = True
) -> bool:
    """Safely puts the item into the queue, optionally discarding the oldest data when the queue is full.

    Args:
        queue: asyncio.Queue object
        item: Data to enqueue
        replace_oldest: True=Discard the oldest data and put in new data when the queue is full, False=Discard the new data directly

    Returns:
        True=Enqueue successfully, False=queue is full and not yet enqueue
    """
    try:
        queue.put_nowait(item)
        return True
    except asyncio.QueueFull:
        if replace_oldest:
            try:
                queue.get_nowait()  # Discards the oldest one
                queue.put_nowait(item)  # puts new data in
                return True
            except asyncio.QueueEmpty:
                # Theoretically this will not happen, but for insurance purposes
                queue.put_nowait(item)
                return True
        return False


def upmix_mono_to_channels(mono_data: np.ndarray, num_channels: int) -> np.ndarray:
    """Upmix mono audio to multichannel (copy to all channels)

    Args:
        mono_data: Mono audio data, shape (N,)
        num_channels: Target number of channels

    Returns:
        Multi-channel audio data, shape (N, num_channels)
    """
    if num_channels == 1:
        return mono_data.reshape(-1, 1)

    # Copy mono to all channels
    return np.tile(mono_data.reshape(-1, 1), (1, num_channels))


def _valid(devs: list[dict], idx: int, kind: str, include_virtual: bool) -> bool:
    if not isinstance(idx, int) or idx < 0 or idx >= len(devs):
        return False
    d = devs[idx]
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    if int(d.get(key, 0)) <= 0:
        return False
    if not include_virtual and _is_virtual(d.get("name", "")):
        return False
    return True


def refresh_portaudio_devices(*, reinitialize: bool = True) -> list[dict]:
    """Re-enumerates the PortAudio device list (hot-plug friendly).

    The caller must first stop all sounddevice streams in this process before calling this function;
    ``sd._terminate`` is not safe when there is an active stream.

    Args:
        reinitialize: True Try ``_terminate`` ``_initialize`` to force
            Rebuild the PortAudio context (good for macOS back-up Bluetooth to appear in the list).
            Downgrade to normal ``query_devices`` on failure.

    Returns:
        Device information dict list (same shape as ``list(sd.query_devices())``)
    """
    if reinitialize:
        terminate = getattr(sd, "_terminate", None)
        initialize = getattr(sd, "_initialize", None)
        if callable(terminate) and callable(initialize):
            try:
                terminate()
                initialize()
                logger.info(t("PortAudio 已重新初始化，准备重新枚举设备"))
            except Exception as e:
                logger.warning(
                    t('PortAudio 重初始化失败，降级为普通枚举: {value1}', value1=e),
                    exc_info=True,
                )
        else:
            logger.debug(t("当前 sounddevice 无 _terminate/_initialize，跳过重初始化"))

    try:
        devices = list(sd.query_devices())
    except Exception as e:
        logger.error(t('query_devices 失败: {value1}', value1=e), exc_info=True)
        return []

    logger.info(t('音频设备枚举完成: {value1} 个', value1=len(devices)))
    return devices


def list_audio_devices(
    *, include_virtual: bool = True
) -> dict[str, list[dict[str, Any]]]:
    """List input/output devices (for setting page and debugging).

    Does not proactively reinitialize PortAudio; when hot plug refresh is required, first
    ``refresh_portaudio_devices()``, then call this function.

    Returns:
        ``{"input": [...], "output": [...]}``, each item contains index/name/sample_rate/channels
    """
    try:
        devices = list(sd.query_devices())
    except Exception as e:
        logger.error(t('列出音频设备失败: {value1}', value1=e), exc_info=True)
        return {"input": [], "output": []}

    default_input = None
    default_output = None
    try:
        if sd.default.device is not None:
            default_input = sd.default.device[0]
            default_output = sd.default.device[1]
    except Exception:
        pass

    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []

    for i, d in enumerate(devices):
        name = d.get("name", "Unknown")
        if not include_virtual and _is_virtual(name):
            continue
        sr = d.get("default_samplerate", 48000)
        sample_rate = int(sr) if isinstance(sr, (int, float)) else 48000
        idx = int(d.get("index", i))

        in_ch = int(d.get("max_input_channels", 0) or 0)
        out_ch = int(d.get("max_output_channels", 0) or 0)

        if in_ch > 0:
            mark = t(" (默认)") if idx == default_input else ""
            inputs.append(
                {
                    "index": idx,
                    "name": name + mark,
                    "raw_name": name,
                    "sample_rate": sample_rate,
                    "channels": in_ch,
                }
            )
        if out_ch > 0:
            mark = t(" (默认)") if idx == default_output else ""
            outputs.append(
                {
                    "index": idx,
                    "name": name + mark,
                    "raw_name": name,
                    "sample_rate": sample_rate,
                    "channels": out_ch,
                }
            )

    return {"input": inputs, "output": outputs}


def find_device_by_name(
    kind: str, device_name: str, *, include_virtual: bool = False
) -> dict[str, Any] | None:
    """Find device by name (fuzzy match)

    Args:
        kind: "input" or "output"
        device_name: device name (supports partial matching)
        include_virtual: whether to include virtual devices

    Returns:
        device information dictionary, or None
    """
    assert kind in ("input", "output")

    try:
        devices = list(sd.query_devices())
    except Exception:
        return None

    key_channels = "max_input_channels" if kind == "input" else "max_output_channels"
    search_name = device_name.casefold().strip()

    # 1. exact match (ignoring case)
    for i, d in enumerate(devices):
        if not _valid(devices, i, kind, include_virtual):
            continue
        if d.get("name", "").casefold().strip() == search_name:
            sr = d.get("default_samplerate", None)
            return {
                "index": int(d.get("index", i)),
                "name": d.get("name", "Unknown"),
                "sample_rate": int(sr) if isinstance(sr, (int, float)) else None,
                "channels": int(d.get(key_channels, 0)),
            }

    # 2. Fuzzy matching (inclusion relationship)
    for i, d in enumerate(devices):
        if not _valid(devices, i, kind, include_virtual):
            continue
        device_full_name = d.get("name", "").casefold()
        if search_name in device_full_name or device_full_name in search_name:
            sr = d.get("default_samplerate", None)
            return {
                "index": int(d.get("index", i)),
                "name": d.get("name", "Unknown"),
                "sample_rate": int(sr) if isinstance(sr, (int, float)) else None,
                "channels": int(d.get(key_channels, 0)),
            }

    return None


def select_audio_device(
    kind: str, *, include_virtual: bool = False
) -> dict[str, Any] | None:
    """Automatically select the audio device (simplified version)

    Strategy:
    1. System default device (sounddevice recommended)
    2. The first available non-virtual device

    Args:
        kind: "input" or "output"
        include_virtual: whether to include virtual devices

    Returns:
        {index, name, sample_rate, channels} or None
    """
    assert kind in ("input", "output")

    try:
        devices = list(sd.query_devices())
    except Exception:
        return None

    key_channels = "max_input_channels" if kind == "input" else "max_output_channels"

    def pack(idx: int, base: dict | None = None) -> dict[str, Any] | None:
        if base is None:
            if not _valid(devices, idx, kind, include_virtual):
                return None
            d = devices[idx]
        else:
            d = base
            if not include_virtual and _is_virtual(d.get("name", "")):
                return None
        sr = d.get("default_samplerate", None)
        return {
            "index": int(d.get("index", idx)),
            "name": d.get("name", "Unknown"),
            "sample_rate": int(sr) if isinstance(sr, (int, float)) else None,
            "channels": int(d.get(key_channels, 0)),
        }

    # 1. sounddevice system default (most reliable)
    try:
        info = sd.query_devices(kind=kind)
        packed = pack(int(info.get("index")), base=info)
        if packed:
            return packed
    except Exception:
        logger.debug(t('查询系统默认{value1}设备失败，尝试兜底策略', value1=kind))

    # 2. Bottom line: the first available non-virtual device
    for i, _d in enumerate(devices):
        if _valid(devices, i, kind, include_virtual):
            return pack(i)

    return None
