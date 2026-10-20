"""Create activation UI in run mode (symmetric with create_viewport)."""

from typing import Any


def create_activation_ui(mode: str, activation_service, init_result: dict) -> Any:
    """gui → GuiActivation; tui/cli/gpio → CliActivation.

    Args:
        mode: Run mode
        activation_service: ActivationService instance
        init_result: initialize() result (to avoid repeated initialize)
    """
    normalized = (mode or "cli").lower()
    if normalized == "gui":
        from src.ui.gui import GuiActivation

        return GuiActivation(activation_service, init_result)

    # tui/cli/gpio: Simple terminal interaction during activation phase
    from src.ui.cli import CliActivation

    return CliActivation(activation_service, init_result)
