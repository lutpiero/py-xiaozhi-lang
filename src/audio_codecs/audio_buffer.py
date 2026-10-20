"""Sample-level PCM Buffer.

Thread-safe FIFO used by output callback mixing
"""

import threading
from collections import deque

import numpy as np


class PcmFifo:
    """Sample-level PCM FIFO (float32 mono, thread-safe).

    The writing end is in the asyncio thread, and the reading end is in the audio output callback thread;
    Used for TTS / mixing in the output callback after music splitting.

    - push: The oldest is discarded when the capacity is exceeded (recorded as dropped)
    - pull: Return a fixed-length block, zero padding for insufficient data; no data is returned at all None
    """

    def __init__(self, max_samples: int):
        self._chunks: deque = deque()
        self._offset = 0  # The number of samples consumed in the first block
        self._size = 0  # Total number of readable samples
        self._max = int(max_samples)
        self._lock = threading.Lock()
        self.dropped = 0

    @property
    def size(self) -> int:
        return self._size

    def push(self, pcm: np.ndarray) -> None:
        """Append float32 mono data; discard the oldest when capacity exceeds limit."""
        if pcm.ndim > 1:
            pcm = pcm.reshape(-1)
        if pcm.dtype != np.float32:
            pcm = pcm.astype(np.float32)
        with self._lock:
            self._chunks.append(pcm)
            self._size += len(pcm)
            while self._size > self._max and self._chunks:
                head = self._chunks[0]
                remain = len(head) - self._offset
                drop = min(remain, self._size - self._max)
                self._offset += drop
                self._size -= drop
                self.dropped += drop
                if self._offset >= len(head):
                    self._chunks.popleft()
                    self._offset = 0

    def pull(self, n: int) -> np.ndarray | None:
        """takes n samples; no data is returned None, zero padding if insufficient."""
        with self._lock:
            if self._size == 0:
                return None
            out = np.zeros(n, dtype=np.float32)
            filled = 0
            while filled < n and self._chunks:
                head = self._chunks[0]
                avail = len(head) - self._offset
                take = min(avail, n - filled)
                out[filled : filled + take] = head[
                    self._offset : self._offset + take
                ]
                filled += take
                self._offset += take
                self._size -= take
                if self._offset >= len(head):
                    self._chunks.popleft()
                    self._offset = 0
            return out

    def clear(self) -> int:
        """Cleared, return the number of discarded samples."""
        with self._lock:
            count = self._size
            self._chunks.clear()
            self._offset = 0
            self._size = 0
            return count
