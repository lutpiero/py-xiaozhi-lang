"""Camera enumeration and testing."""
from PySide6.QtCore import Slot

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


class SettingsCameraDevicesMixin:
    # ========== Camera device list ==========

    def _load_cameras(self, force: bool = False):
        """loads the camera list in the background thread to avoid blocking the Qt main thread.

        is not called when the application starts; it is only triggered when the Settings/Refresh/Camera page is opened.
        """
        if self._cameras_loading:
            return
        if self._cameras_loaded_once and not force and self._cameras:
            return

        self._cameras_loading = True
        self._run_worker(
            self._do_load_cameras,
            name="settings:scan_cameras",
            clear_flags=lambda: setattr(self, "_cameras_loading", False),
        )

    def _do_load_cameras(self):
        """performs camera scanning (OpenCV/V4L2 Optional picamera2)."""
        cameras: list[dict] = []
        try:
            from src.mcp.tools.camera.capture_backend import list_camera_devices

            devices = list_camera_devices(max_index=5, consecutive_fail_limit=2)
            for d in devices:
                cameras.append(
                    {
                        "key": d.key,
                        "index": d.index if d.index is not None else -1,
                        "name": d.name,
                        "kind": d.kind,
                        "path": d.path,
                    }
                )
            logger.info(t('摄像头扫描完成: 找到 {value1} 个', value1=len(cameras)))
        except Exception as e:
            logger.error(t('扫描摄像头失败: {value1}', value1=e), exc_info=True)
            raise
        finally:
            self._cameras = cameras
            self._cameras_loaded_once = True
            self.devicesChanged.emit()
            self.statusMessage.emit(
                t("摄像头列表已刷新（{count} 个）", count=len(cameras))
                if cameras
                else t("未检测到摄像头（Pi CSI 需安装 picamera2）")
            )

    @Slot(result=list)
    def getCameras(self) -> list:
        """Get the camera list (does not automatically trigger scanning; triggered by settings page/refresh)."""
        return [c["name"] for c in self._cameras]

    @Slot()
    def refreshCameras(self):
        """refreshes the camera list (non-blocking)."""
        self._load_cameras(force=True)

    def _current_camera_key(self) -> str:
        """restores the currently selected enumeration key from the configuration."""
        device = str(self._get_value("CAMERA.device", "") or "").strip()
        backend = (
            str(self._get_value("CAMERA.backend", "auto") or "auto").strip().lower()
        )
        if backend == "picamera2":
            return "picamera2"
        if device:
            return device
        try:
            return str(int(self._get_value("CAMERA.camera_index", 0) or 0))
        except (TypeError, ValueError):
            return "0"

    def _get_selectedCameraIndex(self) -> int:
        """Get the subscript of the currently selected camera in the list."""
        current_key = self._current_camera_key()
        for i, c in enumerate(self._cameras):
            if c.get("key") == current_key:
                return i
        # is compatible with old logic: only configured with index
        try:
            current_idx = int(self._get_value("CAMERA.camera_index", 0) or 0)
        except (TypeError, ValueError):
            current_idx = 0
        for i, c in enumerate(self._cameras):
            if c.get("index") == current_idx and c.get("kind") in ("opencv", "v4l2"):
                return i
        return 0

    def _set_selectedCameraIndex(self, index: int):
        """Set the selected camera (write backend/device/index)."""
        if 0 <= index < len(self._cameras):
            camera = self._cameras[index]
            from src.mcp.tools.camera.capture_backend import apply_device_selection

            updates = apply_device_selection(str(camera.get("key", "")))
            for path, value in updates.items():
                self._set_value(path, value)
            logger.info(t('选择摄像头: {value1} -> {value3}', value1=camera['name'], value3=updates))

    @Slot()
    def testCamera(self):
        """Test the camera, capture a frame and display."""
        if not self._cameras:
            self.statusMessage.emit(t("没有可用的摄像头"))
            return

        idx = self._get_selectedCameraIndex()
        if idx < 0 or idx >= len(self._cameras):
            self.statusMessage.emit(t("请先选择摄像头"))
            return

        camera = self._cameras[idx]
        self.statusMessage.emit(t('正在测试摄像头 {value1}...', value1=camera['name']))

        self._run_worker(
            self._do_camera_test,
            camera,
            name="settings:camera_test",
            test_kind="camera",
        )

    def _do_camera_test(self, camera: dict):
        """Perform camera test (go to unity capture_backend)."""
        from src.mcp.tools.camera.capture_backend import (
            CaptureConfig,
            apply_device_selection,
            capture_jpeg,
        )

        updates = apply_device_selection(str(camera.get("key", "")))
        backend = updates.get("CAMERA.backend", "auto")
        device = updates.get("CAMERA.device", "") or ""
        try:
            cam_index = int(updates.get("CAMERA.camera_index", 0) or 0)
        except (TypeError, ValueError):
            cam_index = 0

        try:
            width = int(self._get_value("CAMERA.frame_width", 640) or 640)
            height = int(self._get_value("CAMERA.frame_height", 480) or 480)
            warm = int(self._get_value("CAMERA.warm_up_frames", 5) or 5)
        except (TypeError, ValueError):
            width, height, warm = 640, 480, 5

        cfg = CaptureConfig(
            camera_index=cam_index,
            device=device,
            backend=str(backend),
            frame_width=width,
            frame_height=height,
            warm_up_frames=warm,
            jpeg_max_side=640,
        )
        jpeg = capture_jpeg(cfg)
        if not jpeg:
            self.statusMessage.emit(
                t("[失败] 无法捕获图像（Pi CSI 请装 python3-picamera2 或改选 USB）")
            )
            self.testComplete.emit("camera", False)
            return

        self.statusMessage.emit(
            t('[成功] 摄像头正常 (JPEG {value1} bytes, {value3})', value1=len(jpeg), value3=camera['name'])
        )
        self.testComplete.emit("camera", True)
