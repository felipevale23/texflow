import json
import re

from scripts.init import VSCODE_ASSETS, run_init


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
