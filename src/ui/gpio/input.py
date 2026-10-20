"""GPIO input processing.

encapsulates gpiozero button monitoring and supports GPIO button input of Raspberry Pi.
only supports Linux systems.

Key module specifications:
- Press to output low level (Active Low)
- Release to output high level

Default pin mapping (BCM number):
- KEY1: GPIO 17 - Start/stop conversation
- KEY2: GPIO 27 - Interrupt current voice
- KEY3: GPIO 22 - Switch automatic/manual mode
- KEY4: GPIO 23 - Exit the program

Modify DEFAULT_PINS customizable pins.
"""
import sys
import threading
from typing import Callable, List, Optional

from src.i18n import t
from src.logging import get_logger

logger = get_logger()

# Default GPIO pin configuration (BCM number)
# can be modified according to actual wiring
DEFAULT_PINS: List[int] = [17, 27, 22, 23]


class GPIOInput:
    """GPIO key input processing class.

    encapsulates gpiozero's Button class and provides key event callbacks.
    """

    def __init__(
        self,
        pins: Optional[List[int]] = None,
        bounce_time: float = 0.05,
    ):
        """Initialize GPIO input.

        Args:
            pins: GPIO pin list (BCM number), default uses DEFAULT_PINS
            bounce_time: debounce time (seconds)
        """
        self._pins = pins or DEFAULT_PINS.copy()
        self._bounce_time = bounce_time
        self._buttons: List = []
        self._callbacks: dict[int, dict[str, Optional[Callable]]] = {}
        self._lock = threading.Lock()
        self._available = False

        # Check the platform
        if sys.platform != "linux":
            logger.warning(t("GPIO 模式仅支持 Linux 系统"))
            return

        # Try to import the currently configured pin list of gpiozero
        try:
            from gpiozero import Button  # type: ignore[import-not-found]

            self._Button = Button
            self._available = True
            logger.info(t('GPIO 输入初始化成功，引脚: {value1}', value1=self._pins))
        except ImportError:
            logger.error(
                t("未安装 gpiozero 库，请运行: sudo apt install python3-gpiozero python3-rpi.gpio")
            )
        except Exception as e:
            logger.error(t('GPIO 初始化失败: {value1}', value1=e), exc_info=True)

    @property
    def available(self) -> bool:
        """GPIO is available."""
        return self._available

    @property
    def pins(self) -> List[int]:
        """."""
        return self._pins.copy()

    def setup(
        self,
        on_key1_pressed: Optional[Callable] = None,
        on_key2_pressed: Optional[Callable] = None,
        on_key3_pressed: Optional[Callable] = None,
        on_key4_pressed: Optional[Callable] = None,
    ) -> bool:
        """Set key press callback.

        Args:
            on_key1_pressed: KEY1 pressed callback
            on_key2_pressed: KEY2 Pressed callback
            on_key3_pressed: KEY3 pressed callback
            on_key4_pressed: KEY4 pressed callback

        Returns:
            Whether the setting is successful
        """
        if not self._available:
            logger.warning(t("GPIO 不可用，跳过按键设置"))
            return False

        callbacks = [on_key1_pressed, on_key2_pressed, on_key3_pressed, on_key4_pressed]

        try:
            for i, pin in enumerate(self._pins):
                # Create button instance (Active Low, internal pull-up)
                button = self._Button(pin, pull_up=True, bounce_time=self._bounce_time)
                self._buttons.append(button)

                # Save callback
                with self._lock:
                    self._callbacks[i] = {
                        "pressed": callbacks[i] if i < len(callbacks) else None,
                    }

                # Set press callback
                if i < len(callbacks) and callbacks[i]:
                    # Capture index using closure
                    def make_handler(idx: int):
                        def handler():
                            with self._lock:
                                cb = self._callbacks.get(idx, {}).get("pressed")
                            if cb:
                                logger.debug(f"KEY{idx + 1} (GPIO{self._pins[idx]}) pressed")
                                cb()

                        return handler

                    button.when_pressed = make_handler(i)

                logger.debug(t('KEY{value1} -> GPIO{value3} 已配置', value1=i + 1, value3=pin))

            logger.info(t('GPIO 按键设置完成: {value1} 个按键', value1=len(self._buttons)))
            return True

        except Exception as e:
            logger.error(t('GPIO 按键设置失败: {value1}', value1=e), exc_info=True)
            return False

    def close(self) -> None:
        """Close GPIO resources."""
        for button in self._buttons:
            try:
                button.close()
            except Exception as e:
                logger.warning(t('关闭 GPIO 按钮失败: {value1}', value1=e), exc_info=True)

        self._buttons.clear()
        with self._lock:
            self._callbacks.clear()
        logger.info(t("GPIO 资源已释放"))
