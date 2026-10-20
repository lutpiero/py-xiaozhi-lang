"""Local music cache directory management."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from src.i18n import t
from src.logging import get_logger
from src.utils.resource_finder import get_music_cache_dir

logger = get_logger()


class MusicCache:
    """Manage the music cache directory and temporary files."""

    def __init__(self, root: Path | None = None) -> None:
        base = root or get_music_cache_dir()
        self.root = base
        self.temp_dir = base / "temp"
        self._ready = False
        self._temp_cleaned = False

    def ensure(self) -> None:
        """Create cache directory (idempotent)."""
        if self._ready:
            return
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            self._ready = True
            logger.debug(t('音乐缓存目录就绪: {value1}', value1=self.root))
        except Exception as e:
            logger.error(t('创建缓存目录失败: {value1}', value1=e), exc_info=True)
            self.root = Path(tempfile.gettempdir()) / "xiaozhi_music_cache"
            self.temp_dir = self.root / "temp"
            self.root.mkdir(parents=True, exist_ok=True)
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            self._ready = True

    def prepare(self) -> None:
        """Call before using the cache for the first time: Create the directory and clean it once temp."""
        self.ensure()
        if not self._temp_cleaned:
            self.clean_temp()
            self._temp_cleaned = True

    def path_for_song(self, song_id: str, ext: str = ".mp3") -> Path:
        """Generate the cache file path based on song_id."""
        self.ensure()
        if not ext.startswith("."):
            ext = f".{ext}"
        return self.root / f"{song_id}{ext}"

    def find_song_file(self, song_id: str) -> Path | None:
        """Press song_id Find cached files (try common suffixes)."""
        self.ensure()
        for ext in (".mp3", ".m4a", ".flac", ".wav", ".ogg"):
            p = self.root / f"{song_id}{ext}"
            if p.exists():
                return p
        return None

    def has(self, song_id: str, ext: str = ".mp3") -> bool:
        return self.path_for_song(song_id, ext).exists()

    def temp_path(self, filename: str) -> Path:
        """Temporary file path used during downloading."""
        self.ensure()
        return self.temp_dir / f"temp_{int(time.time())}_{filename}"

    def list_music_files(self) -> list[Path]:
        """List music files in cache."""
        self.ensure()
        if not self.root.exists():
            return []
        files: list[Path] = []
        for pattern in ("*.mp3", "*.m4a", "*.flac", "*.wav", "*.ogg"):
            files.extend(self.root.glob(pattern))
        return files

    def clean_temp(self) -> None:
        """Clear the temp directory."""
        try:
            if not self.temp_dir.exists():
                return
            for file_path in self.temp_dir.glob("*"):
                try:
                    if file_path.is_file():
                        file_path.unlink()
                        logger.debug(t('已删除临时缓存文件: {value1}', value1=file_path.name))
                except Exception as e:
                    logger.warning(
                        t('删除临时缓存文件失败: {value1}, {value3}', value1=file_path.name, value3=e),
                        exc_info=True,
                    )
            logger.debug(t("临时音乐缓存清理完成"))
        except Exception as e:
            logger.error(t('清理临时缓存目录失败: {value1}', value1=e), exc_info=True)
