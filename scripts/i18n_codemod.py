#!/usr/bin/env python3
"""One-time codemod: wrap user-facing Python strings with ``t(...)``.

The transform is deliberately conservative.  It only wraps strings passed to
logging calls, ``print``/``input``, Qt dialogs/actions, exception constructors
and ``*.emit(...)`` signal calls.  Remaining UI strings are handled manually or
by the targeted follow-up passes.

Usage:
    python scripts/i18n_codemod.py [--check] [paths...]
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LOG_LEVELS = {
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "exception",
    "critical",
    "log",
}
QT_TEXT_CALLS = {
    "QMessageBox",
    "QFileDialog",
    "QInputDialog",
    "QAction",
    "QMenu",
    "QSystemTrayIcon",
}
EXCEPTION_SUFFIXES = ("Error", "Exception", "Exit", "Interrupt")


def has_cjk(value: str) -> bool:
    return bool(CJK_RE.search(value))


def _line_offsets(source: str) -> list[int]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    if not source.endswith("\n") and len(offsets) == len(source.splitlines()) + 1:
        pass
    return offsets


def _abs_offset(lines: list[str], lineno: int, byte_col: int) -> int:
    """Convert an AST UTF-8 byte column into a Python string offset."""
    prefix = sum(len(line) for line in lines[: lineno - 1])
    line = lines[lineno - 1]
    char_col = len(line.encode("utf-8")[:byte_col].decode("utf-8"))
    return prefix + char_col


def _call_name(node: ast.Call) -> str:
    return ast.unparse(node.func)


def _is_target_call(node: ast.Call) -> bool:
    func = node.func
    name = _call_name(node)
    attr = func.attr if isinstance(func, ast.Attribute) else None
    lowered = name.lower()

    if attr in LOG_LEVELS and ("log" in lowered.rsplit(".", 1)[0].lower()):
        return True
    if name in {"print", "input"}:
        return True
    if attr == "emit":
        return True
    if any(token in name for token in QT_TEXT_CALLS):
        return True
    if isinstance(func, ast.Name) and func.id.endswith(EXCEPTION_SUFFIXES):
        return True
    if attr == "add_argument" and any(kw.arg == "help" for kw in node.keywords):
        return True
    if isinstance(func, ast.Name) and func.id == "ArgumentParser":
        return True
    return False


def _iter_string_nodes(node: ast.Call):
    """Yield top-level string expressions passed to a call.

    F-string components are intentionally not yielded separately: the whole
    f-string is converted in one replacement.
    """

    def visit(value: ast.AST):
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            yield value
        elif isinstance(value, ast.JoinedStr):
            yield value
        elif isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
            yield from visit(value.left)
            yield from visit(value.right)

    for arg in node.args:
        yield from visit(arg)
    for keyword in node.keywords:
        yield from visit(keyword.value)


def _inside_translation(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, ast.Call):
            name = _call_name(current)
            if name in {"t", "translate", "i18n.t", "i18n.tf"}:
                return True
        current = parents.get(current)
    return False


def _fstring_replacement(node: ast.JoinedStr, source: str) -> str | None:
    parts: list[str] = []
    kwargs: list[str] = []
    for index, value in enumerate(node.values):
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value.replace("{", "{{").replace("}", "}}"))
        elif isinstance(value, ast.FormattedValue):
            expr = ast.get_source_segment(source, value.value)
            if expr is None:
                return None
            name = f"value{index}"
            conversion = ""
            if value.conversion != -1:
                conversion = chr(value.conversion)
            spec = ""
            if value.format_spec is not None:
                spec_src = ast.get_source_segment(source, value.format_spec)
                if spec_src is None:
                    return None
                spec = spec_src.lstrip(":")
                if spec_src.startswith(("f'", 'f"')):
                    return None
            placeholder = "{" + name
            if conversion:
                placeholder += "!" + conversion
            if spec:
                placeholder += ":" + spec
            placeholder += "}"
            parts.append(placeholder)
            kwargs.append(f"{name}={expr}")
        else:
            return None
    message = "".join(parts)
    if not has_cjk(message):
        return None
    args = ", ".join(kwargs)
    literal = repr(message)
    return f"t({literal}{', ' + args if args else ''})"


def _constant_replacement(node: ast.Constant, source: str) -> str | None:
    if not has_cjk(node.value):
        return None
    segment = ast.get_source_segment(source, node)
    if segment is None:
        return None
    if not (segment.startswith(('"', "'", 'r"', "r'", 'u"', "u'"))):
        return None
    return f"t({segment})"


def _ensure_import(source: str, tree: ast.Module) -> str:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "src.i18n":
            if any(alias.name == "t" for alias in node.names):
                return source
        if isinstance(node, ast.Import):
            if any(alias.name == "src.i18n" for alias in node.names):
                return source

    insert_at = 0
    body = tree.body
    index = 0
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        insert_at = body[0].end_lineno or 0
        index = 1
    while index < len(body):
        node = body[index]
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            insert_at = node.end_lineno or insert_at
            index += 1
            continue
        break

    offsets = _line_offsets(source)
    if insert_at:
        position = offsets[insert_at]
    else:
        position = 0
    return source[:position] + "from src.i18n import t\n" + source[position:]


def transform_source(source: str, filename: str) -> tuple[str, int]:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return source, 0

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    replacements: list[tuple[int, int, str]] = []
    lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_target_call(node):
            continue
        strings = list(_iter_string_nodes(node))
        if not strings:
            continue
        for string_node in strings:
            if _inside_translation(string_node, parents):
                continue
            replacement = None
            if isinstance(string_node, ast.JoinedStr):
                replacement = _fstring_replacement(string_node, source)
            elif isinstance(string_node, ast.Constant):
                replacement = _constant_replacement(string_node, source)
            if not replacement:
                continue
            if string_node.end_lineno is None or string_node.end_col_offset is None:
                continue
            start = _abs_offset(lines, string_node.lineno, string_node.col_offset)
            end = _abs_offset(lines, string_node.end_lineno, string_node.end_col_offset)
            if source[start:end].startswith("t("):
                continue
            replacements.append((start, end, replacement))

    if not replacements:
        return source, 0

    result = source
    for start, end, replacement in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    result = _ensure_import(result, ast.parse(result, filename=filename))
    return result, len(replacements)


def iter_python_files(paths: list[Path]):
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            yield path
        elif path.is_dir():
            for child in path.rglob("*.py"):
                if "i18n" in child.parts:
                    continue
                yield child


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["main.py", "src"])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    paths = [ROOT / item for item in args.paths]
    changed_files = 0
    changed_nodes = 0
    for path in iter_python_files(paths):
        if path.name == "__init__.py" and path.parent == ROOT / "src" / "i18n":
            continue
        source = path.read_text(encoding="utf-8")
        result, count = transform_source(source, str(path))
        if result != source:
            changed_files += 1
            changed_nodes += count
            print(f"{path.relative_to(ROOT)}: {count}")
            if not args.check:
                path.write_text(result, encoding="utf-8")
    print(f"\n{changed_files} file(s), {changed_nodes} string(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
