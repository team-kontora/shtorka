"""Self-update of the packaged exe from GitHub releases."""
import hashlib
import json
import os
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from . import __version__, config

LATEST_URL = "https://api.github.com/repos/team-kontora/shtorka/releases/latest"
ASSET = "Shtorka.exe"
# remembers the release installed last, so a release whose exe reports an older version is not installed in a loop
INSTALLED_FILE = config.BASE / "updated_to.txt"

FIRST_CHECK_MS = 15 * 1000
CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000
IDLE_POLL_MS = 5 * 1000


def _parse(tag: str) -> tuple[int, ...]:
    return tuple(int(part) for part in tag.lstrip("v").split("."))


def _open(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": f"Shtorka/{__version__}"})
    return urllib.request.urlopen(request, timeout=30)


def _download(target: Path) -> str | None:
    """Puts a newer release into target and returns its tag, or None when there is nothing to install."""
    with _open(LATEST_URL) as response:
        release = json.load(response)
    tag = release["tag_name"]
    if _parse(tag) <= _parse(__version__):
        return None
    try:
        if INSTALLED_FILE.read_text(encoding="utf-8").strip() == tag:
            return None
    except OSError:
        pass
    asset = next(a for a in release["assets"] if a["name"] == ASSET)

    sha256 = hashlib.sha256()
    with _open(asset["browser_download_url"]) as response, open(target, "wb") as out:
        while chunk := response.read(1 << 16):
            sha256.update(chunk)
            out.write(chunk)
    digest = asset.get("digest")
    if target.stat().st_size != asset["size"] or (digest and digest != f"sha256:{sha256.hexdigest()}"):
        target.unlink()
        return None
    return tag


class Updater(QObject):
    _downloaded = Signal(str)

    def __init__(self, lock: QLockFile):
        super().__init__()
        self._lock = lock
        self._exe = Path(sys.executable)
        self._new = self._exe.with_name(f"{self._exe.stem}.new.exe")
        self._old = self._exe.with_name(f"{self._exe.stem}.old.exe")
        self._tag = None
        self._checking = False
        self._downloaded.connect(self._on_downloaded)

        self._timer = QTimer(self, interval=CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self._check)
        self._timer.start()
        QTimer.singleShot(FIRST_CHECK_MS, self._check)

        # the downloaded exe waits here until no dialog or menu is open
        self._idle = QTimer(self, interval=IDLE_POLL_MS)
        self._idle.timeout.connect(self._install)

    def _check(self) -> None:
        if self._checking or self._tag:
            return
        self._checking = True
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        tag = None
        try:
            # the previous version is still exiting right after an update, so its file goes on a later check
            self._old.unlink(missing_ok=True)
            tag = _download(self._new)
        except Exception:
            # no network, GitHub is down, the folder is read-only: try again on the next check
            pass
        self._downloaded.emit(tag or "")

    def _on_downloaded(self, tag: str) -> None:
        self._checking = False
        if tag:
            self._tag = tag
            self._idle.start()
            self._install()

    def _install(self) -> None:
        if QApplication.activeModalWidget() or QApplication.activePopupWidget():
            return
        self._idle.stop()
        # Windows lets a running exe be renamed but not overwritten. The swap happens right before
        # the restart because the renamed exe can no longer load modules it has not imported yet.
        try:
            self._old.unlink(missing_ok=True)
            self._exe.rename(self._old)
        except OSError:
            return self._give_up()
        try:
            self._new.rename(self._exe)
            self._lock.unlock()
            # without the reset the new exe would take itself for a child of this one and reuse its unpacked files
            subprocess.Popen([str(self._exe)], env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
        except OSError:
            self._exe.unlink(missing_ok=True)
            self._old.rename(self._exe)
            self._lock.tryLock(0)
            return self._give_up()
        try:
            INSTALLED_FILE.write_text(self._tag, encoding="utf-8")
        except OSError:
            pass
        QApplication.quit()

    def _give_up(self) -> None:
        # something keeps the update from applying; leave it until the next start instead of downloading it again
        self._timer.stop()
