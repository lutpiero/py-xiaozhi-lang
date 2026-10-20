"""Activates the HTTP client."""

from __future__ import annotations

import asyncio
import ssl
from typing import TYPE_CHECKING, Callable, Optional

import aiohttp

from src.i18n import t
from src.logging import get_logger

if TYPE_CHECKING:
    from src.activation.identity import DeviceIdentity
    from src.utils.config_manager import ConfigManager

logger = get_logger()


class ActivationHttpClient:
    """Polls the OTA activate endpoint until success or times out."""

    def __init__(
        self,
        config_manager: "ConfigManager",
        identity: "DeviceIdentity",
    ) -> None:
        self._config = config_manager
        self._identity = identity

    async def activate(
        self,
        challenge: str,
        code: str,
        *,
        on_retry_announce: Optional[Callable[[str], None]] = None,
    ) -> bool:
        serial_number = self._identity.get_serial_number()
        if not serial_number:
            logger.error(t("无序列号，无法激活"))
            return False

        hmac_signature = self._identity.generate_hmac_signature(challenge)
        if not hmac_signature:
            logger.error(t("无法生成HMAC签名"))
            return False

        payload = {
            "Payload": {
                "algorithm": "hmac-sha256",
                "serial_number": serial_number,
                "challenge": challenge,
                "hmac": hmac_signature,
            }
        }

        ota_url = self._config.get_config("SYSTEM_OPTIONS.NETWORK.OTA_VERSION_URL")
        if not ota_url:
            logger.error(t("OTA URL未配置"))
            return False

        activate_url = f"{ota_url.rstrip('/')}/activate"
        headers = {
            "Activation-Version": "2",
            "Device-Id": self._config.get_config("SYSTEM_OPTIONS.DEVICE_ID"),
            "Client-Id": self._config.get_config("SYSTEM_OPTIONS.CLIENT_ID"),
            "Content-Type": "application/json",
        }
        logger.info(t('激活URL: {value1}', value1=activate_url))

        max_retries = 60
        retry_interval = 5
        timeout = aiohttp.ClientTimeout(total=10)

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        async with aiohttp.ClientSession(
            timeout=timeout, connector=connector
        ) as session:
            for attempt in range(max_retries):
                try:
                    logger.info(t('激活尝试 {value1}/{value3}', value1=attempt + 1, value3=max_retries))
                    if attempt > 0 and on_retry_announce:
                        try:
                            on_retry_announce(code)
                        except Exception as e:
                            logger.warning(t('激活码播报失败: {value1}', value1=e), exc_info=True)

                    async with session.post(
                        activate_url, headers=headers, json=payload
                    ) as response:
                        logger.debug(t('激活响应: HTTP {value1}', value1=response.status))
                        if response.status == 200:
                            logger.info(t("设备激活成功!"))
                            self._identity.set_activation_status(True)
                            return True
                        if response.status == 202:
                            logger.info(t("等待用户输入验证码..."))
                            await asyncio.sleep(retry_interval)
                            continue
                        logger.warning(t('服务器返回 {value1}，继续重试', value1=response.status))
                        await asyncio.sleep(retry_interval)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(t('激活请求失败: {value1}，重试中...', value1=e), exc_info=True)
                    await asyncio.sleep(retry_interval)

        logger.error(t('激活失败，达到最大重试次数 ({value1})', value1=max_retries))
        return False
