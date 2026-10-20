# -*- coding: utf-8 -*-
"""Emoji Service - Manage emoticon resources."""
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QUrl

from src.i18n import t
from src.logging import get_logger
from src.utils.resource_finder import get_assets_dir

logger = get_logger()


class EmotionService(QObject):
    """Emoticon service - Handle lookup and URL conversion of emoticon files."""

    EXTENSIONS = (".gif", ".png", ".jpg", ".jpeg", ".webp")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache: dict[str, str] = {}
        self._emotion_dir = get_assets_dir() / "emojis"

        if not self._emotion_dir.exists():
            logger.warning(t('表情目录不存在: {value1}', value1=self._emotion_dir))

    def get_emotion_url(self, emotion_name: str) -> str:
        """Get emoticon's QML available URL.

        Args:
            emotion_name: Expression name

        Returns:
            file:// URL or emoji characters
        """
        # Check cache
        if emotion_name in self._cache:
            return self._cache[emotion_name]

        # Find file
        path = self._find_emotion_file(emotion_name)
        if not path:
            # fall back to neutral
            path = self._find_emotion_file("neutral")

        # Convert to URL
        if path:
            url = QUrl.fromLocalFile(str(path)).toString()
        else:
            url = "😊"  # Final fallback
            logger.warning(t('表情 {value1} 未找到，使用 emoji', value1=emotion_name))

        self._cache[emotion_name] = url
        return url

    def _find_emotion_file(self, name: str) -> Optional[Path]:
        """Find emoticon file."""
        for ext in self.EXTENSIONS:
            file_path = self._emotion_dir / f"{name}{ext}"
            if file_path.exists():
                return file_path
        return None

    def clear_cache(self):
        """Clear cache."""
        self._cache.clear()

    def preload(self, names: list[str]):
        """Preload emoticons."""
        for name in names:
            self.get_emotion_url(name)
        logger.debug(t('已预加载 {value1} 个表情', value1=len(names)))
