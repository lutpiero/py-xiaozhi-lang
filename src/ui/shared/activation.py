"""Activate UI base class.

shares the "Get code → Display → service.activate → Result" process; subclasses only display. The
"""

from src.i18n import t


class BaseActivation:
    """Activate UI Base class (non-ABC, to avoid conflict with PySide6 QObject metaclass).

    Args:
        activation_service: ActivationService instance (obtained by create(), not a singleton)
        init_result: initialize() result passed in by handle_activation to avoid duplication initialize
    """

    def __init__(self, activation_service=None, init_result=None):
        # parameter is optional: in PySide6 multiple inheritance, the super chain of QObject.__init__ may be called without parameters.
        self._service = activation_service
        self._init_result = init_result

    def needs_activation(self) -> bool:
        """Whether the UI process needs to be activated."""
        if self._init_result is None:
            return False
        return bool(self._init_result.get("need_activation_ui", False))

    async def _core_activate(self) -> bool:
        """Core activation: code acquisition → UI display → service.activate (including clipboard/broadcast side effects)."""
        if self._service is None:
            self._show_error(t("激活服务未初始化"))
            return False

        data = self._service.get_activation_data()
        if not data:
            self._show_error(t("未获取到激活数据"))
            return False

        self._show_code(data)
        success = await self._service.activate(data)
        self._show_result(success)
        return success

    async def run(self) -> bool:
        """Run the activation process."""
        raise NotImplementedError

    def _show_code(self, data: dict) -> None:
        """displays the activation verification code (CLI print/GUI write Model)."""
        raise NotImplementedError

    def _show_result(self, success: bool) -> None:
        """displays the activation result."""
        raise NotImplementedError

    def _show_error(self, msg: str) -> None:
        """Display errors (optional override)."""
        pass
