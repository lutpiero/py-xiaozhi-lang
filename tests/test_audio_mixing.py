"""TTS/music queue mixing regression test.

covers: PcmFifo sample-level semantics, _pull_mixed mixing/duck/clipping.
Background: TTS and music once shared a FIFO, and the TTS time frames were interleaved sentence by sentence, resulting in "intermittent playback at the same time".
"""

import numpy as np
import pytest

from src.utils.config_manager import initialize_config

try:
    initialize_config()
except Exception:
    pass

from src.audio_codecs.audio_buffer import PcmFifo  # noqa: E402
from src.audio_codecs.audio_codec import (  # noqa: E402
    _MUSIC_DUCK_GAIN,
    AudioCodec,
)


class TestPcmFifo:
    def test_pull_basic(self):
        f = PcmFifo(1000)
        f.push(np.ones(300, dtype=np.float32))
        out = f.pull(200)
        assert out.shape == (200,)
        assert np.all(out == 1)
        assert f.size == 100

    def test_pull_pads_zeros_when_short(self):
        f = PcmFifo(1000)
        f.push(np.ones(100, dtype=np.float32))
        out = f.pull(200)
        assert np.all(out[:100] == 1)
        assert np.all(out[100:] == 0)
        assert f.size == 0

    def test_pull_empty_returns_none(self):
        f = PcmFifo(1000)
        assert f.pull(10) is None

    def test_push_drops_oldest_over_capacity(self):
        f = PcmFifo(1000)
        f.push(np.zeros(600, dtype=np.float32))
        f.push(np.ones(600, dtype=np.float32))
        assert f.size == 1000
        assert f.dropped == 200
        out = f.pull(1000)
        # The oldest 200 0 Discarded, leaving 400 0 600 1
        assert np.all(out[:400] == 0)
        assert np.all(out[400:] == 1)

    def test_clear(self):
        f = PcmFifo(1000)
        f.push(np.ones(500, dtype=np.float32))
        assert f.clear() == 500
        assert f.size == 0
        assert f.pull(10) is None

    def test_multichannel_flattened(self):
        f = PcmFifo(1000)
        f.push(np.ones((100, 2), dtype=np.float32))
        assert f.size == 200


class TestMixing:
    @pytest.fixture()
    def codec(self):
        return AudioCodec()

    def test_music_only_full_gain(self, codec):
        n = codec._mix_chunk
        codec._music_fifo.push(np.full(n, 0.4, dtype=np.float32))
        out = codec._pull_mixed(n)
        assert np.allclose(out, 0.4)

    def test_tts_only(self, codec):
        n = codec._mix_chunk
        codec._tts_fifo.push(np.full(n, 0.5, dtype=np.float32))
        out = codec._pull_mixed(n)
        assert np.allclose(out, 0.5)

    def test_tts_and_music_mixed_with_duck(self, codec):
        n = codec._mix_chunk
        codec._tts_fifo.push(np.full(n, 0.5, dtype=np.float32))
        codec._music_fifo.push(np.full(n, 0.4, dtype=np.float32))
        out = codec._pull_mixed(n)
        assert np.allclose(out, 0.5 + _MUSIC_DUCK_GAIN * 0.4)

    def test_duck_hangover_then_recover(self, codec):
        n = codec._mix_chunk
        # After one TTS, the music still evades during the hangover period
        codec._tts_fifo.push(np.full(n, 0.5, dtype=np.float32))
        codec._music_fifo.push(np.full(n, 0.4, dtype=np.float32))
        codec._pull_mixed(n)

        codec._music_fifo.push(np.full(n, 0.4, dtype=np.float32))
        out = codec._pull_mixed(n)
        assert np.allclose(out, _MUSIC_DUCK_GAIN * 0.4)

        # hangover restores the full volume after exhaustion
        for _ in range(15):
            codec._music_fifo.push(np.full(n, 0.4, dtype=np.float32))
            out = codec._pull_mixed(n)
        assert np.allclose(out, 0.4)

    def test_clip_protection(self, codec):
        n = codec._mix_chunk
        codec._tts_fifo.push(np.full(n, 0.9, dtype=np.float32))
        codec._music_fifo.push(np.full(n, 0.9, dtype=np.float32))
        out = codec._pull_mixed(n)
        assert out.max() <= 1.0

    def test_both_empty_returns_none(self, codec):
        assert codec._pull_mixed(codec._mix_chunk) is None

    def test_clear_semantics_are_independent(self, codec):
        n = codec._mix_chunk
        codec._tts_fifo.push(np.full(n, 0.5, dtype=np.float32))
        codec._music_fifo.push(np.full(n, 0.4, dtype=np.float32))
        codec._tts_fifo.clear()
        # TTS clearing does not affect the music
        assert codec._music_fifo.size == n
