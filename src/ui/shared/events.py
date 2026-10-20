"""UI Data class of related events."""

from dataclasses import dataclass


@dataclass
class UISendTextRequest:
    """Send text."""

    text: str
