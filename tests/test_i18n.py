"""Locale resolution and catalog consistency tests."""

import sys
from pathlib import Path

import pytest

from src.i18n import (
    DEFAULT_LANGUAGE,
    ENV_LANGUAGE,
    get_language,
    load_catalog,
    missing_keys,
    normalize_language,
    placeholder_indexes,
    placeholder_names,
    resolve_language,
    set_language,
    t,
    translator,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import i18n_check  # noqa: E402
from i18n_extract import collect, key_for  # noqa: E402


@pytest.fixture(autouse=True)
def restore_language():
    previous = get_language()
    yield
    set_language(previous)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("zh", "zh_CN"),
        ("zh-CN", "zh_CN"),
        ("zh_Hans", "zh_CN"),
        ("简体中文", "zh_CN"),
        ("en", "en_US"),
        ("en-GB", "en_US"),
        ("English", "en_US"),
        ("fr_FR", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_language(value, expected):
    assert normalize_language(value) == expected


def test_resolve_language_precedence(monkeypatch):
    monkeypatch.setattr(translator, "detect_system_language", lambda: "zh_CN")
    monkeypatch.setenv(ENV_LANGUAGE, "en_US")

    assert resolve_language("zh_CN", "en_US") == "zh_CN"
    assert resolve_language(None, "zh_CN") == "en_US"

    monkeypatch.delenv(ENV_LANGUAGE)
    assert resolve_language(None, "en_US") == "en_US"
    assert resolve_language(None, "auto") == "zh_CN"
    assert resolve_language(None, None) == "zh_CN"
    assert resolve_language("auto", "auto") == "zh_CN"


def test_resolve_language_ignores_unknown_values(monkeypatch):
    monkeypatch.setattr(translator, "detect_system_language", lambda: "en_US")
    monkeypatch.delenv(ENV_LANGUAGE, raising=False)
    assert resolve_language("fr_FR", "de_DE") == "en_US"


def test_translate_and_format():
    catalog = load_catalog("en_US")
    set_language("en_US")

    assert t("待命") == catalog["待命"]
    assert t("已保存 {count} 项", count=3) == catalog["已保存 {count} 项"].format(
        count=3
    )


def test_positional_format(monkeypatch):
    set_language("en_US")
    monkeypatch.setitem(translator._messages, "value: {0}", "value: {0}")
    assert t("value: {0}", 7) == "value: 7"


def test_translate_falls_back_to_context_and_source():
    catalog = load_catalog("en_US")
    set_language("en_US")

    assert t("待命", ctx="missing-context") == catalog["待命"]
    assert t("not-in-catalog") == "not-in-catalog"
    assert "not-in-catalog" in missing_keys()


def test_placeholder_helpers():
    assert placeholder_names("hello {name} {0}") == {"name"}
    assert placeholder_indexes("hello {name} {0} {1}") == {0, 1}


def test_catalogs_are_complete_and_valid():
    keys: dict[str, str] = {}
    for message, context in collect():
        keys[key_for(message, context)] = message

    errors = i18n_check.check_catalog("zh_CN", keys, require_translation=False)
    errors += i18n_check.check_catalog("en_US", keys, require_translation=True)
    assert errors == []


def test_default_language_is_supported():
    assert normalize_language(DEFAULT_LANGUAGE) == DEFAULT_LANGUAGE
