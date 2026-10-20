#!/usr/bin/env python3
"""Wrap Chinese QML string literals with ``i18n.t(...)``.

Skips comments and string comparisons/prefix checks. Strings that are
functional (e.g. ``startsWith("[Success]")``) must be migrated to status codes
separately.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SKIP_CONTEXT = (
    "===",
    "!==",
    "==",
    "!=",
    ".startsWith(",
    ".endsWith(",
    ".includes(",
    ".indexOf(",
    ".match(",
    ".search(",
    ".replace(",
    ".split(",
    "objectName:",
)
ALREADY_WRAPPED = ("i18n.t(", "i18n.tf(", "i18n.tc(", "qsTr(", "QT_TR_NOOP(")


def _line_comment_start(line: str) -> int:
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        else:
            if char in {'"', "'", "`"}:
                quote = char
            elif char == "/" and index + 1 < len(line) and line[index + 1] == "/":
                return index
        index += 1
    return len(line)


def _string_spans(line: str):
    """Yield (start, end, quote) for string literals, respecting escapes."""
    index = 0
    limit = _line_comment_start(line)
    while index < limit:
        char = line[index]
        if char in {'"', "'", "`"}:
            quote = char
            start = index
            index += 1
            escaped = False
            while index < limit:
                current = line[index]
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    yield start, index + 1, quote
                    index += 1
                    break
                index += 1
            continue
        index += 1


def transform_line(line: str) -> tuple[str, int]:
    replacements: list[tuple[int, int, str]] = []
    for start, end, quote in _string_spans(line):
        literal = line[start:end]
        if not CJK_RE.search(literal):
            continue
        prefix = line[:start]
        if any(prefix.rstrip().endswith(token) for token in ALREADY_WRAPPED):
            continue
        if any(token in prefix for token in SKIP_CONTEXT):
            continue
        # Skip QML property names that are identifiers, not visible text.
        stripped = prefix.rstrip()
        if stripped.endswith("property string") or stripped.endswith("signal "):
            continue
        replacements.append((start, end, f"i18n.t({literal})"))
    if not replacements:
        return line, 0
    result = line
    for start, end, replacement in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result, len(replacements)


def transform_file(path: Path, check: bool) -> tuple[int, str]:
    source = path.read_text(encoding="utf-8")
    output_lines = []
    count = 0
    for line in source.splitlines(keepends=True):
        body = line.rstrip("\n")
        transformed, line_count = transform_line(body)
        count += line_count
        output_lines.append(transformed + ("\n" if line.endswith("\n") else ""))
    result = "".join(output_lines)
    if not check and result != source:
        path.write_text(result, encoding="utf-8")
    return count, result if check else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["src/ui/gui/qml"])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    paths = [ROOT / item for item in args.paths]
    total = 0
    changed = 0
    for base in paths:
        files = [base] if base.is_file() else base.rglob("*.qml")
        for path in files:
            count, _ = transform_file(path, args.check)
            if count:
                total += count
                changed += 1
                print(f"{path.relative_to(ROOT)}: {count}")
    print(f"\n{changed} file(s), {total} string(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
