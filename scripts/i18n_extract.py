#!/usr/bin/env python3
"""Extract translatable messages from Python and QML into JSON catalogs.

Usage:
    python scripts/i18n_extract.py            # report missing/extra
    python scripts/i18n_extract.py --write    # write zh_CN identity catalog
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "src" / "i18n" / "locales"
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
QML_CALL_RE = re.compile(
    r"i18n\.(?:t|tf|tc)\(\s*(\"(?:[^\"\\\\]|\\\\.)*\"|'(?:[^'\\\\]|\\\\.)*')"
)


def _call_name(node: ast.Call) -> str:
    try:
        return ast.unparse(node.func)
    except Exception:
        return ""


def _literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract_python(path: Path) -> list[tuple[str, str | None]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node) not in {"t", "translate"}:
            continue
        if not node.args:
            continue
        message = _literal(node.args[0])
        if message is None or not CJK_RE.search(message):
            continue
        context = None
        for keyword in node.keywords:
            if keyword.arg in {"ctx", "context"}:
                context = _literal(keyword.value)
        found.append((message, context))
    return found


def extract_qml(path: Path) -> list[tuple[str, str | None]]:
    source = path.read_text(encoding="utf-8")
    found: list[tuple[str, str | None]] = []
    for match in QML_CALL_RE.finditer(source):
        raw = match.group(1)
        try:
            message = json.loads(raw) if raw.startswith('"') else ast.literal_eval(raw)
        except Exception:
            continue
        if isinstance(message, str) and CJK_RE.search(message):
            found.append((message, None))
    # i18n.tc("context", "message")
    for match in re.finditer(
        r"i18n\.tc\(\s*(\"(?:[^\"\\\\]|\\\\.)*\")\s*,\s*(\"(?:[^\"\\\\]|\\\\.)*\")",
        source,
    ):
        try:
            context = json.loads(match.group(1))
            message = json.loads(match.group(2))
        except Exception:
            continue
        if CJK_RE.search(message):
            found.append((message, context))
    return found


def collect() -> list[tuple[str, str | None]]:
    found: list[tuple[str, str | None]] = []
    for path in [ROOT / "main.py", *sorted((ROOT / "src").rglob("*.py"))]:
        if "i18n" in path.parts:
            continue
        found.extend(extract_python(path))
    for path in sorted((ROOT / "src" / "ui" / "gui" / "qml").rglob("*.qml")):
        found.extend(extract_qml(path))
    return found


def key_for(message: str, context: str | None) -> str:
    return f"{context}|{message}" if context else message


def load_catalog(language: str) -> dict[str, str]:
    path = LOCALES / f"{language}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("messages", data)


def write_catalog(language: str, messages: dict[str, str], name: str) -> None:
    payload = {
        "_meta": {"language": language, "name": name},
        "messages": dict(sorted(messages.items())),
    }
    (LOCALES / f"{language}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    entries = collect()
    keys: dict[str, str] = {}
    for message, context in entries:
        key = key_for(message, context)
        keys[key] = message
    if not keys:
        print("No translatable messages found.")
        return 1

    zh = load_catalog("zh_CN")
    en = load_catalog("en_US")
    missing_zh = sorted(set(keys) - set(zh))
    missing_en = sorted(set(keys) - set(en))
    stale = sorted(set(zh) - set(keys))

    print(f"messages: {len(keys)}")
    print(f"missing zh_CN: {len(missing_zh)}")
    print(f"missing en_US: {len(missing_en)}")
    print(f"stale: {len(stale)}")
    for key in missing_en[:30]:
        print(f"  en missing: {key[:100]}")
    for key in stale[:10]:
        print(f"  stale: {key[:100]}")

    if args.write:
        merged_zh = {key: keys[key] for key in keys}
        for key, value in zh.items():
            if key in merged_zh:
                merged_zh[key] = value
        write_catalog("zh_CN", merged_zh, "简体中文")
        print(f"wrote {LOCALES / 'zh_CN.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
