import json
import re
import sys

from scripts import jsonc
from scripts.init import VSCODE_ASSETS, run_init
from scripts.watcher import BUILD_FAILED, BUILD_OK, BUILD_STARTED


def _strip_jsonc_comments(text: str) -> str:
    return re.sub(r"//.*", "", text)


def test_run_init_creates_vscode_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    run_init(auto_yes=True)

    settings = tmp_path / ".vscode" / "settings.json"
    extensions = tmp_path / ".vscode" / "extensions.json"
    assert settings.exists()
    assert extensions.exists()


def test_run_init_writes_valid_jsonc(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    run_init(auto_yes=True)

    for name in ("settings.json", "extensions.json"):
        content = (tmp_path / ".vscode" / name).read_text(encoding="utf-8")
        json.loads(_strip_jsonc_comments(content))  # não deve lançar


def test_run_init_settings_matches_packaged_asset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    run_init(auto_yes=True)

    written = (tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8")
    packaged = VSCODE_ASSETS.joinpath("settings.json").read_text(encoding="utf-8")
    assert written == packaged


def test_run_init_recommends_latex_workshop_extension(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    run_init(auto_yes=True)

    content = (tmp_path / ".vscode" / "extensions.json").read_text(encoding="utf-8")
    data = json.loads(_strip_jsonc_comments(content))
    assert "James-Yu.latex-workshop" in data["recommendations"]


def test_run_init_recommends_run_on_save_extension(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    run_init(auto_yes=True)

    content = (tmp_path / ".vscode" / "extensions.json").read_text(encoding="utf-8")
    data = json.loads(_strip_jsonc_comments(content))
    assert "pucelle.run-on-save" in data["recommendations"]
    assert "emeraldwalk.RunOnSave" not in data["recommendations"]


def test_run_init_settings_configure_rebuild_on_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    run_init(auto_yes=True)

    content = (tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8")
    data = json.loads(_strip_jsonc_comments(content))

    # Run on Save rebuilda qualquer .tex (e JSON/.sty/.cls/.bib) chamando "texflow --build"...
    commands = data["runOnSave.commands"]
    assert any(
        c["match"] == r"\.(tex|json|sty|cls|bib)$"
        and "texflow" in c["command"]
        and "--build" in c["command"]
        and c["runIn"] == "backend"
        for c in commands
    )
    assert "emeraldwalk.runonsave" not in data
    # ...e o build-on-save nativo do LaTeX Workshop fica desligado pra não
    # duplicar (ele não enxergaria os includes Jinja de qualquer forma).
    assert data["latex-workshop.latex.autoBuild.run"] == "never"


def test_run_init_does_not_overwrite_without_confirmation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vscode_dir = tmp_path / ".vscode"
    vscode_dir.mkdir()
    (vscode_dir / "settings.json").write_text("conteúdo customizado do usuário", encoding="utf-8")

    monkeypatch.setattr("scripts.init.confirm", lambda *_args, **_kwargs: False)
    run_init(auto_yes=False)

    assert (vscode_dir / "settings.json").read_text(encoding="utf-8") == "conteúdo customizado do usuário"


def test_run_init_overwrites_when_auto_yes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vscode_dir = tmp_path / ".vscode"
    vscode_dir.mkdir()
    (vscode_dir / "settings.json").write_text("conteúdo antigo", encoding="utf-8")

    run_init(auto_yes=True)

    content = (vscode_dir / "settings.json").read_text(encoding="utf-8")
    assert content != "conteúdo antigo"
    assert "latex-workshop.latex.recipes" in content


# ----------------------------------------------------------------------
# --engine tectonic / --watch
# ----------------------------------------------------------------------


def _read(tmp_path, name):
    return jsonc.loads((tmp_path / ".vscode" / name).read_text(encoding="utf-8"))


def test_settings_offer_both_recipes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(auto_yes=True)

    data = _read(tmp_path, "settings.json")
    recipes = {r["name"]: r["tools"] for r in data["latex-workshop.latex.recipes"]}
    assert recipes["TexFlow Build"] == ["texflow"]
    assert recipes["TexFlow Build (Tectonic)"] == ["texflow-tectonic"]
    tools = {t["name"]: t for t in data["latex-workshop.latex.tools"]}
    assert tools["texflow-tectonic"]["args"][:4] == ["--build", "--engine", "tectonic", "--fast"]
    assert "--fast" not in tools["texflow"]["args"]
    assert "--engine" not in tools["texflow"]["args"]
    assert data["latex-workshop.latex.recipe.default"] == "TexFlow Build"


def test_run_on_save_matches_json_and_style_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(auto_yes=True)

    (command,) = _read(tmp_path, "settings.json")["runOnSave.commands"]
    match, not_match = command["match"], command["notMatch"]

    def runs(path):
        return bool(re.search(match, path)) and not re.search(not_match, path)

    for name in ("main.tex", "input.json", "style.sty", "doc.cls", "refs.bib"):
        assert runs(f"/proj/{name}"), name
    assert runs("/proj/src/intro.tex")
    assert runs(r"C:\proj\src\intro.tex")
    assert not runs("/proj/build/main.pdf")
    assert not runs("/proj/build/main.tex")
    assert not runs(r"C:\proj\build\main.tex")


def test_init_tectonic_sets_default_recipe_and_run_on_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(auto_yes=True, engine="tectonic")

    data = _read(tmp_path, "settings.json")
    assert data["latex-workshop.latex.recipe.default"] == "TexFlow Build (Tectonic)"
    cmd = data["runOnSave.commands"][0]["command"]
    assert cmd == "texflow --build --engine tectonic --fast --input input.json --template ."
    assert not (tmp_path / ".vscode" / "tasks.json").exists()


def test_init_watch_writes_task_instead_of_run_on_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(auto_yes=True, watch=True)

    settings = _read(tmp_path, "settings.json")
    assert "runOnSave.commands" not in settings
    assert settings["latex-workshop.latex.recipe.default"] == "TexFlow Build"

    recs = _read(tmp_path, "extensions.json")["recommendations"]
    assert recs == ["James-Yu.latex-workshop"]

    (task,) = _read(tmp_path, "tasks.json")["tasks"]
    assert task["label"] == "TexFlow Watch"
    assert task["command"] == "texflow"
    assert task["args"] == ["--build", "--watch", "--input", "input.json", "--template", "."]
    assert task["isBackground"] is True
    assert task["runOptions"]["runOn"] == "folderOpen"


def test_init_watch_tectonic_task_uses_engine(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(auto_yes=True, engine="tectonic", watch=True)

    (task,) = _read(tmp_path, "tasks.json")["tasks"]
    assert task["args"][-3:] == ["--engine", "tectonic", "--fast"]
    assert _read(tmp_path, "settings.json")["latex-workshop.latex.recipe.default"] == "TexFlow Build (Tectonic)"


def test_watch_task_problem_matcher_parses_texflow_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(auto_yes=True, watch=True)

    matcher = _read(tmp_path, "tasks.json")["tasks"][0]["problemMatcher"]
    m = re.match(matcher["pattern"]["regexp"], " • main.tex:12: Undefined control sequence.")
    assert m.group(1, 2, 3) == ("main.tex", "12", "Undefined control sequence.")
    assert re.match(matcher["pattern"]["regexp"], " • ./style.sty:3: Missing $ inserted").group(1) == "style.sty"
    assert not re.match(matcher["pattern"]["regexp"], " • silva2020, souza2021")

    bg = matcher["background"]
    assert re.match(bg["beginsPattern"], BUILD_STARTED)
    assert re.match(bg["endsPattern"], BUILD_OK)
    assert re.match(bg["endsPattern"], BUILD_FAILED)


def test_cli_init_passes_engine_and_watch(monkeypatch):
    from scripts import cli

    calls = []
    monkeypatch.setattr(cli, "run_init", lambda *args: calls.append(args))
    monkeypatch.delenv("TEXFLOW_ENGINE", raising=False)
    monkeypatch.setattr(sys, "argv", ["texflow", "--init", "--engine", "tectonic", "--watch", "-y"])
    cli.cli()
    assert calls == [(True, "tectonic", True)]


# ----------------------------------------------------------------------
# Merge com arquivos existentes
# ----------------------------------------------------------------------

USER_SETTINGS = """{
    // tema do usuário
    "editor.fontSize": 15, // grande
    "latex-workshop.latex.recipe.default": "Minha receita",
    /* exclusões */
    "files.exclude": {"**/build": true},
}
"""


def _write_vscode(tmp_path, name, content):
    vscode_dir = tmp_path / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    (vscode_dir / name).write_text(content, encoding="utf-8")


def test_merge_keeps_user_keys_and_comments(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_vscode(tmp_path, "settings.json", USER_SETTINGS)

    run_init(auto_yes=True, engine="tectonic")

    text = (tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8")
    assert "// tema do usuário" in text and "// grande" in text and "/* exclusões */" in text
    data = jsonc.loads(text)
    assert data["editor.fontSize"] == 15
    assert data["files.exclude"] == {"**/build": True}
    assert data["latex-workshop.latex.recipe.default"] == "TexFlow Build (Tectonic)"
    assert "latex-workshop.latex.recipes" in data
    assert "runOnSave.commands" in data


def test_merge_is_idempotent(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_vscode(tmp_path, "settings.json", USER_SETTINGS)

    run_init(auto_yes=True)
    first = (tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8")
    capsys.readouterr()
    run_init(auto_yes=True)

    assert (tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8") == first
    assert "Já atualizado" in capsys.readouterr().err


def test_merge_with_watch_removes_run_on_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_init(auto_yes=True)
    run_init(auto_yes=True, watch=True)

    assert "runOnSave.commands" not in _read(tmp_path, "settings.json")
    assert "pucelle.run-on-save" not in _read(tmp_path, "extensions.json")["recommendations"]


def test_merge_replaces_legacy_emeraldwalk_run_on_save(tmp_path, monkeypatch):
    """Projetos gerados até a 0.2.1 usavam o emeraldwalk.RunOnSave: o merge
    troca pela configuração do pucelle.run-on-save (manter as duas faria cada
    save compilar duas vezes) e preserva o resto."""
    monkeypatch.chdir(tmp_path)
    _write_vscode(
        tmp_path,
        "settings.json",
        '{\n    "editor.fontSize": 15,\n    "emeraldwalk.runonsave": {\n'
        '        "commands": [{"match": "\\\\.tex$", "cmd": "texflow --build"}]\n    }\n}\n',
    )
    _write_vscode(
        tmp_path,
        "extensions.json",
        '{\n    "recommendations": ["James-Yu.latex-workshop", "emeraldwalk.RunOnSave"]\n}\n',
    )

    run_init(auto_yes=True)

    settings = _read(tmp_path, "settings.json")
    assert "emeraldwalk.runonsave" not in settings
    assert settings["runOnSave.commands"][0]["command"].startswith("texflow --build")
    assert settings["editor.fontSize"] == 15
    assert _read(tmp_path, "extensions.json")["recommendations"] == [
        "James-Yu.latex-workshop",
        "pucelle.run-on-save",
    ]


def test_merge_extensions_keeps_user_recommendations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_vscode(tmp_path, "extensions.json", '{\n    "recommendations": ["ms-python.python"]\n}\n')

    run_init(auto_yes=True)

    assert _read(tmp_path, "extensions.json")["recommendations"] == [
        "ms-python.python",
        "James-Yu.latex-workshop",
        "pucelle.run-on-save",
    ]


def test_merge_tasks_keeps_user_tasks_and_replaces_ours(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_vscode(
        tmp_path,
        "tasks.json",
        '{\n    "version": "2.0.0",\n    "tasks": [\n        // minha\n        {"label": "lint", "command": "make"}\n    ]\n}\n',
    )

    run_init(auto_yes=True, engine="tectonic", watch=True)
    run_init(auto_yes=True, watch=True)

    text = (tmp_path / ".vscode" / "tasks.json").read_text(encoding="utf-8")
    assert "// minha" in text
    tasks = jsonc.loads(text)["tasks"]
    assert [t["label"] for t in tasks] == ["lint", "TexFlow Watch"]
    assert "--engine" not in tasks[1]["args"]


def test_merge_declined_keeps_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_vscode(tmp_path, "settings.json", USER_SETTINGS)
    monkeypatch.setattr("scripts.init.confirm", lambda *_args, **_kwargs: False)

    run_init(auto_yes=False)

    assert (tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8") == USER_SETTINGS
