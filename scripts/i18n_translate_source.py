#!/usr/bin/env python3
"""Translate Chinese comments and docstrings in Python/QML sources.

One-off migration helper. Uses the public Google translate endpoint through
the Jina Reader proxy, caches results in
``/tmp/opencode/i18n_source_cache.json`` and writes only translations that came
back successfully.

Usage:
    python scripts/i18n_translate_source.py --check
    python scripts/i18n_translate_source.py --write
    python scripts/i18n_translate_source.py --write --only src/audio_codecs
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import time
import tokenize
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = Path("/tmp/opencode/i18n_source_cache.json")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
MARKER_RE = re.compile(r"__I18N_BLOCK_(\d+)__")
QUOTE_RE = re.compile(r"(?i)^([rubf]*)(\"\"\"|'''|\"|')")
PROXY = "https://r.jina.ai/"
GOOGLE = "https://translate.googleapis.com/translate_a/single"
MAX_BATCH_CHARS = 1200
MAX_BATCH_ITEMS = 15

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


def request_translation(text: str) -> str:
    query = urllib.parse.urlencode(
        {"client": "gtx", "sl": "zh-CN", "tl": "en", "dt": "t", "q": text}
    )
    target = f"{GOOGLE}?{query}"
    url = PROXY + target
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
            start = body.find("[[")
            if start < 0:
                raise ValueError("translation response did not contain JSON")
            payload = json.loads(body[start:])
            segments = payload[0] if payload else []
            translated = "".join(
                segment[0] for segment in segments if segment and segment[0]
            )
            if translated:
                return translated
            last_error = RuntimeError("empty translation")
        except Exception as error:
            last_error = error
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"translation failed: {last_error}")


def _translate_chunk(chunk: list[str]) -> dict[str, str]:
    payload = "\n".join(
        f"__I18N_BLOCK_{position}__\n{text}" for position, text in enumerate(chunk)
    )
    try:
        translated = request_translation(payload)
        parts = MARKER_RE.split(translated)
        found = {
            int(parts[position]): parts[position + 1].strip("\n")
            for position in range(1, len(parts) - 1, 2)
        }
        if len(found) == len(chunk):
            return {
                text: found[position].strip() for position, text in enumerate(chunk)
            }
        raise RuntimeError("translation markers were lost")
    except Exception as error:
        if len(chunk) == 1:
            print(f"skip {chunk[0][:50]!r}: {error}", file=sys.stderr)
            return {}
        print(
            f"batch of {len(chunk)} failed ({error}); splitting",
            file=sys.stderr,
        )
        middle = len(chunk) // 2
        result = _translate_chunk(chunk[:middle])
        result.update(_translate_chunk(chunk[middle:]))
        return result


def translate_batch(texts: list[str]) -> dict[str, str]:
    missing = sorted({text for text in texts if text and text not in _cache})
    result = {text: _cache[text] for text in texts if text in _cache}
    index = 0
    while index < len(missing):
        chunk: list[str] = []
        size = 0
        while index < len(missing) and len(chunk) < MAX_BATCH_ITEMS:
            text = missing[index]
            if chunk and size + len(text) > MAX_BATCH_CHARS:
                break
            chunk.append(text)
            size += len(text)
            index += 1
        result.update(_translate_chunk(chunk))
        _cache.update(result)
        save_cache()
    return result


def _line_offsets(source: str) -> list[int]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _char_col(line: str, byte_col: int) -> int:
    """AST columns are UTF-8 byte offsets; convert to character offsets."""
    return len(line.encode("utf-8")[:byte_col].decode("utf-8", errors="ignore"))


def _offset(offsets: list[int], lineno: int, col: int) -> int:
    return offsets[lineno - 1] + col


def _split_line(text: str) -> tuple[str, str, str]:
    leading = text[: len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()) :]
    core = (
        text[len(leading) : len(text) - len(trailing)]
        if trailing
        else text[len(leading) :]
    )
    return leading, core, trailing


def _line_core(text: str) -> tuple[str, str, str, str]:
    """Split a line into (leading, prefix, core, trailing).

    Docstring examples may contain comment lines; translate only the comment
    body and keep the ``#`` marker and indentation intact.
    """
    leading, core, trailing = _split_line(text)
    if not core.startswith("#"):
        return leading, "", core, trailing
    match = re.match(r"#(\s*)", core)
    if not match:
        return leading, "", core, trailing
    prefix = "#" + match.group(1)
    body_leading, body, body_trailing = _split_line(core[len(prefix) :])
    return leading + prefix + body_leading, "", body, body_trailing + trailing


def _apply_line(text: str, translations: dict[str, str]) -> str:
    leading, _prefix, core, trailing = _line_core(text)
    if not core:
        return text
    return leading + translations.get(core, core) + trailing


def python_edits(path: Path) -> tuple[str, list[tuple[int, int, str]]]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    source_lines = source.splitlines(keepends=True)
    offsets = _line_offsets(source)
    docstrings: list[tuple[int, int, str, str, list[str]]] = []
    comments: list[tuple[int, int, str, str]] = []
    line_texts: list[str] = []

    seen_docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        if not node.body:
            continue
        statement = node.body[0]
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        value = statement.value
        if id(value) in seen_docstrings or not CJK_RE.search(value.value):
            continue
        seen_docstrings.add(id(value))
        literal = ast.get_source_segment(source, value)
        if literal is None:
            continue
        match = QUOTE_RE.match(literal)
        if not match:
            continue
        prefix, quote = match.groups()
        inner = literal[len(prefix) + len(quote) : -len(quote)]
        lines = inner.splitlines(keepends=True)
        for line in lines:
            _leading, _prefix, core, _trailing = _line_core(line.rstrip("\r\n"))
            if core:
                line_texts.append(core)
        start = _offset(
            offsets,
            value.lineno,
            _char_col(source_lines[value.lineno - 1], value.col_offset),
        )
        end = _offset(
            offsets,
            value.end_lineno,
            _char_col(source_lines[value.end_lineno - 1], value.end_col_offset),
        )
        docstrings.append((start, end, prefix, quote, lines))

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):
        tokens = []
    for token in tokens:
        if token.type != tokenize.COMMENT or not CJK_RE.search(token.string):
            continue
        if token.string.startswith("#!"):
            continue
        match = re.match(r"#(\s*)", token.string)
        if not match:
            continue
        prefix = "#" + match.group(1)
        body = token.string[len(prefix) :]
        if not body or not CJK_RE.search(body):
            continue
        line_texts.append(_split_line(body)[1])
        start = _offset(offsets, token.start[0], token.start[1])
        end = _offset(offsets, token.end[0], token.end[1])
        comments.append((start, end, prefix, body))

    translations = translate_batch([text for text in line_texts if text])
    targets: list[tuple[int, int, str]] = []
    for start, end, prefix, quote, lines in docstrings:
        new_lines = []
        for line in lines:
            if line.endswith("\r\n"):
                newline = "\r\n"
            elif line.endswith("\n"):
                newline = "\n"
            else:
                newline = ""
            content = line[: -len(newline)] if newline else line
            new_lines.append(_apply_line(content, translations) + newline)
        new_inner = "".join(new_lines)
        if new_inner == "".join(lines):
            continue
        if quote in ('"""', "'''"):
            new_inner = new_inner.replace(quote, "\\" + quote[:1] * 3)
        else:
            new_inner = new_inner.replace(quote, "\\" + quote)
        targets.append((start, end, prefix + quote + new_inner + quote))
    for start, end, prefix, body in comments:
        translated = _apply_line(body, translations)
        if translated != body:
            targets.append((start, end, prefix + translated))
    return source, targets


def _qml_comment_index(line: str) -> int:
    quote = ""
    escaped = False
    for index, char in enumerate(line):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in {'"', "'"}:
            quote = char
        elif char == "/" and index + 1 < len(line) and line[index + 1] == "/":
            return index
    return -1


def qml_edits(path: Path) -> tuple[str, list[tuple[int, int, str]]]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    offsets = _line_offsets(source)
    matches: list[tuple[int, int, str, str]] = []
    line_texts: list[str] = []
    for lineno, line in enumerate(lines, 1):
        index = _qml_comment_index(line)
        if index < 0 or not CJK_RE.search(line[index:]):
            continue
        content = line.rstrip("\r\n")
        match = re.match(r"//(\s*)", content[index:])
        if not match:
            continue
        prefix = "//" + match.group(1)
        body = content[index + len(prefix) :]
        if not body:
            continue
        line_texts.append(_split_line(body)[1])
        start = offsets[lineno - 1] + index + len(prefix)
        end = offsets[lineno - 1] + len(content)
        matches.append((start, end, prefix, body))
    translations = translate_batch([text for text in line_texts if text])
    targets: list[tuple[int, int, str]] = []
    for start, end, _prefix, body in matches:
        translated = _apply_line(body, translations)
        if translated != body:
            targets.append((start, end, translated))
    return source, targets


def iter_files(only: str | None):
    if only:
        base = ROOT / only
        if base.is_file():
            yield base
            return
        roots = [base]
    else:
        roots = [ROOT / "main.py", ROOT / "src", ROOT / "scripts", ROOT / "tests"]
        if (ROOT / "examples").exists():
            roots.append(ROOT / "examples")
    for root in roots:
        if root.is_file() and root.suffix in {".py", ".qml"}:
            yield root
        elif root.is_dir():
            patterns = ("*.py", "*.qml") if only else ("*.py",)
            for pattern in patterns:
                for path in sorted(root.rglob(pattern)):
                    if "__pycache__" in path.parts or "locales" in path.parts:
                        continue
                    yield path
    if not only:
        qml_root = ROOT / "src" / "ui" / "gui" / "qml"
        for path in sorted(qml_root.rglob("*.qml")):
            yield path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--only")
    args = parser.parse_args()

    load_cache()
    changed_files = 0
    changed_edits = 0
    for path in iter_files(args.only):
        try:
            if path.suffix == ".qml":
                source, targets = qml_edits(path)
            else:
                source, targets = python_edits(path)
        except Exception as error:
            print(f"skip {path}: {error}", file=sys.stderr)
            continue
        if not targets:
            continue
        changed_files += 1
        changed_edits += len(targets)
        print(f"{path.relative_to(ROOT)}: {len(targets)} edits", flush=True)
        if not args.write:
            continue
        updated = source
        for start, end, replacement in sorted(targets, reverse=True):
            updated = updated[:start] + replacement + updated[end:]
        path.write_text(updated, encoding="utf-8")

    save_cache()
    print(f"files={changed_files} edits={changed_edits} cached={len(_cache)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
