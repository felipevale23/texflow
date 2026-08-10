import importlib.resources as res
import sys
from pathlib import Path

from scripts.utils import confirm

VSCODE_ASSETS = res.files("assets").joinpath("vscode")


def run_init(auto_yes: bool) -> None:
    """Cria .vscode/settings.json e .vscode/extensions.json no diretório
    atual, com a receita do LaTeX Workshop já configurada pro TexFlow."""

    target_dir = Path.cwd() / ".vscode"
    target_dir.mkdir(parents=True, exist_ok=True)

    for name in ("settings.json", "extensions.json"):
        dst = target_dir / name

        if dst.exists() and not confirm(f"{dst} já existe. Sobrescrever?", auto_yes):
            print(f"Mantido: {dst}", file=sys.stderr)
            continue

        content = VSCODE_ASSETS.joinpath(name).read_text(encoding="utf-8")
        dst.write_text(content, encoding="utf-8")
        print(f"Criado: {dst}", file=sys.stderr)

    print(
        "Pronto! Abra a pasta no VS Code — ele vai sugerir instalar a "
        "extensão LaTeX Workshop automaticamente.",
        file=sys.stderr,
    )
