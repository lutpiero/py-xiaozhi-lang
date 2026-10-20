"""music related tools.

- music_player: playback session (created by the container and injected into MCP; the only external entrance)
- playback / bus: PlaybackEngine / MusicEventBridge (internal combination, do not treat it as a public API)
- cache / download / lyrics: cache, direct link, lyrics
- online_search / local_library / metadata: song search and local library
- register_music_tools: Register tools with McpServer (closure holds player)
"""

from .music_player import MusicPlayer
from .register import register_music_tools

__all__ = [
    "MusicPlayer",
    "register_music_tools",
]
