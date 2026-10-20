"""Camera acquisition backend: OpenCV/UVC (Desktop Pi USB) and Picamera2 (Pi CSI).

The desktop USB camera uses OpenCV; the Raspberry Pi CSI official stack uses picamera2 (optional dependency).
``backend=auto`` try first OpenCV, fails and falls back to picamera2.
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.i18n import t
from src.logging import get_logger
from src.utils.config_manager import get_config

logger = get_logger()

_CAPTURE_TIMEOUT_S = 12.0


@dataclass
class CaptureConfig:
    """Acquisition parameters (from CAMERA.* configuration)."""

    camera_index: int = 0
    device: str = ""  # Such as /dev/video0; when not empty, it takes precedence over index
    backend: str = "auto"  # auto | opencv | picamera2
    frame_width: int = 640
    frame_height: int = 480
    warm_up_frames: int = 5
    jpeg_max_side: int = 320


@dataclass
class CameraDeviceInfo:
    """Displayable/optional camera entry."""

    key: str  # The identifier of the written configuration: number index string / device path / "picamera2"
    name: str
    kind: str  # opencv | v4l2 | picamera2
    index: int | None = None
    path: str | None = None


def load_capture_config() -> CaptureConfig:
    """to read CAMERA from ConfigManager Acquisition configuration."""
    cfg = get_config()
    raw_backend = (
        str(cfg.get_config("CAMERA.backend", "auto") or "auto").strip().lower()
    )
    if raw_backend not in ("auto", "opencv", "picamera2"):
        raw_backend = "auto"

    device = str(cfg.get_config("CAMERA.device", "") or "").strip()
    try:
        index = int(cfg.get_config("CAMERA.camera_index", 0) or 0)
    except (TypeError, ValueError):
        index = 0
    try:
        width = int(cfg.get_config("CAMERA.frame_width", 640) or 640)
    except (TypeError, ValueError):
        width = 640
    try:
        height = int(cfg.get_config("CAMERA.frame_height", 480) or 480)
    except (TypeError, ValueError):
        height = 480
    try:
        warm = int(cfg.get_config("CAMERA.warm_up_frames", 5) or 5)
    except (TypeError, ValueError):
        warm = 5
    warm = max(0, min(warm, 30))

    return CaptureConfig(
        camera_index=max(0, index),
        device=device,
        backend=raw_backend,
        frame_width=max(1, width),
        frame_height=max(1, height),
        warm_up_frames=warm,
    )


def _silence_opencv_logs() -> None:
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    try:
        import cv2

        if hasattr(cv2, "setLogLevel"):
            cv2.setLogLevel(0)
        if hasattr(cv2, "utils") and hasattr(cv2.utils, "logging"):
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:
        pass


def _opencv_open_kwargs():
    """Linux is preferred V4L2, other platforms use the default backend."""
    try:
        import cv2

        if sys.platform.startswith("linux") and hasattr(cv2, "CAP_V4L2"):
            return {"apiPreference": cv2.CAP_V4L2}
    except Exception:
        pass
    return {}


def _open_capture(source: Any):
    """Open VideoCapture; source is int index or device path string."""
    import cv2

    kwargs = _opencv_open_kwargs()
    if kwargs:
        cap = cv2.VideoCapture(source, kwargs["apiPreference"])
        if cap is not None and cap.isOpened():
            return cap
        try:
            cap.release()
        except Exception:
            pass
    return cv2.VideoCapture(source)


def _encode_bgr_jpeg(frame, max_side: int = 320) -> bytes | None:
    import cv2

    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    height, width = frame.shape[:2]
    max_dim = max(height, width)
    if max_side > 0 and max_dim > max_side:
        scale = max_side / max_dim
        frame = cv2.resize(
            frame,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        return None
    return buf.tobytes()


def _bgr_from_picamera_array(arr):
    """Picamera2 The default is always RGB/XRGB, convert it to OpenCV BGR."""
    import cv2
    import numpy as np

    if arr is None:
        return None
    if arr.ndim == 2:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    if arr.shape[2] == 4:
        # XRGB / BGRA, etc.: press the RGB channel to take the first 3 and then convert to BGR (picamera2 common RGB)
        rgb = arr[:, :, :3]
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if arr.shape[2] == 3:
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    return np.ascontiguousarray(arr)


def _capture_opencv(cfg: CaptureConfig) -> bytes | None:
    _silence_opencv_logs()
    import cv2

    source: Any
    if cfg.device:
        source = cfg.device
        logger.info(t('OpenCV 打开设备路径: {value1}', value1=source))
    else:
        source = int(cfg.camera_index)
        logger.info(t('OpenCV 打开 index: {value1}', value1=source))

    cap = _open_capture(source)
    if not cap.isOpened():
        logger.error(t('OpenCV 无法打开摄像头 source={value1!r}', value1=source))
        return None

    try:
        # Resolution: best effort setting, failure is not considered fatal
        if cfg.frame_width > 0:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.frame_width)
        if cfg.frame_height > 0:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.frame_height)

        frame = None
        ret = False
        # Warm up: many USB/Pi devices first few frames invalid
        loops = max(1, cfg.warm_up_frames + 1)
        for i in range(loops):
            ret, frame = cap.read()
            if ret and frame is not None and getattr(frame, "size", 0) > 0:
                # Reading one more frame is sometimes more stable, but there are already valid frames that can end the warm-up tail early
                if i >= max(0, cfg.warm_up_frames - 1):
                    break
            time.sleep(0.03)

        if not ret or frame is None:
            logger.error(t('OpenCV 读帧失败 source={value1!r}', value1=source))
            return None

        jpeg = _encode_bgr_jpeg(frame, cfg.jpeg_max_side)
        if not jpeg:
            logger.error(t("OpenCV JPEG 编码失败"))
            return None
        logger.info(
            t('OpenCV 采集成功 source={value1!r} size={value3} backend={value5}', value1=source, value3=len(jpeg), value5=cap.getBackendName() if hasattr(cap, 'getBackendName') else '?')
        )
        return jpeg
    finally:
        try:
            cap.release()
        except Exception:
            pass


def _picamera2_available() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    try:
        import picamera2  # noqa: F401

        return True
    except Exception:
        return False


def _capture_picamera2(cfg: CaptureConfig) -> bytes | None:
    if not sys.platform.startswith("linux"):
        logger.error(t("picamera2 仅支持 Linux/树莓派"))
        return None
    try:
        from picamera2 import Picamera2
    except ImportError:
        logger.error(
            t("未安装 picamera2，无法使用 CSI 摄像头。Pi 上: sudo apt install python3-picamera2")
        )
        return None

    picam2 = None
    try:
        picam2 = Picamera2()
        # still configuration; the size should be as close to the configuration as possible, and the driver will select the closest mode
        controls = {}
        config = picam2.create_still_configuration(
            main={"size": (cfg.frame_width, cfg.frame_height)},
            controls=controls,
        )
        picam2.configure(config)
        picam2.start()
        # Give AE/AWB some time
        time.sleep(0.2)
        for _ in range(max(1, cfg.warm_up_frames)):
            try:
                picam2.capture_array()
            except Exception:
                time.sleep(0.05)
        arr = picam2.capture_array()
        bgr = _bgr_from_picamera_array(arr)
        jpeg = _encode_bgr_jpeg(bgr, cfg.jpeg_max_side)
        if not jpeg:
            logger.error(t("picamera2 JPEG 编码失败"))
            return None
        logger.info(t('picamera2 采集成功 size={value1}', value1=len(jpeg)))
        return jpeg
    except Exception as e:
        logger.error(t('picamera2 采集失败: {value1}', value1=e), exc_info=True)
        return None
    finally:
        if picam2 is not None:
            try:
                picam2.stop()
            except Exception:
                pass
            try:
                picam2.close()
            except Exception:
                pass


def capture_jpeg(cfg: CaptureConfig | None = None) -> bytes | None:
    """Capture a frame of JPEG bytes according to configuration; return on failure None."""
    cfg = cfg or load_capture_config()
    backend = cfg.backend

    def _run() -> bytes | None:
        if backend == "opencv":
            return _capture_opencv(cfg)
        if backend == "picamera2":
            return _capture_picamera2(cfg)

        # auto: OpenCV (USB/UVC) first, then picamera2 (CSI)
        jpeg = _capture_opencv(cfg)
        if jpeg:
            return jpeg
        if _picamera2_available():
            logger.info(t("OpenCV 采集失败，auto 回退 picamera2（CSI）"))
            return _capture_picamera2(cfg)
        return None

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_run)
        try:
            return fut.result(timeout=_CAPTURE_TIMEOUT_S)
        except FuturesTimeout:
            logger.error(
                t('摄像头采集超时 ({value1}s) backend={value3} device={value5!r} index={value7}', value1=_CAPTURE_TIMEOUT_S, value3=backend, value5=cfg.device, value7=cfg.camera_index)
            )
            return None


def _list_v4l2_paths() -> list[str]:
    if not sys.platform.startswith("linux"):
        return []
    dev = Path("/dev")
    if not dev.exists():
        return []
    paths = sorted(
        str(p)
        for p in dev.glob("video*")
        if p.name.startswith("video") and p.name[5:].isdigit()
    )
    return paths


def list_camera_devices(
    max_index: int = 5,
    consecutive_fail_limit: int = 2,
) -> list[CameraDeviceInfo]:
    """Enumerate available cameras (setting page/scan script)."""
    _silence_opencv_logs()
    devices: list[CameraDeviceInfo] = []
    seen: set[str] = set()

    # 1) Linux: /dev/video* is listed first (to facilitate Pi selection of the correct node)
    for path in _list_v4l2_paths():
        try:

            cap = _open_capture(path)
            opened = bool(cap.isOpened())
            if opened:
                # Try to read a frame to determine whether it is a real capture node
                ok = False
                try:
                    for _ in range(2):
                        ret, frame = cap.read()
                        if ret and frame is not None and getattr(frame, "size", 0) > 0:
                            ok = True
                            break
                except Exception:
                    ok = False
                cap.release()
                if ok:
                    key = path
                    if key not in seen:
                        devices.append(
                            CameraDeviceInfo(
                                key=key,
                                name=f"V4L2 {path}",
                                kind="v4l2",
                                path=path,
                            )
                        )
                        seen.add(key)
            else:
                try:
                    cap.release()
                except Exception:
                    pass
        except Exception as e:
            logger.debug(t('探测 {value1} 失败: {value3}', value1=path, value3=e))

    # 2) OpenCV digital index (all platforms)
    consecutive_fail = 0
    for i in range(max(0, max_index) + 1):
        try:
            cap = _open_capture(i)
            opened = bool(cap.isOpened())
            if opened:
                key = str(i)
                # Skip repeat if already listed via /dev/video{i}
                path_alias = f"/dev/video{i}"
                if key not in seen and path_alias not in seen:
                    devices.append(
                        CameraDeviceInfo(
                            key=key,
                            name=t('摄像头 {value1}', value1=i),
                            kind="opencv",
                            index=i,
                        )
                    )
                    seen.add(key)
                try:
                    cap.release()
                except Exception:
                    pass
                consecutive_fail = 0
            else:
                consecutive_fail += 1
                try:
                    cap.release()
                except Exception:
                    pass
                if consecutive_fail >= consecutive_fail_limit:
                    break
        except Exception as e:
            consecutive_fail += 1
            logger.debug(t('探测 index={value1} 失败: {value3}', value1=i, value3=e))
            if consecutive_fail >= consecutive_fail_limit:
                break

    # 3) Raspberry Pi CSI
    if _picamera2_available():
        key = "picamera2"
        if key not in seen:
            devices.append(
                CameraDeviceInfo(
                    key=key,
                    name=t("树莓派 CSI (picamera2)"),
                    kind="picamera2",
                )
            )
            seen.add(key)

    logger.info(t('摄像头枚举完成: {value1} 个 {value3}', value1=len(devices), value3=[d.name for d in devices]))
    return devices


def apply_device_selection(key: str) -> dict[str, Any]:
    """Generate configuration fragments that should be written based on the enumeration key.

    Returns:
        updatable dict: camera_index / device /backend
    """
    key = (key or "").strip()
    if key == "picamera2":
        return {
            "CAMERA.backend": "picamera2",
            "CAMERA.device": "",
            "CAMERA.camera_index": 0,
        }
    if key.startswith("/dev/"):
        return {
            "CAMERA.backend": "opencv",
            "CAMERA.device": key,
            "CAMERA.camera_index": 0,
        }
    try:
        idx = int(key)
    except ValueError:
        idx = 0
    return {
        "CAMERA.backend": "auto",
        "CAMERA.device": "",
        "CAMERA.camera_index": idx,
    }
