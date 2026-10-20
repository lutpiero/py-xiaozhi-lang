"""Audio Device Manager.

Responsibilities:
- Device discovery and selection
- Configuration persistence (by device name, not ID)
- Device information query
"""
from dataclasses import dataclass

from src.constants.constants import AudioConfig
from src.i18n import t
from src.logging import get_logger
from src.utils.audio_utils import find_device_by_name, select_audio_device
from src.utils.config_manager import ConfigManager

logger = get_logger()


@dataclass
class DeviceConfig:
    """Device Configuration Data Class"""

    input_device_id: int
    output_device_id: int
    input_sample_rate: int
    output_sample_rate: int
    input_channels: int
    output_channels: int
    input_frame_size: int
    output_frame_size: int


class AudioDeviceManager:
    """Audio Device Manager (stateless, pure logic)"""

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager

    def load_or_detect_devices(self) -> DeviceConfig:
        """to load configuration or automatically detect device (match by name)

        Returns:
            DeviceConfig: Device configuration

        Raises:
            RuntimeError: Unable to find available device
        """
        audio_config = self.config.get_config("AUDIO_DEVICES", {}) or {}

        input_device_name = audio_config.get("input_device_name")
        output_device_name = audio_config.get("output_device_name")

        # 1. Try to find the device by name
        input_info = None
        output_info = None

        if input_device_name:
            logger.info(t('尝试查找输入设备: {value1}', value1=input_device_name))
            input_info = find_device_by_name("input", input_device_name)
            if input_info:
                logger.info(t('✓ 找到输入设备: {value1} (ID: {value3})', value1=input_info['name'], value3=input_info['index']))
            else:
                logger.warning(t("✗ 未找到设备 '{value1}'，将重新选择", value1=input_device_name))

        if output_device_name:
            logger.info(t('尝试查找输出设备: {value1}', value1=output_device_name))
            output_info = find_device_by_name("output", output_device_name)
            if output_info:
                logger.info(t('✓ 找到输出设备: {value1} (ID: {value3})', value1=output_info['name'], value3=output_info['index']))
            else:
                logger.warning(t("✗ 未找到设备 '{value1}'，将重新选择", value1=output_device_name))

        # 2. If lookup by name fails, automatically select new device
        if not input_info:
            logger.info(t("自动选择输入设备..."))
            input_info = select_audio_device("input")
            if not input_info:
                raise RuntimeError(t("无法找到可用的输入设备"))

        if not output_info:
            logger.info(t("自动选择输出设备..."))
            output_info = select_audio_device("output")
            if not output_info:
                raise RuntimeError(t("无法找到可用的输出设备"))

        # 3. Input is fixed mono (protocol required to avoid array driver delays), output maintains device channel number
        input_channels = 1
        output_channels = output_info["channels"]

        device_input_sample_rate = input_info["sample_rate"]
        device_output_sample_rate = output_info["sample_rate"]

        logger.info(
            t('使用输入设备: {value1} | {value3}Hz {value5}ch', value1=input_info['name'], value3=device_input_sample_rate, value5=input_channels)
        )
        logger.info(
            t('使用输出设备: {value1} | {value3}Hz {value5}ch', value1=output_info['name'], value3=device_output_sample_rate, value5=output_channels)
        )

        # 4. Save device name (not ID) to configuration
        if (
            input_device_name != input_info["name"]
            or output_device_name != output_info["name"]
        ):
            self.config.update_config("AUDIO_DEVICES.input_device_name", input_info["name"])
            self.config.update_config("AUDIO_DEVICES.input_sample_rate", device_input_sample_rate)
            self.config.update_config("AUDIO_DEVICES.input_channels", input_channels)
            self.config.update_config("AUDIO_DEVICES.output_device_name", output_info["name"])
            self.config.update_config("AUDIO_DEVICES.output_sample_rate", device_output_sample_rate)
            self.config.update_config("AUDIO_DEVICES.output_channels", output_channels)
            logger.info(t("设备配置已保存"))

        return DeviceConfig(
            input_device_id=input_info["index"],
            output_device_id=output_info["index"],
            input_sample_rate=device_input_sample_rate,
            output_sample_rate=device_output_sample_rate,
            input_channels=input_channels,
            output_channels=output_channels,
            input_frame_size=int(
                device_input_sample_rate * (AudioConfig.FRAME_DURATION / 1000)
            ),
            output_frame_size=int(
                device_output_sample_rate * (AudioConfig.FRAME_DURATION / 1000)
            ),
        )
