import json
import os
from pathlib import Path

BASE = Path(os.environ.get("APPDATA", Path.home())) / "shtorka"
CONFIG_FILE = BASE / "config.json"

DEFAULTS = {
    "process_names": ["telegram.exe", "ayugram.exe", "64gram.exe"],
    "color": "#000000",
    "style": "flat",
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict):
        cfg.update(data)
    names = cfg["process_names"]
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        names = DEFAULTS["process_names"]
    # process names are compared in lower case
    cfg["process_names"] = [n.lower() for n in names]
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
