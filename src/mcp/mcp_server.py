"""
MCP Server Implementation for Python
Reference: https://modelcontextprotocol.io/specification/2024-11-05
"""
import json
from collections.abc import Callable
from typing import Any

from src.constants.system import SystemConstants
from src.i18n import t
from src.logging import get_logger
from src.mcp.tooling import McpTool, PropertyList

logger = get_logger()


class McpServer:
    """
    MCP server implementation.

    is created by ServiceContainer and injected by McpPlugin.
    """

    def __init__(self):
        self.tools: list[McpTool] = []
        self._send_callback: Callable | None = None
        self._camera = None
        # Plug-in tool_name -> plugin_id
        self._plugin_tool_owner: dict[str, str] = {}

    def set_send_callback(self, callback: Callable | None):
        """
        Set the callback function for sending messages; pass None to unbind.
        """
        self._send_callback = callback

    def set_camera(self, camera) -> None:
        """Inject camera (vision configuration / take_photo shared)."""
        self._camera = camera

    def get_camera(self):
        return self._camera

    def detach(self) -> None:
        """Unbind the runtime dependencies when the container is closed, and retain the tool list to facilitate restarting the same process."""
        self._send_callback = None
        self._camera = None

    def add_tool(
        self, tool: McpTool | tuple[str, str, PropertyList, Callable]
    ):
        """
        Add tool.
        """
        if isinstance(tool, tuple):
            # Create McpTool from parameters
            name, description, properties, callback = tool
            tool = McpTool(name, description, properties, callback)

        # Check if it already exists
        if any(item.name == tool.name for item in self.tools):
            logger.warning(t('Tool {value1} already added（拒绝重复注册）', value1=tool.name))
            return

        logger.info(f"Add tool: {tool.name}")
        self.tools.append(tool)

    def remove_tools_by_names(self, names: set[str] | list[str]) -> int:
        """Remove the tool by name and return the number removed."""
        name_set = set(names)
        if not name_set:
            return 0
        before = len(self.tools)
        self.tools = [t for t in self.tools if t.name not in name_set]
        return before - len(self.tools)

    def unload_plugin(self, plugin_id: str) -> int:
        """Uninstall plug-in plug-in registered tools."""
        from src.mcp.plugins.registry import PluginRegistry

        reg = PluginRegistry(tool_owner=self._plugin_tool_owner)
        return reg.unload_plugin(self, plugin_id)

    def reload_external_plugins(
        self, music_player=None, volume_controller=None
    ) -> list:
        """Only reload plug-ins: first remove the known plug-in tools, and then scan and load according to the configuration.

        Note: Built-in tools will not be re-registered; built-ins should already be in tools.
        """
        # Uninstall all currently registered plug-in tools
        if self._plugin_tool_owner:
            names = set(self._plugin_tool_owner.keys())
            self.remove_tools_by_names(names)
            self._plugin_tool_owner.clear()

        from src.mcp.plugins.loader import load_mcp_plugins_from_config

        capabilities = {}
        if music_player is not None:
            capabilities["music_player"] = music_player
        try:
            from src.utils.config_manager import get_config

            capabilities["config_readonly"] = get_config()
        except Exception:
            pass

        return load_mcp_plugins_from_config(
            self.add_tool,
            capabilities=capabilities,
            tool_owner=self._plugin_tool_owner,
        )

    def add_common_tools(self, music_player=None, volume_controller=None):
        """
        adds common tools (all explicitly mounted via register_*).

        music_player: Container-injected MusicPlayer; registers the music tool when provided.
        volume_controller: Optional injected VolumeController; created in register if not provided.
        camera / screenshot Registered separately in setup by McpPlugin.
        """
        # Back up the original tool list
        original_tools = self.tools.copy()
        self.tools.clear()

        if music_player is not None:
            from src.mcp.tools.music import register_music_tools

            register_music_tools(self.add_tool, music_player)

        from src.mcp.tools.app import register_app_tools
        from src.mcp.tools.volume import register_volume_tools
        from src.mcp.tools.weather import register_weather_tools

        register_volume_tools(self.add_tool, volume_controller)
        register_app_tools(self.add_tool)
        register_weather_tools(self.add_tool)

        # Plug-in: User directory plug-in package (included) lib/), failed isolation
        try:
            from src.mcp.plugins.loader import load_mcp_plugins_from_config

            capabilities = {}
            if music_player is not None:
                capabilities["music_player"] = music_player
            try:
                from src.utils.config_manager import get_config

                capabilities["config_readonly"] = get_config()
            except Exception:
                pass

            load_mcp_plugins_from_config(
                self.add_tool,
                capabilities=capabilities,
                tool_owner=self._plugin_tool_owner,
            )
        except Exception as e:
            logger.error(t('加载外挂 MCP 插件失败: {value1}', value1=e), exc_info=True)

        # Restore the original tool
        self.tools.extend(original_tools)

    async def parse_message(self, message: str | dict[str, Any]):
        """
        Parse MCP messages.
        """
        request_id = None
        try:
            if isinstance(message, str):
                data = json.loads(message)
            else:
                data = message

            logger.info(
                t('[MCP] 解析消息: {value1}', value1=json.dumps(data, ensure_ascii=False, indent=2))
            )

            # Check the JSONRPC version
            if data.get("jsonrpc") != "2.0":
                logger.error(f"Invalid JSONRPC version: {data.get('jsonrpc')}")
                return

            method = data.get("method")
            if not method:
                logger.error("Missing method")
                return

            # Ignore the notification
            if method.startswith("notifications"):
                logger.info(t('[MCP] 忽略通知消息: {value1}', value1=method))
                return

            params = data.get("params", {})
            request_id = data.get("id")

            if request_id is None:
                logger.error(f"Invalid id for method: {method}")
                return

            logger.info(
                t('[MCP] 处理方法: {value1}, ID: {value3}, 参数: {value5}', value1=method, value3=request_id, value5=params)
            )

            # handles different methods
            if method == "initialize":
                await self._handle_initialize(request_id, params)
            elif method == "tools/list":
                await self._handle_tools_list(request_id, params)
            elif method == "tools/call":
                await self._handle_tool_call(request_id, params)
            else:
                logger.error(f"Method not implemented: {method}")
                await self._reply_error(
                    request_id, f"Method not implemented: {method}"
                )

        except Exception as e:
            logger.error(f"Error parsing MCP message: {e}", exc_info=True)
            if request_id is not None:
                await self._reply_error(request_id, str(e))

    async def _handle_initialize(
        self, request_id: int, params: dict[str, Any]
    ):
        """
        handles initialization requests.
        """
        # Parse capabilities
        capabilities = params.get("capabilities", {})
        await self._parse_capabilities(capabilities)

        # returns server information
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": SystemConstants.APP_NAME,
                "version": SystemConstants.APP_VERSION,
            },
        }

        await self._reply_result(request_id, result)

    def _disabled_tool_names(self) -> set[str]:
        """Read from configuration MCP_TOOLS.DISABLED (blacklist)."""
        try:
            from src.mcp.tool_catalog import normalize_disabled
            from src.utils.config_manager import get_config

            raw = get_config().get_config("MCP_TOOLS.DISABLED", []) or []
            return set(normalize_disabled(raw))
        except Exception:
            return set()

    def _iter_enabled_tools(self):
        disabled = self._disabled_tool_names()
        for tool in self.tools:
            if tool.name not in disabled:
                yield tool

    async def _handle_tools_list(
        self, request_id: int, params: dict[str, Any]
    ):
        """
        handles tool list requests (pressed MCP_TOOLS.DISABLED filter).
        """
        cursor = params.get("cursor", "")
        max_payload_size = 8000

        tools_json = []
        total_size = 0
        found_cursor = not cursor
        next_cursor = ""

        for tool in self._iter_enabled_tools():
            # If the starting position has not been found, continue searching
            if not found_cursor:
                if tool.name == cursor:
                    found_cursor = True
                else:
                    continue

            # Check the size
            tool_json = tool.to_json()
            tool_size = len(json.dumps(tool_json))

            if total_size + tool_size + 100 > max_payload_size:
                next_cursor = tool.name
                break

            tools_json.append(tool_json)
            total_size += tool_size

        result = {"tools": tools_json}
        if next_cursor:
            result["nextCursor"] = next_cursor

        await self._reply_result(request_id, result)

    async def _handle_tool_call(
        self, request_id: int, params: dict[str, Any]
    ):
        """
        handles tool call requests.
        """
        logger.info(
            t('[MCP] 收到工具调用请求! ID={value1}, 参数={value3}', value1=request_id, value3=params)
        )

        tool_name = params.get("name")
        if not tool_name:
            await self._reply_error(request_id, "Missing tool name")
            return

        logger.info(t('[MCP] 尝试调用工具: {value1}', value1=tool_name))

        if tool_name in self._disabled_tool_names():
            await self._reply_error(
                request_id, f"Tool disabled: {tool_name}"
            )
            return

        # Find the tool
        tool = None
        for item in self.tools:
            if item.name == tool_name:
                tool = item
                break

        if not tool:
            await self._reply_error(
                request_id, f"Unknown tool: {tool_name}"
            )
            return

        # Get parameters
        arguments = params.get("arguments", {})

        logger.info(t('[MCP] 开始执行工具 {value1}, 参数: {value3}', value1=tool_name, value3=arguments))

        # Asynchronously calling tools
        try:
            result = await tool.call(arguments)
            logger.info(t('[MCP] 工具 {value1} 执行成功，结果: {value3}', value1=tool_name, value3=result))
            await self._reply_result(request_id, json.loads(result))
        except Exception as e:
            logger.error(
                t('[MCP] 工具 {value1} 执行失败: {value3}', value1=tool_name, value3=e), exc_info=True
            )
            await self._reply_error(request_id, str(e))

    async def _parse_capabilities(self, capabilities):
        """
        Parse capabilities.
        """
        vision = capabilities.get("vision", {})
        if vision and isinstance(vision, dict):
            url = vision.get("url")
            token = vision.get("token")
            if url:
                camera = self._camera
                if camera is None:
                    from src.mcp.tools.camera import create_camera

                    camera = create_camera()
                    self._camera = camera
                camera.set_explain_url(url)
                if token:
                    camera.set_explain_token(token)
                logger.info(f"Vision service configured with URL: {url}")

    async def _reply_result(self, request_id: int, result: Any):
        """
        Send successful response Should .
        """
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }

        result_len = len(json.dumps(result))
        logger.info(
            t('[MCP] 发送成功响应: ID={value1}, 结果长度={value3}', value1=request_id, value3=result_len)
        )

        if self._send_callback:
            await self._send_callback(json.dumps(payload))
        else:
            logger.error(t("[MCP] 发送回调未设置!"))

    async def _reply_error(self, request_id: int, message: str):
        """
        send an error response.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32603, "message": message},
        }

        logger.error(
            t('[MCP] 发送错误响应: ID={value1}, 错误={value3}', value1=request_id, value3=message)
        )

        if self._send_callback:
            await self._send_callback(json.dumps(payload))
