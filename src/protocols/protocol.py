import asyncio
import json

from src.constants.constants import AbortReason, ListeningMode
from src.i18n import t
from src.logging import get_logger

logger = get_logger()


class Protocol:
    def __init__(self):
        self.session_id = ""
        # The initialization callback function is None
        self._on_incoming_json = None
        self._on_incoming_audio = None
        self._on_audio_channel_opened = None
        self._on_audio_channel_closed = None
        self._on_network_error = None
        # New connection status change callback
        self._on_connection_state_changed = None
        self._on_reconnecting = None

        # Connection status and automatic reconnection (public, moved up from subclasses)
        self._is_closing = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5  # Reconnects 5 times by default
        self._auto_reconnect_enabled = False  # Automatic reconnection is disabled by default
        self._connection_monitor_task = None

    def on_incoming_json(self, callback):
        """
        Set the JSON message receiving callback function.
        """
        self._on_incoming_json = callback

    def on_incoming_audio(self, callback):
        """
        sets the audio data reception callback function.
        """
        self._on_incoming_audio = callback

    def on_audio_channel_opened(self, callback):
        """
        sets the audio channel open callback function.
        """
        self._on_audio_channel_opened = callback

    def on_audio_channel_closed(self, callback):
        """
        sets the audio channel close callback function.
        """
        self._on_audio_channel_closed = callback

    def on_network_error(self, callback):
        """
        Set the network error callback function.
        """
        self._on_network_error = callback

    def on_connection_state_changed(self, callback):
        """sets the connection status change callback function.

        Args:
            callback: callback function, receiving parameters (connected: bool, reason: str)
        """
        self._on_connection_state_changed = callback

    def on_reconnecting(self, callback):
        """sets the reconnection attempt callback function.

        Args:
            callback: callback function, receiving parameters (attempt: int, max_attempts: int)
        """
        self._on_reconnecting = callback

    async def send_text(self, message):
        """
        Sends a text message The abstract method of information needs to be implemented in the subclass.
        """
        raise NotImplementedError(t("send_text方法必须由子类实现"))

    async def send_audio(self, data: bytes):
        """
        Abstract method for sending audio data, which needs to be implemented in subclasses.
        """
        raise NotImplementedError(t("send_audio方法必须由子类实现"))

    def is_audio_channel_opened(self) -> bool:
        """
        Abstract method to check if the audio channel is open, needs to be implemented in the subclass.
        """
        raise NotImplementedError(t("is_audio_channel_opened方法必须由子类实现"))

    async def open_audio_channel(self) -> bool:
        """
        is an abstract method for opening the audio channel and needs to be implemented in a subclass.
        """
        raise NotImplementedError(t("open_audio_channel方法必须由子类实现"))

    async def close_audio_channel(self):
        """
        The abstract method of closing the audio channel needs to be implemented in the subclass.
        """
        raise NotImplementedError(t("close_audio_channel方法必须由子类实现"))

    async def send_abort_speaking(self, reason):
        """
        Sends a message to stop the voice.
        """
        message = {"session_id": self.session_id, "type": "abort"}
        if reason == AbortReason.WAKE_WORD_DETECTED:
            message["reason"] = "wake_word_detected"
        await self.send_text(json.dumps(message))

    async def send_wake_word_detected(self, wake_word):
        """
        sends the message that the wake word is detected.
        """
        message = {
            "session_id": self.session_id,
            "type": "listen",
            "state": "detect",
            "text": wake_word,
        }
        await self.send_text(json.dumps(message))

    async def send_start_listening(self, mode):
        """
        Sends a message to start listening.
        """
        mode_map = {
            ListeningMode.REALTIME: "realtime",
            ListeningMode.AUTO_STOP: "auto",
            ListeningMode.MANUAL: "manual",
        }
        message = {
            "session_id": self.session_id,
            "type": "listen",
            "state": "start",
            "mode": mode_map[mode],
        }
        await self.send_text(json.dumps(message))

    async def send_stop_listening(self):
        """
        Sends a message to stop listening.
        """
        message = {"session_id": self.session_id, "type": "listen", "state": "stop"}
        await self.send_text(json.dumps(message))

    async def send_iot_descriptors(self, descriptors):
        """
        sends the IoT device description information.
        """
        try:
            # Parse descriptor data
            if isinstance(descriptors, str):
                descriptors_data = json.loads(descriptors)
            else:
                descriptors_data = descriptors

            # Checks if it is an array
            if not isinstance(descriptors_data, list):
                logger.error("IoT descriptors should be an array")
                return

            # Send a separate message for each descriptor
            for i, descriptor in enumerate(descriptors_data):
                if descriptor is None:
                    logger.error(f"Failed to get IoT descriptor at index {i}")
                    continue

                message = {
                    "session_id": self.session_id,
                    "type": "iot",
                    "update": True,
                    "descriptors": [descriptor],
                }

                try:
                    await self.send_text(json.dumps(message))
                except Exception as e:
                    logger.error(
                        f"Failed to send JSON message for IoT descriptor "
                        f"at index {i}: {e}"
                    )
                    continue

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse IoT descriptors: {e}", exc_info=True)
            return

    async def send_iot_states(self, states):
        """
        sends the IoT device status information.
        """
        if isinstance(states, str):
            states_data = json.loads(states)
        else:
            states_data = states

        message = {
            "session_id": self.session_id,
            "type": "iot",
            "update": True,
            "states": states_data,
        }
        await self.send_text(json.dumps(message))

    async def send_mcp_message(self, payload):
        """
        sends MCP message.
        """
        if isinstance(payload, str):
            payload_data = json.loads(payload)
        else:
            payload_data = payload

        message = {
            "session_id": self.session_id,
            "type": "mcp",
            "payload": payload_data,
        }

        await self.send_text(json.dumps(message))

    # ============ Connection status check (template method, subclass implementation) ============

    def _is_connected(self) -> bool:
        """Checks if the connection is alive.

        Subclasses must implement this method to return the health status of the current protocol connection.

        Returns:
            bool: Returns True if the connection is alive, otherwise returns False
        """
        raise NotImplementedError(t("_is_connected方法必须由子类实现"))

    # ============ Protocol-specific cleanup (template method, subclass implementation) ============

    async def _do_cleanup(self):
        """Cleans up protocol specific resources (excluding public status and Monitoring tasks).

        Subclasses should implement this method:
        - Close protocol-specific network connections (socket/websocket/mqtt client, etc.)
        - Cancel protocol-specific background tasks (heartbeat, message handling, etc.)
        - Reset protocol-specific timestamp/status

        should not be used in this method:
        - Set self.connected = False (responsible for base class _handle_connection_loss)
        - Cancel self._connection_monitor_task (base class _handle_connection_loss is responsible)
        """
        raise NotImplementedError(t("_do_cleanup方法必须由子类实现"))

    # ============ Connection monitoring (public, subclasses can override _monitor_interval) ============

    @property
    def _monitor_interval(self) -> float:
        """Connection monitoring check interval (seconds), subclasses can override."""
        return 5.0

    def _start_connection_monitor(self):
        """Start the connection health monitoring background task."""
        if (
            self._connection_monitor_task is None
            or self._connection_monitor_task.done()
        ):
            self._connection_monitor_task = asyncio.create_task(
                self._connection_monitor()
            )

    async def _connection_monitor(self):
        """connection health status monitoring coroutine.

        loop check self._is_connected() Return value,
        Called when a disconnection is found self._handle_connection_loss().
        """
        try:
            while not self._is_closing:
                await asyncio.sleep(self._monitor_interval)

                if not self._is_connected():
                    logger.warning(t("检测到连接已断开"))
                    await self._handle_connection_loss(t("连接检测失败"))
                    break

        except asyncio.CancelledError:
            logger.debug(t("连接监控任务被取消"))
        except Exception as e:
            logger.error(t('连接监控异常: {value1}', value1=e), exc_info=True)

    # ============ Automatic reconnection (public) ============

    def enable_auto_reconnect(self, enabled: bool = True, max_attempts: int = 5):
        """enables or disables the automatic reconnection function.

        Args:
            enabled: Whether to enable automatic reconnection
            max_attempts: The maximum number of reconnection attempts
        """
        self._auto_reconnect_enabled = enabled
        if enabled:
            self._max_reconnect_attempts = max_attempts
            logger.info(t('启用自动重连，最大尝试次数: {value1}', value1=max_attempts))
        else:
            self._max_reconnect_attempts = 0
            logger.info(t("禁用自动重连"))

    async def _handle_connection_loss(self, reason: str, *, clean: bool = False):
        """handles connection loss (common logic).

        Process:
        1. Update connection status
        2. Cancel the connection monitoring task
        3. Call the subclass _do_cleanup() to clean up the protocol-specific resources
        4. Notify the observer (status change, audio channel closing)
        5. Decide whether to automatically reconnect according to the configuration

        Args:
            clean: The server is shut down normally (such as the session ends). Only the channel is recovered,
                   does not trigger automatic reconnection and does not report network errors.
        """
        if clean:
            logger.info(t('连接已由服务端正常关闭: {value1}', value1=reason))
        else:
            logger.warning(t('连接丢失: {value1}', value1=reason))

        was_connected = self.connected
        self.connected = False

        # Cancel the connection monitoring task
        await self._cancel_monitor_task()

        # Notifies the connection status change
        if self._on_connection_state_changed and was_connected:
            try:
                self._on_connection_state_changed(False, reason)
            except Exception as e:
                logger.error(t('调用连接状态变化回调失败: {value1}', value1=e), exc_info=True)

        # calls the subclass protocol specific cleanup
        await self._do_cleanup()

        # Notifies the audio channel to close
        if self._on_audio_channel_closed:
            try:
                await self._on_audio_channel_closed()
            except Exception as e:
                logger.error(t('调用音频通道关闭回调失败: {value1}', value1=e), exc_info=True)

        # The server is shut down normally: the end of the session is not considered a fault, and no reconnection is reported without an error.
        # Restart as needed during the next interaction open_audio_channel
        if clean:
            return

        # determines whether to attempt automatic reconnection based on the configuration
        if (
            not self._is_closing
            and self._auto_reconnect_enabled
            and self._reconnect_attempts < self._max_reconnect_attempts
        ):
            await self._attempt_reconnect(reason)
        else:
            if self._on_network_error:
                if (
                    self._auto_reconnect_enabled
                    and self._reconnect_attempts >= self._max_reconnect_attempts
                ):
                    await self._on_network_error(t('连接丢失且重连失败: {value1}', value1=reason))
                else:
                    await self._on_network_error(t('连接丢失: {value1}', value1=reason))

    async def _attempt_reconnect(self, original_reason: str):
        """attempts to automatically reconnect (public logic).

        Use the exponential backoff strategy and call the subclass's connect() for the actual connection.
        """
        self._reconnect_attempts += 1

        # Notification to start reconnection
        if self._on_reconnecting:
            try:
                self._on_reconnecting(
                    self._reconnect_attempts, self._max_reconnect_attempts
                )
            except Exception as e:
                logger.error(t('调用重连回调失败: {value1}', value1=e), exc_info=True)

        logger.info(
            t('尝试自动重连 ({value1}/{value3})', value1=self._reconnect_attempts, value3=self._max_reconnect_attempts)
        )

        # Exponential backoff wait, up to 30 seconds
        await asyncio.sleep(min(self._reconnect_attempts * 2, 30))

        try:
            success = await self.connect()
            if success:
                logger.info(t("自动重连成功"))
                if self._on_connection_state_changed:
                    self._on_connection_state_changed(True, t("重连成功"))
            else:
                logger.warning(
                    t('自动重连失败 ({value1}/{value3})', value1=self._reconnect_attempts, value3=self._max_reconnect_attempts)
                )
                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    if self._on_network_error:
                        await self._on_network_error(
                            t('重连失败，已达到最大重连次数: {value1}', value1=original_reason)
                        )
        except Exception as e:
            logger.error(t('重连过程中出错: {value1}', value1=e), exc_info=True)
            if self._reconnect_attempts >= self._max_reconnect_attempts:
                if self._on_network_error:
                    await self._on_network_error(t('重连异常: {value1}', value1=str(e)))

    async def _cancel_monitor_task(self):
        """Cancel and wait for the connection monitoring task to be completed."""
        if self._connection_monitor_task and not self._connection_monitor_task.done():
            self._connection_monitor_task.cancel()
            try:
                await self._connection_monitor_task
            except asyncio.CancelledError:
                pass

    def get_connection_info(self) -> dict:
        """Get connection information (base class implementation, subclasses can be extended).

        Returns:
            dict: A dictionary containing connection status, reconnection times and other information
        """
        return {
            "is_closing": self._is_closing,
            "auto_reconnect_enabled": self._auto_reconnect_enabled,
            "reconnect_attempts": self._reconnect_attempts,
            "max_reconnect_attempts": self._max_reconnect_attempts,
        }
