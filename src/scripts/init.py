import importlib.resources as res
import json
import sys
from collections.abc import Callable
from pathlib import Path

from scripts import jsonc
from scripts.utils import confirm

VSCODE_ASSETS = res.files("assets").joinpath("vscode")

TECTONIC_RECIPE = "TexFlow Build (Tectonic)"
RUN_ON_SAVE_KEY = "emeraldwalk.runonsave"
RUN_ON_SAVE_EXT = "emeraldwalk.RunOnSave"
RUN_ON_SAVE_CMD = "texflow --build --input input.json --template ."
WATCH_TASK = "TexFlow Watch"


def _asset(name: str) -> str:
    return VSCODE_ASSETS.joinpath(name).read_text(encoding="utf-8")


def _root_object(text: str) -> jsonc.Node:
    root = jsonc.parse(text)
    if root.kind != "object":
        raise jsonc.JSONCError("o valor raiz não é um objeto")
    return root


def _scalar(text: str, node: jsonc.Node):
    return json.loads(text[node.start : node.end]) if node.kind == "scalar" else None


def _is_managed(key: str) -> bool:
    """Chaves de settings.json que pertencem ao TexFlow e podem ser
    sobrescritas num merge; todo o resto é do usuário e fica intacto."""
    return key.startswith("latex-workshop.") or key == RUN_ON_SAVE_KEY


def _remove_recommendation(text: str, ext: str) -> str:
    recs = jsonc.find(_root_object(text), "recommendations")
    if recs is not None and recs.value.kind == "array":
        for n, item in enumerate(recs.value.elements):
            if _scalar(text, item.value) == ext:
                return jsonc.remove(text, recs.value, n)
    return text


# ----------------------------------------------------------------------
# Conteúdo gerado: os assets de assets/vscode/ ajustados pro engine/modo
# ----------------------------------------------------------------------


def render_settings(engine: str, watch: bool) -> str:
    text = _asset("settings.json")

    if engine == "tectonic":
        text = jsonc.set_member(
            text, "latex-workshop.latex.recipe.default", json.dumps(TECTONIC_RECIPE)
        )
        old = json.dumps(RUN_ON_SAVE_CMD)
        new = json.dumps(
            RUN_ON_SAVE_CMD.replace("--build", "--build --engine tectonic")
        )
        if text.count(old) != 1:
            raise RuntimeError(
                "assets/vscode/settings.json: comando do RunOnSave não encontrado"
            )
        text = text.replace(old, new)

    # No modo watch quem rebuilda é a task "TexFlow Watch"; manter o
    # RunOnSave faria cada save compilar duas vezes.
    if watch:
        text = jsonc.remove_member(text, RUN_ON_SAVE_KEY)

    return text


def render_extensions(watch: bool) -> str:
    text = _asset("extensions.json")
    if watch:
        text = _remove_recommendation(text, RUN_ON_SAVE_EXT)
    return text


def render_tasks(engine: str) -> str:
    text = _asset("tasks.json")

    if engine == "tectonic":
        task = jsonc.find(_root_object(text), "tasks").value.elements[0].value
        args = jsonc.find(task, "args").value
        indent = jsonc.indent_of(text, args.elements[-1].start)
        text = jsonc.insert_last(text, args, f'{indent}"--engine",\n{indent}"tectonic"')

    return text


# ----------------------------------------------------------------------
# Merge com arquivos que já existem: só as partes do TexFlow mudam
# ----------------------------------------------------------------------


def merge_settings(current: str, generated: str, watch: bool) -> str:
    _root_object(current)
    gen_root = _root_object(generated)

    for n, el in enumerate(gen_root.elements):
        if not _is_managed(el.key):
            continue
        value = generated[el.value.start : el.value.end]
        current = jsonc.set_member(
            current, el.key, value, doc=jsonc.leading(generated, gen_root, n)
        )

    if watch:
        current = jsonc.remove_member(current, RUN_ON_SAVE_KEY)

    return current


def merge_extensions(current: str, generated: str, watch: bool) -> str:
    wanted = jsonc.loads(generated)["recommendations"]

    recs = jsonc.find(_root_object(current), "recommendations")
    if recs is None or recs.value.kind != "array":
        gen_recs = jsonc.find(_root_object(generated), "recommendations")
        return jsonc.set_member(
            current,
            "recommendations",
            generated[gen_recs.value.start : gen_recs.value.end],
        )

    present = {_scalar(current, item.value) for item in recs.value.elements}
    for ext in wanted:
        if ext in present:
            continue
        recs = jsonc.find(_root_object(current), "recommendations")
        items = recs.value.elements
        indent = jsonc.indent_of(current, items[-1].start) if items else "        "
        current = jsonc.insert_last(current, recs.value, f"{indent}{json.dumps(ext)}")

    if watch:
        current = _remove_recommendation(current, RUN_ON_SAVE_EXT)

    return current


def merge_tasks(current: str, generated: str, _watch: bool) -> str:
    gen_tasks = jsonc.find(_root_object(generated), "tasks").value
    gen_task = gen_tasks.elements[0]
    task_value = generated[gen_task.value.start : gen_task.value.end]
    task_block = jsonc.indent_of(generated, gen_task.start) + task_value

    tasks = jsonc.find(_root_object(current), "tasks")
    if tasks is None or tasks.value.kind != "array":
        return jsonc.set_member(
            current, "tasks", generated[gen_tasks.start : gen_tasks.end]
        )

    for el in tasks.value.elements:
        if el.value.kind != "object":
            continue
        label = jsonc.find(el.value, "label")
        if label is not None and _scalar(current, label.value) == WATCH_TASK:
            return jsonc.replace_value(current, el, task_value)

    return jsonc.insert_last(current, tasks.value, task_block)


# ----------------------------------------------------------------------


Merge = Callable[[str, str, bool], str]


def _write(
    dst: Path, generated: str, merge: Merge, watch: bool, auto_yes: bool
) -> None:
    if not dst.exists():
        dst.write_text(generated, encoding="utf-8")
        print(f"Criado: {dst}", file=sys.stderr)
        return

    current = dst.read_text(encoding="utf-8")
    try:
        merged = merge(current, generated, watch)
    except ValueError:  # JSONCError e json.JSONDecodeError
        # Não deu pra ler como JSONC: sem como mesclar com segurança, cai
        # no comportamento antigo (sobrescrever, com confirmação).
        if not confirm(
            f"{dst} já existe (e não é um JSONC válido). Sobrescrever?", auto_yes
        ):
            print(f"Mantido: {dst}", file=sys.stderr)
            return
        dst.write_text(generated, encoding="utf-8")
        print(f"Sobrescrito: {dst}", file=sys.stderr)
        return

    if merged == current:
        print(f"Já atualizado: {dst}", file=sys.stderr)
        return

    if not confirm(
        f"{dst} já existe. Atualizar só a configuração do TexFlow, mantendo o resto?",
        auto_yes,
    ):
        print(f"Mantido: {dst}", file=sys.stderr)
        return

    dst.write_text(merged, encoding="utf-8")
    print(f"Atualizado: {dst}", file=sys.stderr)


def run_init(auto_yes: bool, engine: str = "latexmk", watch: bool = False) -> None:
    """Cria .vscode/settings.json e .vscode/extensions.json no diretório
    atual, com a receita do LaTeX Workshop já configurada pro TexFlow, e
    também .vscode/tasks.json (task "TexFlow Watch") se watch=True.

    Se os arquivos já existirem, só as chaves do TexFlow são atualizadas
    (latex-workshop.* e emeraldwalk.runonsave no settings.json, as
    recomendações no extensions.json, a task "TexFlow Watch" no
    tasks.json), preservando o resto e os comentários."""

    target_dir = Path.cwd() / ".vscode"
    target_dir.mkdir(parents=True, exist_ok=True)

    files: list[tuple[str, str, Merge]] = [
        ("settings.json", render_settings(engine, watch), merge_settings),
        ("extensions.json", render_extensions(watch), merge_extensions),
    ]
    if watch:
        files.append(("tasks.json", render_tasks(engine), merge_tasks))

    for name, generated, merge in files:
        _write(target_dir / name, generated, merge, watch, auto_yes)

    if watch:
        print(
            "Pronto! Abra a pasta no VS Code: ele vai sugerir instalar a "
            'extensão LaTeX Workshop e iniciar a task "TexFlow Watch" '
            "(permita as tasks automáticas quando ele perguntar).",
            file=sys.stderr,
        )
    else:
        print(
            "Pronto! Abra a pasta no VS Code — ele vai sugerir instalar a "
            "extensão LaTeX Workshop automaticamente.",
            file=sys.stderr,
        )
