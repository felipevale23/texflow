from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from scripts import split
from scripts.split import (
    Chapter,
    chapters_for,
    find_chapters,
    include_name,
    rewrite_main,
)

MAIN = r"""\documentclass{book}
<<% include "preamble.tex" %>>
\begin{document}
% <<% include "commented.tex" %>> is a Jinja tag anyway, but not alone on the line
<<% include "src/intro/intro.tex" %>>
  <<%- include 'src/metodo.tex' -%>>
\begin{appendices}
<<% include "src/apendice.tex" %>>
\end{appendices}
\begin{figure} % \end{figure} num comentário não conta
<<% include "src/fig.tex" %>>
\end{figure}
<<% include "src/conclusao.tex" %>> e texto na mesma linha
\end{document}
"""


def _env(root: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(root)),
        variable_start_string="<<",
        variable_end_string=">>",
        block_start_string="<<%",
        block_end_string="%>>",
        trim_blocks=True,
        lstrip_blocks=True,
    )


def test_find_chapters_only_top_level_body_includes():
    chapters = find_chapters(MAIN)
    assert [c.template for c in chapters] == [
        "src/intro/intro.tex",
        "src/metodo.tex",
        "src/apendice.tex",
    ]
    assert [c.line for c in chapters] == [4, 5, 7]


def test_include_name_is_safe():
    assert include_name("src/intro/intro.tex") == "_include/src-intro-intro"
    assert include_name("./src/Capítulo 1.tex") == "_include/src-Cap-tulo-1"


def test_rewrite_main_replaces_includes_and_adds_includeonly():
    chapters = find_chapters(MAIN)
    text = rewrite_main(MAIN, chapters, [chapters[1]])
    lines = text.splitlines()
    assert lines[2] == r"\includeonly{_include/src-metodo}"
    assert lines[3] == r"\begin{document}"
    assert r"\include{_include/src-intro-intro}" in lines
    assert r"\include{_include/src-metodo}" in lines
    assert r"\include{_include/src-apendice}" in text
    assert '<<% include "src/fig.tex" %>>' in text


def test_rewrite_main_without_only_has_no_includeonly():
    chapters = find_chapters(MAIN)
    assert r"\includeonly" not in rewrite_main(MAIN, chapters, None)


def test_chapters_for_follows_nested_includes(tmp_path):
    (tmp_path / "src" / "intro").mkdir(parents=True)
    (tmp_path / "src" / "intro" / "intro.tex").write_text('<<% include "src/intro/secao.tex" %>>')
    (tmp_path / "src" / "intro" / "secao.tex").write_text("texto")
    (tmp_path / "src" / "metodo.tex").write_text("texto")
    env = _env(tmp_path)
    chapters = [Chapter("src/intro/intro.tex", "_include/a", 0), Chapter("src/metodo.tex", "_include/b", 1)]
    for c in chapters:
        c.deps = split.template_deps(env, c.template)

    assert chapters_for(tmp_path / "src" / "intro" / "secao.tex", tmp_path, chapters) == [chapters[0]]
    assert chapters_for(tmp_path / "src" / "metodo.tex", tmp_path, chapters) == [chapters[1]]
    assert chapters_for(tmp_path / "style.sty", tmp_path, chapters) == []
    assert chapters_for(Path("/elsewhere/x.tex"), tmp_path, chapters) == []


def _project(tmp_path: Path) -> tuple[Path, Path]:
    tpl = tmp_path / "tpl"
    (tpl / "src").mkdir(parents=True)
    (tpl / "main.tex").write_text(
        "\\begin{document}\n"
        '<<% include "src/a.tex" %>>\n'
        '<<% include "src/b.tex" %>>\n'
        "\\end{document}\n"
    )
    (tpl / "src" / "a.tex").write_text(r"\chapter{A} << titulo >>")
    (tpl / "src" / "b.tex").write_text(r"\chapter{B}")
    build = tpl / "build"
    build.mkdir()
    return tpl, build


def test_plan_renders_chapters_with_context(tmp_path):
    tpl, build = _project(tmp_path)
    split.plan(_env(tpl), tpl, build, tpl / "src" / "a.tex", {"titulo": "Olá"})
    assert (build / "_include" / "src-a.tex").read_text() == r"\chapter{A} Olá"
    assert (build / "_include" / "src-b.tex").read_text() == r"\chapter{B}"


def test_plan_does_full_build_until_all_aux_exist(tmp_path):
    tpl, build = _project(tmp_path)
    env = _env(tpl)

    first = split.plan(env, tpl, build, tpl / "src" / "a.tex", {"titulo": ""})
    assert first.only == []
    assert r"\includeonly" not in first.main_source

    for name in ("src-a", "src-b"):
        (build / "_include" / f"{name}.aux").write_text("")
    second = split.plan(env, tpl, build, tpl / "src" / "a.tex", {"titulo": ""})
    assert [c.template for c in second.only] == ["src/a.tex"]
    assert r"\includeonly{_include/src-a}" in second.main_source


def test_plan_for_non_chapter_file_is_full_build(tmp_path):
    tpl, build = _project(tmp_path)
    (build / "_include").mkdir()
    for name in ("src-a", "src-b"):
        (build / "_include" / f"{name}.aux").write_text("")
    plan = split.plan(_env(tpl), tpl, build, tpl / "main.tex", {"titulo": ""})
    assert plan.only == []
    assert plan.describe().startswith("build completo")


def test_active_after_first_split_build(tmp_path):
    tpl, build = _project(tmp_path)
    assert not split.active(build)
    split.plan(_env(tpl), tpl, build, None, {"titulo": ""})
    assert split.active(build)


def test_plan_without_changed_file_is_full_split_build(tmp_path):
    tpl, build = _project(tmp_path)
    (build / "_include").mkdir()
    for name in ("src-a", "src-b"):
        (build / "_include" / f"{name}.aux").write_text("")
    plan = split.plan(_env(tpl), tpl, build, None, {"titulo": ""})
    assert plan.only == []
    assert r"\include{_include/src-a}" in plan.main_source
    assert r"\includeonly" not in plan.main_source
