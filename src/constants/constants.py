import platform
from enum import Enum


class ListeningMode(str, Enum):
    """
    Listening mode.
    """

    REALTIME = "realtime"
    AUTO_STOP = "auto_stop"
    MANUAL = "manual"


class AbortReason(str, Enum):
    """
    Abort reason.
    """

    NONE = "none"
    WAKE_WORD_DETECTED = "wake_word_detected"
    USER_INTERRUPTION = "user_interruption"


class DeviceState(str, Enum):
    """
    Device status.
    """

    IDLE = "idle"
    LISTENING = "listening"
    SPEAKING = "speaking"


class EventType:
    """
    Event type.
    """

    SCHEDULE_EVENT = "schedule_event"
    AUDIO_INPUT_READY_EVENT = "audio_input_ready_event"
    AUDIO_OUTPUT_READY_EVENT = "audio_output_ready_event"


def get_frame_duration() -> int:
    """Get the frame length of the device.

    is read from the configuration first. If there is no configuration, it is automatically detected based on the device architecture.
    does not read configuration when import constants.

    returns:
        int: frame length (ms), supports 20/40/60
    """
    try:
        from src.utils.config_manager import get_config

        configured = get_config().get_config(
            "AUDIO_DEVICES.frame_duration"
        )
        if configured in [20, 40, 60]:
            return configured

        # Automatically detected when no configuration (maintains backward compatibility)
        machine = platform.machine().lower()
        arm_archs = ["arm", "aarch64", "armv7l", "armv6l"]
        is_arm_device = any(arch in machine for arch in arm_archs)

        if is_arm_device:
            # ARM devices (such as Raspberry Pi) use larger frame lengths to reduce CPU load
            return 60
        else:
            # Other devices (Windows/macOS/Linux x86) have sufficient performance to use low latency
            return 20

    except Exception:
        # If acquisition fails, return to the default value of 20ms (suitable for most modern devices)
        return 20


class AudioConfig:
    """
    Audio configuration class - protocol layer parameters, independent of the device layer (DeviceConfig).

    Default value is declared in the class body; dynamically loaded from ConfigManager via reload().
    is no longer in the import Force reload to avoid constants module side effects.
    """

    # Fixed value of server protocol (does not change with configuration)
    INPUT_SAMPLE_RATE = 16000  # Protocol requirements: input 16kHz
    CHANNELS = 1  # Protocol requirements: mono

    # The following are dynamic values. When reload(),
    OUTPUT_SAMPLE_RATE: int = 24000
    FRAME_DURATION: int = 20
    INPUT_FRAME_SIZE: int = 320

    @classmethod
    def reload(cls):
        """Reload protocol audio parameters from ConfigManager, support runtime hot reload.

        Settings UI After modifying opus_output_sample_rate / frame_duration,
        Call this method to make the new value take effect the next time initialize/reload_devices.
        """
        try:
            from src.utils.config_manager import get_config

            config = get_config()
            cls.OUTPUT_SAMPLE_RATE = config.get_config(
                "AUDIO_DEVICES.opus_output_sample_rate", 24000
            )
        except Exception:
            # Retains the current/default value when the configuration is unavailable
            pass
        cls.FRAME_DURATION = get_frame_duration()
        cls.INPUT_FRAME_SIZE = int(cls.INPUT_SAMPLE_RATE * (cls.FRAME_DURATION / 1000))
