import hashlib
import io
import json

import pytest

from shtorka import updater

SETUP = b"setup bytes"
DOWNLOAD = "https://example.invalid/ShtorkaSetup.exe"


class Response(io.BytesIO):
    pass


class GitHub:
    """The latest release, as the redirect and the API report it; counts what was asked."""

    def __init__(self, tag="v99.0.0", digest=None):
        self.tag = tag
        self.digest = digest or "sha256:" + hashlib.sha256(SETUP).hexdigest()
        self.looks = 0
        self.api_calls = 0
        self.downloads = 0

    def latest_tag(self):
        self.looks += 1
        return self.tag

    def open(self, url, headers=None):
        if url == updater.LATEST_URL:
            self.api_calls += 1
            asset = {"name": updater.ASSET, "browser_download_url": DOWNLOAD, "size": len(SETUP), "digest": self.digest}
            return Response(json.dumps({"tag_name": self.tag, "assets": [asset]}).encode())
        assert url == DOWNLOAD
        self.downloads += 1
        return Response(SETUP)


@pytest.fixture
def github(monkeypatch, tmp_path):
    server = GitHub()
    monkeypatch.setattr(updater, "_latest_tag", server.latest_tag)
    monkeypatch.setattr(updater, "_open", server.open)
    monkeypatch.setattr(updater, "PORTABLE", False)
    monkeypatch.setattr(updater, "INSTALLED_FILE", tmp_path / "updated_to.txt")
    return server


def test_downloads_a_newer_release(github, tmp_path):
    target = tmp_path / "setup.exe"
    assert updater._download(target) == "v99.0.0"
    assert target.read_bytes() == SETUP


def test_no_new_release_never_touches_the_api(github, tmp_path):
    github.tag = "v0.0.1"
    for _ in range(3):
        assert updater._download(tmp_path / "setup.exe") is None
    # only the redirect was looked at: the API and its 60 requests an hour stay untouched
    assert github.looks == 3 and github.api_calls == 0


def test_a_release_installed_already_is_not_fetched(github, tmp_path):
    updater.INSTALLED_FILE.write_text("v99.0.0", encoding="utf-8")
    assert updater._download(tmp_path / "setup.exe") is None
    assert github.api_calls == 0


def test_a_broken_download_is_dropped(github, tmp_path):
    github.digest = "sha256:" + "0" * 64
    target = tmp_path / "setup.exe"
    assert updater._download(target) is None
    assert not target.exists()


@pytest.mark.parametrize(
    "location",
    [
        "https://github.com/team-kontora/shtorka/releases/tag/v1.0.4",
        "https://github.com/team-kontora/shtorka/releases/tag/v1.0.4/",
    ],
)
def test_tag_from_the_redirect(location):
    assert updater._tag_from(location) == "v1.0.4"


def test_a_redirect_elsewhere_is_not_a_tag():
    # a repository with no releases redirects to the list of them
    with pytest.raises(ValueError):
        updater._tag_from("https://github.com/team-kontora/shtorka/releases")
