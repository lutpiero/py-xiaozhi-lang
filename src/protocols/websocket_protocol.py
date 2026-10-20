import asyncio
import json
import logging
import ssl

import websockets

from src.constants.constants import AudioConfig
from src.i18n import t
from src.logging import get_logger
from src.protocols.protocol import Protocol
from src.utils.config_manager import get_config

# The server may use a self-signed certificate, temporarily skipping client certificate verification
# to avoid connection failure caused by informal SSL certificates in production environments
ssl_context = ssl._create_unverified_context()

logger = get_logger()


class WebsocketProtocol(Protocol):
    def __init__(self):
        super().__init__()
        # Get configuration manager instance
        self.config = get_config()
        self.websocket = None
        self.connected = False
        self.hello_received = None  # Set to initialization None
        # Message processing task reference to facilitate cancellation when closing
        self._message_task = None

        self.WEBSOCKET_URL = self.config.get_config(
            "SYSTEM_OPTIONS.NETWORK.WEBSOCKET_URL"
        )
        access_token = self.config.get_config(
            "SYSTEM_OPTIONS.NETWORK.WEBSOCKET_ACCESS_TOKEN"
        )
        device_id = self.config.get_config("SYSTEM_OPTIONS.DEVICE_ID")
        client_id = self.config.get_config("SYSTEM_OPTIONS.CLIENT_ID")

        self.HEADERS = {
            "Authorization": f"Bearer {access_token}",
            "Protocol-Version": "1",
            "Device-Id": device_id,  # Get device MAC address
            "Client-Id": client_id,
        }

    async def connect(self) -> bool:
        """
        to connect to the WebSocket server.
        """
        if self._is_closing:
            logger.warning(t("连接正在关闭中，取消新的连接尝试"))
            return False

        try:
            # Created at connection time Event, ensuring that
            self.hello_received = asyncio.Event()

            # Determine whether SSL should be used
            current_ssl_context = None
            if self.WEBSOCKET_URL.startswith("wss://"):
                current_ssl_context = ssl_context

            # to establish a WebSocket connection (compatible with different Python versions)
            try:
                # new way of writing (in Python 3.11 version)
                self.websocket = await websockets.connect(
                    uri=self.WEBSOCKET_URL,
                    ssl=current_ssl_context,
                    additional_headers=self.HEADERS,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=10,
                    open_timeout=5,
                    max_size=10 * 1024 * 1024,
                    compression=None,
                    proxy=None,
                )
            except TypeError:
                # old way of writing (In older Python versions)
                self.websocket = await websockets.connect(
                    self.WEBSOCKET_URL,
                    ssl=current_ssl_context,
                    extra_headers=self.HEADERS,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=10,
                    open_timeout=5,
                    max_size=10 * 1024 * 1024,
                    compression=None,
                )

            # Start the message processing loop (save the task reference and can be canceled when closing)
            self._message_task = asyncio.create_task(self._message_handler())

            # Start the connection monitoring
            self._start_connection_monitor()

            # Send client hello message
            hello_message = {
                "type": "hello",
                "version": 1,
                "features": {
                    "mcp": True,
                },
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",
                    "sample_rate": AudioConfig.INPUT_SAMPLE_RATE,
                    "channels": AudioConfig.CHANNELS,
                    "frame_duration": AudioConfig.FRAME_DURATION,
                },
            }
            await self.send_text(json.dumps(hello_message))

            # Wait for server hello response
            try:
                await asyncio.wait_for(self.hello_received.wait(), timeout=10.0)
                self.connected = True
                self._reconnect_attempts = 0  # resets the reconnect count
                logger.info(t("已连接到WebSocket服务器"))

                # Notifies the connection status change
                if self._on_connection_state_changed:
                    self._on_connection_state_changed(True, t("连接成功"))

                return True
            except asyncio.TimeoutError:
                logger.error(t("等待服务器hello响应超时"))
                await self._do_cleanup()
                if self._on_network_error:
                    await self._on_network_error(t("等待响应超时"))
                return False

        except Exception as e:
            logger.error(t('WebSocket连接失败: {value1}', value1=e), exc_info=True)
            await self._do_cleanup()
            if self._on_network_error:
                await self._on_network_error(t('无法连接服务: {value1}', value1=str(e)))
            return False

    # ============ Template method implementation ============

    @property
    def _monitor_interval(self) -> float:
        """WSS connection monitoring check interval (seconds)."""
        return 5.0

    def _is_connected(self) -> bool:
        """Check WebSocket Whether the connection is alive."""
        if not self.websocket:
            return False
        return self.websocket.close_code is None

    async def _do_cleanup(self):
        """WebSocket protocol specific resource cleanup.

        Clean up message processing tasks, heartbeat tasks, WebSocket Connection and heartbeat timestamp.
        is not responsible for canceling the connection monitoring task (base class _handle_connection_loss Responsible).
        """
        # Cancel message processing task
        if self._message_task and not self._message_task.done():
            self._message_task.cancel()
            try:
                await self._message_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(t('等待消息任务取消时异常: {value1}', value1=e))
        self._message_task = None

        # Close the WebSocket connection
        if self.websocket and self.websocket.close_code is None:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(t('关闭WebSocket连接时出错: {value1}', value1=e), exc_info=True)

        self.websocket = None

    def get_connection_info(self) -> dict:
        """Get WSS connection information.

        Returns:
            dict: A dictionary containing connection status, reconnection times and other information
        """
        info = super().get_connection_info()
        info.update(
            {
                "connected": self.connected,
                "websocket_closed": (
                    self.websocket.close_code is not None if self.websocket else True
                ),
                "websocket_url": self.WEBSOCKET_URL,
            }
        )
        return info

    async def _message_handler(self):
        """
        handles the received WebSocket message.
        """
        try:
            async for message in self.websocket:
                if self._is_closing:
                    break

                try:
                    if isinstance(message, str):
                        try:
                            data = json.loads(message)
                            msg_type = data.get("type")
                            if msg_type == "hello":
                                # handles the server hello message
                                await self._handle_server_hello(data)
                            else:
                                if self._on_incoming_json:
                                    self._on_incoming_json(data)
                        except json.JSONDecodeError as e:
                            logger.error(t('无效的JSON消息: {value1}, 错误: {value3}', value1=message, value3=e), exc_info=True)
                    elif isinstance(message, bytes):
                        # Binary message, possibly audio
                        if self._on_incoming_audio:
                            self._on_incoming_audio(message)
                except Exception as e:
                    # handles errors for a single message in the correct event loop, but continues processing other messages
                    logger.error(t('处理消息时出错: {value1}', value1=e), exc_info=True)
                    continue

        except asyncio.CancelledError:
            logger.debug(t("消息处理任务被取消"))
            return
        except websockets.ConnectionClosedOK as e:
            if not self._is_closing:
                logger.info(t('WebSocket连接已由服务端正常关闭: {value1}', value1=e))
                await self._handle_connection_loss(
                    t('服务端关闭连接: {value1}', value1=e.code), clean=True
                )
        except websockets.ConnectionClosedError as e:
            if not self._is_closing:
                logger.info(t('WebSocket连接错误关闭: {value1}', value1=e))
                await self._handle_connection_loss(t('连接错误: {value1} {value3}', value1=e.code, value3=e.reason))
        except websockets.InvalidState as e:
            logger.error(t('WebSocket状态无效: {value1}', value1=e), exc_info=True)
            await self._handle_connection_loss(t("连接状态异常"))
        except ConnectionResetError:
            logger.warning(t("连接被重置"))
            await self._handle_connection_loss(t("连接被重置"))
        except OSError as e:
            logger.error(t('网络I/O错误: {value1}', value1=e), exc_info=True)
            await self._handle_connection_loss(t("网络I/O错误"))
        except Exception as e:
            logger.error(t('消息处理循环异常: {value1}', value1=e), exc_info=True)
            await self._handle_connection_loss(t('消息处理异常: {value1}', value1=str(e)))

    async def send_audio(self, data: bytes):
        """
        Send audio data.
        """
        if not self.is_audio_channel_opened():
            return

        try:
            await self.websocket.send(data)
        except websockets.ConnectionClosedOK as e:
            # The server recovers the session normally (such as closing after TTS), which does not count as a network error
            logger.info(t('发送音频时连接已由服务端正常关闭: {value1}', value1=e))
            await self._handle_connection_loss(
                t('发送音频时服务端关闭: {value1}', value1=e.code), clean=True
            )
        except websockets.ConnectionClosedError as e:
            logger.warning(t('发送音频时连接异常关闭: {value1}', value1=e))
            await self._handle_connection_loss(t('发送音频失败: {value1} {value3}', value1=e.code, value3=e.reason))
        except Exception as e:
            logger.error(t('发送音频数据失败: {value1}', value1=e), exc_info=True)
            # Do not call the network error callback here, let the connection processor handle it
            await self._handle_connection_loss(t('发送音频异常: {value1}', value1=str(e)))

    async def send_text(self, message: str):
        """
        Send text message.
        """
        if not self.websocket or self._is_closing:
            logger.warning(t("WebSocket未连接或正在关闭，无法发送消息"))
            return

        try:
            close_code = self.websocket.close_code
        except Exception:
            close_code = None
        if close_code is not None:
            # 1000/1001/1005 is considered a normal shutdown (the server takes back the session)
            clean = close_code in (1000, 1001, 1005)
            logger.log(
                logging.INFO if clean else logging.WARNING,
                t('WebSocket 已关闭 (code={value1})，跳过发送文本', value1=close_code),
            )
            if self.connected:
                await self._handle_connection_loss(
                    t('发送文本失败: 连接已关闭 {value1}', value1=close_code), clean=clean
                )
            return

        try:
            await self.websocket.send(message)
        except websockets.ConnectionClosedOK as e:
            # The server recovers the session normally, which does not count as a network error
            logger.info(t('发送文本时连接已由服务端正常关闭: {value1}', value1=e))
            if self.connected and not self._is_closing:
                await self._handle_connection_loss(
                    t('发送文本时服务端关闭: {value1}', value1=e.code), clean=True
                )
        except websockets.ConnectionClosedError as e:
            logger.warning(t('发送文本时连接异常关闭: {value1}', value1=e))
            if self.connected and not self._is_closing:
                await self._handle_connection_loss(
                    t('发送文本错误: {value1} {value3}', value1=e.code, value3=e.reason)
                )
        except Exception as e:
            logger.error(t('发送文本消息失败: {value1}', value1=e), exc_info=True)
            if self.connected and not self._is_closing:
                await self._handle_connection_loss(t('发送文本异常: {value1}', value1=str(e)))

    def is_audio_channel_opened(self) -> bool:
        """Check whether the audio channel is open.

        More accurately checks connection status, including the actual status of WebSocket
        """
        if not self.websocket or not self.connected or self._is_closing:
            return False

        # Check the actual status of WebSocket
        try:
            return self.websocket.close_code is None
        except Exception:
            return False

    async def open_audio_channel(self) -> bool:
        """to establish a WebSocket connection.

        creates a new WebSocket if not already connected Connect
        Returns:
            bool: Whether the connection is successful
        """
        if not self.is_audio_channel_opened():
            return await self.connect()
        return True

    async def _handle_server_hello(self, data: dict):
        """
        handles the server's hello message.
        """
        try:
            # Verify transmission method
            transport = data.get("transport")
            if not transport or transport != "websocket":
                logger.error(t('不支持的传输方式: {value1}', value1=transport))
                return

            # Set hello Receive event
            self.hello_received.set()

            # notifies that the audio channel is open
            if self._on_audio_channel_opened:
                await self._on_audio_channel_opened()

            logger.info(t("成功处理服务器 hello 消息"))

        except Exception as e:
            logger.error(t('处理服务器 hello 消息时出错: {value1}', value1=e), exc_info=True)
            if self._on_network_error:
                await self._on_network_error(t('处理服务器响应失败: {value1}', value1=str(e)))

    async def close_audio_channel(self):
        """
        Close the audio channel.
        """
        self._is_closing = True

        try:
            self.connected = False

            # Cancel the connection monitoring task (base class management)
            await self._cancel_monitor_task()

            # Protocol-specific cleanup
            await self._do_cleanup()

            if self._on_audio_channel_closed:
                await self._on_audio_channel_closed()

        except Exception as e:
            logger.error(t('关闭音频通道失败: {value1}', value1=e), exc_info=True)
        finally:
            self._is_closing = False
