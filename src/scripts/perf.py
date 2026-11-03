"""Harness de performance do TexFlow (`uv run perf`).

Mede, de fora (rodando a CLI como o usuário roda), quanto tempo cada
cenário leva, numa cópia temporária do template, sem tocar nos arquivos
originais:

- startup: `texflow --version` (partida do processo; pesa no binário do
  PyInstaller);
- cold: build com o build/ vazio;
- noop: rebuild sem mudar nada;
- text: rebuild depois de mudar só texto;
- cite: rebuild depois de acrescentar uma citação (só com .bib);
- draft: rebuild com --only depois de mudar só texto num capítulo;
- watch: do save até o fim do rebuild no modo --watch.

Cada cenário roda em cada configuração (engine, --fast, cache do biber).
Saída: tabela com mediana e mínimo; --json grava os resultados e --compare
mostra a diferença em relação a um JSON anterior.

Exemplos:
    uv run perf                                  # template de exemplo
    uv run perf -t ~/tese -i ~/tese/input.json -n 5 --json antes.json
    uv run perf -t ~/tese -i ~/tese/input.json --texflow ~/.local/bin/texflow \\
        --compare antes.json
"""

import argparse
import json
import os
import platform
import queue
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from classes.task import (
    IGNORE_FILE,
    is_excluded_dir,
    load_ignore_patterns,
    matches_ignore,
)
from scripts.split import find_chapters

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_TEMPLATE = ROOT / "assets" / "templates" / "journal"

SCENARIOS = ("startup", "cold", "noop", "text", "cite", "draft", "watch")
BUILD_END = re.compile(r"\[texflow\] build (concluído|falhou)")
# Variáveis que mudam o comportamento do build: limpas antes de cada run pra
# que só a configuração do cenário valha.
TEXFLOW_ENV = ("TEXFLOW_ENGINE", "TEXFLOW_FAST", "TEXFLOW_NO_CACHE", "TEXFLOW_DEBUG")


@dataclass(frozen=True)
class Config:
    name: str
    engine: str
    fast: bool = False
    cache: bool = True

    def flags(self) -> list[str]:
        return ["--engine", self.engine, *(["--fast"] if self.fast else [])]

    def env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k not in TEXFLOW_ENV}
        if not self.cache:
            env["TEXFLOW_NO_CACHE"] = "1"
        return env


CONFIGS = {
    c.name: c
    for c in (
        Config("latexmk", "latexmk"),
        Config("tectonic", "tectonic"),
        Config("tectonic-fast", "tectonic", fast=True),
        Config("tectonic-nocache", "tectonic", cache=False),
        Config("tectonic-fast-nocache", "tectonic", fast=True, cache=False),
    )
}
DEFAULT_CONFIGS = ("latexmk", "tectonic", "tectonic-fast", "tectonic-fast-nocache")


@dataclass
class Result:
    config: str
    scenario: str
    times: list[float] = field(default_factory=list)
    ok: bool = True
    # Com o Tectonic: quantas vezes o biber rodou de verdade (o resto veio
    # do cache). None quando não se aplica.
    biber_runs: int | None = None
    note: str = ""

    @property
    def median(self) -> float | None:
        return statistics.median(self.times) if self.times else None

    @property
    def best(self) -> float | None:
        return min(self.times) if self.times else None

    def to_dict(self) -> dict:
        return {**asdict(self), "median": self.median, "min": self.best}


# ----------------------------------------------------------------------
# Template de trabalho: cópia temporária + edições
# ----------------------------------------------------------------------


def copy_template(src: Path, dst: Path) -> None:
    """Copia o template sem o que o próprio TexFlow ignora (build/, pastas
    ocultas, node_modules, .venv, .texflowignore): é isso que o build lê, e
    copiar um projeto grande inteiro só atrasaria o harness."""
    src = src.resolve()
    patterns = load_ignore_patterns(src)

    def ignore(directory: str, names: list[str]) -> set[str]:
        base = Path(directory)
        skipped = set()
        for name in names:
            path = base / name
            is_dir = path.is_dir()
            rel = path.relative_to(src).as_posix()
            if (is_dir and is_excluded_dir(name)) or (
                patterns and name != IGNORE_FILE and matches_ignore(rel, is_dir, patterns)
            ):
                skipped.add(name)
        return skipped

    shutil.copytree(src, dst, ignore=ignore, symlinks=True)


def insert_before_end_document(main_tex: Path, snippet: str) -> None:
    """Insere um trecho antes do último \\end{document} do main.tex."""
    text = main_tex.read_text(encoding="utf-8")
    marker = r"\end{document}"
    pos = text.rfind(marker)
    if pos < 0:
        raise ValueError(f"{main_tex} não tem \\end{{document}}")
    main_tex.write_text(text[:pos] + snippet + "\n" + text[pos:], encoding="utf-8")


def text_edit(main_tex: Path, n: int) -> None:
    insert_before_end_document(main_tex, f"\nParágrafo de benchmark número {n}, só texto.\n")


def find_cite_key(template: Path) -> str | None:
    """Primeira chave do primeiro .bib do template (fora de build/)."""
    for bib in sorted(template.rglob("*.bib")):
        if "build" in bib.relative_to(template).parts:
            continue
        m = re.search(r"@\w+\s*\{\s*([^,\s]+)\s*,", bib.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1)
    return None


def cite_edit(main_tex: Path, key: str, n: int) -> None:
    # Uma citação muda o .bcf: o biber precisa rodar de novo.
    insert_before_end_document(main_tex, f"\nCitação de benchmark {n} \\cite{{{key}}}.\n")


# ----------------------------------------------------------------------
# Execução
# ----------------------------------------------------------------------


class Runner:
    def __init__(self, texflow: list[str], workdir: Path, input_name: str, verbose: bool):
        self.texflow = texflow
        self.workdir = workdir
        self.input_name = input_name
        self.verbose = verbose

    def build_cmd(self, config: Config, *extra: str) -> list[str]:
        return [
            *self.texflow,
            "--build",
            *extra,
            *config.flags(),
            "--input",
            self.input_name,
            "--template",
            ".",
        ]

    def timed(self, cmd: list[str], env: dict[str, str]) -> tuple[float, bool, str]:
        start = time.perf_counter()
        proc = subprocess.run(
            cmd, cwd=self.workdir, env=env, capture_output=True, text=True, check=False
        )
        elapsed = time.perf_counter() - start
        out = proc.stdout + proc.stderr
        # O TexFlow reporta erro de build ("✖ Erro: ...") e sai com 0.
        ok = proc.returncode == 0 and "✖" not in out
        if self.verbose or not ok:
            print(out[-2000:], file=sys.stderr)
        return elapsed, ok, out

    def build(self, config: Config, *extra: str) -> tuple[float, bool]:
        elapsed, ok, _ = self.timed(self.build_cmd(config, *extra), config.env())
        return elapsed, ok

    def clean_build(self) -> None:
        build = self.workdir / "build"
        if build.exists():
            for path in build.rglob("*"):
                if path.is_dir() and not path.is_symlink():
                    path.chmod(0o755)
            shutil.rmtree(build)


def biber_marker(workdir: Path) -> float | None:
    """mtime do .bbl guardado pelo cache do biber: muda quando o biber roda
    de verdade e fica igual quando o shim devolve o cache."""
    cached = workdir / "build" / ".texflow-cache" / "main.bbl"
    return cached.stat().st_mtime_ns if cached.exists() else None


def run_startup(runner: Runner, n: int) -> Result:
    result = Result("-", "startup")
    for _ in range(n):
        elapsed, ok, _ = runner.timed([*runner.texflow, "--version"], dict(os.environ))
        result.times.append(elapsed)
        result.ok &= ok
    return result


def run_build_scenario(
    runner: Runner, config: Config, scenario: str, n: int, cite_key: str | None
) -> Result:
    result = Result(config.name, scenario)
    main_tex = runner.workdir / "main.tex"
    track_biber = config.engine == "tectonic" and config.cache
    if track_biber:
        result.biber_runs = 0

    if scenario == "cite" and cite_key is None:
        result.note = "pulado: sem .bib no template"
        return result

    extra: tuple[str, ...] = ()
    if scenario == "draft":
        chapters = find_chapters(main_tex.read_text(encoding="utf-8"))
        if not chapters:
            result.note = "pulado: sem capítulos pra --only"
            return result
        chapter = runner.workdir / chapters[0].template
        extra = ("--only", str(chapter))
        result.note = f"--only {chapters[0].template}"

    if scenario != "cold":
        # Estado de partida: um build completo já feito (no draft, o
        # primeiro --only é o build completo no formato \include).
        runner.clean_build()
        _, ok = runner.build(config, *extra)
        if not ok:
            result.ok, result.note = False, "build inicial falhou"
            return result

    for i in range(n):
        if scenario == "cold":
            runner.clean_build()
        elif scenario == "text":
            text_edit(main_tex, i)
        elif scenario == "cite":
            cite_edit(main_tex, cite_key, i)
        elif scenario == "draft":
            with chapter.open("a", encoding="utf-8") as f:
                f.write(f"\nParágrafo de benchmark número {i}, só texto.\n")

        before = biber_marker(runner.workdir)
        elapsed, ok = runner.build(config, *extra)
        result.times.append(elapsed)
        result.ok &= ok
        if track_biber and biber_marker(runner.workdir) != before:
            result.biber_runs += 1

    return result


def run_watch_scenario(runner: Runner, config: Config, n: int, timeout: float) -> Result:
    """Do save (edição do main.tex) até o marcador de fim de build do watch."""
    result = Result(config.name, "watch")
    runner.clean_build()
    proc = subprocess.Popen(
        runner.build_cmd(config, "--watch"),
        cwd=runner.workdir,
        env=config.env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    ends: queue.Queue[str] = queue.Queue()

    def reader() -> None:
        for line in proc.stderr:
            if runner.verbose:
                print(line, end="", file=sys.stderr)
            m = BUILD_END.search(line)
            if m:
                ends.put(m.group(1))

    threading.Thread(target=reader, daemon=True).start()
    try:
        first = ends.get(timeout=timeout)
        if first != "concluído":
            result.ok, result.note = False, "build inicial do watch falhou"
            return result
        for i in range(n):
            # Dá tempo do watcher voltar a observar depois do build anterior.
            time.sleep(0.5)
            start = time.perf_counter()
            text_edit(runner.workdir / "main.tex", 1000 + i)
            status = ends.get(timeout=timeout)
            result.times.append(time.perf_counter() - start)
            result.ok &= status == "concluído"
    except queue.Empty:
        result.ok, result.note = False, f"sem fim de build em {timeout:.0f} s"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    return result


# ----------------------------------------------------------------------
# Relatório
# ----------------------------------------------------------------------


def _fmt(seconds: float | None) -> str:
    return "-" if seconds is None else f"{seconds:6.2f}s"


def format_table(results: list[Result], baseline: dict | None = None) -> str:
    rows = [("config", "cenário", "mediana", "mín", "n", "biber", "vs base", "")]
    for r in results:
        biber = "-" if r.biber_runs is None else f"{r.biber_runs}/{len(r.times)} rodou"
        delta = ""
        if baseline and r.median is not None:
            old = baseline.get((r.config, r.scenario))
            if old:
                delta = f"{r.median - old:+.2f}s ({(r.median - old) / old:+.0%})"
        status = f"FALHOU {r.note}".strip() if not r.ok else r.note
        rows.append(
            (r.config, r.scenario, _fmt(r.median), _fmt(r.best), str(len(r.times)), biber, delta, status)
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)).rstrip() for row in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


def load_baseline(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        (r["config"], r["scenario"]): r["median"]
        for r in data["results"]
        if r.get("median") is not None
    }


def texflow_version(texflow: list[str]) -> str:
    proc = subprocess.run([*texflow, "--version"], capture_output=True, text=True, check=False)
    return (proc.stdout + proc.stderr).strip()


# ----------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="perf",
        description="Mede o tempo de build do TexFlow por cenário e configuração.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Cenários: " + ", ".join(SCENARIOS) + ". Configs: " + ", ".join(CONFIGS),
    )
    p.add_argument("-t", "--template", type=Path, default=DEFAULT_TEMPLATE, help="pasta do template")
    p.add_argument("-i", "--input", type=Path, help="JSON de dados (padrão: <template>/input.json)")
    p.add_argument(
        "--texflow",
        default="texflow",
        help="comando do TexFlow a medir (padrão: 'texflow' do PATH; com `uv run`, o do código-fonte)",
    )
    p.add_argument("-n", "--repeat", type=int, default=3, help="repetições por cenário (padrão: 3)")
    p.add_argument(
        "-c", "--configs", default=",".join(DEFAULT_CONFIGS), help="configs separadas por vírgula"
    )
    p.add_argument(
        "-s", "--scenarios", default=",".join(SCENARIOS), help="cenários separados por vírgula"
    )
    p.add_argument("--json", type=Path, help="grava os resultados neste JSON")
    p.add_argument("--compare", type=Path, help="JSON de uma rodada anterior pra comparar")
    p.add_argument("--timeout", type=float, default=600, help="limite por build no watch (s)")
    p.add_argument("-v", "--verbose", action="store_true", help="mostra a saída do TexFlow")
    args = p.parse_args(argv)

    args.configs = [c.strip() for c in args.configs.split(",") if c.strip()]
    args.scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    unknown = [c for c in args.configs if c not in CONFIGS] + [
        s for s in args.scenarios if s not in SCENARIOS
    ]
    if unknown:
        p.error(f"desconhecido(s): {', '.join(unknown)}")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    texflow = shlex.split(args.texflow)
    if shutil.which(texflow[0]) is None and not Path(texflow[0]).is_file():
        sys.exit(f"TexFlow não encontrado: {texflow[0]}")

    template = args.template.resolve()
    input_path = (args.input or template / "input.json").resolve()
    configs = [CONFIGS[c] for c in args.configs]
    if "latexmk" in args.configs and shutil.which("latexmk") is None:
        print("aviso: latexmk não está no PATH; a config latexmk vai falhar", file=sys.stderr)

    version = texflow_version(texflow)
    print(f"{version} | {' '.join(texflow)} | {template} | n={args.repeat}", file=sys.stderr)

    results: list[Result] = []
    with tempfile.TemporaryDirectory(prefix="texflow-perf-") as tmp:
        workdir = Path(tmp) / "template"
        copy_template(template, workdir)
        # O JSON vai junto, com nome fixo (o original pode estar fora do template).
        input_name = "perf-input.json"
        shutil.copy2(input_path, workdir / input_name)
        cite_key = find_cite_key(workdir)
        pristine = (workdir / "main.tex").read_text(encoding="utf-8")
        runner = Runner(texflow, workdir, input_name, args.verbose)

        if "startup" in args.scenarios:
            print("• startup", file=sys.stderr)
            results.append(run_startup(runner, args.repeat))

        for config in configs:
            for scenario in args.scenarios:
                if scenario == "startup":
                    continue
                print(f"• {config.name} / {scenario}", file=sys.stderr)
                (workdir / "main.tex").write_text(pristine, encoding="utf-8")
                if scenario == "watch":
                    result = run_watch_scenario(runner, config, args.repeat, args.timeout)
                else:
                    result = run_build_scenario(runner, config, scenario, args.repeat, cite_key)
                results.append(result)

    baseline = load_baseline(args.compare) if args.compare else None
    print()
    print(format_table(results, baseline))

    if args.json:
        payload = {
            "meta": {
                "texflow": version,
                "command": texflow,
                "template": str(template),
                "repeat": args.repeat,
                "date": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "host": platform.node(),
                "platform": platform.platform(),
            },
            "results": [r.to_dict() for r in results],
        }
        args.json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nResultados em {args.json}", file=sys.stderr)

    if not all(r.ok for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
