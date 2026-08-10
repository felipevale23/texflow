import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from configs.version import __version__
from scripts.utils import confirm

GITHUB_REPO = "felipevale23/texflow"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


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

    asset_name = _asset_name()
    asset = next((a for a in release.get("assets", []) if a["name"] == asset_name), None)
    if asset is None:
        raise RuntimeError(f"Nenhum binário publicado em {latest_tag} para esta plataforma ({asset_name}).")

    if not confirm(f"Atualizar TexFlow de {__version__} para {latest_tag}?", auto_yes):
        return

    target = Path(sys.executable)
    tmp = target.parent / f".{target.name}.update-tmp"

    try:
        subprocess.run(
            ["curl", "-fL", asset["browser_download_url"], "-o", str(tmp)],
            check=True,
        )
        tmp.chmod(0o755)
        os.replace(tmp, target)
    except FileNotFoundError as e:
        raise RuntimeError("`curl` não encontrado. Instale-o e tente novamente.") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Falha ao baixar o binário: {e}") from e
    finally:
        tmp.unlink(missing_ok=True)

    print(f"Atualizado com sucesso: {__version__} -> {latest_tag}")


def run_uninstall(auto_yes: bool) -> None:
    if not is_frozen():
        print(
            "Você está rodando o TexFlow a partir do código-fonte. "
            "Não há binário para remover — apague a pasta do clone se desejar."
        )
        return

    target = Path(sys.executable)

    if not confirm(f"Remover {target}?", auto_yes):
        return

    target.unlink()
    print(f"Removido: {target}")
    print("Se você adicionou uma entrada no PATH manualmente, lembre-se de removê-la do seu shell rc.")
