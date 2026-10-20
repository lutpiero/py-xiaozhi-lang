"""activates the verification code broadcasting module.

uses pre-recorded WAV sound effects to announce the activation verification code and is only used during the device activation process.
does not depend on FFmpeg and can work in a clean environment without system FFmpeg.
"""
import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from src.i18n import t
from src.logging import get_logger
from src.utils.resource_finder import get_app_root

logger = get_logger()

# audio resource directory
_ASSETS_DIR = get_app_root() / "assets" / "sounds"
# The default sampling rate of the resource (the same as the preset WAV in assets/sounds Alignment)
_DEFAULT_SAMPLE_RATE = 24000


class ActivationAnnouncer:
    """activates the verification code broadcaster."""

    def __init__(self, locale: str = "zh-CN"):
        self._locale = locale
        self._stop_flag = threading.Event()
        self._play_thread: threading.Thread | None = None

    def _get_sound_path(self, name: str) -> Path | None:
        """obtains the sound effect file path (only WAV)."""
        sound_file = _ASSETS_DIR / self._locale / f"{name}.wav"
        if sound_file.exists():
            return sound_file
        # Fallback to zh-CN
        if self._locale != "zh-CN":
            fallback = _ASSETS_DIR / "zh-CN" / f"{name}.wav"
            if fallback.exists():
                return fallback
        return None

    def _load_wav(self, file_path: Path) -> tuple[np.ndarray, int] | None:
        """Load WAV is float32 mono and returns (samples, sample_rate).

        Args:
            file_path: WAV file path.

        Returns:
            (float32 audio, sampling rate), returns None on failure.
        """
        try:
            with wave.open(str(file_path), "rb") as wf:
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)

            if sample_width == 2:
                audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            elif sample_width == 4:
                audio = (
                    np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
                )
            elif sample_width == 1:
                # 8-bit PCM is unsigned
                audio = (
                    np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0
                ) / 128.0
            else:
                logger.error(t('不支持的 WAV 位深: {value1} bit ({value3})', value1=sample_width * 8, value3=file_path))
                return None

            if channels > 1:
                audio = audio.reshape(-1, channels).mean(axis=1)

            return audio, sample_rate
        except Exception as e:
            logger.error(t('加载 WAV 失败 {value1}: {value3}', value1=file_path, value3=e), exc_info=True)
            return None

    def _play_sounds(self, names: list[str]) -> None:
        """Play sound effect sequence (executed in worker thread)."""
        for name in names:
            if self._stop_flag.is_set():
                logger.debug(t("播报被中断"))
                break

            sound_path = self._get_sound_path(name)
            if not sound_path:
                logger.warning(t('音效文件不存在: {value1}', value1=name))
                continue

            loaded = self._load_wav(sound_path)
            if loaded is None or self._stop_flag.is_set():
                continue

            audio, sample_rate = loaded
            if sample_rate <= 0:
                sample_rate = _DEFAULT_SAMPLE_RATE

            try:
                sd.play(audio, sample_rate)
                # Wait in sections to facilitate response to interrupts
                while sd.get_stream().active:
                    if self._stop_flag.is_set():
                        sd.stop()
                        break
                    self._stop_flag.wait(0.05)
            except Exception as e:
                logger.error(t('播放失败: {value1}', value1=e), exc_info=True)

    def announce(self, code: str) -> None:
        """Broadcast verification code (non-blocking).

        Args:
            code: Verification code string, such as "123456"
        """
        if not code or not code.isdigit():
            logger.warning(t('无效的验证码: {value1}', value1=code))
            return

        # Stop the previous broadcast
        self.stop()

        # Build playback sequence: activation prompt Each number
        sounds = ["activation"] + list(code)

        logger.info(t('播报验证码: {value1}', value1=code))

        self._stop_flag.clear()
        self._play_thread = threading.Thread(
            target=self._play_sounds,
            args=(sounds,),
            daemon=True,
            name="ActivationAnnouncer",
        )
        self._play_thread.start()

    def stop(self) -> None:
        """Stop the broadcast."""
        self._stop_flag.set()

        # Stop the audio playback
        try:
            sd.stop()
        except Exception as e:
            logger.debug(t('停止音频播放失败: {value1}', value1=e))

        # waits for the thread to end
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=1)

        self._play_thread = None


# Global instance
_announcer: ActivationAnnouncer | None = None


def announce_activation_code(code: str, locale: str = "zh-CN") -> None:
    """Broadcast activation verification code.

    Args:
        code: Verification code string
        locale: The language code
    """
    global _announcer
    if _announcer is None:
        _announcer = ActivationAnnouncer(locale)
    _announcer.announce(code)


def stop_announcement() -> None:
    """Stop the verification code broadcast."""
    global _announcer
    if _announcer:
        _announcer.stop()
