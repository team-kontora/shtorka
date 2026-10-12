import json
import os
from pathlib import Path

BASE = Path(os.environ.get("APPDATA", Path.home())) / "shtorka"
CONFIG_FILE = BASE / "config.json"

DEFAULTS = {
    "process_names": ["telegram.exe", "ayugram.exe", "64gram.exe"],
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg
