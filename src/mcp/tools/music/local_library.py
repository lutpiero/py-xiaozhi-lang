"""Local cache music library: scan, list, search."""

from __future__ import annotations

import time
from pathlib import Path

from src.i18n import t
from src.logging import get_logger

from .cache import MusicCache
from .metadata import MUTAGEN_AVAILABLE, MusicMetadata

logger = get_logger()


class LocalLibrary:
    """Local list that revolves around MusicCache."""

    def __init__(self, cache: MusicCache):
        self._cache = cache
        self._playlist: list[MusicMetadata] | None = None
        self._last_scan_time = 0.0

    def invalidate(self) -> None:
        self._playlist = None
        self._last_scan_time = 0.0

    def scan(self, force_refresh: bool = False) -> list[MusicMetadata]:
        now = time.time()
        if (
            not force_refresh
            and self._playlist is not None
            and (now - self._last_scan_time) < 300
        ):
            return self._playlist

        self._cache.prepare()
        playlist: list[MusicMetadata] = []
        music_files = self._cache.list_music_files()
        if not music_files and not self._cache.root.exists():
            logger.warning(t('缓存目录不存在: {value1}', value1=self._cache.root))
            return playlist

        logger.debug(t('找到 {value1} 个音乐文件', value1=len(music_files)))

        for file_path in music_files:
            try:
                metadata = MusicMetadata(file_path)
                if MUTAGEN_AVAILABLE:
                    metadata.extract_metadata()
                playlist.append(metadata)
            except Exception as e:
                logger.debug(t('处理音乐文件失败 {value1}: {value3}', value1=file_path.name, value3=e))

        playlist.sort(key=lambda x: (x.artist or "Unknown", x.title or x.filename))
        self._playlist = playlist
        self._last_scan_time = now
        logger.info(t('扫描完成，找到 {value1} 首本地音乐', value1=len(playlist)))
        return playlist

    def get_playlist(self, force_refresh: bool = False) -> dict:
        try:
            playlist = self.scan(force_refresh)
            if not playlist:
                return {
                    "status": "info",
                    "message": t("本地缓存中没有音乐文件"),
                    "playlist": [],
                    "total_count": 0,
                }

            formatted = [m.display_name() for m in playlist]
            return {
                "status": "success",
                "message": t('找到 {value1} 首本地音乐', value1=len(playlist)),
                "playlist": formatted,
                "total_count": len(playlist),
            }
        except Exception as e:
            logger.error(t('获取本地歌单失败: {value1}', value1=e), exc_info=True)
            return {
                "status": "error",
                "message": t('获取本地歌单失败: {value1}', value1=str(e)),
                "playlist": [],
                "total_count": 0,
            }

    def search(self, query: str) -> dict:
        try:
            playlist = self.scan()
            if not playlist:
                return {
                    "status": "info",
                    "message": t("本地缓存中没有音乐文件"),
                    "results": [],
                    "found_count": 0,
                }

            q = (query or "").lower()
            results = []
            for metadata in playlist:
                searchable = " ".join(
                    filter(
                        None,
                        [
                            metadata.title,
                            metadata.artist,
                            metadata.album,
                            metadata.filename,
                        ],
                    )
                ).lower()
                if q in searchable:
                    results.append(
                        {
                            "song_info": metadata.display_name(),
                            "file_id": metadata.file_id,
                            "duration": metadata.format_duration(),
                        }
                    )

            return {
                "status": "success",
                "message": t('在本地音乐中找到 {value1} 首匹配的歌曲', value1=len(results)),
                "results": results,
                "found_count": len(results),
            }
        except Exception as e:
            logger.error(t('搜索本地音乐失败: {value1}', value1=e), exc_info=True)
            return {
                "status": "error",
                "message": t('搜索失败: {value1}', value1=str(e)),
                "results": [],
                "found_count": 0,
            }

    def resolve(self, file_id: str) -> tuple[Path, MusicMetadata] | None:
        """Find files by id and read metadata."""
        self._cache.prepare()
        path = self._cache.find_song_file(file_id)
        if path is None:
            return None
        metadata = MusicMetadata(path)
        if MUTAGEN_AVAILABLE:
            metadata.extract_metadata()
        return path, metadata
