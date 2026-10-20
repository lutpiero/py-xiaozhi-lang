import numpy as np

from src.i18n import t

# ============================================================
# Opus library loading (must be before importing opuslib)
# ============================================================
from src.utils.opus_loader import setup_opus

setup_opus()

# must be imported after setup_opus()
import opuslib  # noqa: E402
import opuslib.api.decoder as decoder_api  # noqa: E402
import opuslib.api.encoder as encoder_api  # noqa: E402

from src.logging import get_logger  # noqa: E402

logger = get_logger()


_OPUS_BANDWIDTHS = {
    "NB": "8kHz", "MB": "12kHz", "WB": "16kHz",
    "SWB": "24kHz", "FB": "48kHz",
}


def parse_opus_toc(opus_data: bytes) -> dict:
    """Parses encoding parameters from the TOC bytes of an Opus packet.

    Parsed according to RFC 6716 Section 3.1:
    - TOC high 5 bits = config (determines mode/bandwidth/single frame duration)
    - TOC low 2 bits = code (determines the number of frames)

    Returns:
        dict with keys: duration_ms, frame_ms, num_frames, bandwidth, mode
        Empty package returns None
    """
    if not opus_data:
        return None

    toc = opus_data[0]
    config = (toc >> 3) & 0x1F
    code = toc & 0x03

    # config → Mode Bandwidth Single frame duration
    if config < 12:
        mode = "SILK"
        bandwidth = ("NB", "MB", "WB")[config // 4]
        frame_ms = (10, 20, 40, 60)[config % 4]
    elif config < 16:
        mode = "Hybrid"
        bandwidth = ("SWB", "FB")[(config - 12) // 2]
        frame_ms = (10, 20)[config % 2]
    else:
        mode = "CELT"
        bandwidth = ("NB", "WB", "SWB", "FB")[(config - 16) // 4]
        frame_ms = (2.5, 5, 10, 20)[config % 4]

    # code → Number of frames
    if code == 0:
        num_frames = 1
    elif code <= 2:
        num_frames = 2
    else:
        num_frames = (opus_data[1] & 0x3F) if len(opus_data) >= 2 else 1

    return {
        "duration_ms": frame_ms * num_frames,
        "frame_ms": frame_ms,
        "num_frames": num_frames,
        "bandwidth": bandwidth,
        "bandwidth_hz": _OPUS_BANDWIDTHS[bandwidth],
        "mode": mode,
    }


class OpusCodec:
    """Opus codec

    uses libopus's encode_float and decode_float Interface,
    """

    def __init__(
        self,
        input_sample_rate: int,
        output_sample_rate: int,
        channels: int = 1,
    ):
        """Initialize Opus codec

        Args:
            input_sample_rate: input sampling rate (encoding), such as 16000
            output_sample_rate: output sampling rate (decoding), such as 24000
            channels: Number of channels, default 1
        """
        self.input_sample_rate = input_sample_rate
        self.output_sample_rate = output_sample_rate
        self.channels = channels
        self.encoder = None
        self.decoder = None

    def initialize(self):
        """Create codec

        Raises:
            Exception: Creation failed
        """
        try:
            # Input encoder: 16kHz mono
            self.encoder = opuslib.Encoder(
                self.input_sample_rate,
                self.channels,
                opuslib.APPLICATION_VOIP,
            )

            # Output decoder: 24kHz mono
            self.decoder = opuslib.Decoder(self.output_sample_rate, self.channels)

            logger.info(
                t('Opus编解码器创建成功 (float32模式) | 编码: {value1}Hz | 解码: {value3}Hz', value1=self.input_sample_rate, value3=self.output_sample_rate)
            )
        except Exception as e:
            logger.error(t('创建Opus编解码器失败: {value1}', value1=e), exc_info=True)
            raise

    def encode(self, pcm_float32: np.ndarray, frame_size: int) -> bytes:
        """Encoding float32 PCM → Opus

        Args:
            pcm_float32: float32 array, range [-1.0, 1.0]
            frame_size: number of samples

        Returns:
            Opus encoded data

        Raises:
            RuntimeError: Encoder is not initialized
            Exception: Encoding failed
        """
        if self.encoder is None:
            raise RuntimeError(t("编码器未初始化"))

        # converted to bytes (float32 format)
        pcm_bytes = pcm_float32.astype(np.float32).tobytes()

        # uses encode_float (libopus native support)
        return self.encoder.encode_float(pcm_bytes, frame_size)

    def decode(self, opus_data: bytes, frame_size: int) -> np.ndarray:
        """decoding Opus → float32 PCM

        Args:
            opus_data: Opus encoding data
            frame_size: expected number of samples

        Returns:
            float32 array, range [-1.0, 1.0]

        Raises:
            RuntimeError: Decoder is not initialized
            Exception: Decoding failed
        """
        if self.decoder is None:
            raise RuntimeError(t("解码器未初始化"))

        # uses decode_float (libopus native support)
        # Note: channels are specified when creating Decoder, decode_float does not require this parameter
        pcm_bytes = self.decoder.decode_float(opus_data, frame_size, decode_fec=False)

        # converted to numpy Array
        return np.frombuffer(pcm_bytes, dtype=np.float32)

    def close(self):
        """Releases resources, explicitly destroys C-layer codec state.

        opuslib's Encoder/Decoder.__del__ will also call destroy(),
        must first make encoder_state/decoder_state empty to avoid double free.
        Idempotent: safe to call repeatedly.
        """
        if getattr(self, '_closed', False):
            return
        self._closed = True

        if self.encoder is not None:
            encoder_api.destroy(self.encoder.encoder_state)
            self.encoder.encoder_state = None  # Prevents __del__ secondary release
            self.encoder = None
        if self.decoder is not None:
            decoder_api.destroy(self.decoder.decoder_state)
            self.decoder.decoder_state = None  # Prevents __del__ secondary release
            self.decoder = None
        logger.debug(t("Opus编解码器已释放"))
