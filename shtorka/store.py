"""Templates kept in a single JSON file."""
import hashlib
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from . import config

if getattr(sys, "frozen", False):
    # the packaged exe unpacks its code to a temp folder, so the file lives with the settings
    TEMPLATES_FILE = config.BASE / "templates.json"
else:
    # run from source: next to the code, where git ignores it
    TEMPLATES_FILE = Path(__file__).resolve().parent.parent / "templates.json"


@dataclass
class Template:
    title: str
    text: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


def _fold(text: str) -> str:
    # people type е for ё
    return text.casefold().replace("ё", "е")


def search(templates: list[Template], query: str) -> list[Template]:
    """Templates that contain every word of the query; those with all of them in the title come first."""
    words = _fold(query).split()
    if not words:
        return list(templates)
    in_title = [t for t in templates if all(w in _fold(t.title) for w in words)]
    in_text = [t for t in templates if t not in in_title and all(w in _fold(f"{t.title}\n{t.text}") for w in words)]
    return in_title + in_text


def _fallback_id(entry: dict) -> str:
    # entries typed into the file by hand have no id; derive one that survives reloads
    return hashlib.md5(f"{entry['title']}\0{entry['text']}".encode()).hexdigest()[:12]


class BrokenFile(Exception):
    """The templates file exists but cannot be read; writing over it would lose the templates."""


class Store(QObject):
    changed = Signal()

    def __init__(self, path: Path = TEMPLATES_FILE):
        super().__init__()
        self.path = path
        self._mtime = self._stat()
        # pick up the file being edited or replaced by hand
        self._watch = QTimer(self, interval=1000)
        self._watch.timeout.connect(self._check)
        self._watch.start()

    def _stat(self) -> float:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0.0

    def _check(self) -> None:
        mtime = self._stat()
        if mtime != self._mtime:
            self._mtime = mtime
            self.changed.emit()

    def _read(self) -> list[Template]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as e:
            raise BrokenFile(str(e)) from e
        if not text.strip():
            return []
        try:
            data = json.loads(text)
            return [Template(d["title"], d["text"], d.get("id") or _fallback_id(d)) for d in data]
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise BrokenFile(str(e)) from e

    def load(self) -> list[Template]:
        try:
            return self._read()
        except BrokenFile:
            return []

    def _write(self, templates: list[Template]) -> None:
        templates.sort(key=lambda t: t.title.casefold())
        # write a copy first, so that a crash halfway leaves the old file whole
        temp = self.path.with_name(self.path.name + ".tmp")
        temp.write_text(
            json.dumps([asdict(t) for t in templates], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temp, self.path)
        self._mtime = self._stat()
        self.changed.emit()

    def save(self, tpl: Template) -> None:
        """Raises BrokenFile rather than overwrite a file it cannot read."""
        self._write([t for t in self._read() if t.id != tpl.id] + [tpl])

    def delete(self, tpl: Template) -> None:
        """Raises BrokenFile rather than overwrite a file it cannot read."""
        self._write([t for t in self._read() if t.id != tpl.id])
