"""Protocol manager.

to encapsulate communication protocol operations and forward messages through the event bus.
Audio data goes through the direct channel (bounded queue single consumer) to avoid per-frame create_task stack.
"""
import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from src.constants.constants import ListeningMode
from src.core.event_bus import EventBus, Events
from src.i18n import t
from src.logging import get_logger

if TYPE_CHECKING:
    from src.core.task_manager import TaskManager
    from src.protocols.protocol import Protocol

logger = get_logger()

# Audio callback type
AudioCallback = Callable[[bytes], Awaitable[None]]

# Inbound audio bounded queue: discard the oldest frame when full to prevent the event loop from being flooded with tasks
_INCOMING_AUDIO_QUEUE_SIZE = 64


class ProtocolTransport:
    """is responsible for protocol creation and connection management."""

    def __init__(
        self,
        event_bus: EventBus,
        task_manager: Optional["TaskManager"] = None,
    ):
        self._event_bus = event_bus
        self._task_manager = task_manager
        self._protocol: Optional["Protocol"] = None
        self._connect_lock = asyncio.Lock()
        self._incoming_audio_handler: Optional[AudioCallback] = None

        # Bounded audio queue Single consumer (replaces per-packet create_task)
        self._audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(
            maxsize=_INCOMING_AUDIO_QUEUE_SIZE
        )
        self._audio_consumer_task: Optional[asyncio.Task] = None
        self._audio_consumer_running = False

    def set_task_manager(self, task_manager: "TaskManager") -> None:
        """Injection TaskManager (can be bound after the container is initialized)."""
        self._task_manager = task_manager

    @property
    def protocol(self) -> Optional["Protocol"]:
        return self._protocol

    def set_protocol(self, protocol_type: str) -> None:
        logger.debug(t('设置协议类型: {value1}', value1=protocol_type))

        if protocol_type == "mqtt":
            from src.protocols.mqtt_protocol import MqttProtocol

            self._protocol = MqttProtocol(asyncio.get_running_loop())
        else:
            from src.protocols.websocket_protocol import WebsocketProtocol

            self._protocol = WebsocketProtocol()

        self._setup_callbacks()
        self._ensure_audio_consumer()

    def set_audio_handler(self, handler: Optional[AudioCallback]) -> None:
        self._incoming_audio_handler = handler
        self._ensure_audio_consumer()

    def _setup_callbacks(self) -> None:
        if not self._protocol:
            return

        self._protocol.on_network_error(self._on_network_error)
        self._protocol.on_incoming_json(self._on_incoming_json)
        self._protocol.on_incoming_audio(self._on_incoming_audio)
        self._protocol.on_audio_channel_opened(self._on_audio_channel_opened)
        self._protocol.on_audio_channel_closed(self._on_audio_channel_closed)

    def _spawn(self, coro: Awaitable, name: str) -> None:
        """and takes priority in TaskManager; otherwise local create_task and records exceptions."""
        if self._task_manager is not None:
            task = self._task_manager.spawn(coro, name=name)
            if task is None:
                # Closing: close unscheduled coroutines to avoid warnings
                if asyncio.iscoroutine(coro):
                    coro.close()
            return

        try:
            task = asyncio.create_task(coro, name=name)

            def _on_done(t: asyncio.Task) -> None:
                if t.cancelled():
                    return
                exc = t.exception()
                if exc:
                    logger.error(t('任务 {value1} 异常结束: {value3}', value1=name, value3=exc), exc_info=exc)

            task.add_done_callback(_on_done)
        except Exception as e:
            logger.error(t('创建任务失败 {value1}: {value3}', value1=name, value3=e), exc_info=True)
            if asyncio.iscoroutine(coro):
                coro.close()

    def _ensure_audio_consumer(self) -> None:
        """ensures inbound audio consumer Running (idempotent)."""
        if self._audio_consumer_running:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return

        self._audio_consumer_running = True
        if self._task_manager is not None:
            self._audio_consumer_task = self._task_manager.spawn(
                self._audio_consumer_loop(), name="protocol:audio_consumer"
            )
        else:
            self._audio_consumer_task = asyncio.create_task(
                self._audio_consumer_loop(), name="protocol:audio_consumer"
            )

        if self._audio_consumer_task is None:
            self._audio_consumer_running = False
            return

        def _on_done(t: asyncio.Task) -> None:
            self._audio_consumer_running = False
            self._audio_consumer_task = None
            if t.cancelled():
                return
            # TaskManager.spawn has recorded exceptions; local create_task time-replenishing logs
            if self._task_manager is None:
                exc = t.exception()
                if exc:
                    logger.error(t('音频 consumer 异常结束: {value1}', value1=exc), exc_info=exc)

        self._audio_consumer_task.add_done_callback(_on_done)

    async def _audio_consumer_loop(self) -> None:
        """Single consumer processes inbound audio serially, avoiding per-frame Task explosion."""
        while True:
            data = await self._audio_queue.get()
            if data is None:
                # Poison pill: Exit
                return
            try:
                if self._incoming_audio_handler:
                    await self._incoming_audio_handler(data)
                else:
                    await self._event_bus.emit(Events.INCOMING_AUDIO, data)
            except Exception as e:
                logger.error(t('处理入站音频失败: {value1}', value1=e), exc_info=True)

    def _enqueue_audio(self, data: bytes) -> None:
        """Bounded enqueue: If full, discard the oldest frame and put the latest frame."""
        try:
            self._audio_queue.put_nowait(data)
            return
        except asyncio.QueueFull:
            pass

        # discards the oldest
        try:
            self._audio_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            self._audio_queue.put_nowait(data)
        except asyncio.QueueFull:
            logger.warning(t("入站音频队列仍满，丢弃当前帧"))

    async def _stop_audio_consumer(self) -> None:
        """Stop consumer and clear the queue."""
        if self._audio_consumer_task and not self._audio_consumer_task.done():
            try:
                self._audio_queue.put_nowait(None)
            except asyncio.QueueFull:
                # Forces a position to be released when the queue is full
                try:
                    self._audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    self._audio_queue.put_nowait(None)
                except asyncio.QueueFull:
                    self._audio_consumer_task.cancel()

            try:
                await self._audio_consumer_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(t('等待音频 consumer 退出时异常: {value1}', value1=e))

        self._audio_consumer_task = None
        self._audio_consumer_running = False

        # Clear the residue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _on_network_error(self, error_message: str = None) -> None:
        if error_message:
            logger.error(t('网络错误: {value1}', value1=error_message))
        await self._event_bus.emit(Events.NETWORK_ERROR, error_message)

    def _on_incoming_json(self, json_data: dict) -> None:
        self._spawn(
            self._event_bus.emit(Events.INCOMING_JSON, json_data),
            name="protocol:incoming_json",
        )

    def _on_incoming_audio(self, data: bytes) -> None:
        try:
            self._ensure_audio_consumer()
            self._enqueue_audio(data)
        except Exception as exc:
            logger.warning(t('分发音频数据失败: {value1}', value1=exc), exc_info=True)

    async def _on_audio_channel_opened(self) -> None:
        logger.info(t("协议通道已打开"))
        await self._event_bus.emit(Events.AUDIO_CHANNEL_OPENED)
        await self._event_bus.emit(Events.PROTOCOL_CONNECTED, self._protocol)

    async def _on_audio_channel_closed(self) -> None:
        logger.info(t("协议通道已关闭"))
        await self._event_bus.emit(Events.AUDIO_CHANNEL_CLOSED)
        await self._event_bus.emit(Events.PROTOCOL_DISCONNECTED)

    def is_audio_channel_opened(self) -> bool:
        try:
            return bool(self._protocol and self._protocol.is_audio_channel_opened())
        except Exception:
            logger.debug(t("检查音频通道状态时发生异常"), exc_info=True)
            return False

    async def connect(self, timeout: float = 12.0) -> bool:
        if self.is_audio_channel_opened():
            return True

        if not self._protocol:
            logger.error(t("协议未初始化"))
            return False

        async with self._connect_lock:
            if self.is_audio_channel_opened():
                return True

            try:
                opened = await asyncio.wait_for(
                    self._protocol.open_audio_channel(),
                    timeout=timeout,
                )
                if not opened:
                    logger.error(t("协议连接失败"))
                    return False

                logger.info(t("协议连接已建立"))
                return True

            except asyncio.TimeoutError:
                logger.error(t("协议连接超时"))
                return False
            except Exception as e:
                logger.error(t('协议连接异常: {value1}', value1=e), exc_info=True)
                return False

    async def disconnect(self) -> None:
        if self._protocol:
            try:
                await self._protocol.close_audio_channel()
            except Exception as e:
                logger.error(t('关闭协议失败: {value1}', value1=e), exc_info=True)
        await self._stop_audio_consumer()


class ProtocolGateway:
    """is the gateway responsible for message sending."""

    def __init__(self, transport: ProtocolTransport):
        self._transport = transport

    async def send_audio(self, data: bytes) -> None:
        protocol = self._transport.protocol
        if protocol and self._transport.is_audio_channel_opened():
            await protocol.send_audio(data)
        else:
            logger.debug(t("音频通道未打开，跳过发送音频数据"))

    async def send_text(self, text: str) -> None:
        protocol = self._transport.protocol
        if protocol:
            await protocol.send_text(text)

    async def send_start_listening(self, mode: ListeningMode) -> None:
        protocol = self._transport.protocol
        if protocol and self._transport.is_audio_channel_opened():
            await protocol.send_start_listening(mode)
        else:
            logger.warning(t("音频通道未打开，跳过 send_start_listening"))

    async def send_stop_listening(self) -> None:
        protocol = self._transport.protocol
        if protocol and self._transport.is_audio_channel_opened():
            await protocol.send_stop_listening()
        else:
            logger.debug(t("音频通道未打开，跳过 send_stop_listening"))

    async def send_abort_speaking(self, reason: str = None) -> None:
        protocol = self._transport.protocol
        if protocol:
            await protocol.send_abort_speaking(reason)

    async def send_wake_word_detected(self, wake_word: str) -> None:
        protocol = self._transport.protocol
        if protocol and self._transport.is_audio_channel_opened():
            await protocol.send_wake_word_detected(wake_word)
        else:
            logger.warning(t("音频通道未打开，跳过 send_wake_word_detected"))

    async def send_iot_descriptors(self, descriptors) -> None:
        protocol = self._transport.protocol
        if protocol:
            await protocol.send_iot_descriptors(descriptors)

    async def send_iot_states(self, states) -> None:
        protocol = self._transport.protocol
        if protocol:
            await protocol.send_iot_states(states)

    async def send_mcp_message(self, payload) -> None:
        protocol = self._transport.protocol
        if protocol:
            await protocol.send_mcp_message(payload)


class ProtocolManager:
    """exposes a unified interface to the outside, and internally combines Transport Gateway."""

    def __init__(
        self,
        event_bus: EventBus,
        task_manager: Optional["TaskManager"] = None,
    ):
        self._transport = ProtocolTransport(event_bus, task_manager=task_manager)
        self._gateway = ProtocolGateway(self._transport)

    def set_task_manager(self, task_manager: "TaskManager") -> None:
        self._transport.set_task_manager(task_manager)

    @property
    def protocol(self) -> Optional["Protocol"]:
        return self._transport.protocol

    def set_protocol(self, protocol_type: str) -> None:
        self._transport.set_protocol(protocol_type)

    def set_audio_handler(self, handler: Optional[AudioCallback]) -> None:
        self._transport.set_audio_handler(handler)

    def is_audio_channel_opened(self) -> bool:
        return self._transport.is_audio_channel_opened()

    async def connect(self, timeout: float = 12.0) -> bool:
        return await self._transport.connect(timeout)

    async def disconnect(self) -> None:
        await self._transport.disconnect()

    async def send_audio(self, data: bytes) -> None:
        await self._gateway.send_audio(data)

    async def send_text(self, text: str) -> None:
        await self._gateway.send_text(text)

    async def send_start_listening(self, mode: ListeningMode) -> None:
        await self._gateway.send_start_listening(mode)

    async def send_stop_listening(self) -> None:
        await self._gateway.send_stop_listening()

    async def send_abort_speaking(self, reason: str = None) -> None:
        await self._gateway.send_abort_speaking(reason)

    async def send_wake_word_detected(self, wake_word: str) -> None:
        await self._gateway.send_wake_word_detected(wake_word)

    async def send_iot_descriptors(self, descriptors) -> None:
        await self._gateway.send_iot_descriptors(descriptors)

    async def send_iot_states(self, states) -> None:
        await self._gateway.send_iot_states(states)

    async def send_mcp_message(self, payload) -> None:
        await self._gateway.send_mcp_message(payload)
