"""Templates kept in a single JSON file next to the code (the file is gitignored)."""
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

TEMPLATES_FILE = Path(__file__).resolve().parent.parent / "templates.json"


@dataclass
class Template:
    title: str
    text: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


def _fallback_id(entry: dict) -> str:
    # entries typed into the file by hand have no id; derive one that survives reloads
    return hashlib.md5(f"{entry['title']}\0{entry['text']}".encode()).hexdigest()[:12]


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

    def load(self) -> list[Template]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [Template(d["title"], d["text"], d.get("id") or _fallback_id(d)) for d in data]
        except (OSError, ValueError, KeyError, TypeError):
            return []

    def _write(self, templates: list[Template]) -> None:
        templates.sort(key=lambda t: t.title.casefold())
        self.path.write_text(
            json.dumps([asdict(t) for t in templates], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self._mtime = self._stat()
        self.changed.emit()

    def save(self, tpl: Template) -> None:
        self._write([t for t in self.load() if t.id != tpl.id] + [tpl])

    def delete(self, tpl: Template) -> None:
        self._write([t for t in self.load() if t.id != tpl.id])
