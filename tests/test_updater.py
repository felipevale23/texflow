import sys
import tarfile
from pathlib import Path

import pytest

from scripts import updater
from scripts.updater import _asset_name, _is_newer, _parse_version, is_frozen


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v1.2.3", (1, 2, 3)),
        ("1.2.3", (1, 2, 3)),
        ("v1.2", (1, 2, 0)),
        ("v2", (2, 0, 0)),
        ("v1.2.3-rc1", (1, 2, 3)),
        ("garbage", (0, 0, 0)),
        ("", (0, 0, 0)),
    ],
)
def test_parse_version(tag, expected):
    assert _parse_version(tag) == expected


@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        ("v0.2.0", "0.1.0", True),
        ("v0.1.0", "0.1.0", False),
        ("v0.0.9", "0.1.0", False),
        ("v1.0.0", "0.1.0", True),
    ],
)
def test_is_newer(latest, current, expected):
    assert _is_newer(latest, current) is expected


def test_asset_name_matches_current_release_convention():
    assert _asset_name("Linux", "x86_64") == "texflow-linux-x86_64"


def test_asset_name_is_platform_forward_compatible():
    assert _asset_name("Darwin", "arm64") == "texflow-darwin-arm64"


def test_is_frozen_true(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert is_frozen() is True


def test_is_frozen_false(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert is_frozen() is False


# ----------------------------------------------------------------------
# Instalação em pasta (--onedir)
# ----------------------------------------------------------------------



def _onedir(root: Path, version: str) -> Path:
    lib = root / "texflow"
    (lib / "_internal").mkdir(parents=True)
    (lib / "_internal" / "VERSION").write_text(version)
    exe = lib / "texflow"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    return lib


def _package(tmp_path: Path, version: str, *, broken: bool = False) -> Path:
    src = _onedir(tmp_path / f"pkg-{version}", version)
    if broken:
        (src / "texflow").unlink()
    archive = tmp_path / f"texflow-{version}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src, arcname="texflow")
    return archive


def _fake_download(archive: Path):
    return lambda _url, dst: dst.write_bytes(archive.read_bytes())


def test_install_dir_detects_onedir(tmp_path, monkeypatch):
    lib = _onedir(tmp_path, "1")
    link = tmp_path / "bin" / "texflow"
    link.parent.mkdir()
    link.symlink_to(lib / "texflow")
    monkeypatch.setattr(sys, "executable", str(link))
    assert updater.install_dir() == lib.resolve()


def test_install_dir_is_none_for_onefile(tmp_path, monkeypatch):
    exe = tmp_path / "texflow"
    exe.write_text("x")
    monkeypatch.setattr(sys, "executable", str(exe))
    assert updater.install_dir() is None


def test_onedir_update_swaps_the_whole_folder(tmp_path, monkeypatch):
    lib = _onedir(tmp_path / "lib", "old")
    (lib / "_internal" / "stale.so").write_text("x")
    link = tmp_path / "texflow-link"
    link.symlink_to(lib / "texflow")
    monkeypatch.setattr(updater, "_download", _fake_download(_package(tmp_path, "new")))

    updater._update_onedir("https://example/pkg.tar.gz", lib)

    assert (lib / "_internal" / "VERSION").read_text() == "new"
    assert not (lib / "_internal" / "stale.so").exists()
    assert link.resolve() == (lib / "texflow").resolve()
    assert sorted(p.name for p in lib.parent.iterdir()) == ["texflow"]


def test_onedir_update_with_bad_package_keeps_current_install(tmp_path, monkeypatch):
    lib = _onedir(tmp_path / "lib", "old")
    monkeypatch.setattr(updater, "_download", _fake_download(_package(tmp_path, "new", broken=True)))

    with pytest.raises(RuntimeError, match="inesperado"):
        updater._update_onedir("https://example/pkg.tar.gz", lib)

    assert (lib / "_internal" / "VERSION").read_text() == "old"
    assert sorted(p.name for p in lib.parent.iterdir()) == ["texflow"]


def test_run_update_picks_tarball_for_onedir(tmp_path, monkeypatch):
    lib = _onedir(tmp_path / "lib", "old")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(lib / "texflow"))
    name = updater._asset_name()
    release = {
        "tag_name": "v99.0.0",
        "assets": [
            {"name": name, "browser_download_url": "https://example/onefile"},
            {"name": f"{name}.tar.gz", "browser_download_url": "https://example/onedir"},
        ],
    }
    monkeypatch.setattr(updater, "_fetch_latest_release", lambda: release)
    urls = []
    monkeypatch.setattr(updater, "_update_onedir", lambda url, d: urls.append((url, d)))

    updater.run_update(auto_yes=True)

    assert urls == [("https://example/onedir", lib.resolve())]


def test_uninstall_onedir_removes_folder_and_symlink(tmp_path, monkeypatch):
    lib = _onedir(tmp_path / "lib", "1")
    home = tmp_path / "home"
    link = home / ".local" / "bin" / "texflow"
    link.parent.mkdir(parents=True)
    link.symlink_to(lib / "texflow")
    other = home / ".local" / "bin" / "other"
    other.write_text("x")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(link))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(updater.shutil, "which", lambda _name: None)

    updater.run_uninstall(auto_yes=True)

    assert not lib.exists()
    assert not link.is_symlink()
    assert other.exists()
