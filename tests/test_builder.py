import importlib.resources as res
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import builder
from scripts.builder import (
    ENGINES,
    latexmk_build_process,
    resolve_engine,
    resolve_tectonic,
    summarize_latex_log,
    tectonic_build_process,
)

_HAS_LATEX = shutil.which("latexmk") is not None and shutil.which("xelatex") is not None


@pytest.mark.skipif(not _HAS_LATEX, reason="latexmk/xelatex não disponíveis neste ambiente")
def test_repeat_build_is_cached_symlinked_and_ansi_free(tmp_path):
    """Simula o cenário do LaTeX Workshop: processo Python novo por build,
    stdout/stderr não-TTY (pipe), e um segundo save sem mudanças reais."""

    template_src = res.files("assets").joinpath("templates", "journal")
    template_dir = tmp_path / "journal"
    shutil.copytree(str(template_src), template_dir)
    data_path = template_dir / "input.json"

    script = (
        "import json, sys, time\n"
        "from scripts.builder import build\n"
        "t0 = time.perf_counter()\n"
        f"build({str(data_path)!r}, {str(template_dir)!r})\n"
        "print(json.dumps({'elapsed': time.perf_counter() - t0}))\n"
    )

    def run_build():
        # subprocess.PIPE não é TTY: reproduz exatamente o que o VS Code
        # LaTeX Workshop vê ao rodar a recipe a cada Ctrl+S.
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
        )
        return proc

    first = run_build()
    second = run_build()

    combined_output = first.stdout + first.stderr + second.stdout + second.stderr
    assert "\x1b" not in combined_output, "saída não-TTY não deve conter sequências ANSI"

    first_elapsed = json.loads(first.stdout.strip().splitlines()[-1])["elapsed"]
    second_elapsed = json.loads(second.stdout.strip().splitlines()[-1])["elapsed"]
    assert second_elapsed < first_elapsed / 2, (
        f"segundo build ({second_elapsed:.2f}s) deveria ser bem mais rápido "
        f"que o primeiro ({first_elapsed:.2f}s) graças ao cache"
    )

    build_dir = template_dir / "build"
    assert (build_dir / "main.log").exists()
    images_links = list((build_dir / "images").iterdir())
    plots_links = list((build_dir / "plots").iterdir())
    assert images_links and all(p.is_symlink() for p in images_links)
    assert plots_links and all(p.is_symlink() for p in plots_links)


def test_no_error_indication():
    assert summarize_latex_log("tudo certo, nada a reportar") == (
        "Nenhuma indicação clara de erro encontrada no stdout."
    )


def test_latex_error_with_line_number():
    stdout = (
        "! Undefined control sequence.\n"
        "l.12 \\foobar\n"
        "     {texto}\n"
    )
    result = summarize_latex_log(stdout)
    assert "Erros LaTeX (primeiros):" in result
    assert "linha 12" in result
    assert "Undefined control sequence." in result


def test_unresolved_placeholders():
    stdout = "algum texto << minha.variavel >> e depois << outra >>"
    result = summarize_latex_log(stdout)
    assert "Placeholders não resolvidos:" in result
    assert "minha.variavel" in result
    assert "outra" in result


def test_missing_character():
    stdout = "Missing character: There is no ⚡ in font TeXGyreTermes-Regular!"
    result = summarize_latex_log(stdout)
    assert "Caracteres faltando" in result
    assert "TeXGyreTermes-Regular" in result


def test_undefined_citation():
    stdout = "LaTeX Warning: Citation 'silva2020' on page 3 undefined on input line 42."
    result = summarize_latex_log(stdout)
    assert "Citações não encontradas" in result
    assert "silva2020" in result


def test_undefined_reference():
    stdout = "LaTeX Warning: Reference `fig:one' on page 1 undefined on input line 7."
    result = summarize_latex_log(stdout)
    assert "Referências não resolvidas" in result
    assert "fig:one" in result


def test_missing_bibliography_file():
    stdout = "No file main.bbl."
    result = summarize_latex_log(stdout)
    assert "bibliografia ausente" in result
    assert "main.bbl" in result


def test_empty_bibliography_warning():
    stdout = "LaTeX Warning: Empty bibliography on input line 3."
    result = summarize_latex_log(stdout)
    assert "Bibliografia vazia." in result


def test_biber_rerun_hint():
    stdout = "Please (re)run Biber on the file: main"
    result = summarize_latex_log(stdout)
    assert "biber output" in result


def test_overfull_hbox_warning():
    stdout = "Overfull \\hbox (12.0pt too wide) in paragraph at lines 10--11\n"
    result = summarize_latex_log(stdout)
    assert "Overfull" in result
    assert "1 ocorrência" in result


def test_output_written_success_message():
    stdout = "Output written on main.pdf (3 pages)."
    result = summarize_latex_log(stdout)
    assert "PDF gerado: main.pdf (3 páginas)." in result


def test_stderr_is_included_in_analysis():
    result = summarize_latex_log("", stderr="! Emergency stop.\n")
    assert "Emergency stop." in result


# ----------------------------------------------------------------------
# Engines: seleção, resolução do binário do Tectonic e comando montado
# ----------------------------------------------------------------------


def test_engine_default_is_latexmk(monkeypatch):
    monkeypatch.delenv("TEXFLOW_ENGINE", raising=False)
    assert resolve_engine(None) == "latexmk"


def test_engine_from_env(monkeypatch):
    monkeypatch.setenv("TEXFLOW_ENGINE", "tectonic")
    assert resolve_engine(None) == "tectonic"


def test_engine_flag_wins_over_env(monkeypatch):
    monkeypatch.setenv("TEXFLOW_ENGINE", "tectonic")
    assert resolve_engine("latexmk") == "latexmk"


def test_engine_invalid_is_rejected(monkeypatch):
    monkeypatch.setenv("TEXFLOW_ENGINE", "pdflatex")
    with pytest.raises(ValueError, match="pdflatex"):
        resolve_engine(None)


def test_engines_map_to_build_functions():
    assert ENGINES == {"latexmk": latexmk_build_process, "tectonic": tectonic_build_process}


def _run_cli(monkeypatch, argv, env_engine=None):
    from scripts import cli

    calls = []
    monkeypatch.setattr(cli, "build", lambda *args: calls.append(args))
    monkeypatch.setattr(sys, "argv", ["texflow", *argv])
    if env_engine:
        monkeypatch.setenv("TEXFLOW_ENGINE", env_engine)
    else:
        monkeypatch.delenv("TEXFLOW_ENGINE", raising=False)
    cli.cli()
    return calls


def test_cli_passes_engine_flag_to_build(monkeypatch):
    calls = _run_cli(monkeypatch, ["--build", "--input", "x.json", "--template", "t", "--engine", "tectonic"])
    assert calls == [("x.json", "t", "tectonic")]


def test_cli_uses_env_engine_without_flag(monkeypatch):
    calls = _run_cli(monkeypatch, ["--build", "--input", "x.json", "--template", "t"], env_engine="tectonic")
    assert calls == [("x.json", "t", "tectonic")]


def test_cli_flag_overrides_env_engine(monkeypatch):
    calls = _run_cli(
        monkeypatch,
        ["--build", "--input", "x.json", "--template", "t", "--engine", "latexmk"],
        env_engine="tectonic",
    )
    assert calls == [("x.json", "t", "latexmk")]


def _fake_exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def no_tectonic(monkeypatch, tmp_path):
    """Ambiente sem nenhum Tectonic: sem env, sem _MEIPASS, sem PATH."""
    monkeypatch.delenv("TEXFLOW_TECTONIC", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pybin" / "python"))
    monkeypatch.setattr(builder.shutil, "which", lambda _name: None)
    return tmp_path


def test_tectonic_env_var_has_priority(no_tectonic, monkeypatch):
    explicit = _fake_exe(no_tectonic / "custom" / "tectonic")
    _fake_exe(no_tectonic / "pybin" / "tectonic")
    monkeypatch.setattr(builder.shutil, "which", lambda _name: "/usr/bin/tectonic")
    monkeypatch.setenv("TEXFLOW_TECTONIC", str(explicit))
    assert resolve_tectonic() == str(explicit)


def test_tectonic_env_var_pointing_nowhere_is_an_error(no_tectonic, monkeypatch):
    monkeypatch.setattr(builder.shutil, "which", lambda _name: "/usr/bin/tectonic")
    monkeypatch.setenv("TEXFLOW_TECTONIC", str(no_tectonic / "nope"))
    with pytest.raises(FileNotFoundError, match="TEXFLOW_TECTONIC"):
        resolve_tectonic()


def test_tectonic_bundled_in_meipass(no_tectonic, monkeypatch):
    bundled = _fake_exe(no_tectonic / "meipass" / "tectonic")
    _fake_exe(no_tectonic / "pybin" / "tectonic")
    monkeypatch.setattr(sys, "_MEIPASS", str(no_tectonic / "meipass"), raising=False)
    monkeypatch.setattr(builder.shutil, "which", lambda _name: "/usr/bin/tectonic")
    assert resolve_tectonic() == str(bundled)


def test_tectonic_next_to_executable(no_tectonic, monkeypatch):
    beside = _fake_exe(no_tectonic / "pybin" / "tectonic")
    monkeypatch.setattr(builder.shutil, "which", lambda _name: "/usr/bin/tectonic")
    assert resolve_tectonic() == str(beside)


def test_tectonic_on_path(no_tectonic, monkeypatch):
    monkeypatch.setattr(builder.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert resolve_tectonic() == "/usr/bin/tectonic"


def test_tectonic_not_found_has_clear_error(no_tectonic):
    with pytest.raises(FileNotFoundError, match="--engine latexmk"):
        resolve_tectonic()


@pytest.fixture
def captured_cmd(monkeypatch):
    calls = []
    monkeypatch.setattr(
        builder, "run_latex_command", lambda emoji, cmd, cwd=None, env=None: calls.append((cmd, cwd, env))
    )
    monkeypatch.delenv("TEXFLOW_DEBUG", raising=False)
    monkeypatch.delenv("TEXFLOW_FAST", raising=False)
    monkeypatch.delenv("TEXFLOW_BIBER", raising=False)
    # Cache do biber desligado aqui; ele tem os próprios testes abaixo.
    monkeypatch.setenv("TEXFLOW_NO_CACHE", "1")
    # Sem biber 2.17 "instalado", independente da máquina que roda os testes.
    monkeypatch.setattr(builder, "DEFAULT_TECTONIC_BIBER", Path("/nonexistent/biber"))
    return calls


def test_latexmk_command(captured_cmd, tmp_path):
    latexmk_build_process(tmp_path)
    cmd, cwd, env = captured_cmd[0]
    assert cmd[0] == "latexmk"
    assert cmd[-1] == "main.tex"
    assert "-synctex=1" in cmd and "-file-line-error" in cmd and "-quiet" in cmd
    assert cwd == str(tmp_path)
    assert env["TEXINPUTS"].startswith(str(tmp_path))


def test_latexmk_command_debug(captured_cmd, tmp_path, monkeypatch):
    monkeypatch.setenv("TEXFLOW_DEBUG", "1")
    latexmk_build_process(tmp_path)
    cmd = captured_cmd[0][0]
    assert "-verbose" in cmd and "-quiet" not in cmd


def test_tectonic_command(captured_cmd, tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "resolve_tectonic", lambda: "/opt/tectonic")
    tectonic_build_process(tmp_path)
    cmd, cwd, env = captured_cmd[0]
    assert cmd == [
        "/opt/tectonic", "-X", "compile", "main.tex",
        "--synctex", "--keep-logs", "--keep-intermediates", "--outdir", ".",
    ]  # fmt: skip
    assert cwd == str(tmp_path)
    assert env["TEXINPUTS"].startswith(str(tmp_path))


def test_tectonic_command_debug_prints(captured_cmd, tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "resolve_tectonic", lambda: "/opt/tectonic")
    monkeypatch.setenv("TEXFLOW_DEBUG", "1")
    tectonic_build_process(tmp_path)
    assert captured_cmd[0][0][-1] == "--print"


def _build_dir_with(tmp_path, *names):
    for name in names:
        (tmp_path / name).write_text("x")
    return tmp_path


def test_tectonic_fast_runs_single_pass_when_intermediates_exist(captured_cmd, tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "resolve_tectonic", lambda: "/opt/tectonic")
    monkeypatch.setenv("TEXFLOW_FAST", "1")
    tectonic_build_process(_build_dir_with(tmp_path, "main.aux", "main.bcf", "main.bbl"))
    assert captured_cmd[0][0][-1] == "--reruns=0"


def test_tectonic_fast_without_biblatex_needs_only_aux(captured_cmd, tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "resolve_tectonic", lambda: "/opt/tectonic")
    monkeypatch.setenv("TEXFLOW_FAST", "1")
    tectonic_build_process(_build_dir_with(tmp_path, "main.aux"))
    assert "--reruns=0" in captured_cmd[0][0]


@pytest.mark.parametrize(
    "files",
    [(), ("main.bbl",), ("main.aux", "main.bcf")],
    ids=["clean-build-dir", "no-aux", "biblatex-without-bbl"],
)
def test_tectonic_fast_falls_back_to_full_build(captured_cmd, tmp_path, monkeypatch, files):
    monkeypatch.setattr(builder, "resolve_tectonic", lambda: "/opt/tectonic")
    monkeypatch.setenv("TEXFLOW_FAST", "1")
    tectonic_build_process(_build_dir_with(tmp_path, *files))
    assert "--reruns=0" not in captured_cmd[0][0]


def test_tectonic_without_fast_ignores_intermediates(captured_cmd, tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "resolve_tectonic", lambda: "/opt/tectonic")
    tectonic_build_process(_build_dir_with(tmp_path, "main.aux", "main.bcf", "main.bbl"))
    assert "--reruns=0" not in captured_cmd[0][0]


def test_tectonic_puts_default_biber_first_on_path(captured_cmd, tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "resolve_tectonic", lambda: "/opt/tectonic")
    biber = _fake_exe(tmp_path / "opt" / "biber-2.17" / "bin" / "biber")
    monkeypatch.setattr(builder, "DEFAULT_TECTONIC_BIBER", biber)
    tectonic_build_process(tmp_path)
    env = captured_cmd[0][2]
    assert env["PATH"].split(os.pathsep)[0] == str(biber.parent)


@pytest.mark.parametrize("as_dir", [False, True], ids=["binary", "directory"])
def test_tectonic_biber_env_var_wins(captured_cmd, tmp_path, monkeypatch, as_dir):
    monkeypatch.setattr(builder, "resolve_tectonic", lambda: "/opt/tectonic")
    monkeypatch.setattr(builder, "DEFAULT_TECTONIC_BIBER", _fake_exe(tmp_path / "default" / "biber"))
    custom = _fake_exe(tmp_path / "custom" / "biber")
    monkeypatch.setenv("TEXFLOW_BIBER", str(custom.parent if as_dir else custom))
    tectonic_build_process(tmp_path)
    assert captured_cmd[0][2]["PATH"].split(os.pathsep)[0] == str(custom.parent)


def test_tectonic_biber_env_var_pointing_nowhere_is_an_error(captured_cmd, tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "resolve_tectonic", lambda: "/opt/tectonic")
    monkeypatch.setenv("TEXFLOW_BIBER", str(tmp_path / "nope"))
    with pytest.raises(FileNotFoundError, match="TEXFLOW_BIBER"):
        tectonic_build_process(tmp_path)


def test_tectonic_without_compatible_biber_keeps_path(captured_cmd, tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "resolve_tectonic", lambda: "/opt/tectonic")
    monkeypatch.setenv("PATH", "/usr/bin")
    tectonic_build_process(tmp_path)
    assert captured_cmd[0][2]["PATH"] == "/usr/bin"


@pytest.mark.skipif(os.name == "nt", reason="o shim do cache é um script sh")
def test_tectonic_puts_biber_cache_shim_first(captured_cmd, tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "resolve_tectonic", lambda: "/opt/tectonic")
    biber = _fake_exe(tmp_path / "opt" / "bin" / "biber")
    monkeypatch.setattr(builder, "DEFAULT_TECTONIC_BIBER", biber)
    monkeypatch.delenv("TEXFLOW_NO_CACHE")
    build_dir = tmp_path / "build"
    build_dir.mkdir()

    tectonic_build_process(build_dir)

    path = captured_cmd[0][2]["PATH"].split(os.pathsep)
    shim = build_dir / ".texflow-cache" / "bin" / "biber"
    assert path[:2] == [str(shim.parent), str(biber.parent)]
    assert str(biber) in shim.read_text()
    assert os.access(shim, os.X_OK)


def test_cli_fast_flag_sets_env(monkeypatch):
    # setenv (e não delenv) pro monkeypatch restaurar a env depois: a CLI
    # escreve direto em os.environ.
    monkeypatch.setenv("TEXFLOW_FAST", "0")
    _run_cli(monkeypatch, ["--build", "--input", "x.json", "--template", "t", "--fast"])
    assert os.environ["TEXFLOW_FAST"] == "1"


# ----------------------------------------------------------------------
# Resumo de erros: formatos do Tectonic e do -file-line-error
# ----------------------------------------------------------------------


def test_tectonic_file_line_error_on_stderr():
    stderr = (
        "warning: main.tex:38: Requested font \"lasy9\" at 9.0pt\n"
        "error: main.tex:5: Undefined control sequence\n"
        "error: the XeTeX engine had an unrecoverable error\n"
    )
    result = summarize_latex_log("note: Running TeX ...", stderr)
    assert " • main.tex:5: Undefined control sequence" in result
    assert "main.tex:38" not in result  # warnings ficam de fora
    assert "the XeTeX engine had an unrecoverable error" in result


def test_file_line_error_from_latexmk_log_strips_dot_slash():
    log = "./main.tex:12: Undefined control sequence.\nl.12 \\foobar\n"
    result = summarize_latex_log(log)
    assert " • main.tex:12: Undefined control sequence." in result
    assert "linha 12" not in result  # o "! ..." equivalente não duplica


def test_bang_error_deduplicated_against_file_line_error():
    stdout = "! Undefined control sequence.\nl.5 \\foobar\n"
    stderr = "error: main.tex:5: Undefined control sequence\n"
    result = summarize_latex_log(stdout, stderr)
    assert result.count("Undefined control sequence") == 1


def test_citation_with_backtick_quote():
    stdout = "LaTeX Warning: Citation `nada' on page 1 undefined on input line 3."
    result = summarize_latex_log(stdout)
    assert "nada" in result and "Citações não encontradas (1)" in result


def test_reference_does_not_span_lines():
    stdout = (
        "LaTeX Warning: Reference `fig_1' on page 3 undefined on input line 210.\n"
        "LaTeX Warning: Citation 'Ha' on page 3 undefined on input line 265.\n"
    )
    result = summarize_latex_log(stdout)
    assert " • fig_1\n" in result + "\n"


def test_biber_version_mismatch_hint():
    stdout = (
        "ERROR - Error: Found biblatex control file version 3.8, expected version 3.11.\n"
        "This means that your biber (2.22) and biblatex (3.17) versions are incompatible.\n"
        "Please (re)run Biber on the file: main\n"
    )
    result = summarize_latex_log(stdout, "error: the external tool exited with error code 2")
    assert "biber incompatível" in result
    assert "3.8" in result and "3.11." in result and "3.11.." not in result
    assert "--engine latexmk" in result
    assert "biber output" not in result  # "rode o biber de novo" não ajuda aqui


def test_run_latex_command_reads_fresh_main_log(tmp_path, monkeypatch):
    (tmp_path / "main.tex").write_text("\\documentclass{article}")
    stale = tmp_path / "main.log"

    def fake_run(cmd, **_kwargs):
        stale.write_text("./main.tex:7: Missing $ inserted.\n")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    monkeypatch.setattr(builder.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match=r"main\.tex:7: Missing \$ inserted"):
        builder.run_latex_command("⚡", ["latexmk", "main.tex"], cwd=str(tmp_path))


def test_run_latex_command_ignores_stale_main_log(tmp_path, monkeypatch):
    (tmp_path / "main.tex").write_text("\\documentclass{article}")
    stale = tmp_path / "main.log"
    stale.write_text("./main.tex:7: erro antigo\n")
    os.utime(stale, (0, 0))

    monkeypatch.setattr(
        builder.subprocess, "run", lambda cmd, **_k: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
    )
    with pytest.raises(RuntimeError) as exc:
        builder.run_latex_command("⚡", ["latexmk", "main.tex"], cwd=str(tmp_path))
    assert "erro antigo" not in str(exc.value)


# ----------------------------------------------------------------------
# Integração com o Tectonic de verdade (lento: baixa pacotes na 1ª vez)
# ----------------------------------------------------------------------


def _has_tectonic() -> bool:
    try:
        resolve_tectonic()
    except FileNotFoundError:
        return False
    return True


@pytest.mark.slow
@pytest.mark.skipif(not _has_tectonic(), reason="tectonic não disponível neste ambiente")
def test_tectonic_builds_minimal_template(tmp_path):
    template_dir = tmp_path / "mini"
    template_dir.mkdir()
    (template_dir / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nOlá << nome >>.\n\\end{document}\n",
        encoding="utf-8",
    )
    data_path = template_dir / "input.json"
    data_path.write_text(json.dumps({"payload": {"nome": "Tectonic"}}), encoding="utf-8")

    from scripts.builder import build

    assert build(str(data_path), str(template_dir), "tectonic") is True

    build_dir = template_dir / "build"
    assert (build_dir / "main.pdf").exists()
    assert (build_dir / "main.synctex.gz").exists()
    assert (build_dir / "main.log").exists()
