#!/usr/bin/env python3
"""Validate extracted messages against the JSON catalogs.

Checks missing/stale keys, placeholder parity, whitespace preservation and
untranslated Chinese text in ``en_US``.

Usage:
    python scripts/i18n_check.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from i18n_extract import collect, key_for, load_catalog  # noqa: E402

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
PLACEHOLDER_RE = re.compile(
    r"(?<!\{)\{[A-Za-z_][A-Za-z0-9_]*\}(?!\})|(?<!\{)\{\d+\}(?!\})"
)


def placeholder_set(text: str) -> set[str]:
    return set(PLACEHOLDER_RE.findall(text))


def leading(text: str) -> str:
    return text[: len(text) - len(text.lstrip())]


def trailing(text: str) -> str:
    return text[len(text.rstrip()) :]


def check_catalog(
    language: str,
    keys: dict[str, str],
    require_translation: bool,
) -> list[str]:
    catalog = load_catalog(language)
    errors: list[str] = []
    missing = sorted(set(keys) - set(catalog))
    stale = sorted(set(catalog) - set(keys))
    for key in missing:
        errors.append(f"{language}: missing key {key[:120]!r}")
    for key in stale:
        errors.append(f"{language}: stale key {key[:120]!r}")

    for key in sorted(set(keys) & set(catalog)):
        value = catalog[key]
        source = keys[key]
        if require_translation and not value:
            errors.append(f"{language}: empty translation for {key[:120]!r}")
            continue
        if require_translation and CJK_RE.search(value):
            errors.append(f"{language}: Chinese text remains in {key[:120]!r}")
        if placeholder_set(source) != placeholder_set(value):
            errors.append(f"{language}: placeholder mismatch for {key[:120]!r}")
        if leading(source) != leading(value):
            errors.append(f"{language}: leading whitespace mismatch for {key[:120]!r}")
        if trailing(source) != trailing(value):
            errors.append(f"{language}: trailing whitespace mismatch for {key[:120]!r}")
    return errors


def main() -> int:
    entries = collect()
    keys: dict[str, str] = {}
    for message, context in entries:
        keys[key_for(message, context)] = message

    errors = check_catalog("zh_CN", keys, require_translation=False)
    errors.extend(check_catalog("en_US", keys, require_translation=True))

    print(f"messages: {len(keys)}")
    if errors:
        print(f"errors: {len(errors)}")
        for error in errors[:100]:
            print(f"  {error}")
        return 1
    print("catalogs OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
