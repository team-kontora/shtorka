"""Self-update of the packaged app from GitHub releases."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from . import __version__, config

LATEST_URL = "https://api.github.com/repos/team-kontora/shtorka/releases/latest"
ASSET = "ShtorkaSetup.exe"
# remembers the release installed last, so a release whose exe reports an older version is not installed in a loop
INSTALLED_FILE = config.BASE / "updated_to.txt"

FROZEN = getattr(sys, "frozen", False)
# the single-file exe unpacks itself elsewhere; the installed app keeps its files next to the exe
PORTABLE = FROZEN and Path(sys._MEIPASS).parent != Path(sys.executable).parent
# where Setup puts the app
INSTALLED_EXE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / "Shtorka" / "Shtorka.exe"

FIRST_CHECK_MS = 15 * 1000
CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000
IDLE_POLL_MS = 5 * 1000


def launch(exe: Path, *args: str) -> None:
    # without the reset a packaged exe started from this one would take itself for its child and reuse its unpacked files
    subprocess.Popen([str(exe), *args], env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})


def _parse(tag: str) -> tuple[int, ...]:
    return tuple(int(part) for part in tag.lstrip("v").split("."))


def _open(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": f"Shtorka/{__version__}"})
    return urllib.request.urlopen(request, timeout=30)


def _wanted(tag: str) -> bool:
    if PORTABLE:
        # the single-file copy moves to the installed app even when that is the same version
        return _parse(tag) >= _parse(__version__)
    if _parse(tag) <= _parse(__version__):
        return False
    try:
        return INSTALLED_FILE.read_text(encoding="utf-8").strip() != tag
    except OSError:
        return True


def _download(target: Path) -> str | None:
    """Puts the Setup of a release worth installing into target and returns its tag, or None when there is none."""
    with _open(LATEST_URL) as response:
        release = json.load(response)
    tag = release["tag_name"]
    if not _wanted(tag):
        return None
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
        self._setup = Path(tempfile.gettempdir()) / ASSET
        self._tag = None
        self._checking = False
        self._downloaded.connect(self._on_downloaded)

        self._timer = QTimer(self, interval=CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self._check)
        self._timer.start()
        QTimer.singleShot(FIRST_CHECK_MS, self._check)

        # the downloaded Setup waits here until no dialog or menu is open
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
            # the Setup of the previous update
            self._setup.unlink(missing_ok=True)
            tag = _download(self._setup)
        except Exception:
            # no network or GitHub is down: try again on the next check
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
        try:
            # Setup waits for this copy to quit, replaces the files and starts the app again
            launch(self._setup, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
        except OSError:
            # something keeps Setup from running; leave it until the next start instead of downloading it again
            self._timer.stop()
            return
        try:
            INSTALLED_FILE.write_text(self._tag, encoding="utf-8")
        except OSError:
            pass
        self._lock.unlock()
        QApplication.quit()
