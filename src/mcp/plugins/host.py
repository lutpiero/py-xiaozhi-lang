"""Plug-in MCP host API (stable contract).

The plug-in only uses the McpHost registration tool and the capabilities according to the whitelist, and is prohibited from relying on global singletons.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from src.i18n import t
from src.logging import get_logger
from src.mcp.tooling import McpTool, Property, PropertyList, PropertyType

logger = get_logger()

# The default allowed host.get name (music_player, etc. need to be configured to be explicitly added)
DEFAULT_ALLOW_GET = frozenset({"config_readonly", "logger"})


class McpHost:
    """Bound to the host facade of an assembly process."""

    def __init__(
        self,
        add_tool: Callable[[McpTool], None],
        *,
        capabilities: dict[str, Any] | None = None,
        allow_get: Sequence[str] | None = None,
        plugin_id: str | None = None,
    ) -> None:
        self._add_tool = add_tool
        self._capabilities = dict(capabilities or {})
        self._allow_get = frozenset(allow_get) if allow_get is not None else DEFAULT_ALLOW_GET
        self._plugin_id = plugin_id or "unknown"
        self._registered_names: list[str] = []

    @property
    def plugin_id(self) -> str:
        return self._plugin_id

    @property
    def registered_tool_names(self) -> list[str]:
        return list(self._registered_names)

    def bind_plugin(self, plugin_id: str) -> "McpHost":
        """Returns the view bound to the specified plugin_id (shared add_tool / capabilities)."""
        child = McpHost(
            self._add_tool,
            capabilities=self._capabilities,
            allow_get=self._allow_get,
            plugin_id=plugin_id,
        )
        return child

    def add_tool(self, tool: McpTool) -> None:
        """Register tool; record name for uninstallation/diagnosis."""
        self._add_tool(tool)
        self._registered_names.append(tool.name)
        logger.info(
            t("[MCP插件:%s] 注册工具: %s"), self._plugin_id, tool.name
        )

    def get(self, name: str) -> Any:
        """Returns host capabilities according to the whitelist; None if not authorized or not provided."""
        if name not in self._allow_get:
            logger.warning(
                t("[MCP插件:%s] host.get(%r) 不在白名单 %s"),
                self._plugin_id,
                name,
                sorted(self._allow_get),
            )
            return None
        if name == "logger":
            return get_logger()
        return self._capabilities.get(name)

    def tool(
        self,
        name: str,
        description: str,
        props: Sequence[Property | dict[str, Any]] | None = None,
    ):
        """Decorator: Register function as McpTool (do not write global registry)."""

        def decorator(func: Callable):
            prop_list = _to_property_list(props)
            self.add_tool(McpTool(name, description, prop_list, func))
            return func

        return decorator


def _to_property_list(
    props: Sequence[Property | dict[str, Any]] | None,
) -> PropertyList:
    if not props:
        return PropertyList()
    converted: list[Property] = []
    for p in props:
        if isinstance(p, Property):
            converted.append(p)
            continue
        if not isinstance(p, dict):
            raise TypeError(t('props 项须为 Property 或 dict，得到 {value1}', value1=type(p)))
        converted.append(_dict_to_property(p))
    return PropertyList(converted)


def _dict_to_property(data: dict[str, Any]) -> Property:
    """supports simplified dict: {name, type: str|int|bool|string|integer|boolean, ...}."""
    name = data["name"]
    raw_type = data.get("type", "string")
    type_map = {
        "str": PropertyType.STRING,
        "string": PropertyType.STRING,
        "int": PropertyType.INTEGER,
        "integer": PropertyType.INTEGER,
        "bool": PropertyType.BOOLEAN,
        "boolean": PropertyType.BOOLEAN,
        PropertyType.STRING: PropertyType.STRING,
        PropertyType.INTEGER: PropertyType.INTEGER,
        PropertyType.BOOLEAN: PropertyType.BOOLEAN,
    }
    if isinstance(raw_type, PropertyType):
        ptype = raw_type
    else:
        ptype = type_map.get(str(raw_type).lower())
        if ptype is None:
            raise ValueError(t('未知属性类型: {value1}', value1=raw_type))
    return Property(
        name,
        ptype,
        default_value=data.get("default", data.get("default_value")),
        min_value=data.get("min", data.get("min_value")),
        max_value=data.get("max", data.get("max_value")),
    )
