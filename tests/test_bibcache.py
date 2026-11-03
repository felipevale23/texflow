import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import bibcache
from scripts.bibcache import install_shim, run_cached_biber

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


def test_second_run_with_same_inputs_uses_cache(tmp_path):
    biber, counter = _fake_biber(tmp_path)
    cache = tmp_path / "cache"

    assert run_cached_biber(biber, cache, ["main"], _workdir(tmp_path, "w1", "bcf-1")) == 0
    work2 = _workdir(tmp_path, "w2", "bcf-1")
    assert run_cached_biber(biber, cache, ["main"], work2) == 0

    assert _runs(counter) == 1
    assert (work2 / "main.bbl").read_text() == "bcf-1"
    assert (work2 / "main.blg").is_file()


@pytest.mark.parametrize("change", ["bcf", "bib"])
def test_changed_inputs_run_biber_again(tmp_path, change):
    biber, counter = _fake_biber(tmp_path)
    cache = tmp_path / "cache"
    run_cached_biber(biber, cache, ["main"], _workdir(tmp_path, "w1", "bcf-1"))

    if change == "bcf":
        work2 = _workdir(tmp_path, "w2", "bcf-2")
    else:
        work2 = _workdir(tmp_path, "w2", "bcf-1", bib="@book{b}")
    run_cached_biber(biber, cache, ["main"], work2)

    assert _runs(counter) == 2
    expected = "bcf-2" if change == "bcf" else "bcf-1"
    assert (work2 / "main.bbl").read_text() == expected


def test_different_biber_binary_invalidates_cache(tmp_path):
    biber, counter = _fake_biber(tmp_path)
    cache = tmp_path / "cache"
    run_cached_biber(biber, cache, ["main"], _workdir(tmp_path, "w1", "bcf-1"))

    biber.write_text(biber.read_text() + "# nova versão\n")
    run_cached_biber(biber, cache, ["main"], _workdir(tmp_path, "w2", "bcf-1"))

    assert _runs(counter) == 2


def test_failed_biber_is_not_cached(tmp_path):
    biber = tmp_path / "biber"
    biber.write_text('#!/bin/sh\necho x >> "$0.runs"\nexit 2\n')
    biber.chmod(0o755)
    cache = tmp_path / "cache"

    assert run_cached_biber(biber, cache, ["main"], _workdir(tmp_path, "w1", "bcf")) == 2
    assert run_cached_biber(biber, cache, ["main"], _workdir(tmp_path, "w2", "bcf")) == 2
    assert len(Path(f"{biber}.runs").read_text().splitlines()) == 2


def test_cache_can_be_disabled(monkeypatch):
    monkeypatch.setenv("TEXFLOW_NO_CACHE", "1")
    assert not bibcache.cache_enabled()


def test_shim_calls_texflow_and_caches(tmp_path, monkeypatch):
    """O shim gerado roda de verdade: chama este TexFlow (pelo código-fonte)
    com --biber-cache, que roda o biber falso só na primeira vez."""
    main_py = Path(__file__).resolve().parents[1] / "src" / "main.py"
    monkeypatch.setattr(sys, "argv", [str(main_py)])
    biber, counter = _fake_biber(tmp_path)
    shim_dir = install_shim(tmp_path / "build", biber)

    for name in ("w1", "w2"):
        work = _workdir(tmp_path, name, "bcf-1")
        result = subprocess.run(
            [str(shim_dir / "biber"), "main"], cwd=work, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr
        assert (work / "main.bbl").read_text() == "bcf-1"

    assert _runs(counter) == 1
    assert "cache" in result.stdout
