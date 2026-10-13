import json

import pytest

from shtorka import config


@pytest.fixture(autouse=True)
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_FILE", path)
    return path


def test_defaults_without_file():
    assert config.load() == config.DEFAULTS


@pytest.mark.parametrize("content", ["{", "[1, 2]", '"text"'])
def test_unreadable_file_gives_defaults(config_file, content):
    config_file.write_text(content, encoding="utf-8")
    assert config.load() == config.DEFAULTS


def test_process_names_are_lower_case(config_file):
    config_file.write_text('{"process_names": ["AyuGram.exe"]}', encoding="utf-8")
    assert config.load()["process_names"] == ["ayugram.exe"]


def test_bad_process_names_fall_back(config_file):
    config_file.write_text('{"process_names": "telegram.exe"}', encoding="utf-8")
    assert config.load()["process_names"] == config.DEFAULTS["process_names"]


def test_save_keeps_other_keys(config_file):
    config_file.write_text('{"process_names": ["a.exe"]}', encoding="utf-8")
    config.save(color="#2b5278")
    config.save(style="rounded")
    assert json.loads(config_file.read_text(encoding="utf-8")) == {
        "process_names": ["a.exe"],
        "color": "#2b5278",
        "style": "rounded",
    }
    assert config.load()["color"] == "#2b5278"
