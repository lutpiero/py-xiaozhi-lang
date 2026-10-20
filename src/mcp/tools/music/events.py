"""Music player event data type definition.

Data structure used for EventBus event communication.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class MusicStateData:
    """Music status change event data.

    Attributes:
        state: Playing status ("playing", "paused", "stopped", "completed")
        song: Song name
        position: Current play position (seconds)
        duration: Total duration (seconds)
        pause_source: Pause source ("tts", "manual", "external", None)
    """

    state: str
    song: str
    position: float
    duration: float
    pause_source: Optional[str] = None


@dataclass
class MusicLyricsData:
    """Lyrics update event data.

    Attributes:
        text: Lyric text
        time_sec: Timestamp (seconds)
        song_id: Song ID (optional)
    """

    text: str
    time_sec: float
    song_id: Optional[str] = None


@dataclass
class MusicControlRequest:
    """Music control request data.

    Attributes:
        source: Request source ("tts", "manual", "external", etc.)
    """

    source: str = "external"
