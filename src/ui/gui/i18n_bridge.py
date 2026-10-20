"""QML-facing translator object.

QML text uses ``i18n.t("sourcetext")`` (or ``i18n.tf`` for placeholders). The
language is selected before the QML engine starts, so no live retranslation
signal is needed; changing the language requires an application restart.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Slot

from src.i18n import get_language, t


class I18nBridge(QObject):
    """Expose the active locale catalog to QML."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    @Property(str, constant=True)
    def language(self) -> str:
        return get_language()

    @Slot(str, result=str)
    def t(self, message: str) -> str:
        return t(message)

    @Slot(str, str, result=str)
    def tc(self, context: str, message: str) -> str:
        return t(message, context=context)

    @Slot(str, "QVariantList", result=str)
    def tf(self, message: str, args: list) -> str:
        return t(message, *(str(value) for value in args))
