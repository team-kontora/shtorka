import json
import os
from pathlib import Path

BASE = Path(os.environ.get("APPDATA", Path.home())) / "shtorka"
CONFIG_FILE = BASE / "config.json"

DEFAULTS = {
    "process_names": ["telegram.exe", "ayugram.exe", "64gram.exe"],
    "color": "#000000",
    "style": "flat",
    "auto_update": True,
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save(**values) -> None:
    """Write settings changed from the app, keeping whatever else the file holds."""
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.update(values)
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
