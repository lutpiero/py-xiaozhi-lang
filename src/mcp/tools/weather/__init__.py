"""weather tools MCP.

- register_weather_tools: Explicit registration (current mock, to be connected to the real API)
"""

from .register import register_weather_tools

__all__ = ["register_weather_tools"]
