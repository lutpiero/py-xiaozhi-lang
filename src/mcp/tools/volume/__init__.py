"""volume control tools.

- VolumeController / platform backend: see volume_controller / windows|macos|linux
- register_volume_tools: Register with McpServer (closure holds controller, no module singleton)
"""

from .register import create_volume_controller, register_volume_tools
from .volume_controller import VolumeController

__all__ = [
    "VolumeController",
    "create_volume_controller",
    "register_volume_tools",
]
