"""Resource Pool.

Unified resource registration and release mechanism. All resources that need to be cleaned up (C extensions, audio streams, network connections, etc.)
is registered in the pool and released uniformly in the reverse order of registration during shutdown to avoid repeated releases and omissions.
"""
import asyncio
from typing import Awaitable, Callable, Union

from src.i18n import t
from src.logging import get_logger

logger = get_logger()

CleanupFunc = Callable[[], Union[None, Awaitable[None]]]


class ResourcePool:
    """Resource Pool — Register the cleaning function and release it uniformly in reverse order.

    Usage:
        pool = ResourcePool()
        pool.register("opus_codec", opus_codec.close)
        pool.register("audio_stream", stream_manager.stop)
        await pool.shutdown()
    """

    def __init__(self):
        self._resources: list[tuple[str, CleanupFunc]] = []
        self._shutting_down = False

    def register(self, name: str, cleanup: CleanupFunc) -> None:
        """registers a cleanup function.

        Args:
            name: Resource name (for logging and troubleshooting)
            cleanup: Cleanup function, which can be a normal function or async function
        """
        if self._shutting_down:
            logger.warning(t('资源池正在关闭，跳过注册: {value1}', value1=name))
            return
        self._resources.append((name, cleanup))

    async def shutdown(self) -> None:
        """Release all registered resources and execute them in the reverse order of registration."""
        if self._shutting_down:
            return
        self._shutting_down = True

        for name, cleanup in reversed(self._resources):
            try:
                result = cleanup()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(t('释放资源失败 [{value1}]: {value3}', value1=name, value3=e), exc_info=True)

        self._resources.clear()
        logger.debug(t("资源池已清空"))
