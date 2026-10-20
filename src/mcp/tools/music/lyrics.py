"""Pull and parse the lyrics, and get the current sentence according to the playback progress."""

from __future__ import annotations

import asyncio
from typing import Any

import requests

from src.i18n import t
from src.logging import get_logger

logger = get_logger()

# (time seconds, text)
LyricLine = tuple[float, str]

# Filter out lines with information such as lyrics/composition
_METADATA_PREFIXES = (
    "作词",
    "作曲",
    "编曲",
    "制作",
    "演唱",
    "原唱",
    "翻唱",
)


def lyric_at(
    lyrics: list[LyricLine], current_time: float, *, lead: float = 0.5
) -> tuple[int, str] | None:
    """Find which lyrics should be displayed according to the current playback time.

    Return (subscript, text); returns None if there are no lyrics.
    """
    if not lyrics:
        return None

    next_lyric_index = None
    for i, (time_sec, _) in enumerate(lyrics):
        if time_sec > current_time - lead:
            next_lyric_index = i
            break

    if next_lyric_index is not None and next_lyric_index > 0:
        idx = next_lyric_index - 1
    elif next_lyric_index is None:
        idx = len(lyrics) - 1
    else:
        idx = 0

    return idx, lyrics[idx][1]


def format_lyric_display(
    text: str, position: float, duration: float
) -> str:
    """spells the lyrics line used on the UI, for example [00:12/03:45] Lyric content."""
    return f"[{_fmt(position)}/{_fmt(duration)}] {text}"


def _fmt(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes:02d}:{secs:02d}"


def parse_kuwo_lrc_list(lrc_list: list[dict]) -> tuple[list[LyricLine], int]:
    """Parse the lrclist returned by me.

    returns (lyrics list, number of filtered information lines).
    """
    lyrics: list[LyricLine] = []
    filtered = 0
    for item in lrc_list:
        time_str = item.get("time", "")
        text = (item.get("lineLyric") or "").strip()
        if not text or not time_str:
            continue
        try:
            time_sec = float(time_str)
        except (ValueError, TypeError):
            continue
        if text.startswith(_METADATA_PREFIXES):
            filtered += 1
            continue
        lyrics.append((time_sec, text))
    return lyrics, filtered


async def fetch_kuwo_lyrics(
    song_id: str,
    *,
    lyrics_url: str,
    headers: dict[str, Any] | None = None,
) -> list[LyricLine]:
    """pulls the lyrics from the KuWo interface and parses them."""
    try:
        logger.info(t('获取歌词: ID={value1}', value1=song_id))
        response = await asyncio.to_thread(
            requests.get,
            lyrics_url,
            params={"musicId": song_id},
            headers=headers or {},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != 200:
            logger.info(t("该歌曲暂无歌词"))
            return []

        lrc_list = data.get("data", {}).get("lrclist", [])
        if not lrc_list:
            logger.warning(t("未获取到歌词数据"))
            return []

        lyrics, filtered = parse_kuwo_lrc_list(lrc_list)
        logger.info(
            t('成功获取歌词，共 {value1} 行（过滤 {value3} 行元数据）', value1=len(lyrics), value3=filtered)
        )
        return lyrics
    except Exception as e:
        logger.error(t('获取歌词失败: {value1}', value1=e), exc_info=True)
        return []
