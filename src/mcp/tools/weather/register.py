"""Register the weather MCP tool (current mock, to be connected to the real API)."""

from __future__ import annotations

from collections.abc import Callable

from src.i18n import t
from src.logging import get_logger
from src.mcp.tooling import McpTool, Property, PropertyList, PropertyType

from .service import get_forecast_payload, get_weather_payload

logger = get_logger()


def register_weather_tools(add_tool: Callable[[McpTool], None]) -> None:
    """Register the weather tool with McpServer."""

    tools: list[McpTool] = [
        McpTool(
            "get_weather",
            (
                t("获取指定城市的当前天气。"
                "参数: city - 城市名称（如：北京、上海、广州）")
            ),
            PropertyList(
                [Property("city", PropertyType.STRING, default_value=t("北京"))]
            ),
            get_weather_payload,
        ),
        McpTool(
            "get_forecast",
            (
                t("获取指定城市的天气预报。"
                "参数: city - 城市名称, days - 预报天数(1-7天)")
            ),
            PropertyList(
                [
                    Property("city", PropertyType.STRING, default_value=t("北京")),
                    Property(
                        "days",
                        PropertyType.INTEGER,
                        default_value=3,
                        min_value=1,
                        max_value=7,
                    ),
                ]
            ),
            get_forecast_payload,
        ),
    ]

    for tool in tools:
        add_tool(tool)
    logger.info(t("已注册 %d 个天气 MCP 工具（register_weather_tools, mock）"), len(tools))
