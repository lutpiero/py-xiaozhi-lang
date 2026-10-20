"""Audio device enumeration, selection and testing."""

from __future__ import annotations

import asyncio
import time

import numpy as np
import sounddevice as sd
from PySide6.QtCore import Slot

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


class SettingsAudioDevicesMixin:
    # ========== Audio device settings ==========

    def _apply_device_lists(self, devices: dict) -> None:
        """populates the input/output list with enumeration results and notifies QML."""
        self._input_devices = list(devices.get("input") or [])
        self._output_devices = list(devices.get("output") or [])
        self._audio_devices_loaded = True
        logger.debug(
            t('加载了 {value1} 个输入设备, {value3} 个输出设备', value1=len(self._input_devices), value3=len(self._output_devices))
        )
        self.devicesChanged.emit()

    def _load_audio_devices(self, force: bool = False):
        """loads the available audio device list (normal enumeration, does not re-initialize PortAudio).

        Args:
            force: True (when setting is opened)
        """
        if self._audio_devices_loaded and not force:
            return
        try:
            from src.utils.audio_utils import list_audio_devices

            devices = list_audio_devices(include_virtual=True)
            self._apply_device_lists(devices)
        except Exception as e:
            logger.error(t('加载音频设备失败: {value1}', value1=e), exc_info=True)
            self._input_devices = []
            self._output_devices = []

    @Slot(result=list)
    def getInputDevices(self) -> list:
        """Gets the input device list (enumerated again when called for the first time)."""
        self._load_audio_devices()
        return [d["name"] for d in self._input_devices]

    @Slot(result=list)
    def getOutputDevices(self) -> list:
        """Get Output device list (enumerated again when called for the first time)."""
        self._load_audio_devices()
        return [d["name"] for d in self._output_devices]

    @Slot()
    def refreshDevices(self):
        """Hot refresh device list (stop flow → PortAudio re-enumeration → restart flow).

        When connecting to Bluetooth during operation, you need to AudioPlugin first stops streaming and then ``refresh_portaudio_devices``.
        Downgrade to local ordinary enumeration when there is no EventBus.
        """
        if getattr(self, "_audio_devices_refreshing", False):
            self.statusMessage.emit(t("设备刷新进行中…"))
            return

        event_bus = getattr(self, "_event_bus", None)
        task_manager = getattr(self, "_task_manager", None)

        if event_bus is None or task_manager is None:
            logger.warning(t("SettingsModel: 无 EventBus/TaskManager，降级为本地设备枚举"))
            self._load_audio_devices(force=True)
            self.statusMessage.emit(
                t("设备列表已刷新（未协调音频流；后连蓝牙可能仍不可见）")
            )
            return

        self._audio_devices_refreshing = True
        self.statusMessage.emit(t("正在刷新音频设备（会短暂中断麦克风/播放）…"))

        async def _refresh():
            from src.core.event_bus import Events
            from src.utils.audio_utils import list_audio_devices

            # Future as payload: AudioPlugin in handler set_result (device list)
            # emit will await all handlers and return future It is usually done to force re-enumeration when
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            await event_bus.emit(Events.AUDIO_DEVICES_REFRESH_REQUEST, fut)
            if fut.done():
                result = fut.result()
            else:
                logger.warning(t("AudioPlugin 未完成设备刷新 Future，本地枚举兜底"))
                result = list_audio_devices(include_virtual=True)
                if not fut.done():
                    fut.set_result(result)
            return result if isinstance(result, dict) else {"input": [], "output": []}

        def _on_task_done(task: asyncio.Task):
            def _apply():
                try:
                    if task.cancelled():
                        devices = {"input": [], "output": []}
                    else:
                        exc = task.exception()
                        if exc is not None:
                            logger.error(t('设备刷新任务异常: {value1}', value1=exc), exc_info=exc)
                            devices = {"input": [], "output": []}
                        else:
                            devices = task.result()
                except Exception as e:
                    logger.error(t('读取刷新结果失败: {value1}', value1=e), exc_info=True)
                    devices = {"input": [], "output": []}
                try:
                    if not isinstance(devices, dict):
                        devices = {"input": [], "output": []}
                    self._apply_device_lists(devices)
                    n_in = len(self._input_devices)
                    n_out = len(self._output_devices)
                    self.statusMessage.emit(
                        t('设备列表已刷新（输入 {value1} / 输出 {value3}）', value1=n_in, value3=n_out)
                    )
                finally:
                    self._audio_devices_refreshing = False

            self._schedule_ui(_apply)

        try:
            task = task_manager.spawn(_refresh(), name="ui:audio_devices_refresh")
            if task is None:
                self._audio_devices_refreshing = False
                self._load_audio_devices(force=True)
                self.statusMessage.emit(t("应用正在关闭，已本地枚举"))
                return
            task.add_done_callback(_on_task_done)
        except Exception as e:
            self._audio_devices_refreshing = False
            logger.error(t('无法调度设备刷新: {value1}', value1=e), exc_info=True)
            self._load_audio_devices(force=True)
            self.statusMessage.emit(t('设备刷新失败，已本地枚举: {value1}', value1=e))

    def _schedule_ui(self, fn) -> None:
        """Throw the callback back to the Qt main thread (spawn's done may be in the loop thread)."""
        try:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, fn)
        except Exception:
            try:
                fn()
            except Exception as e:
                logger.error(t('UI 回调失败: {value1}', value1=e), exc_info=True)

    def _get_selectedInputIndex(self) -> int:
        """Gets the currently selected input device index."""
        current_id = self._get_value("AUDIO_DEVICES.input_device_id", -1)
        current_name = self._get_value("AUDIO_DEVICES.input_device_name", "")

        # matches first by device name
        if current_name:
            for i, d in enumerate(self._input_devices):
                if d["raw_name"] == current_name:
                    return i

        # secondly by device ID
        for i, d in enumerate(self._input_devices):
            if d["index"] == current_id:
                return i
        return 0

    def _set_selectedInputIndex(self, index: int):
        """Set the selected input device."""
        if 0 <= index < len(self._input_devices):
            device = self._input_devices[index]
            self._set_value("AUDIO_DEVICES.input_device_id", device["index"])
            self._set_value("AUDIO_DEVICES.input_device_name", device["raw_name"])
            self._set_value("AUDIO_DEVICES.input_sample_rate", device["sample_rate"])
            self._set_value("AUDIO_DEVICES.input_channels", min(device["channels"], 1))
            logger.info(t('选择输入设备: {value1}', value1=device['name']))

    def _get_selectedOutputIndex(self) -> int:
        """Gets the currently selected output device index."""
        current_id = self._get_value("AUDIO_DEVICES.output_device_id", -1)
        current_name = self._get_value("AUDIO_DEVICES.output_device_name", "")

        # matches first by device name
        if current_name:
            for i, d in enumerate(self._output_devices):
                if d["raw_name"] == current_name:
                    return i

        # secondly by device ID
        for i, d in enumerate(self._output_devices):
            if d["index"] == current_id:
                return i
        return 0

    def _set_selectedOutputIndex(self, index: int):
        """Set the selected output device."""
        if 0 <= index < len(self._output_devices):
            device = self._output_devices[index]
            self._set_value("AUDIO_DEVICES.output_device_id", device["index"])
            self._set_value("AUDIO_DEVICES.output_device_name", device["raw_name"])
            self._set_value("AUDIO_DEVICES.output_sample_rate", device["sample_rate"])
            self._set_value("AUDIO_DEVICES.output_channels", min(device["channels"], 2))
            logger.info(t('选择输出设备: {value1}', value1=device['name']))

    # Device information display
    def _get_inputDeviceInfo(self) -> str:
        idx = self._get_selectedInputIndex()
        if 0 <= idx < len(self._input_devices):
            d = self._input_devices[idx]
            return t("采样率: {rate}Hz, 通道: {channels}", rate=d["sample_rate"], channels=d["channels"])
        return t("未选择设备")

    def _get_outputDeviceInfo(self) -> str:
        idx = self._get_selectedOutputIndex()
        if 0 <= idx < len(self._output_devices):
            d = self._output_devices[idx]
            return t("采样率: {rate}Hz, 通道: {channels}", rate=d["sample_rate"], channels=d["channels"])
        return t("未选择设备")

    # Opus output sampling rate
    def _get_opusOutputSampleRate(self) -> int:
        return self._get_value("AUDIO_DEVICES.opus_output_sample_rate", 24000)

    def _set_opusOutputSampleRate(self, value: int):
        self._set_value("AUDIO_DEVICES.opus_output_sample_rate", value)

    # Audio frame length
    def _get_frameDuration(self) -> int:
        return self._get_value("AUDIO_DEVICES.frame_duration", 20)

    def _set_frameDuration(self, value: int):
        if value in [20, 40, 60]:
            self._set_value("AUDIO_DEVICES.frame_duration", value)

    # Audio test
    @Slot()
    def testInputDevice(self):
        """Test input device (recording)."""
        if self._testing_input:
            return

        idx = self._get_selectedInputIndex()
        if idx < 0 or idx >= len(self._input_devices):
            self.statusMessage.emit(t("请先选择输入设备"))
            return

        device = self._input_devices[idx]
        self._testing_input = True
        self.statusMessage.emit(t("开始录音测试..."))

        self._run_worker(
            self._do_input_test,
            device,
            name="settings:input_test",
            test_kind="input",
            clear_flags=lambda: setattr(self, "_testing_input", False),
        )

    def _do_input_test(self, device: dict):
        """performs recording test (exception caused by _run_worker takes over)."""
        device_id = device["index"]
        sample_rate = device["sample_rate"]
        duration = 3

        self.statusMessage.emit(t('请对着麦克风说话 ({value1}秒)...', value1=duration))
        time.sleep(1)

        recording = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            device=device_id,
            dtype=np.float32,
        )
        sd.wait()

        max_amplitude = np.max(np.abs(recording))

        if max_amplitude < 0.001:
            self.statusMessage.emit(t("[失败] 未检测到音频信号"))
            self.testComplete.emit("input", False)
        elif max_amplitude > 0.8:
            self.statusMessage.emit(t("[警告] 音频信号过载"))
            self.testComplete.emit("input", True)
        else:
            self.statusMessage.emit(t('[成功] 录音测试通过 (音量: {value1:.1%})', value1=max_amplitude))
            self.testComplete.emit("input", True)

    @Slot()
    def testOutputDevice(self):
        """Test output device (playback)."""
        if self._testing_output:
            return

        idx = self._get_selectedOutputIndex()
        if idx < 0 or idx >= len(self._output_devices):
            self.statusMessage.emit(t("请先选择输出设备"))
            return

        device = self._output_devices[idx]
        self._testing_output = True
        self.statusMessage.emit(t("开始播放测试..."))

        self._run_worker(
            self._do_output_test,
            device,
            name="settings:output_test",
            test_kind="output",
            clear_flags=lambda: setattr(self, "_testing_output", False),
        )

    def _do_output_test(self, device: dict):
        """Execute the playback test (exceptions are taken care of by _run_worker)."""
        device_id = device["index"]
        sample_rate = device["sample_rate"]
        duration = 2.0
        frequency = 440

        self.statusMessage.emit(t("播放 440Hz 测试音..."))
        time.sleep(0.5)

        time_axis = np.linspace(0, duration, int(sample_rate * duration))
        audio = 0.3 * np.sin(2 * np.pi * frequency * time_axis)

        fade_samples = int(0.1 * sample_rate)
        audio[:fade_samples] *= np.linspace(0, 1, fade_samples)
        audio[-fade_samples:] *= np.linspace(1, 0, fade_samples)

        sd.play(audio, samplerate=sample_rate, device=device_id)
        sd.wait()

        self.statusMessage.emit(t("[成功] 播放测试完成"))
        self.testComplete.emit("output", True)
