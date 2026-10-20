"""UI Common: ViewPort contract, factory, activation base class, cross-end event DTO.

Qt ViewModel in src.ui.gui.models (GUI use only).
"""

from src.ui.shared.activation import BaseActivation
from src.ui.shared.events import UISendTextRequest
from src.ui.shared.factory import create_viewport
from src.ui.shared.viewport import ViewPort

__all__ = [
    "BaseActivation",
    "UISendTextRequest",
    "ViewPort",
    "create_viewport",
]
