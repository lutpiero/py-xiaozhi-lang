"""
VL camera implementation using Zhipu AI.
"""

import base64
import json

import httpx
from openai import OpenAI

from src.i18n import t
from src.logging import get_logger
from src.utils.config_manager import get_config

from .base_camera import BaseCamera

logger = get_logger()


class VLCamera(BaseCamera):
    """
    Zhipu AI camera implementation.
    """

    def __init__(self):
        """
        initializes the Zhipu AI camera.
        """
        super().__init__()
        config = get_config()

        # Initialize OpenAI client (set timeout to prevent API The thread pool hangs when there is no response)
        self.client = OpenAI(
            api_key=config.get_config("CAMERA.VLapi_key"),
            base_url=config.get_config(
                "CAMERA.Local_VL_url",
                "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            ),
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
        self.model = config.get_config("CAMERA.models", "glm-4v-plus")
        logger.info(f"VL Camera initialized with model: {self.model}")

    def capture(self) -> bool:
        """
        Capture images (OpenCV/V4L2 or picamera2, see capture_backend).
        """
        return self.capture_frame()

    def analyze(self, question: str, image_data: bytes | None = None) -> str:
        try:
            buf = image_data if image_data is not None else self.jpeg_data["buf"]
            if not buf:
                return json.dumps(
                    {"success": False, "message": "Camera buffer is empty"}
                )

            # converts the image to Base64
            image_base64 = base64.b64encode(buf).decode("utf-8")

            # Prepare message
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                question
                                if question
                                else t("图中描绘的是什么景象？请详细描述。")
                            ),
                        },
                    ],
                },
            ]

            # sends the request
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                modalities=["text"],
                stream=True,
                stream_options={"include_usage": True},
            )

            # collects the response
            result = ""
            for chunk in completion:
                if chunk.choices:
                    result += chunk.choices[0].delta.content or ""

            # Record response
            logger.info(f"VL analysis completed, question={question}")
            return json.dumps({"success": True, "text": result}, ensure_ascii=False)

        except Exception as e:
            error_msg = f"Failed to analyze image with VL: {e}"
            logger.error(error_msg, exc_info=True)
            return json.dumps({"success": False, "message": error_msg})
