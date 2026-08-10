import importlib.resources as res
import json
import shutil
import subprocess
import sys

import pytest

from scripts.builder import summarize_latex_log

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
