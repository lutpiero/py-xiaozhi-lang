"""Session control: listening/speaking state machine and protocol transmission.

is separated from the UI side SessionActions (button copy/mode): here it is only responsible for connect /
listen / abort / TTS loopback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.constants.constants import DeviceState, ListeningMode
from src.core.event_bus import Events
from src.i18n import t
from src.logging import get_logger

if TYPE_CHECKING:
    from src.core.event_bus import EventBus
    from src.core.protocol_manager import ProtocolManager
    from src.core.state_manager import StateManager
    from src.plugins.manager import PluginManager

logger = get_logger()


class ConversationSession:
    """Application-level session controller."""

    def __init__(
        self,
        state: "StateManager",
        protocol: "ProtocolManager",
        plugins: "PluginManager",
        event_bus: Optional["EventBus"] = None,
    ) -> None:
        self.state = state
        self.protocol = protocol
        self.plugins = plugins
        self._event_bus = event_bus
        self._aborted = False
        # MCP tool configuration reconnection, etc.: keep IDLE after the channel is opened, and do not automatically enter application-level session logic such as listening
        self._keep_idle_on_channel_open = False

    # -------------------------
    # Event subscription
    # -------------------------
    def bind_events(self, event_bus: "EventBus") -> None:
        """Subscribe to protocol/status related events (can be called repeatedly, subject to the last time)."""
        self._event_bus = event_bus
        event_bus.on(Events.AUDIO_CHANNEL_OPENED, self._on_audio_channel_opened)
        event_bus.on(Events.AUDIO_CHANNEL_CLOSED, self._on_audio_channel_closed)
        event_bus.on(Events.INCOMING_JSON, self._on_incoming_json)
        # Note: INCOMING_AUDIO takes the direct channel and no longer passes EventBus
        event_bus.on(Events.NETWORK_ERROR, self._on_network_error)
        event_bus.on(Events.DEVICE_STATE_CHANGED, self._on_device_state_changed)
        event_bus.on(
            Events.PROTOCOL_RECONNECT_REQUEST, self._on_protocol_reconnect_request
        )

    # -------------------------
    # Event handler
    # -------------------------
    async def _on_audio_channel_opened(self, _=None) -> None:
        if self._keep_idle_on_channel_open:
            self._keep_idle_on_channel_open = False
            self.state.set_keep_listening(False)
            await self.state.set_device_state(DeviceState.IDLE)
            logger.info(t("协议通道已打开（配置重连）：保持空闲，不进入聆听"))
            return
        await self.state.set_device_state(DeviceState.LISTENING)

    async def _on_audio_channel_closed(self, _=None) -> None:
        await self.state.set_device_state(DeviceState.IDLE)

    async def _on_network_error(self, error_message: str = None) -> None:
        """Network error: Stop continuous listening and reset the device status to IDLE."""
        self.state.set_keep_listening(False)
        try:
            if not self.state.is_idle():
                await self.state.set_device_state(DeviceState.IDLE)
        except Exception as e:
            logger.error(t('网络错误后复位设备状态失败: {value1}', value1=e), exc_info=True)

    async def _on_device_state_changed(self, data: dict) -> None:
        new_state = data.get("new_state")
        if new_state:
            await self.plugins.notify_device_state_changed(new_state)
            if new_state == DeviceState.LISTENING:
                self._aborted = False

    async def _on_incoming_json(self, json_data: dict) -> None:
        try:
            msg_type = json_data.get("type") if isinstance(json_data, dict) else None
            logger.info(t('收到JSON消息: type={value1}', value1=msg_type))

            if msg_type == "tts":
                state = json_data.get("state")
                if state == "start":
                    await self._handle_tts_start()
                elif state == "stop":
                    await self._handle_tts_stop()

            await self.plugins.notify_incoming_json(json_data)

        except Exception as e:
            logger.error(t('处理 JSON 消息失败: {value1}', value1=e), exc_info=True)

    async def _handle_tts_start(self) -> None:
        if (
            self.state.keep_listening
            and self.state.listening_mode == ListeningMode.REALTIME
        ):
            await self.state.set_device_state(DeviceState.LISTENING)
        else:
            await self.state.set_device_state(DeviceState.SPEAKING)

    async def _handle_tts_stop(self) -> None:
        # If you want to continue listening, try to listen first, then clear the queue and change the status
        if not self.state.keep_listening:
            await self.state.set_device_state(DeviceState.IDLE)
            return

        # realtime is usually still in the listen, there is no need to send it again.
        if self.state.listening_mode != ListeningMode.REALTIME:
            if self.protocol.is_audio_channel_opened():
                try:
                    await self.protocol.send_start_listening(self.state.listening_mode)
                except Exception as e:
                    logger.warning(
                        t('TTS 结束后重新 listen 失败: {value1}', value1=e),
                        exc_info=True,
                    )
            else:
                logger.warning(t("TTS 结束但协议通道已关闭，跳过重新 listen"))

        try:
            audio_plugin = self.plugins.get_plugin("audio")
            if audio_plugin and audio_plugin.codec:
                await audio_plugin.codec.clear_audio_queue()
        except Exception as e:
            logger.warning(t('清空音频队列失败: {value1}', value1=e), exc_info=True)

        await self.state.set_device_state(DeviceState.LISTENING)

    # -------------------------
    # Operation method
    # -------------------------
    async def connect_protocol(self) -> bool:
        if self.protocol.is_audio_channel_opened():
            return True

        opened = await self.protocol.connect()
        if opened:
            await self.plugins.notify_protocol_connected(self.protocol.protocol)
        return opened

    async def _on_protocol_reconnect_request(self, _=None) -> None:
        """The MCP tool list changes after the settings are saved: disconnect and reconnect if connected, so that the server can relist.

        Only refreshes the protocol/tool view and does not restore the listening session (avoid entering "Listening" after saving settings).
        """
        try:
            if not self.protocol.is_audio_channel_opened():
                logger.info(t("MCP 工具配置已更新（当前未连接，下次连接生效）"))
                return
            logger.info(t("MCP 工具配置已更新，正在重连协议…"))
            # Interrupt the ongoing listening/speaking semantics to avoid continuing after reconnection keep_listening
            self.state.set_keep_listening(False)
            self._aborted = False
            self._keep_idle_on_channel_open = True
            try:
                await self.protocol.disconnect()
                ok = await self.connect_protocol()
            except Exception:
                self._keep_idle_on_channel_open = False
                raise
            if ok:
                # Double insurance: if the OPENED callback sequence is abnormal, it will still be idle
                if not self.state.is_idle():
                    await self.state.set_device_state(DeviceState.IDLE)
                logger.info(t("协议重连成功（新 tools/list 将在握手时生效，保持空闲）"))
            else:
                self._keep_idle_on_channel_open = False
                logger.warning(t("协议重连失败，请手动重新连接"))
        except Exception as e:
            self._keep_idle_on_channel_open = False
            logger.error(t('协议重连失败: {value1}', value1=e), exc_info=True)

    async def start_listening(self, mode: ListeningMode) -> None:
        ok = await self.connect_protocol()
        if not ok:
            return

        self.state.set_listening_mode(mode)
        self.state.set_keep_listening(mode != ListeningMode.MANUAL)
        await self.protocol.send_start_listening(mode)
        await self.state.set_device_state(DeviceState.LISTENING)

    async def stop_listening(self) -> None:
        self.state.set_keep_listening(False)
        await self.protocol.send_stop_listening()
        await self.state.set_device_state(DeviceState.IDLE)

    async def start_listening_manual(self) -> None:
        ok = await self.connect_protocol()
        if not ok:
            return

        self.state.set_keep_listening(False)

        if self.state.is_speaking():
            logger.info(t("说话中发送打断"))
            await self.protocol.send_abort_speaking(None)
            await self.state.set_device_state(DeviceState.IDLE)

        await self.protocol.send_start_listening(ListeningMode.MANUAL)
        await self.state.set_device_state(DeviceState.LISTENING)

    async def stop_listening_manual(self) -> None:
        await self.protocol.send_stop_listening()
        await self.state.set_device_state(DeviceState.IDLE)

    async def start_auto_conversation(self) -> None:
        ok = await self.connect_protocol()
        if not ok:
            return

        mode = (
            ListeningMode.REALTIME
            if self.state.aec_enabled
            else ListeningMode.AUTO_STOP
        )
        self.state.set_listening_mode(mode)
        self.state.set_keep_listening(True)

        await self.protocol.send_start_listening(mode)
        await self.state.set_device_state(DeviceState.LISTENING)

    async def abort_speaking(self, reason: str) -> None:
        # When the automatic dialogue is still listening, return to listening after interrupting, do not stop at idle
        if self._aborted:
            logger.debug(t('已经中止，忽略重复请求: {value1}', value1=reason))
            return

        logger.info(t('中止语音输出: {value1}', value1=reason))
        self._aborted = True
        self.state.set_aborted(True)
        try:
            if self.protocol.is_audio_channel_opened():
                await self.protocol.send_abort_speaking(reason)
        except Exception as e:
            logger.warning(t('发送 abort 失败: {value1}', value1=e), exc_info=True)

        if self.state.keep_listening:
            if self.state.listening_mode != ListeningMode.REALTIME:
                if self.protocol.is_audio_channel_opened():
                    try:
                        await self.protocol.send_start_listening(
                            self.state.listening_mode
                        )
                    except Exception as e:
                        logger.warning(
                            t('打断后重新 listen 失败: {value1}', value1=e),
                            exc_info=True,
                        )
            await self.state.set_device_state(DeviceState.LISTENING)
            self._aborted = False
            self.state.set_aborted(False)
            logger.debug(t("打断后已恢复持续监听"))
        else:
            await self.state.set_device_state(DeviceState.IDLE)
