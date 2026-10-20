"""
Base camera implementation.
"""
from abc import ABC, abstractmethod
from typing import Any

from src.i18n import t
from src.logging import get_logger
from src.utils.config_manager import get_config

from .capture_backend import capture_jpeg, load_capture_config

logger = get_logger()


class BaseCamera(ABC):
    """
    is a basic camera class that defines the interface.
    """

    def __init__(self):
        """
        Initializes the basic camera.
        """
        self.jpeg_data = {"buf": b"", "len": 0}  # JPEG byte data of the image

        # Read camera parameters from the configuration (acquisition details are provided by capture_backend Unified reading)
        config = get_config()
        self.camera_index = config.get_config("CAMERA.camera_index", 0)
        self.frame_width = config.get_config("CAMERA.frame_width", 640)
        self.frame_height = config.get_config("CAMERA.frame_height", 480)

    def capture_frame(self) -> bool:
        """Acquire a frame of JPEG using a pluggable backend (OpenCV/V4L2 or picamera2).

        Desktop USB / Pi USB go OpenCV; Pi CSI falls back to picamera2 after OpenCV fails in auto mode.
        has timeout protection to prevent the driver from hanging and threads.
        """
        cfg = load_capture_config()
        # is aligned with the instance field (if the external index is changed, the configuration shall prevail, and the configuration is authoritative)
        self.camera_index = cfg.camera_index
        self.frame_width = cfg.frame_width
        self.frame_height = cfg.frame_height

        jpeg = capture_jpeg(cfg)
        if not jpeg:
            logger.error(
                t('摄像头采集失败 (backend={value1}, device={value3!r}, index={value5})', value1=cfg.backend, value3=cfg.device, value5=cfg.camera_index)
            )
            return False

        self.set_jpeg_data(jpeg)
        logger.info(
            f"Image captured successfully (size: {self.jpeg_data['len']} bytes)"
        )
        return True

    # Compatible with the old name
    def capture_with_cv2(self) -> bool:
        return self.capture_frame()

    def set_explain_url(self, url: str):  # noqa: B027
        """sets the vision service URL (subclasses can override on demand)."""

    def set_explain_token(self, token: str):  # noqa: B027
        """sets the vision service token (subclasses can override on demand)."""

    @abstractmethod
    def capture(self) -> bool:
        """
        Capture image.
        """

    @abstractmethod
    def analyze(self, question: str, image_data: bytes | None = None) -> str:
        """Analyze the image.

        Args:
            question: User question
            image_data: Optional external image data, used when None self.jpeg_data
        """

    def get_jpeg_data(self) -> dict[str, Any]:
        """
        Gets JPEG data.
        """
        return self.jpeg_data

    def set_jpeg_data(self, data_bytes: bytes):
        """
        Sets JPEG data.
        """
        self.jpeg_data["buf"] = data_bytes
        self.jpeg_data["len"] = len(data_bytes)
