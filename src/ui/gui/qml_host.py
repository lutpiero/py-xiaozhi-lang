"""QML engine host: loading, context injection, root window operation."""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


def _show_window(window, *, activate: bool) -> None:
    """displays the window; try not to rush to the foreground when activate=False (macOS Full screen Space friendly)."""
    if window is None:
        return

    if activate:
        window.show()
        window.raise_()
        window.requestActivate()
        return

    # QWidget Path: ShowWithoutActivating
    set_attr = getattr(window, "setAttribute", None)
    if callable(set_attr):
        set_attr(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        try:
            window.show()
        finally:
            set_attr(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        return

    # QQuickWindow / QWindow: temporarily removed to gain focus, avoid becoming key window
    # (key window on macOS will squeeze out the Space of other full screen apps)
    flags = window.flags()
    try:
        window.setFlags(flags | Qt.WindowType.WindowDoesNotAcceptFocus)
        window.show()
    finally:
        window.setFlags(flags)


class QmlAppHost:
    """is only responsible for the QML engine life cycle and root object access, and does not touch business logic."""

    def __init__(self) -> None:
        self._engine: QQmlApplicationEngine | None = None

    @property
    def engine(self) -> QQmlApplicationEngine | None:
        return self._engine

    def create_engine(self) -> QQmlApplicationEngine:
        self._engine = QQmlApplicationEngine()
        return self._engine

    def inject_context(self, properties: dict) -> None:
        if not self._engine:
            raise RuntimeError("QML engine not created")
        ctx = self._engine.rootContext()
        for name, obj in properties.items():
            ctx.setContextProperty(name, obj)
        logger.debug(t("QmlAppHost: 已注入 QML 上下文 %s"), list(properties))

    def load_main(self) -> None:
        if not self._engine:
            raise RuntimeError("QML engine not created")
        qml_dir = Path(__file__).parent / "qml"
        self._engine.addImportPath(str(qml_dir))
        main_qml = qml_dir / "main.qml"
        self._engine.load(QUrl.fromLocalFile(str(main_qml)))
        if not self._engine.rootObjects():
            logger.error(t("QmlAppHost: QML 加载失败"))
            raise RuntimeError("Failed to load QML")
        logger.debug(t("QmlAppHost: 已加载 %s"), main_qml)

    def root_window(self):
        if not self._engine:
            return None
        roots = self._engine.rootObjects()
        return roots[0] if roots else None

    def show_root(self, *, activate: bool = True) -> None:
        """displays the main window.

        Args:
            activate: True=grab the foreground (tray "display window"/shortcut key);
                      False=Only display, no requestActivate (cold start, avoid crowding out macOS full-screen App)
        """
        _show_window(self.root_window(), activate=activate)

    def toggle_root_visible(self) -> None:
        window = self.root_window()
        if window is None:
            return
        if window.isVisible():
            window.hide()
        else:
            # Users actively switch: need to go to the front desk
            self.show_root(activate=True)

    def shutdown(self) -> None:
        if self._engine:
            self._engine.deleteLater()
            self._engine = None
