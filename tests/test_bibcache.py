import os
import subprocess
from pathlib import Path

import pytest

from scripts import bibcache
from scripts.bibcache import install_shim

pytestmark = pytest.mark.skipif(os.name == "nt", reason="o shim do cache é um script sh")


def _fake_biber(tmp_path: Path) -> tuple[Path, Path]:
    """biber falso: conta as execuções e gera <stem>.bbl a partir do .bcf."""
    counter = tmp_path / "runs"
    biber = tmp_path / "bin" / "biber"
    biber.parent.mkdir()
    biber.write_text(
        "#!/bin/sh\n"
        f'echo x >> "{counter}"\n'
        'cat "$1.bcf" > "$1.bbl"\n'
        'echo log > "$1.blg"\n'
    )
    biber.chmod(0o755)
    return biber, counter


def _runs(counter: Path) -> int:
    return len(counter.read_text().splitlines()) if counter.exists() else 0


def _workdir(tmp_path: Path, name: str, bcf: str, bib: str = "@book{a}") -> Path:
    """Imita a pasta temporária onde o Tectonic roda o biber."""
    work = tmp_path / name
    (work / "src").mkdir(parents=True)
    (work / "main.bcf").write_text(bcf)
    (work / "src" / "refs.bib").write_text(bib)
    return work


def _run(shim_dir: Path, work: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(shim_dir / "biber"), "main"], cwd=work, capture_output=True, text=True, check=False
    )


@pytest.fixture
def setup(tmp_path):
    biber, counter = _fake_biber(tmp_path)
    shim_dir = install_shim(tmp_path / "build", biber)
    return tmp_path, biber, counter, shim_dir


def test_second_run_with_same_inputs_uses_cache(setup):
    tmp_path, _biber, counter, shim_dir = setup

    assert _run(shim_dir, _workdir(tmp_path, "w1", "bcf-1")).returncode == 0
    work2 = _workdir(tmp_path, "w2", "bcf-1")
    result = _run(shim_dir, work2)

    assert result.returncode == 0
    assert "cache" in result.stdout
    assert _runs(counter) == 1
    assert (work2 / "main.bbl").read_text() == "bcf-1"
    assert (work2 / "main.blg").is_file()


@pytest.mark.parametrize("change", ["bcf", "bib", "bib-name"])
def test_changed_inputs_run_biber_again(setup, change):
    tmp_path, _biber, counter, shim_dir = setup
    _run(shim_dir, _workdir(tmp_path, "w1", "bcf-1"))

    if change == "bcf":
        work2 = _workdir(tmp_path, "w2", "bcf-2")
    elif change == "bib":
        work2 = _workdir(tmp_path, "w2", "bcf-1", bib="@book{b}")
    else:
        work2 = _workdir(tmp_path, "w2", "bcf-1")
        (work2 / "src" / "refs.bib").rename(work2 / "src" / "outro.bib")
    _run(shim_dir, work2)

    assert _runs(counter) == 2
    assert (work2 / "main.bbl").read_text() == ("bcf-2" if change == "bcf" else "bcf-1")


def test_different_biber_binary_invalidates_cache(setup):
    tmp_path, biber, counter, shim_dir = setup
    _run(shim_dir, _workdir(tmp_path, "w1", "bcf-1"))

    biber.write_text(biber.read_text() + "# nova versão\n")
    _run(shim_dir, _workdir(tmp_path, "w2", "bcf-1"))

    assert _runs(counter) == 2


def test_failed_biber_is_not_cached_and_keeps_exit_code(tmp_path):
    biber = tmp_path / "biber"
    biber.write_text(f'#!/bin/sh\necho x >> "{tmp_path}/runs"\nexit 2\n')
    biber.chmod(0o755)
    shim_dir = install_shim(tmp_path / "build", biber)

    assert _run(shim_dir, _workdir(tmp_path, "w1", "bcf")).returncode == 2
    assert _run(shim_dir, _workdir(tmp_path, "w2", "bcf")).returncode == 2
    assert _runs(tmp_path / "runs") == 2


def test_paths_with_spaces(tmp_path):
    base = tmp_path / "com espaço"
    base.mkdir()
    biber, counter = _fake_biber(base)
    shim_dir = install_shim(base / "meu build", biber)

    for name in ("w1", "w2"):
        assert _run(shim_dir, _workdir(base, name, "bcf")).returncode == 0
    assert _runs(counter) == 1


def test_install_shim_is_stable(setup):
    tmp_path, biber, _counter, shim_dir = setup
    shim = shim_dir / "biber"
    before = shim.stat().st_mtime_ns
    install_shim(tmp_path / "build", biber)
    assert shim.stat().st_mtime_ns == before


def test_cache_can_be_disabled(monkeypatch):
    monkeypatch.setenv("TEXFLOW_NO_CACHE", "1")
    assert not bibcache.cache_enabled()


def test_freeze_returns_last_full_bbl_even_if_inputs_changed(setup, monkeypatch):
    tmp_path, _biber, counter, shim_dir = setup
    _run(shim_dir, _workdir(tmp_path, "w1", "bcf-completo"))

    monkeypatch.setenv("TEXFLOW_BIBER_FREEZE", "1")
    work2 = _workdir(tmp_path, "w2", "bcf-so-um-capitulo")
    result = _run(shim_dir, work2)

    assert result.returncode == 0
    assert "rascunho" in result.stdout
    assert _runs(counter) == 1
    assert (work2 / "main.bbl").read_text() == "bcf-completo"


def test_freeze_without_cache_runs_biber(setup, monkeypatch):
    tmp_path, _biber, counter, shim_dir = setup
    monkeypatch.setenv("TEXFLOW_BIBER_FREEZE", "1")
    _run(shim_dir, _workdir(tmp_path, "w1", "bcf"))
    assert _runs(counter) == 1
