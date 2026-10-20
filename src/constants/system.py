# System constant definition
from enum import Enum

from src.i18n import t


class InitializationStage(Enum):
    """
    Initialization phase enum.
    """

    DEVICE_FINGERPRINT = t("第一阶段：设备身份准备")
    CONFIG_MANAGEMENT = t("第二阶段：配置管理初始化")
    OTA_CONFIG = t("第三阶段：OTA获取配置")
    ACTIVATION = t("第四阶段：激活流程")


class SystemConstants:
    """
    System constants.
    """

    # Application information
    APP_NAME = "py-xiaozhi"  # Program identification name (ASCII, used for directory, configuration, bundle_id)
    APP_DISPLAY_NAME = "小智"  # Display name (for window title, Launchpad, installer UI)
    APP_VERSION = "2.1.2"
    BOARD_TYPE = "bread-compact-wifi"

    # Default timeout setting
    DEFAULT_TIMEOUT = 10
    ACTIVATION_MAX_RETRIES = 60
    ACTIVATION_RETRY_INTERVAL = 5

    # File name constant
    CONFIG_FILE = "config.json"
    EFUSE_FILE = "efuse.json"
