import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

from configs.version import __version__
from scripts.utils import confirm

GITHUB_REPO = "felipevale23/texflow"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path | None:
    """Pasta da instalação em pasta (--onedir, ver install.sh): a que tem o
    executável e o _internal/. None no arquivo único (--onefile)."""
    exe_dir = Path(sys.executable).resolve().parent
    return exe_dir if (exe_dir / "_internal").is_dir() else None


def _download(url: str, dst: Path) -> None:
    try:
        subprocess.run(["curl", "-fL", url, "-o", str(dst)], check=True)
    except FileNotFoundError as e:
        raise RuntimeError("`curl` não encontrado. Instale-o e tente novamente.") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Falha ao baixar o binário: {e}") from e


def _update_onefile(url: str) -> None:
    target = Path(sys.executable)
    tmp = target.parent / f".{target.name}.update-tmp"
    try:
        _download(url, tmp)
        tmp.chmod(0o755)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def _update_onedir(url: str, lib: Path) -> None:
    """Baixa o .tar.gz (uma pasta "texflow/" com o executável e o
    _internal/), extrai ao lado da instalação e troca a pasta inteira. O
    symlink no PATH aponta pra <lib>/texflow e continua valendo."""
    work = lib.parent / f".{lib.name}.update-tmp"
    old = lib.parent / f".{lib.name}.old"
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        archive = work / "pkg.tar.gz"
        _download(url, archive)
        with tarfile.open(archive) as tar:
            tar.extractall(work, filter="data")
        new = work / "texflow"
        if not ((new / "_internal").is_dir() and (new / "texflow").is_file()):
            raise RuntimeError("Pacote da release inesperado: falta texflow/texflow ou texflow/_internal.")
        os.replace(lib, old)
        try:
            os.replace(new, lib)
        except OSError:
            os.replace(old, lib)
            raise
        shutil.rmtree(old, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _parse_version(tag: str) -> tuple[int, int, int]:
    tag = tag.strip().lstrip("vV")
    parts = tag.split(".")[:3]
    nums = []
    for part in parts:
        match = re.match(r"\d+", part)
        nums.append(int(match.group()) if match else 0)
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def _is_newer(latest_tag: str, current_version: str) -> bool:
    return _parse_version(latest_tag) > _parse_version(current_version)


def _asset_name(system: str | None = None, machine: str | None = None) -> str:
    import platform

    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    return f"texflow-{system}-{machine}"


def _fetch_latest_release() -> dict:
    request = urllib.request.Request(
        GITHUB_API_LATEST,
        headers={
            "User-Agent": "texflow-updater",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.URLError as e:
        raise RuntimeError(f"Falha ao consultar releases no GitHub: {e}") from e


def run_update(auto_yes: bool) -> None:
    if not is_frozen():
        print("Você está rodando o TexFlow a partir do código-fonte. Use `git pull && uv sync` para atualizar.")
        return

    release = _fetch_latest_release()
    latest_tag = release["tag_name"]

    if not _is_newer(latest_tag, __version__):
        print(f"Você já está na versão mais recente ({__version__}).")
        return

    lib = install_dir()
    asset_name = _asset_name() + (".tar.gz" if lib else "")
    asset = next((a for a in release.get("assets", []) if a["name"] == asset_name), None)
    if asset is None:
        raise RuntimeError(f"Nenhum binário publicado em {latest_tag} para esta plataforma ({asset_name}).")

    if not confirm(f"Atualizar TexFlow de {__version__} para {latest_tag}?", auto_yes):
        return

    if lib:
        _update_onedir(asset["browser_download_url"], lib)
    else:
        _update_onefile(asset["browser_download_url"])

    print(f"Atualizado com sucesso: {__version__} -> {latest_tag}")


def run_uninstall(auto_yes: bool) -> None:
    if not is_frozen():
        print(
            "Você está rodando o TexFlow a partir do código-fonte. "
            "Não há binário para remover — apague a pasta do clone se desejar."
        )
        return

    lib = install_dir()
    if lib is None:
        target = Path(sys.executable)
        if not confirm(f"Remover {target}?", auto_yes):
            return
        target.unlink()
        print(f"Removido: {target}")
    else:
        exe = lib / "texflow"
        links = _links_to(exe)
        listed = ", ".join(str(p) for p in [lib, *links])
        if not confirm(f"Remover {listed}?", auto_yes):
            return
        for link in links:
            link.unlink()
        shutil.rmtree(lib)
        print(f"Removido: {listed}")
    print("Se você adicionou uma entrada no PATH manualmente, lembre-se de removê-la do seu shell rc.")


def _links_to(exe: Path) -> list[Path]:
    """Symlinks pro executável da instalação em pasta: o do install.sh
    (~/.local/bin/texflow ou TEXFLOW_INSTALL_DIR) e o que estiver no PATH."""
    candidates = [Path.home() / ".local" / "bin" / "texflow"]
    if os.getenv("TEXFLOW_INSTALL_DIR"):
        candidates.append(Path(os.environ["TEXFLOW_INSTALL_DIR"]) / "texflow")
    on_path = shutil.which("texflow")
    if on_path:
        candidates.append(Path(on_path))
    links = []
    for c in candidates:
        if c.is_symlink() and c.resolve() == exe.resolve() and c not in links:
            links.append(c)
    return links
