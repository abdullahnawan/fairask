"""Tests for the public data downloader.

No network: each test serves a local file through a `file://` URL, which is
enough to exercise the skip, the write and the HTML guard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import download


@pytest.fixture
def local_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect RAW to a temp dir and register one local CSV as a source."""
    origin = tmp_path / "origin.csv"
    origin.write_text("mls,price\nX1,100\n", encoding="utf-8")
    monkeypatch.setattr(download, "RAW", tmp_path / "raw")
    monkeypatch.setitem(download.SOURCES, "local", (origin.as_uri(), "local/origin.csv"))
    return origin


def test_downloads_into_raw(local_csv: Path) -> None:
    dest = download.fetch("local")
    assert dest.read_text(encoding="utf-8") == local_csv.read_text(encoding="utf-8")


def test_second_call_skips_the_download(local_csv: Path, capsys: pytest.CaptureFixture) -> None:
    download.fetch("local")
    capsys.readouterr()
    download.fetch("local")
    assert "already have" in capsys.readouterr().out


def test_rejects_an_html_page_and_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = tmp_path / "outage.html"
    page.write_text("<html>maintenance</html>", encoding="utf-8")
    monkeypatch.setattr(download, "RAW", tmp_path / "raw")
    monkeypatch.setitem(download.SOURCES, "bad", (page.as_uri(), "bad/data.zip"))

    with pytest.raises(ValueError, match="HTML page"):
        download.fetch("bad")

    dest = tmp_path / "raw" / "bad" / "data.zip"
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".partial").exists()
