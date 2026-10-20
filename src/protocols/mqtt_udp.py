"""UDP encrypted audio channel supporting MQTT session.

is responsible for: socket, packet receiving thread, AES encryption and decryption; through event loop Call back the frame to the upper layer.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

from src.i18n import t
from src.logging import get_logger
from src.protocols.mqtt_crypto import (
    aes_ctr_decrypt,
    aes_ctr_encrypt,
    build_audio_nonce,
)

logger = get_logger()


class MqttUdpChannel:
    """UDP audio transmission (encrypted Opus frame)."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self.socket: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.running = False

        self.server = ""
        self.port = 0
        self.aes_key: str | None = None  # hex
        self.aes_nonce: str | None = None  # hex
        self.local_sequence = 0
        self.remote_sequence = 0

        self._on_incoming_audio = None

    def configure(
        self,
        server: str,
        port: int,
        aes_key: str,
        aes_nonce: str,
    ) -> None:
        self.server = server
        self.port = port
        self.aes_key = aes_key
        self.aes_nonce = aes_nonce
        self.local_sequence = 0
        self.remote_sequence = 0

    def set_audio_handler(self, handler) -> None:
        self._on_incoming_audio = handler

    def is_ready(self) -> bool:
        return (
            self.socket is not None
            and self.running
            and bool(self.server)
            and self.port > 0
        )

    def start(self) -> None:
        """Create the socket and start the receiving thread (will stop the old resource first)."""
        self.stop()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Explicit binding to ensure the correct routing of the macOS network stack UDP
        sock.bind(("0.0.0.0", 0))
        sock.settimeout(0.5)
        self.socket = sock

        self.running = True
        self.thread = threading.Thread(
            target=self._receive_loop, name="mqtt-udp-rx", daemon=True
        )
        self.thread.start()
        logger.info(
            t('UDP接收线程已启动，监听来自 {value1}:{value3} 的数据', value1=self.server, value3=self.port)
        )

    def stop(self) -> None:
        """Stop the receiving thread and close the socket."""
        self.running = False
        if self.thread and self.thread.is_alive():
            try:
                self.thread.join(1.0)
            except RuntimeError:
                pass
        self.thread = None

        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.error(t('关闭UDP套接字失败: {value1}', value1=e), exc_info=True)
        self.socket = None

    def reset_session(self) -> None:
        """Clear the session side field after goodbye."""
        self.stop()
        self.server = ""
        self.port = 0
        self.aes_key = None
        self.aes_nonce = None
        self.local_sequence = 0
        self.remote_sequence = 0

    def send_audio(self, audio_data: bytes) -> bool:
        if not self.socket or not self.server or not self.port:
            logger.error(t("UDP通道未初始化"))
            return False
        if not self.aes_key or not self.aes_nonce:
            logger.error(t("UDP 加密参数缺失"))
            return False

        self.local_sequence = (self.local_sequence + 1) & 0xFFFFFFFF
        new_nonce = build_audio_nonce(
            self.aes_nonce, len(audio_data), self.local_sequence
        )
        encrypt_encoded_data = aes_ctr_encrypt(
            bytes.fromhex(self.aes_key),
            bytes.fromhex(new_nonce),
            bytes(audio_data),
        )
        packet = bytes.fromhex(new_nonce) + encrypt_encoded_data
        self.socket.sendto(packet, (self.server, self.port))

        if self.local_sequence % 10 == 0:
            logger.info(
                t('已发送音频数据包，序列号: {value1}，目标: {value3}:{value5}', value1=self.local_sequence, value3=self.server, value5=self.port)
            )
        return True

    def _receive_loop(self) -> None:
        debug_counter = 0
        while self.running and self.socket:
            try:
                data, _addr = self.socket.recvfrom(4096)
                debug_counter += 1
                try:
                    if len(data) < 16:
                        logger.error(t('无效的音频数据包大小: {value1}', value1=len(data)))
                        continue
                    if not self.aes_key:
                        continue

                    received_nonce = data[:16]
                    encrypted_audio = data[16:]
                    decrypted = aes_ctr_decrypt(
                        bytes.fromhex(self.aes_key),
                        received_nonce,
                        encrypted_audio,
                    )

                    if debug_counter % 100 == 0:
                        logger.debug(
                            t('已解密音频数据包 #{value1}, 大小: {value3} 字节', value1=debug_counter, value3=len(decrypted))
                        )

                    if self._on_incoming_audio:
                        self._dispatch_audio(decrypted)

                except Exception as e:
                    logger.error(t('处理音频数据包错误: {value1}', value1=e), exc_info=True)
                    continue
            except TimeoutError:
                pass
            except Exception as e:
                logger.error(t('UDP接收线程错误: {value1}', value1=e), exc_info=True)
                if not self.running:
                    break
                time.sleep(0.1)

        logger.info(t("UDP接收线程已停止"))

    def _dispatch_audio(self, audio_data: bytes) -> None:
        """Scheduling the frame callback from the packet receiving thread to the event loop (handler must be synchronous, in the loop Thread execution)."""
        handler = self._on_incoming_audio
        if not handler:
            return
        try:
            self._loop.call_soon_threadsafe(handler, audio_data)
        except Exception as e:
            logger.error(t('调度音频回调失败: {value1}', value1=e), exc_info=True)
