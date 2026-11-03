import json

import pytest

from scripts import perf
from scripts.perf import (
    Config,
    Result,
    copy_template,
    find_cite_key,
    format_table,
    insert_before_end_document,
    load_baseline,
    parse_args,
)


def test_insert_before_last_end_document(tmp_path):
    main = tmp_path / "main.tex"
    main.write_text("\\begin{document}\n% \\end{document} num comentário\nA\n\\end{document}\n")
    insert_before_end_document(main, "B")
    assert main.read_text().endswith("A\nB\n\\end{document}\n")


def test_insert_without_end_document_fails(tmp_path):
    main = tmp_path / "main.tex"
    main.write_text("nada")
    with pytest.raises(ValueError):
        insert_before_end_document(main, "B")


def test_copy_template_skips_what_texflow_ignores(tmp_path):
    src = tmp_path / "proj"
    for d in ("src", "build", "node_modules", ".venv", "simulation"):
        (src / d).mkdir(parents=True)
        (src / d / "f").write_text("x")
    (src / "main.tex").write_text("x")
    (src / "old.pdf").write_text("x")
    (src / ".texflowignore").write_text("simulation\n*.pdf\n")

    copy_template(src, tmp_path / "copy")

    assert {p.name for p in (tmp_path / "copy").iterdir()} == {"src", "main.tex", ".texflowignore"}


def test_find_cite_key_ignores_build(tmp_path):
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "a.bib").write_text("@book{fromBuild,\n}")
    (tmp_path / "refs.bib").write_text("% c\n@article{ Real2024 ,\n title={x}}")
    assert find_cite_key(tmp_path) == "Real2024"
    assert find_cite_key(tmp_path / "build" / "nada") is None


def test_config_flags_and_env(monkeypatch):
    monkeypatch.setenv("TEXFLOW_FAST", "1")
    monkeypatch.setenv("TEXFLOW_ENGINE", "latexmk")
    c = Config("x", "tectonic", fast=True, cache=False)
    assert c.flags() == ["--engine", "tectonic", "--fast"]
    env = c.env()
    assert env["TEXFLOW_NO_CACHE"] == "1"
    assert "TEXFLOW_FAST" not in env and "TEXFLOW_ENGINE" not in env


def test_table_and_baseline_roundtrip(tmp_path):
    results = [
        Result("tectonic", "text", [10.0, 9.0, 11.0], biber_runs=0),
        Result("latexmk", "cite", [], ok=False, note="build inicial falhou"),
        Result("latexmk", "draft", [], note="pulado: sem capítulos pra --only"),
    ]
    path = tmp_path / "base.json"
    path.write_text(json.dumps({"results": [r.to_dict() for r in results]}))
    baseline = load_baseline(path)
    assert baseline == {("tectonic", "text"): 10.0}

    faster = [Result("tectonic", "text", [8.0], biber_runs=0)]
    table = format_table(faster, baseline)
    assert "-2.00s (-20%)" in table
    assert "0/1 rodou" in table
    table = format_table(results)
    assert "FALHOU build inicial falhou" in table
    assert "pulado: sem capítulos" in table


def test_parse_args_rejects_unknown_names():
    with pytest.raises(SystemExit):
        parse_args(["-c", "tectonic,nope"])
    args = parse_args(["-c", "tectonic-fast", "-s", "text,watch"])
    assert args.configs == ["tectonic-fast"] and args.scenarios == ["text", "watch"]


def test_default_template_exists():
    assert (perf.DEFAULT_TEMPLATE / "main.tex").is_file()
