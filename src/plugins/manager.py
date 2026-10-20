"""Plug-in manager.

manages the plug-in life cycle and supports dependency declaration and topological sorting.
"""
from typing import TYPE_CHECKING, Any, List, Optional

from src.i18n import t
from src.logging import get_logger

from .base import Plugin

if TYPE_CHECKING:
    from src.bootstrap.protocols import PluginCommands, PluginContext

logger = get_logger()


class PluginManager:
    """Plug-in manager.

    Responsibilities:
    - Sort by dependency topology
    - Automatically inject plug-in dependencies
    - Unify setup/start/stop broadcast
    - Error isolation, the failure of a single plug-in does not affect other plug-ins
    - Failure mark Skip downstream when dependency fails
    """

    def __init__(self) -> None:
        self._plugins: List[Plugin] = []
        self._by_name: dict[str, Plugin] = {}
        self._sorted: bool = False

    def register(self, *plugins: Plugin) -> None:
        """Register the plug-in.

        Sort by priority first, and then sort by dependency topology during setup_all.
        """
        sorted_plugins = sorted(plugins, key=lambda p: getattr(p, "priority", 50))
        for p in sorted_plugins:
            if p not in self._plugins:
                self._plugins.append(p)
                try:
                    name = getattr(p, "name", None)
                    if isinstance(name, str) and name:
                        self._by_name[name] = p
                except Exception as e:
                    logger.error(t('插件注册失败: {value1}', value1=e), exc_info=True)
        self._sorted = False

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get plug-in instance based on plug-in name."""
        return self._by_name.get(name)

    def is_failed(self, name: str) -> bool:
        """Whether the plug-in failed (not registered is considered a failure)."""
        plugin = self._by_name.get(name)
        return plugin is None or plugin.failed

    def failed_plugins(self) -> List[str]:
        """Returns all failed plug-in names."""
        return [
            p.name
            for p in self._plugins
            if getattr(p, "name", None) and p.failed
        ]

    def _dependencies_ok(self, plugin: Plugin) -> bool:
        """Check whether the dependencies declared by the plug-in are all available (registered and not failed)."""
        requires = getattr(plugin, "requires", []) or []
        for dep_name in requires:
            dep = self._by_name.get(dep_name)
            if dep is None:
                logger.warning(
                    t('插件 {value1} 依赖 {value3} 未注册', value1=getattr(plugin, 'name', 'unknown'), value3=dep_name)
                )
                return False
            if dep.failed:
                logger.warning(
                    t('插件 {value1} 依赖 {value3} 已失败，跳过', value1=getattr(plugin, 'name', 'unknown'), value3=dep_name)
                )
                return False
        return True

    def _active_plugins(self) -> List[Plugin]:
        """Non-failed plug-in list."""
        return [p for p in self._plugins if not p.failed]

    def _topological_sort(self) -> List[Plugin]:
        """Topological sorting of the plug-in list, ensuring that dependencies are initialized before dependencies.

        Returns:
            Sorted plug-in list

        Raises:
            ValueError: There is a circular dependency
        """
        # Build dependency graph
        in_degree: dict[str, int] = {}
        dependents: dict[str, List[str]] = {}  # is relied upon by

        for p in self._plugins:
            name = getattr(p, "name", "")
            if name:
                in_degree[name] = 0
                dependents[name] = []

        for p in self._plugins:
            name = getattr(p, "name", "")
            requires = getattr(p, "requires", []) or []
            for dep in requires:
                if dep in self._by_name:
                    in_degree[name] = in_degree.get(name, 0) + 1
                    dependents[dep].append(name)
                else:
                    logger.warning(t('插件 {value1} 声明的依赖 {value3} 未注册，忽略', value1=name, value3=dep))

        # Kahn algorithm
        queue = [name for name, degree in in_degree.items() if degree == 0]
        result: List[Plugin] = []

        while queue:
            # Selects the node with the smallest priority from the node with in-degree 0
            queue.sort(
                key=lambda n: getattr(self._by_name.get(n), "priority", 50)
            )
            current = queue.pop(0)
            plugin = self._by_name.get(current)
            if plugin:
                result.append(plugin)

            for dependent in dependents.get(current, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len([p for p in self._plugins if getattr(p, "name", "")]):
            raise ValueError(t("插件存在循环依赖"))

        # Add plug-ins without name to the end
        unnamed = [p for p in self._plugins if not getattr(p, "name", "")]
        result.extend(unnamed)

        return result

    def _inject_dependencies(self) -> None:
        """Injects its declared dependencies into each plug-in."""
        for p in self._plugins:
            requires = getattr(p, "requires", []) or []
            for dep_name in requires:
                dep_plugin = self._by_name.get(dep_name)
                if dep_plugin:
                    p._inject_dependency(dep_name, dep_plugin)
                    logger.debug(t('注入依赖: {value1} <- {value3}', value1=p.name, value3=dep_name))

    async def setup_all(self, ctx: "PluginContext", cmd: "PluginCommands") -> None:
        """Initialize all plug-ins.

        Initialized in the order after topological sorting, automatically inject dependencies.
        setup failure or plug-in dependency failure will be mark_failed and skip subsequent life cycles.

        Args:
            ctx: Plug-in context
            cmd: Plug-in command interface
        """
        # Topological sorting
        if not self._sorted:
            try:
                self._plugins = self._topological_sort()
                self._sorted = True
                logger.info(
                    t('插件拓扑排序完成: {value1}', value1=[p.name for p in self._plugins if hasattr(p, 'name')])
                )
            except ValueError as e:
                logger.error(t('插件排序失败: {value1}', value1=e), exc_info=True)
                # Demoted to prioritization
                self._plugins.sort(key=lambda p: getattr(p, "priority", 50))

        # Inject dependencies
        self._inject_dependencies()

        # initialization
        for p in list(self._plugins):
            name = getattr(p, "name", "unknown")
            if p.failed:
                continue
            if not self._dependencies_ok(p):
                p.mark_failed()
                logger.error(t('插件 {value1} 因依赖失败被跳过 setup', value1=name))
                continue
            try:
                await p.setup(ctx, cmd)
            except Exception as e:
                p.mark_failed()
                logger.error(t('插件 {value1} setup 失败: {value3}', value1=name, value3=e), exc_info=True)

    async def start_all(self) -> None:
        """Start all plug-ins that have not failed."""
        for p in list(self._plugins):
            if p.failed:
                continue
            if not self._dependencies_ok(p):
                p.mark_failed()
                logger.error(
                    t('插件 {value1} 因依赖失败被跳过 start', value1=getattr(p, 'name', 'unknown'))
                )
                continue
            try:
                await p.start()
            except Exception as e:
                p.mark_failed()
                logger.error(
                    t('插件 {value1} start 失败: {value3}', value1=getattr(p, 'name', 'unknown'), value3=e),
                    exc_info=True,
                )

    async def notify_protocol_connected(self, protocol: Any) -> None:
        """Notifies that the protocol is connected."""
        for p in self._active_plugins():
            try:
                if p.on_protocol_connected:
                    await p.on_protocol_connected(protocol)
            except Exception as e:
                logger.error(
                    t('插件 {value1} on_protocol_connected 失败: {value3}', value1=getattr(p, 'name', 'unknown'), value3=e),
                    exc_info=True,
                )

    async def notify_incoming_json(self, message: Any) -> None:
        """Notifies that JSON has been received Message."""
        for p in self._active_plugins():
            try:
                await p.on_incoming_json(message)
            except Exception as e:
                logger.error(
                    t('插件 {value1} on_incoming_json 失败: {value3}', value1=getattr(p, 'name', 'unknown'), value3=e),
                    exc_info=True,
                )

    async def notify_incoming_audio(self, data: bytes) -> None:
        """Notifies of receipt of audio data."""
        for p in self._active_plugins():
            try:
                await p.on_incoming_audio(data)
            except Exception as e:
                logger.error(
                    t('插件 {value1} on_incoming_audio 失败: {value3}', value1=getattr(p, 'name', 'unknown'), value3=e),
                    exc_info=True,
                )

    async def notify_device_state_changed(self, state: Any) -> None:
        """Notifies of device status change."""
        for p in self._active_plugins():
            try:
                await p.on_device_state_changed(state)
            except Exception as e:
                logger.error(
                    t('插件 {value1} on_device_state_changed 失败: {value3}', value1=getattr(p, 'name', 'unknown'), value3=e),
                    exc_info=True,
                )

    async def stop_all(self) -> None:
        """Stops all plug-ins (in reverse order; failed plug-ins still try to stop for cleaning)."""
        for p in reversed(self._plugins):
            try:
                await p.stop()
            except Exception as e:
                logger.error(
                    t('插件 {value1} stop 失败: {value3}', value1=getattr(p, 'name', 'unknown'), value3=e),
                    exc_info=True,
                )
