"""Modo rascunho por capítulo (`texflow --build --only <arquivo>`).

O LaTeX não compila "só o que mudou": qualquer edição faz o TeX diagramar
o documento inteiro. O jeito do próprio LaTeX de compilar só um pedaço é
`\\include` + `\\includeonly`: os capítulos de fora não são diagramados, mas
a numeração de páginas, o sumário e as referências deles vêm do .aux de
cada um, gravado no build anterior.

Aqui o TexFlow faz isso com os parciais do template:

1. cada `<<% include "x.tex" %>>` que está sozinho na linha, no corpo do
   documento e fora de qualquer ambiente, vira um arquivo próprio em
   build/_include/ (renderizado com o mesmo contexto) e, no main.tex,
   `\\include{_include/<nome>}`;
2. o arquivo passado em --only é ligado ao capítulo que o inclui (direto ou
   por outros <<% include %>> dentro dele) e o main.tex ganha
   `\\includeonly{...}` com esse capítulo.

Sem capítulo correspondente (preâmbulo, input.json, um parcial dentro de
um ambiente) ou sem os .aux dos capítulos (primeiro build nesse modo), o
build é completo, já no formato \\include, e os próximos saem rápidos.

Depois do primeiro --only (existe build/_include/), os builds normais
também usam o formato \\include, só que sem \\includeonly: voltar ao
main.tex inline invalidaria o main.aux (ele aponta pros .aux dos capítulos)
e custaria um build completo de várias passadas a cada troca. Limpar o
build/ volta ao formato inline.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from jinja2 import Environment, meta

INCLUDE_DIR = "_include"

# <<% include "x" %>> sozinho na linha (com os delimitadores do TexFlow e os
# modificadores de espaço do Jinja, <<%- / -%>>).
_INCLUDE_LINE = re.compile(r"""^[ \t]*<<%-?\s*include\s+(["'])([^"']+)\1\s*-?%>>[ \t]*$""")
# Ambientes que só agrupam capítulos/seções (pacote appendix): um include
# dentro deles também pode virar \include.
SECTIONING_ENVS = frozenset({"appendices", "appendix", "subappendices"})

_BEGIN = re.compile(r"\\begin\s*\{([^}]+)\}")
_END = re.compile(r"\\end\s*\{([^}]+)\}")


@dataclass
class Chapter:
    template: str  # nome do template, ex.: "src/introducao/introducao.tex"
    name: str  # nome do \include, ex.: "_include/src-introducao-introducao"
    line: int  # linha (0-based) do <<% include %>> no main.tex
    deps: set[str] = field(default_factory=set)  # templates que ele usa


def _strip_comment(line: str) -> str:
    """Tira o comentário LaTeX (% não escapado) da linha."""
    return re.sub(r"(?<!\\)%.*", "", line)


def _normalize(name: str) -> str:
    return PurePosixPath(name.replace("\\", "/")).as_posix().lstrip("./")


def include_name(template: str) -> str:
    """Nome seguro pro \\include (sem espaços nem caracteres especiais)."""
    stem = _normalize(template).removesuffix(".tex")
    return f"{INCLUDE_DIR}/" + re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-")


def find_chapters(source: str) -> list[Chapter]:
    """<<% include %>> do corpo do documento que podem virar \\include:
    sozinhos na linha, depois do \\begin{document} e fora de ambientes (ou
    só dentro de SECTIONING_ENVS, como o appendices)."""
    chapters: list[Chapter] = []
    in_body = False
    stack: list[str] = []
    for n, raw in enumerate(source.splitlines()):
        m = _INCLUDE_LINE.match(raw)
        if m:
            if in_body and all(env in SECTIONING_ENVS for env in stack):
                chapters.append(Chapter(m.group(2), include_name(m.group(2)), n))
            continue
        line = _strip_comment(raw)
        for env in (e.strip() for e in _BEGIN.findall(line)):
            if env == "document":
                in_body = True
            elif in_body:
                stack.append(env)
        for env in (e.strip() for e in _END.findall(line)):
            if env == "document":
                in_body = False
            elif in_body and stack:
                stack.pop()
    return chapters


def template_deps(env: Environment, name: str, seen: set[str] | None = None) -> set[str]:
    """O template e todos os que ele inclui/importa/estende, recursivamente
    (só nomes constantes; um include com nome dinâmico não entra)."""
    seen = set() if seen is None else seen
    name = _normalize(name)
    if name in seen:
        return seen
    seen.add(name)
    source, _, _ = env.loader.get_source(env, name)
    for ref in meta.find_referenced_templates(env.parse(source)):
        if ref:
            template_deps(env, ref, seen)
    return seen


def chapters_for(changed: Path, template_dir: Path, chapters: list[Chapter]) -> list[Chapter]:
    """Capítulos que dependem do arquivo alterado (vazio se nenhum)."""
    try:
        rel = changed.resolve().relative_to(template_dir.resolve()).as_posix()
    except ValueError:
        return []
    return [c for c in chapters if rel in c.deps]


def rewrite_main(source: str, chapters: list[Chapter], only: list[Chapter] | None) -> str:
    """main.tex com os capítulos trocados por \\include e, se `only`, o
    \\includeonly antes do \\begin{document}."""
    lines = source.splitlines(keepends=True)
    for c in chapters:
        end = "\n" if lines[c.line].endswith("\n") else ""
        lines[c.line] = f"\\include{{{c.name}}}{end}"
    text = "".join(lines)
    if only:
        names = ",".join(c.name for c in only)
        text, count = re.subn(
            r"^([ \t]*\\begin\s*\{document\})",
            lambda m: f"\\includeonly{{{names}}}\n{m.group(1)}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count == 0:
            raise RuntimeError("main.tex sem \\begin{document}: não dá pra usar --only.")
    return text


def write_if_changed(path: Path, text: str) -> None:
    """Escreve só se mudou (preserva o mtime pro cache do latexmk)."""
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@dataclass
class SplitPlan:
    main_source: str  # main.tex reescrito, pra renderizar com env.from_string
    chapters: list[Chapter]
    only: list[Chapter]  # vazio: build completo

    def describe(self) -> str:
        if self.only:
            return "rascunho (--only): só " + ", ".join(c.template for c in self.only)
        return "build completo (formato \\include)"


def active(build_dir: Path) -> bool:
    """Se o build anterior foi no formato \\include (houve um --only)."""
    return (build_dir / INCLUDE_DIR).is_dir()


def plan(
    env: Environment, template_dir: Path, build_dir: Path, changed: Path | None, context: dict
) -> SplitPlan:
    """Renderiza os capítulos em build/_include/ e decide o \\includeonly
    (nenhum se changed=None: build completo no formato \\include)."""
    source, _, _ = env.loader.get_source(env, "main.tex")
    chapters = find_chapters(source)
    for c in chapters:
        c.deps = template_deps(env, c.template)
        rendered = env.get_template(c.template).render(**context)
        write_if_changed(build_dir / f"{c.name}.tex", rendered)

    only = chapters_for(changed, template_dir, chapters) if changed else []
    # Sem o .aux de algum capítulo (primeiro build nesse formato, ou depois
    # de um build normal), o \includeonly deixaria páginas/referências
    # erradas: faz o completo, que grava todos.
    if only and not all((build_dir / f"{c.name}.aux").is_file() for c in chapters):
        only = []
    return SplitPlan(rewrite_main(source, chapters, only), chapters, only)
