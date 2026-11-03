import importlib.resources as res
import sys
from collections.abc import Callable
from pathlib import Path

from classes.task import is_excluded_dir, load_ignore_patterns, matches_ignore
from scripts.builder import DEFAULT_ENGINE, build

# Janela pra agrupar rajadas de eventos (ex: editor que salva via arquivo
# temporário + rename) num rebuild só.
DEBOUNCE_MS = 300

# Marcadores fixos de início/fim de cada build: o problemMatcher da task
# "TexFlow Watch" (assets/vscode/tasks.json) usa esses textos como
# beginsPattern/endsPattern pra saber quando um build terminou.
BUILD_STARTED = "[texflow] build iniciado"
BUILD_OK = "[texflow] build concluído"
BUILD_FAILED = "[texflow] build falhou"

# Pastas que nunca disparam rebuild: build/ é onde o próprio build escreve
# (senão cada compilação dispararia outra, em loop) — o CopyTree também
# nunca copia "build" — e .vscode/ não é conteúdo do template.
IGNORED_DIRS = ("build", ".vscode")


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.stderr.flush()


def watch_paths(data_path: Path, template_dir: Path) -> list[Path]:
    """Pastas/arquivos observados: o template, o JSON de dados (se estiver
    fora do template) e os assets de imagens/plots, quando existirem como
    pasta real no disco (no binário PyInstaller eles são extraídos num
    diretório temporário que ninguém edita, então não vale a pena)."""
    paths = [template_dir]
    if not data_path.is_relative_to(template_dir):
        paths.append(data_path)

    if getattr(sys, "frozen", False):
        return paths

    for name in ("images", "plots"):
        asset = res.files("assets").joinpath(name)
        if isinstance(asset, Path) and asset.is_dir():
            paths.append(asset)

    return paths


def _ignored_in_template(path: Path, template_dir: Path, patterns: list[str]) -> bool:
    """True se o caminho está numa pasta que o CopyTree não copia (oculta,
    node_modules, venv...) ou casa com o .texflowignore: mudar algo ali não
    muda o build, então não vale um rebuild."""
    try:
        parts = path.relative_to(template_dir).parts
    except ValueError:
        return False
    for i, part in enumerate(parts):
        is_dir = i < len(parts) - 1 or path.is_dir()
        if is_dir and is_excluded_dir(part):
            return True
        if patterns and matches_ignore("/".join(parts[: i + 1]), is_dir, patterns):
            return True
    return False


def watch_filter(template_dir: Path | None = None):
    from watchfiles import DefaultFilter

    default = DefaultFilter(ignore_dirs=(*DefaultFilter.ignore_dirs, *IGNORED_DIRS))
    if template_dir is None:
        return default

    patterns = load_ignore_patterns(template_dir)

    def accept(change, path: str) -> bool:
        return default(change, path) and not _ignored_in_template(
            Path(path), template_dir, patterns
        )

    return accept


def watch(
    data_path: str,
    template_folder: str,
    engine: str = DEFAULT_ENGINE,
    *,
    rebuild: Callable[[str, str, str], bool] = build,
    watcher: Callable | None = None,
) -> None:
    """Faz um build e depois refaz (render → copy → compile) a cada mudança
    no JSON, no template ou nos assets, até Ctrl+C. Build com erro não
    derruba o watcher: o resumo do erro é impresso e ele continua
    observando. O cache incremental (mtime preservado em classes/task.py +
    .fdb_latexmk) mantém os rebuilds rápidos."""

    if watcher is None:
        from watchfiles import watch as watcher

    data = Path(data_path).resolve()
    template_dir = Path(template_folder).resolve()
    paths = watch_paths(data, template_dir)

    def run_build() -> None:
        _log(BUILD_STARTED)
        try:
            ok = rebuild(str(data), str(template_dir), engine)
        except Exception as e:  # noqa: BLE001 - nenhum erro de build pode matar o watcher
            _log(f"✖ Erro: {e}")
            ok = False
        _log(BUILD_OK if ok else BUILD_FAILED)

    try:
        run_build()
        _log(f"👀 Observando: {', '.join(str(p) for p in paths)} (Ctrl+C para sair)")

        for changes in watcher(
            *paths,
            watch_filter=watch_filter(template_dir),
            debounce=DEBOUNCE_MS,
            raise_interrupt=False,
        ):
            changed = sorted({Path(p).name for _change, p in changes})
            _log(f"🔄 Mudança em: {', '.join(changed)}")
            run_build()

    except KeyboardInterrupt:
        pass

    _log("👋 Watch encerrado.")
