import copy
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from src.i18n import t
from src.logging import get_logger
from src.utils.resource_finder import (
    get_config_dir,
    get_user_data_dir,
)

logger = get_logger()

# In-process authoritative configuration: created by initialize_config(), read by get_config(); no lazy singleton
_current: "ConfigManager | None" = None


def initialize_config() -> "ConfigManager":
    """Create or return the initialized configuration manager (called by the application entry)."""
    global _current
    if _current is None:
        _current = ConfigManager()
        # Apply PATHS to overwrite and migrate cache/logs/music/keywords (the config directory will not be migrated)
        try:
            from src.utils.resource_finder import apply_path_overrides_from_config

            apply_path_overrides_from_config(_current, migrate=True)
        except Exception as e:
            logger.warning(t("应用 PATHS 目录覆盖失败: %s"), e, exc_info=True)
    return _current


def get_config() -> "ConfigManager":
    """Get the initialized configuration manager.

    Raises:
        RuntimeError: Not yet initialize_config()
    """
    if _current is None:
        raise RuntimeError(
            t("ConfigManager 未初始化：请在入口调用 initialize_config()")
        )
    return _current


def reset_config() -> None:
    """Discard process configuration (testing only)."""
    global _current
    _current = None


class ConfigManager:
    """
    Configuration manager (normal instance; process authority held by initialize_config/get_config).
    """

    # Current schema version; when loading migrate_config() will upgrade to this version
    CONFIG_VERSION = 1

    # Default configuration (complete product schema; deepcopy when loading, sharing nested objects with instances is prohibited)
    DEFAULT_CONFIG = {
        "CONFIG_VERSION": 1,
        "SYSTEM_OPTIONS": {
            "CLIENT_ID": None,
            "DEVICE_ID": None,
            "WINDOW_SIZE_MODE": "default",
            # auto | zh_CN | en_US (auto: environment variable/system language)
            "LANGUAGE": "auto",
            "NETWORK": {
                "OTA_VERSION_URL": "https://api.tenclass.net/xiaozhi/ota/",
                "WEBSOCKET_URL": None,
                "WEBSOCKET_ACCESS_TOKEN": None,
                "MQTT_INFO": None,
                "ACTIVATION_VERSION": "v2",  # Optional values: v1, v2
                "AUTHORIZATION_URL": "https://xiaozhi.me/",
            },
        },
        "WAKE_WORD_OPTIONS": {
            "USE_WAKE_WORD": True,
            "MODEL_PATH": "models/zh",
            "NUM_THREADS": 5,
            "PROVIDER": "cpu",
            "MAX_ACTIVE_PATHS": 2,
            "KEYWORDS_SCORE": 1.8,
            "KEYWORDS_THRESHOLD": 0.2,
            "NUM_TRAILING_BLANKS": 1,
            "WAKE_WORD": "你好小智",
            "WAKE_WORD_LANG": "zh",
        },
        "CAMERA": {
            "camera_index": 0,
            # Device path takes precedence over index, as in "/dev/video0" (Raspberry Pi USB/V4L2)
            "device": "",
            # auto | opencv | picamera2; auto OpenCV first, try again if failed CSI(picamera2)
            "backend": "auto",
            "frame_width": 640,
            "frame_height": 480,
            "fps": 30,
            # The number of warm-up frames discarded after opening (the first few frames of USB/Pi are often invalid)
            "warm_up_frames": 5,
            "Local_VL_url": "https://open.bigmodel.cn/api/paas/v4/",
            "VLapi_key": "",
            "models": "glm-4v-plus",
        },
        "SHORTCUTS": {
            "ENABLED": True,
            "MANUAL_PRESS": {"modifier": "ctrl", "key": "j", "description": "按住说话"},
            "AUTO_TOGGLE": {"modifier": "ctrl", "key": "k", "description": "自动对话"},
            "ABORT": {"modifier": "ctrl", "key": "q", "description": "中断对话"},
            "MODE_TOGGLE": {"modifier": "ctrl", "key": "m", "description": "切换模式"},
            "WINDOW_TOGGLE": {
                "modifier": "ctrl",
                "key": "w",
                "description": "显示/隐藏窗口",
            },
        },
        "AEC_OPTIONS": {
            "ENABLED": False,
            # TTS does not pause the music when AEC is in place, and the mix avoids parallel playback (automatically reverts to pause when the engine is bypassed)
            "MUSIC_PARALLEL": True,
            # Delay compensation (number of protocol frames), actual delay_ms = 40 N * frame length
            "FRAME_DELAY": 3,
            # Noise suppression/Qualcomm preprocessing
            "ENABLE_PREPROCESS": True,
        },
        # Writable directory overwrite (config is still fixed in user data/config; null=default)
        # Environment variables take precedence: XIAOZHI_CACHE_DIR / XIAOZHI_LOG_DIR /
        # XIAOZHI_MUSIC_CACHE_DIR / XIAOZHI_KEYWORDS_DIR / XIAOZHI_DATA_DIR
        # Change CACHE/LOG/MUSIC/KEYWORDS will be copied from the old directory to the new directory at startup (without deleting the old one)
        "PATHS": {
            "CACHE_DIR": None,
            "LOG_DIR": None,
            "MUSIC_CACHE_DIR": None,
            "KEYWORDS_DIR": None,
        },
        # External MCP plug-in (user directory mcp_plugins, comes with lib/)
        "MCP_PLUGINS": {
            "ENABLED": True,
            "DIR": None,  # null = {user data}/mcp_plugins
            "ENABLED_IDS": [],  # Empty = By plugin enabled_by_default
            "DISABLED_IDS": [],
            "ALLOW_HOST_GET": ["config_readonly", "logger"],
            # Strict verification (off by default, to avoid failure to load when the sample package has no platforms/abi)
            "ENFORCE_PREFIX": False,
            "REQUIRE_PYTHON_ABI": False,
            "REQUIRE_PLATFORMS": False,
        },
        # MCP tool exposure (blacklist: does not appear in tools/list, call is also rejected)
        "MCP_TOOLS": {
            "DISABLED": [],  # Such as ["music_player.stop", "self.application.launch"]
        },
        "AUDIO_DEVICES": {
            "input_device_id": None,
            "input_device_name": None,
            "output_device_id": None,
            "output_device_name": None,
            "input_sample_rate": None,
            "output_sample_rate": None,
            "input_channels": None,
            "output_channels": None,
            "opus_output_sample_rate": 24000,  # Opus decoding sampling rate: 24000 (official) or 16000 (Third Party)
            "frame_duration": 20,  # Audio frame length (ms): 20 (low latency) / 40 (balanced) / 60 (low CPU)
        },
        "LOGGING": {
            "LEVEL": "INFO",  # DEBUG, INFO, WARNING, ERROR, CRITICAL
            "FORMAT_TYPE": "colored",  # colored, json, simple
            "ENABLE_CONSOLE": True,
            "ENABLE_FILE": True,
            "ENABLE_ERROR_FILE": True,
            "ENABLE_JSON_FILE": False,
            "ENABLE_ASYNC": False,
            "ENABLE_SENSITIVE_FILTER": True,
            "MAX_BYTES": 10485760,  # 10MB
            "BACKUP_COUNT": 30,
            "ROTATION_WHEN": "midnight",  # midnight, H, D
            "THIRD_PARTY_LEVELS": {
                "urllib3": "WARNING",
                "websockets": "WARNING",
                "asyncio": "WARNING",
                "paho": "WARNING",
                "PIL": "WARNING",
            },
        },
        # Music API (empty string = run with built-in default URL)
        "MUSIC": {
            "SEARCH_URL": "",
            "URL_API": "",
            "URL_API_KEY": "",
            "LYRICS_URL": "",
            "DEFAULT_PLATFORM": "kw",
            "DEFAULT_QUALITY": "320k",
        },
    }

    def __init__(self):
        """Initialize the configuration manager (direct construction; please use the application initialize_config)."""
        self._init_config_paths()
        self._config = self._load_config()

    def _init_config_paths(self):
        """
        Initialize the configuration file path.

        The configuration file is stored in the user data directory and can be written after packaging.
        Migrate the default configuration from the installation directory on first run.
        """
        self.config_dir = get_user_data_dir() / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.config_file = self.config_dir / "config.json"

        # If there is no configuration file in the user directory, try to migrate from the installation directory
        if not self.config_file.exists():
            install_config = get_config_dir() / "config.json"
            if install_config.exists():
                try:
                    # Verify JSON first to avoid copying damaged installation configurations
                    json.loads(install_config.read_text(encoding="utf-8"))
                    shutil.copy2(install_config, self.config_file)
                    logger.info(
                        t('已从安装目录迁移配置: {value1} -> {value3}', value1=install_config, value3=self.config_file)
                    )
                except Exception as e:
                    logger.warning(
                        t('迁移配置文件失败: {value1}，将使用默认配置', value1=e), exc_info=True
                    )

        logger.info(t('配置目录: {value1}', value1=self.config_dir.absolute()))
        logger.info(t('配置文件: {value1}', value1=self.config_file.absolute()))

    def _default_config_copy(self) -> Dict[str, Any]:
        """Deep copy the default configuration to avoid instances and class attributes sharing nested dict/list."""
        return copy.deepcopy(self.DEFAULT_CONFIG)

    def _load_config(self) -> Dict[str, Any]:
        """Load the configuration file; create if it does not exist; fall back to the default if it is damaged."""
        try:
            if self.config_file.exists():
                logger.debug(t('找到配置文件: {value1}', value1=self.config_file))
                try:
                    raw = self.config_file.read_text(encoding="utf-8")
                    config = json.loads(raw)
                except Exception as e:
                    backup = self._backup_corrupt_config(e)
                    backup_suffix = t("至 {value1}", value1=backup) if backup else ""
                    logger.error(
                        t(
                            "配置文件损坏，已备份{value1}并回退默认: {value3}",
                            value1=backup_suffix,
                            value3=e,
                        ),
                        exc_info=True,
                    )
                    defaults = self._default_config_copy()
                    self._save_config(defaults)
                    return defaults

                if not isinstance(config, dict):
                    backup = self._backup_corrupt_config(
                        TypeError(t('根节点须为 object，实际为 {value1}', value1=type(config).__name__))
                    )
                    backup_suffix = t("至 {value1}", value1=backup) if backup else ""
                    logger.error(
                        t(
                            "配置文件根节点无效，已备份{value1}并回退默认",
                            value1=backup_suffix,
                        )
                    )
                    defaults = self._default_config_copy()
                    self._save_config(defaults)
                    return defaults

                merged = self._merge_configs(self._default_config_copy(), config)
                # The version is subject to the "disk file"; merge will bring the default CONFIG_VERSION, leading to misjudgment that migration has been carried out
                try:
                    file_ver = int(config.get("CONFIG_VERSION", 0) or 0)
                except (TypeError, ValueError):
                    file_ver = 0
                return self._migrate_config(merged, from_version=file_ver)

            logger.info(t("配置文件不存在，创建默认配置"))
            defaults = self._default_config_copy()
            self._save_config(defaults)
            return defaults

        except Exception as e:
            logger.error(t('配置加载错误: {value1}', value1=e), exc_info=True)
            return self._default_config_copy()

    def _migrate_config(
        self, config: Dict[str, Any], *, from_version: int | None = None
    ) -> Dict[str, Any]:
        """Press CONFIG_VERSION to do forward migration; write back to the disk if necessary.

        from_version: The version in the disk file (before merge). If omitted, read the field
        (if the default value has been merged at this time, it may already be the latest version, and the migration will be skipped).

        Convention:
        - The default/illegal version is regarded as 0
        - Only do patches with low reversibility requirements in each step (renaming, patching, standardization)
        - Write back after upgrading to CONFIG_VERSION to avoid repeated migration next time
        """
        if from_version is not None:
            ver = int(from_version)
        else:
            try:
                raw_ver = config.get("CONFIG_VERSION", 0)
                try:
                    ver = int(raw_ver)
                except (TypeError, ValueError):
                    ver = 0
            except Exception:
                ver = 0

        original = ver
        # --- Migration steps (added incrementally by version) ---
        if ver < 1:
            # v1: introduce the version number; complete MCP_TOOLS; normalize the subscribe_topic string "null"
            config.setdefault("MCP_TOOLS", {"DISABLED": []})
            if not isinstance(config.get("MCP_TOOLS"), dict):
                config["MCP_TOOLS"] = {"DISABLED": []}
            config["MCP_TOOLS"].setdefault("DISABLED", [])

            try:
                net = config.get("SYSTEM_OPTIONS", {}).get("NETWORK", {})
                mqtt = net.get("MQTT_INFO")
                if isinstance(mqtt, dict) and mqtt.get("subscribe_topic") == "null":
                    mqtt["subscribe_topic"] = None
            except Exception:
                pass
            ver = 1

        # Future: if ver < 2: ...; ver = 2

        if ver != original or config.get("CONFIG_VERSION") != self.CONFIG_VERSION:
            config["CONFIG_VERSION"] = self.CONFIG_VERSION
            if self._save_config(config):
                logger.info(
                    t("配置已迁移: v%s -> v%s"), original, self.CONFIG_VERSION
                )
            else:
                logger.warning(
                    t("配置迁移后写回失败（内存已是 v%s）"), self.CONFIG_VERSION
                )
        else:
            config["CONFIG_VERSION"] = self.CONFIG_VERSION
        return config

    def _backup_corrupt_config(self, error: Exception) -> str | None:
        """Back up the damaged config.json as .corrupt-timestamp, return the backup path."""
        try:
            if not self.config_file.exists():
                return None
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = self.config_file.with_name(f"config.json.corrupt-{ts}")
            # Avoids duplication of names in extreme cases
            n = 0
            while backup.exists():
                n += 1
                backup = self.config_file.with_name(f"config.json.corrupt-{ts}-{n}")
            shutil.copy2(self.config_file, backup)
            logger.warning(t("已备份损坏配置: %s (%s)"), backup, error)
            return str(backup)
        except Exception as e:
            logger.error(t("备份损坏配置失败: %s"), e, exc_info=True)
            return None

    def _save_config(self, config: dict) -> bool:
        """Atomic write configuration file (temporary file rename to prevent write interruption damage)."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)

            tmp_file = self.config_file.with_suffix(".tmp")
            tmp_file.write_text(
                json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(tmp_file, self.config_file)
            logger.debug(t('配置已保存到: {value1}', value1=self.config_file))
            return True

        except Exception as e:
            logger.error(t('配置保存错误: {value1}', value1=e), exc_info=True)
            return False

    @staticmethod
    def _merge_configs(default: dict, custom: dict) -> dict:
        """Recursive merge configuration: default is the bottom, custom overrides; both sides are dict Time-deep merge.

        Note: The caller should pass in the deepcopy default to avoid contaminating class-level DEFAULT_CONFIG.
        """
        result = default  # can be merged in place when it is an independent copy
        for key, value in custom.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ConfigManager._merge_configs(result[key], value)
            else:
                result[key] = value
        return result

    def get_config(self, path: str, default: Any = None) -> Any:
        """
        Obtains the configuration value through the path
        path: dot-separated configuration path, such as "SYSTEM_OPTIONS.NETWORK.MQTT_INFO"
        """
        try:
            value = self._config
            for key in path.split("."):
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def update_config(self, path: str, value: Any, *, save: bool = True) -> bool:
        """
        updates specific configuration items
        path: dot-separated configuration path, such as "SYSTEM_OPTIONS.NETWORK.MQTT_INFO"
        save: Whether to place the order immediately; pass False when updating in batches, and finally save_config()/update_configs

        If the intermediate node is None/not dict, will be promoted to dict before writing (compatible with defaults such as MQTT_INFO: null).
        """
        try:
            current: Any = self._config
            *parts, last = path.split(".")
            for part in parts:
                if not isinstance(current, dict):
                    raise TypeError(
                        t('配置路径前缀不是对象，无法写入 {value1}（当前节点类型 {value3}）', value1=path, value3=type(current).__name__)
                    )
                existing = current.get(part, None)
                if not isinstance(existing, dict):
                    # Key missing or value None/scalar: Create empty object to continue drilling down
                    existing = {}
                    current[part] = existing
                current = existing
            if not isinstance(current, dict):
                raise TypeError(t('配置路径无法写入: {value1}', value1=path))
            current[last] = value
            if not save:
                return True
            return self._save_config(self._config)
        except Exception as e:
            logger.error(t('配置更新错误 {value1}: {value3}', value1=path, value3=e), exc_info=True)
            return False

    def update_configs(self, updates: Dict[str, Any]) -> bool:
        """Update multiple configuration paths in batches and only write to the disk once.

        Args:
            updates: path -> value, for example
                {"SYSTEM_OPTIONS.NETWORK.WEBSOCKET_URL": "wss://..."}
        """
        if not updates:
            return True
        try:
            for path, value in updates.items():
                if not self.update_config(path, value, save=False):
                    return False
            return self._save_config(self._config)
        except Exception as e:
            logger.error(t('批量配置更新错误: {value1}', value1=e), exc_info=True)
            return False

    def save_config(self) -> bool:
        """Push the current memory configuration to disk."""
        return self._save_config(self._config)

    def reload_config(self, *, apply_paths: bool = True) -> bool:
        """Reload configuration file.

        apply_paths: Whether to reapply PATHS overrides (without migrating directories).
        PATHS Directory migration is only performed during initialize_config.
        """
        try:
            self._config = self._load_config()
            if apply_paths:
                try:
                    from src.utils.resource_finder import (
                        apply_path_overrides_from_config,
                    )

                    apply_path_overrides_from_config(self, migrate=False)
                except Exception as e:
                    logger.warning(
                        t("reload 后应用 PATHS 失败: %s"), e, exc_info=True
                    )
            logger.info(t("配置文件已重新加载"))
            return True
        except Exception as e:
            logger.error(t('配置重新加载失败: {value1}', value1=e), exc_info=True)
            return False

    def generate_uuid(self) -> str:
        """Generate UUID v4."""
        return str(uuid.uuid4())

    def initialize_client_id(self):
        """Ensure client ID is present."""
        if not self.get_config("SYSTEM_OPTIONS.CLIENT_ID"):
            client_id = self.generate_uuid()
            success = self.update_config("SYSTEM_OPTIONS.CLIENT_ID", client_id)
            if success:
                logger.info(t('已生成新的客户端ID: {value1}', value1=client_id))
            else:
                logger.error(t("保存新的客户端ID失败"))
