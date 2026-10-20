#!/usr/bin/env python3
"""Fill en_US.json from the extracted Chinese message catalog.

Uses Google Translate through the Jina Reader proxy as a bootstrap.  Review the
generated catalog and add overrides in ``scripts/i18n_overrides.json`` for
product terminology.

Usage:
    python scripts/i18n_translate.py --write
    python scripts/i18n_translate.py --write --workers 8 --limit 50
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from i18n_extract import collect, key_for, load_catalog, write_catalog  # noqa: E402

CACHE_PATH = Path("/tmp/opencode/i18n_cache.json")
OVERRIDES_PATH = ROOT / "scripts" / "i18n_overrides.json"
PLACEHOLDER_RE = re.compile(r"\{[^{}\n]+\}|%[sdrif]|%%|https?://\S+|`[^`]+`")
RICH_RE = re.compile(
    r"\[/?(?:bold|italic|underline|dim|red|green|yellow|blue|cyan|magenta|white|black|on [a-z]+|link[^\]]*|#[0-9a-fA-F]{3,8})(?: [^\]]*)?\]"
)
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

_lock = threading.Lock()
_cache: dict[str, str] = {}


def load_cache() -> None:
    global _cache
    try:
        _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        _cache = {}


def save_cache() -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = CACHE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CACHE_PATH)


def protect(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def replace(match: re.Match[str]) -> str:
        token = f"__I18N_{len(tokens)}__"
        tokens.append(match.group(0))
        return token

    protected = RICH_RE.sub(replace, text)
    protected = PLACEHOLDER_RE.sub(replace, protected)
    protected = protected.replace("\n", " __I18N_NL__ ")
    return protected, tokens


def restore(text: str, tokens: list[str]) -> str:
    for index, token in enumerate(tokens):
        text = text.replace(f"__I18N_{index}__", token)
        text = text.replace(f"__i18n_{index}__", token)
    return text.replace(" __I18N_NL__ ", "\n").replace("__I18N_NL__", "\n")


def request_translation(text: str) -> str:
    data = urllib.parse.urlencode(
        {"client": "gtx", "sl": "zh-CN", "tl": "en", "dt": "t", "q": text}
    ).encode("utf-8")
    target = "https://translate.googleapis.com/translate_a/single?" + data.decode(
        "utf-8"
    )
    request = urllib.request.Request(
        "https://r.jina.ai/" + target,
        headers={"User-Agent": "py-xiaozhi-i18n/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
    start = body.find("[[")
    if start < 0:
        raise ValueError("translation response did not contain JSON")
    payload = json.loads(body[start:])
    segments = payload[0] if payload else []
    return "".join(segment[0] for segment in segments if segment and segment[0])


def _translate_segment(text: str) -> str:
    protected, tokens = protect(text)
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            return restore(request_translation(protected), tokens)
        except Exception as error:
            last_error = error
            time.sleep(2.0 * (attempt + 1))
    print(f"translation failed: {text[:60]!r}: {last_error}", file=sys.stderr)
    return text


def translate_text(text: str) -> str:
    if not CJK_RE.search(text):
        return text
    with _lock:
        cached = _cache.get(text)
    if cached:
        return cached
    leading = text[: len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()) :]
    core = (
        text[len(leading) : len(text) - len(trailing)]
        if trailing
        else text[len(leading) :]
    )
    if not core:
        return text
    # Translate each line and each "a | b" segment separately.  The public
    # endpoint occasionally drops the first clause of mixed technical lines
    # containing placeholders and pipes.
    parts = re.split(r"(\n|\s*\|\s*)", core)
    translated_parts = []
    for part in parts:
        if CJK_RE.search(part):
            translated_parts.append(_translate_segment(part))
        else:
            translated_parts.append(part)
    translated = leading + "".join(translated_parts) + trailing
    with _lock:
        _cache[text] = translated
    return translated


def _needs_repair(key: str, value: str, source: str) -> bool:
    if not value:
        return True
    if CJK_RE.search(value):
        return True
    key_placeholders = set(re.findall(r"\{[^{}]+\}", key))
    value_placeholders = set(re.findall(r"\{[^{}]+\}", value))
    if key_placeholders != value_placeholders:
        return True
    if key[: len(key) - len(key.lstrip())] != value[: len(value) - len(value.lstrip())]:
        return True
    if key[len(key.rstrip()) :] != value[len(value.rstrip()) :]:
        return True
    return False


def load_overrides() -> dict[str, str]:
    try:
        data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()}
    except Exception:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()

    load_cache()
    overrides = load_overrides()
    entries = collect()
    keys: dict[str, str] = {}
    for message, context in entries:
        keys[key_for(message, context)] = message

    en = load_catalog("en_US")
    pending: dict[str, str] = {}
    for key, message in keys.items():
        if key in overrides:
            en[key] = overrides[key]
            continue
        existing = en.get(key)
        if existing and existing != message:
            if not args.repair or not _needs_repair(key, existing, message):
                continue
        pending[message] = key

    messages = sorted(pending)
    if args.limit:
        messages = messages[: args.limit]
    print(f"keys={len(keys)} pending={len(messages)}")

    if messages:
        if args.repair:
            for message in messages:
                with _lock:
                    _cache.pop(message, None)
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {
                executor.submit(translate_text, message): message
                for message in messages
            }
            for index, future in enumerate(as_completed(futures), 1):
                message = futures[future]
                result = future.result()
                key = pending[message]
                en[key] = overrides.get(key, result)
                if index % 50 == 0:
                    with _lock:
                        save_cache()
                    print(f"translated {index}/{len(messages)}")
    with _lock:
        save_cache()

    # Context keys: prefer a context-specific override, otherwise use the
    # translation of the base message.
    for key in keys:
        if key in en:
            continue
        if "|" in key:
            base = key.split("|", 1)[1]
            en[key] = overrides.get(key, en.get(base, base))
        else:
            en[key] = overrides.get(key, keys[key])

    if args.write:
        write_catalog("zh_CN", {key: keys[key] for key in keys}, "简体中文")
        write_catalog(
            "en_US",
            {key: en.get(key, keys[key]) for key in keys},
            "English",
        )
        print("wrote catalogs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
