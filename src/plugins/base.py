"""Plug-in base class.

uses the PluginContext and PluginCommands interfaces to interact with core services.
"""

import asyncio
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext
    from src.core.resource_pool import ResourcePool


class Plugin:
    """Plug-in base class.

    The plug-in obtains status through PluginContext and performs operations through PluginCommands.

    Properties:
        name: Plug-in name, used for dependency declaration and log
        priority: Priority, the smaller the value, the higher the priority (range: 1-100)
        requires: list of dependent plug-in names, which will be automatically injected by PluginManager

    Usage:
        class MyPlugin(Plugin):
            name = "my_plugin"
            priority = 50
            requires = ["audio"]

            async def setup(self, ctx, cmd):
                await super().setup(ctx, cmd)
                # self.deps["audio"] gives the AudioPlugin instance
    """

    name: str = "plugin"
    priority: int = 50  # Priority, the smaller the value, the higher the priority (range: 1-100)
    requires: List[str] = []  # Dependent plug-in name list

    def __init__(self) -> None:
        self._started = False
        self._failed = False
        self._ctx: "PluginContext" = None
        self._cmd: "PluginCommands" = None
        self._deps: dict[str, "Plugin"] = {}  # Dependency injection plug-in instance

    @property
    def ctx(self) -> "PluginContext":
        """
        Get the plug-in context.
        """
        return self._ctx

    @property
    def cmd(self) -> "PluginCommands":
        """
        Get the plug-in command interface.
        """
        return self._cmd

    @property
    def deps(self) -> dict[str, "Plugin"]:
        """Get the dependent plug-in instance."""
        return self._deps

    @property
    def failed(self) -> bool:
        """Whether the plug-in has been marked as failed (setup/start) Failure or dependency failure)."""
        return self._failed

    def mark_failed(self) -> None:
        """Mark plug-in failed, subsequent start/notify will be skipped."""
        self._failed = True

    def get_dep(self, name: str) -> Optional["Plugin"]:
        """Get the dependent plug-in with the specified name."""
        return self._deps.get(name)

    def _inject_dependency(self, name: str, plugin: "Plugin") -> None:
        """Inject dependent plug-in (called by PluginManager)."""
        self._deps[name] = plugin

    async def setup(self, ctx: "PluginContext", cmd: "PluginCommands") -> None:
        """Plug-in preparation phase.

        Args:
            ctx: Plug-in context (read-only state access)
            cmd: Plug-in command interface (execution operation)
        """
        self._ctx = ctx
        self._cmd = cmd
        await asyncio.sleep(0)

    async def start(self) -> None:
        """
        Plug-in start (usually called after the protocol connection is established).
        """
        self._started = True
        await asyncio.sleep(0)

    async def on_protocol_connected(self, protocol: Any) -> None:
        """
        Notification after the protocol channel is established.
        """
        await asyncio.sleep(0)

    async def on_incoming_json(self, message: Any) -> None:
        """
        Notification when receiving JSON message.
        """
        await asyncio.sleep(0)

    async def on_incoming_audio(self, data: bytes) -> None:
        """
        Notification when audio data is received.
        """
        await asyncio.sleep(0)

    async def on_device_state_changed(self, state: Any) -> None:
        """
        Device status change notification.
        """
        await asyncio.sleep(0)

    async def stop(self) -> None:
        """
        Plug-in stop.
        """
        self._started = False
        await asyncio.sleep(0)

    def register_resources(self, pool: "ResourcePool") -> None:
        """
        Register the cleanup function with the resource pool. Subclasses override this method to register resources that need to be released.
        Resources are released in the reverse order of registration, with those registered first and then released.

        Args:
            pool: Resource pool instance
        """
        pass
