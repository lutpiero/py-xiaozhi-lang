#!/usr/bin/env python3
"""Second pass: wrap status/message dictionaries, MCP descriptions and UI calls."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from i18n_codemod import (  # noqa: E402
    _abs_offset,
    _constant_replacement,
    _ensure_import,
    _fstring_replacement,
)

TARGET_CALLS = {
    "_on_connection_state_changed",
    "_handle_connection_loss",
    "_on_network_error",
    "_warn_if_unknown",
    "set_button_text",
    "set_status",
    "write_log",
    "_log",
    "_show_error",
    "log",
    "McpTool",
    "SettingField",
    "Static",
    "Binding",
    "Button",
    "reactive",
    "hints.append",
    "missing.append",
    "ActivationResult",
    "CameraDeviceInfo",
}
MESSAGE_CALLS = {"result.get", "args.get", "data.get"}
MESSAGE_KEYS = {
    "message",
    "error",
    "text",
    "title",
    "description",
    "label",
    "help",
    "summary",
    "detail",
    "hint",
    "reason",
    "warning",
}


def call_name(node: ast.Call) -> str:
    try:
        return ast.unparse(node.func)
    except Exception:
        return ""


def short_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return call_name(node)


def target_strings(node: ast.Call):
    name = call_name(node)
    short = short_name(node)
    is_target = short in TARGET_CALLS or name in TARGET_CALLS
    is_message = short in MESSAGE_CALLS or name in MESSAGE_CALLS
    if not is_target and not is_message:
        return
    for arg in node.args:
        if isinstance(arg, (ast.Constant, ast.JoinedStr)):
            if is_message:
                continue
            yield arg
    for keyword in node.keywords:
        if isinstance(keyword.value, (ast.Constant, ast.JoinedStr)):
            yield keyword.value
    if is_message:
        if len(node.args) >= 2:
            first = node.args[0]
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value in MESSAGE_KEYS
            ):
                second = node.args[1]
                if isinstance(second, (ast.Constant, ast.JoinedStr)):
                    yield second


def transform(source: str, filename: str) -> tuple[str, int]:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return source, 0

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    lines = source.splitlines(keepends=True)
    replacements: list[tuple[int, int, str]] = []

    def add(node: ast.AST) -> None:
        if isinstance(node, ast.JoinedStr):
            replacement = _fstring_replacement(node, source)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            replacement = _constant_replacement(node, source)
        else:
            return
        if not replacement or node.end_lineno is None or node.end_col_offset is None:
            return
        current: ast.AST | None = node
        while current in parents:
            current = parents[current]
            if isinstance(current, ast.Call) and call_name(current) in {
                "t",
                "translate",
                "i18n.t",
                "i18n.tf",
            }:
                return
        start = _abs_offset(lines, node.lineno, node.col_offset)
        end = _abs_offset(lines, node.end_lineno, node.end_col_offset)
        replacements.append((start, end, replacement))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for child in target_strings(node):
                add(child)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=False):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value in MESSAGE_KEYS
                ):
                    add(value)

    if not replacements:
        return source, 0
    result = source
    for start, end, replacement in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    result = _ensure_import(result, ast.parse(result, filename=filename))
    return result, len(replacements)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["main.py", "src"])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    total = 0
    changed = 0
    for base in [ROOT / item for item in args.paths]:
        files = [base] if base.is_file() else base.rglob("*.py")
        for path in files:
            if "i18n" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            result, count = transform(source, str(path))
            if result != source:
                changed += 1
                total += count
                print(f"{path.relative_to(ROOT)}: {count}")
                if not args.check:
                    path.write_text(result, encoding="utf-8")
    print(f"\n{changed} file(s), {total} string(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
