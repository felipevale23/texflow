"""Cache do biber pro engine Tectonic.

O Tectonic roda o biber a cada build, mesmo quando só o texto mudou. O
latexmk evita isso comparando as entradas; aqui o TexFlow faz o mesmo: põe
na frente do PATH um "biber" (shim) que chama `texflow --biber-cache`. Ele
calcula um hash das entradas (o .bcf e os .bib que o Tectonic copia pra
pasta temporária onde roda o biber, mais o binário do biber usado) e, se
for igual ao do último build, devolve o .bbl/.blg guardados em vez de rodar
o biber. Uma citação nova ou um .bib editado mudam o hash e o biber roda.
"""

import hashlib
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

CACHE_FLAG = "--biber-cache"
# Dentro de build/ (o CopyTree nunca copia build/, e é oculta).
CACHE_DIRNAME = ".texflow-cache"
OUTPUT_SUFFIXES = (".bbl", ".blg")
DIGEST_FILE = "biber.digest"


def cache_enabled() -> bool:
    """TEXFLOW_NO_CACHE=1 desliga o cache. No Windows o shim (script sh)
    não funciona, então fica desligado."""
    return os.getenv("TEXFLOW_NO_CACHE") != "1" and os.name != "nt"


def input_digest(workdir: Path, real_biber: Path) -> str:
    """Hash das entradas do biber: todos os arquivos da pasta onde o
    Tectonic o roda (menos as saídas), com caminho relativo, e o binário
    do biber (caminho, tamanho e mtime: trocar de versão invalida)."""
    h = hashlib.sha256()
    stat = real_biber.stat()
    h.update(f"{real_biber.resolve()}\0{stat.st_size}\0{stat.st_mtime_ns}\0".encode())
    for path in sorted(p for p in workdir.rglob("*") if p.is_file()):
        if path.suffix in OUTPUT_SUFFIXES:
            continue
        h.update(path.relative_to(workdir).as_posix().encode() + b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _stem(args: list[str]) -> str:
    """Nome base do documento: o último argumento do biber ("main" ou
    "main.bcf")."""
    name = Path(args[-1]).name if args else "main"
    return name.removesuffix(".bcf")


def run_cached_biber(
    real_biber: Path, cache_dir: Path, args: list[str], workdir: Path | None = None
) -> int:
    workdir = workdir or Path.cwd()
    stem = _stem(args)
    digest = input_digest(workdir, real_biber)
    digest_file = cache_dir / DIGEST_FILE
    cached = [cache_dir / f"{stem}{suffix}" for suffix in OUTPUT_SUFFIXES]

    try:
        hit = digest_file.read_text(encoding="utf-8") == digest and cached[0].is_file()
    except OSError:
        hit = False

    if hit:
        for path in cached:
            if path.is_file():
                shutil.copy2(path, workdir / path.name)
        print("texflow: entradas do biber iguais ao build anterior; usando o .bbl em cache.")
        return 0

    result = subprocess.run([str(real_biber), *args], cwd=workdir, check=False)
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest_file.unlink(missing_ok=True)
    if result.returncode == 0 and (workdir / f"{stem}.bbl").is_file():
        for suffix in OUTPUT_SUFFIXES:
            produced = workdir / f"{stem}{suffix}"
            if produced.is_file():
                shutil.copy2(produced, cache_dir / produced.name)
        digest_file.write_text(digest, encoding="utf-8")
    return result.returncode


def _self_command() -> list[str]:
    """Como chamar este mesmo TexFlow: o binário do PyInstaller, ou o
    Python + o script de entrada quando roda do código-fonte."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(sys.argv[0]).resolve())]


def install_shim(build_dir: Path, real_biber: Path) -> Path:
    """Escreve build/.texflow-cache/bin/biber e devolve a pasta dele, pra ir
    na frente do PATH do Tectonic."""
    cache_dir = build_dir / CACHE_DIRNAME
    bin_dir = cache_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    cmd = [*_self_command(), CACHE_FLAG, str(real_biber), str(cache_dir.resolve())]
    shim = bin_dir / "biber"
    shim.write_text(
        "#!/bin/sh\n"
        "# Gerado pelo TexFlow: cache do biber (ver scripts/bibcache.py).\n"
        f'exec {" ".join(shlex.quote(part) for part in cmd)} "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return bin_dir


def main(argv: list[str]) -> int:
    """Entrada do shim: texflow --biber-cache <biber real> <pasta do cache> <args do biber>."""
    if len(argv) < 2:
        print(f"uso: texflow {CACHE_FLAG} <biber> <pasta do cache> [args]", file=sys.stderr)
        return 2
    real_biber, cache_dir, *args = argv
    return run_cached_biber(Path(real_biber), Path(cache_dir), args)
