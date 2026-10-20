"""task manager.

Unifiedly manages the creation, tracking and cleanup of asynchronous tasks.
"""
import asyncio
from typing import Any, Awaitable, Callable, Optional

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


class TaskManager:
    """Asynchronous Task Manager.

    Responsibilities:
    - Create and track asynchronous tasks
    - Cancel all tasks when closing
    - Provides thread-safe task scheduling

    Usage:
        tm = TaskManager()
        tm.set_loop(asyncio.get_running_loop())
        task = tm.spawn(some_coroutine(), "task_name")
        tm.schedule_nowait(some_function, arg1, arg2)
        await tm.cancel_all()
    """

    def __init__(self):
        self._tasks: set[asyncio.Task] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._shutdown_event: Optional[asyncio.Event] = None
        self._running: bool = False

    def initialize(self, loop: asyncio.AbstractEventLoop = None) -> None:
        """Initialize the task manager.

        Args:
            loop: event loop, when None, use the currently running loop
        """
        self._loop = loop or asyncio.get_running_loop()
        self._shutdown_event = asyncio.Event()
        self._running = True
        logger.debug(t("TaskManager 已初始化"))

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """
        Gets the event loop.
        """
        return self._loop

    @property
    def running(self) -> bool:
        """
        Is it running.
        """
        return self._running

    @property
    def shutdown_event(self) -> Optional[asyncio.Event]:
        """
        Gets the shutdown event.
        """
        return self._shutdown_event

    def spawn(self, coro: Awaitable[Any], name: str) -> Optional[asyncio.Task]:
        """Creates an asynchronous task and tracks the task object created by

        Args:
            coro: Coroutine object
            name: task name

        Returns:
            , returns if the application is closing None
        """
        # Check if it is shutting down
        if not self._running or (
            self._shutdown_event and self._shutdown_event.is_set()
        ):
            logger.debug(t('跳过任务创建（应用正在关闭）: {value1}', value1=name))
            return None

        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)

        def _on_done(t: asyncio.Task):
            self._tasks.discard(t)
            if not t.cancelled():
                exc = t.exception()
                if exc:
                    # done callback has no active exception context and must pass the exc body
                    logger.error(t('任务 {value1} 异常结束: {value3}', value1=name, value3=exc), exc_info=exc)

        task.add_done_callback(_on_done)
        return task

    def schedule_nowait(self, fn: Callable, *args, **kwargs) -> None:
        """Thread-safely schedules callable objects.

        If the callable object returns to the coroutine, the task will be automatically created.

        Args:
            fn: Callable object
            *args: Positional parameters
            **kwargs: Keyword parameters
        """
        # Checks for shutdown in progress - silently rejects
        if not self._running or (
            self._shutdown_event and self._shutdown_event.is_set()
        ):
            return

        if not self._loop or self._loop.is_closed():
            # Silently skips when closing, does not print warnings
            return

        def _runner():
            try:
                result = fn(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    task = self.spawn(
                        result, name=f"scheduled:{getattr(fn, '__name__', 'anon')}"
                    )
                    if task is None:
                        result.close()
            except Exception as e:
                logger.error(t('调度的可调用执行失败: {value1}', value1=e), exc_info=True)

        self._loop.call_soon_threadsafe(_runner)

    async def wait_shutdown(self) -> None:
        """
        Waits for shutdown signal.
        """
        if self._shutdown_event:
            await self._shutdown_event.wait()

    def request_shutdown(self) -> None:
        """
        Requests shutdown.
        """
        if self._shutdown_event and not self._shutdown_event.is_set():
            self._shutdown_event.set()
            logger.info(t("收到关闭请求"))

    async def cancel_all(self) -> None:
        """Cancel all tracked tasks.

        will wait for all tasks to be completed or canceled.
        """
        self._running = False

        if self._shutdown_event:
            self._shutdown_event.set()

        if not self._tasks:
            return

        logger.info(t('正在取消 {value1} 个任务...', value1=len(self._tasks)))

        # Cancel all tasks
        for task in list(self._tasks):
            if not task.done():
                task.cancel()

        # Waits for all tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        logger.info(t("所有任务已取消"))

    def task_count(self) -> int:
        """
        Gets the current number of tasks.
        """
        return len(self._tasks)

    def get_task_names(self) -> list[str]:
        """
        Gets all task names.
        """
        return [t.get_name() for t in self._tasks if not t.done()]
