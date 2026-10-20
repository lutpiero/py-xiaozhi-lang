"""State manager.

Centrally manages device status and broadcasts status changes through the event bus.
"""
import asyncio
from typing import TYPE_CHECKING

from src.constants.constants import DeviceState, ListeningMode
from src.core.event_bus import EventBus, Events
from src.i18n import t
from src.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger()


class StateManager:
    """Device status manager.

    Responsibilities:
    - Manage device state (IDLE, LISTENING, SPEAKING)
    - Manage listening mode (REALTIME, AUTO_STOP, MANUAL)
    - Manage session state (keep_listening, aec_enabled)
    - Broadcast state changes over the event bus

    Usage:
        state = StateManager(event_bus)
        await state.set_device_state(DeviceState.LISTENING)
        if state.is_listening():
            ...
    """

    def __init__(self, event_bus: EventBus, aec_enabled: bool = True):
        self._event_bus = event_bus
        self._lock = asyncio.Lock()

        # Device Status
        self._device_state: DeviceState = DeviceState.IDLE

        # AEC configuration
        self._aec_enabled: bool = aec_enabled

        # Listening mode: Per AEC Configuration determines the default mode
        self._listening_mode: ListeningMode = (
            ListeningMode.REALTIME if aec_enabled else ListeningMode.AUTO_STOP
        )

        # Session status
        self._keep_listening: bool = False

        # Abort flag
        self._aborted: bool = False

    # -------------------------
    # Device Status
    # -------------------------
    @property
    def device_state(self) -> DeviceState:
        """
        Gets the current device status.
        """
        return self._device_state

    async def set_device_state(self, state: DeviceState) -> None:
        """sets the device state.

        Args:
            state: New device state

        If the status changes, it will be broadcast through the event bus.
        """
        async with self._lock:
            if self._device_state == state:
                return

            old_state = self._device_state
            self._device_state = state
            logger.info(t('设备状态变更: {value1} -> {value3}', value1=old_state, value3=state))

            # Reset the abort flag
            if state == DeviceState.LISTENING:
                self._aborted = False

        # Broadcast outside the lock to avoid deadlock
        await self._event_bus.emit(
            Events.DEVICE_STATE_CHANGED,
            {"old_state": old_state, "new_state": state},
        )

    def is_idle(self) -> bool:
        """
        is in idle state.
        """
        return self._device_state == DeviceState.IDLE

    def is_listening(self) -> bool:
        """
        is listening.
        """
        return self._device_state == DeviceState.LISTENING

    def is_speaking(self) -> bool:
        """
        is talking.
        """
        return self._device_state == DeviceState.SPEAKING

    # -------------------------
    # Listening mode
    # -------------------------
    @property
    def listening_mode(self) -> ListeningMode:
        """
        Gets the current listening mode.
        """
        return self._listening_mode

    def set_listening_mode(self, mode: ListeningMode) -> None:
        """
        sets the listening mode.
        """
        self._listening_mode = mode
        logger.debug(t('监听模式设置为: {value1}', value1=mode))

    # -------------------------
    # Session status
    # -------------------------
    @property
    def keep_listening(self) -> bool:
        """
        maintains continuous monitoring.
        """
        return self._keep_listening

    def set_keep_listening(self, value: bool) -> None:
        """
        sets the continuous listening state.
        """
        self._keep_listening = value
        logger.debug(t('持续监听: {value1}', value1=value))

    @property
    def aec_enabled(self) -> bool:
        """
        AEC is enabled.
        """
        return self._aec_enabled

    # -------------------------
    # Abort status
    # -------------------------
    @property
    def aborted(self) -> bool:
        """
        Is aborted.
        """
        return self._aborted

    def set_aborted(self, value: bool) -> None:
        """
        Set abort status.
        """
        self._aborted = value

    # -------------------------
    # Composite status query
    # -------------------------
    def should_capture_audio(self) -> bool:
        """should collect audio.

        Required in the following situations Set:
        1. Listening and not aborted
        2. Talking, but AEC is enabled and keeps listening in real-time mode
        """
        if self._device_state == DeviceState.LISTENING and not self._aborted:
            return True

        return (
            self._device_state == DeviceState.SPEAKING
            and self._aec_enabled
            and self._keep_listening
            and self._listening_mode == ListeningMode.REALTIME
        )

    def get_snapshot(self) -> dict:
        """Get status snapshot.

        returns a dictionary of all current states for debugging and logging.
        """
        return {
            "device_state": self._device_state,
            "listening_mode": self._listening_mode,
            "keep_listening": self._keep_listening,
            "aec_enabled": self._aec_enabled,
            "aborted": self._aborted,
        }
