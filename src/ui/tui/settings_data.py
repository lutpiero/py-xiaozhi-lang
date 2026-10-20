"""TUI settings: configuration field definition and reading and writing (connected to ConfigManager CONFIG_CHANGED)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.i18n import t
from src.logging import get_logger
from src.utils.config_manager import get_config

logger = get_logger()


@dataclass(frozen=True)
class SettingField:
    """An editable configuration item."""

    path: str
    label: str
    kind: str = "str"  # str | int | bool | choice
    choices: tuple[str, ...] = ()
    help: str = ""


# First issue: System/Audio/Camera/ The wake word
SETTING_SECTIONS: list[tuple[str, list[SettingField]]] = [
    (
        t("系统"),
        [
            SettingField(
                "SYSTEM_OPTIONS.NETWORK.OTA_VERSION_URL",
                "OTA URL",
                help=t("OTA / 激活配置地址"),
            ),
            SettingField(
                "SYSTEM_OPTIONS.NETWORK.WEBSOCKET_URL",
                "WebSocket URL",
                help=t("WebSocket 服务地址"),
            ),
            SettingField(
                "SYSTEM_OPTIONS.DEVICE_ID",
                t("设备 ID"),
                help=t("Device-Id（通常为 MAC）"),
            ),
            SettingField(
                "SYSTEM_OPTIONS.CLIENT_ID",
                t("客户端 ID"),
                help="Client-Id",
            ),
        ],
    ),
    (
        t("音频"),
        [
            SettingField(
                "AUDIO_DEVICES.input_device_name",
                t("输入设备名"),
                help=t("按名称匹配麦克风（热插拔后 ID 会变）"),
            ),
            SettingField(
                "AUDIO_DEVICES.output_device_name",
                t("输出设备名"),
                help=t("按名称匹配扬声器/耳机"),
            ),
            SettingField(
                "AUDIO_DEVICES.opus_output_sample_rate",
                t("Opus 输出采样率"),
                kind="choice",
                choices=("24000", "16000"),
                help=t("官方 24000 / 第三方常 16000"),
            ),
            SettingField(
                "AUDIO_DEVICES.frame_duration",
                t("帧时长 ms"),
                kind="choice",
                choices=("20", "40", "60"),
                help=t("20 低延迟 / 60 低 CPU"),
            ),
        ],
    ),
    (
        t("摄像头"),
        [
            SettingField(
                "CAMERA.backend",
                t("采集后端"),
                kind="choice",
                choices=("auto", "opencv", "picamera2"),
                help=t("auto 先 OpenCV，失败再 Pi CSI"),
            ),
            SettingField(
                "CAMERA.device",
                t("设备路径"),
                help=t("如 /dev/video0；非空优先于 index"),
            ),
            SettingField(
                "CAMERA.camera_index",
                t("设备 index"),
                kind="int",
                help=t("OpenCV 数字索引"),
            ),
            SettingField(
                "CAMERA.frame_width",
                t("宽度"),
                kind="int",
            ),
            SettingField(
                "CAMERA.frame_height",
                t("高度"),
                kind="int",
            ),
        ],
    ),
    (
        t("唤醒词"),
        [
            SettingField(
                "WAKE_WORD_OPTIONS.USE_WAKE_WORD",
                t("启用唤醒词"),
                kind="bool",
            ),
            SettingField(
                "WAKE_WORD_OPTIONS.WAKE_WORD",
                t("唤醒词"),
                help=t("如：你好小智"),
            ),
            SettingField(
                "WAKE_WORD_OPTIONS.WAKE_WORD_LANG",
                t("语言"),
                kind="choice",
                choices=("zh", "en"),
            ),
        ],
    ),
]


def load_setting_values() -> dict[str, str]:
    """reads the current configuration as a string table (path -> display value)."""
    cfg = get_config()
    values: dict[str, str] = {}
    for _section, fields in SETTING_SECTIONS:
        for f in fields:
            raw = cfg.get_config(f.path, "")
            if f.kind == "bool":
                values[f.path] = "true" if bool(raw) else "false"
            elif raw is None:
                values[f.path] = ""
            else:
                values[f.path] = str(raw)
    return values


def parse_field_value(field: SettingField, text: str) -> Any:
    """Convert the input box string into the configuration value."""
    s = (text or "").strip()
    if field.kind == "int":
        if s == "":
            return 0
        return int(s)
    if field.kind == "bool":
        return s.lower() in ("1", "true", "yes", "on", "是")
    if field.kind == "choice":
        if field.choices and s not in field.choices:
            # The user value is still written, and the upper layer verification prompts
            return s
        if field.path.endswith("opus_output_sample_rate") or field.path.endswith(
            "frame_duration"
        ):
            try:
                return int(s)
            except ValueError:
                return s
        return s
    return s


def save_settings(values: dict[str, str]) -> tuple[bool, str]:
    """Write the configuration in batches and place it on the disk.

    Returns:
        (ok, message)
    """
    cfg = get_config()
    updates: dict[str, Any] = {}
    try:
        for _section, fields in SETTING_SECTIONS:
            for f in fields:
                if f.path not in values:
                    continue
                updates[f.path] = parse_field_value(f, values[f.path])
        if not updates:
            return True, t("无变更")
        ok = cfg.update_configs(updates)
        if not ok:
            return False, t("保存失败（写盘错误）")
        logger.info(t('TUI 已保存 {value1} 项配置', value1=len(updates)))
        return True, t("已保存 {count} 项", count=len(updates))
    except Exception as e:
        logger.error(t('TUI 保存配置失败: {value1}', value1=e), exc_info=True)
        return False, t("保存失败: {error}", error=e)
