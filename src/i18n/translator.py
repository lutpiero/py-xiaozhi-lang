"""Small JSON-backed translation catalog.

Chinese source strings are used as message ids (gettext-style). A context can
be supplied for strings that share the same source text but need different
translations.

Catalogs live in ``src/i18n/locales/<language>.json``::

    {
      "_meta": {"language": "en_US", "name": "English"},
      "messages": {
        "standby": "Idle",
        "Saved {count} items": "Saved {count} item(s)",
        "tray|Settings": "Settings"
      }
    }
"""

from __future__ import annotations

import json
import locale
import os
import re
import threading
from pathlib import Path
from typing import Any

DEFAULT_LANGUAGE = "zh_CN"
SYSTEM_LANGUAGE = "auto"
SUPPORTED_LANGUAGES = ("zh_CN", "en_US")
LANGUAGE_LABELS = {
    "zh_CN": "简体中文",
    "en_US": "English",
}
ENV_LANGUAGE = "XIAOZHI_LANG"
CONTEXT_SEPARATOR = "|"
_CATALOG_DIR = Path(__file__).resolve().parent / "locales"

_ALIASES = {
    "zh": "zh_CN",
    "zh-cn": "zh_CN",
    "zh_cn": "zh_CN",
    "zh-hans": "zh_CN",
    "zh-hans-cn": "zh_CN",
    "chinese": "zh_CN",
    "简体中文": "zh_CN",
    "中文": "zh_CN",
    "en": "en_US",
    "en-us": "en_US",
    "en_us": "en_US",
    "english": "en_US",
}

_lock = threading.RLock()
_current_language = DEFAULT_LANGUAGE
_messages: dict[str, str] = {}
_missing: set[str] = set()


def normalize_language(value: Any) -> str | None:
    """Return a supported language code for *value*, or ``None``."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    lowered = raw.lower().replace(" ", "")
    if lowered in _ALIASES:
        return _ALIASES[lowered]
    if lowered.startswith("zh"):
        return "zh_CN"
    if lowered.startswith("en"):
        return "en_US"
    return None


def detect_system_language() -> str:
    """Best-effort OS locale detection without requiring Qt."""
    candidates = [
        os.environ.get("LC_ALL"),
        os.environ.get("LC_MESSAGES"),
        os.environ.get("LANG"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        normalized = normalize_language(candidate.split(".")[0].split("@")[0])
        if normalized:
            return normalized

    getter = locale.getlocale
    if callable(getter):
        try:
            value = getter()
        except Exception:
            value = None
        if value:
            raw = value[0] if isinstance(value, tuple) else value
            normalized = normalize_language(raw)
            if normalized:
                return normalized
    return DEFAULT_LANGUAGE


def resolve_language(
    explicit: Any = None,
    config_value: Any = None,
    *,
    use_env: bool = True,
) -> str:
    """Resolve the active language.

    Precedence: explicit argument > ``XIAOZHI_LANG`` > config value >
    OS locale > ``zh_CN``.  ``auto``/``None`` in config means "detect".
    """
    normalized = normalize_language(explicit)
    if normalized:
        return normalized

    if use_env:
        normalized = normalize_language(os.environ.get(ENV_LANGUAGE))
        if normalized:
            return normalized

    if (
        config_value is not None
        and str(config_value).strip().lower() != SYSTEM_LANGUAGE
    ):
        normalized = normalize_language(config_value)
        if normalized:
            return normalized

    return detect_system_language()


def _catalog_path(language: str) -> Path:
    return _CATALOG_DIR / f"{language}.json"


def load_catalog(language: str) -> dict[str, str]:
    path = _catalog_path(language)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    messages = data.get("messages", data)
    if not isinstance(messages, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in messages.items()
        if not str(key).startswith("_") and isinstance(value, (str, int, float))
    }


def set_language(language: Any, *, fallback: str = DEFAULT_LANGUAGE) -> str:
    """Activate *language* and load its catalog.  Returns the active code."""
    global _current_language, _messages
    normalized = normalize_language(language) or normalize_language(fallback)
    if normalized is None:
        normalized = DEFAULT_LANGUAGE
    with _lock:
        _current_language = normalized
        _messages = load_catalog(normalized)
        _missing.clear()
    return normalized


def initialize_language(
    explicit: Any = None,
    config_value: Any = None,
) -> str:
    """Resolve and activate a language using the standard precedence."""
    return set_language(resolve_language(explicit, config_value))


def get_language() -> str:
    return _current_language


def get_language_label(language: str | None = None) -> str:
    code = language or _current_language
    return LANGUAGE_LABELS.get(code, code)


def available_languages() -> tuple[str, ...]:
    return SUPPORTED_LANGUAGES


def _lookup_key(message: str, context: str | None) -> str:
    if context:
        return f"{context}{CONTEXT_SEPARATOR}{message}"
    return message


def translate(
    message: str,
    *args: Any,
    context: str | None = None,
    ctx: str | None = None,
    **kwargs: Any,
) -> str:
    """Translate *message*, falling back to the source string.

    ``context``/``ctx`` selects a context-specific entry.  Keyword arguments
    are applied with :meth:`str.format`; positional arguments use numbered
    ``{0}`` placeholders (also used by the QML bridge).
    """
    if not isinstance(message, str):
        return str(message)
    context = context or ctx
    with _lock:
        source = _messages.get(_lookup_key(message, context))
        if source is None and context:
            source = _messages.get(message)
        if source is None:
            source = message
            _missing.add(_lookup_key(message, context))
    try:
        if kwargs:
            return source.format(**kwargs)
        if args:
            return source.format(*args)
    except (KeyError, IndexError, ValueError):
        return source
    return source


def missing_keys() -> set[str]:
    """Keys requested since the last language change (for diagnostics/tests)."""
    with _lock:
        return set(_missing)


def catalog_messages(language: str) -> dict[str, str]:
    return load_catalog(language)


def clear_missing_keys() -> None:
    with _lock:
        _missing.clear()


def _normalize_placeholder_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def placeholder_names(text: str) -> set[str]:
    """Named ``{name}`` placeholders in a message (``{0}`` excluded)."""
    names: set[str] = set()
    for match in re.finditer(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})", text):
        names.add(match.group(1))
    return names


def placeholder_indexes(text: str) -> set[int]:
    indexes: set[int] = set()
    for match in re.finditer(r"(?<!\{)\{(\d+)\}(?!\})", text):
        indexes.add(int(match.group(1)))
    return indexes


# Load a usable catalog as soon as this module is imported.  ``main.py`` will
# re-apply config/CLI preferences after configuration has been initialized.
set_language(detect_system_language())
