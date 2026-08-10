import importlib.resources as res
import os
import re
import subprocess
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.shortcuts import print_formatted_text

from classes.data import Data
from classes.task import CopyTree, FnTask, RenderTemplate, Task
from configs.paths import BUILD_DIR
from configs.spinner import spinner
from configs.style import STYLE
from scripts.utils import is_tty


def check_unresolved_placeholders(tex_file):
    """Verifica se ainda existem placeholders não resolvidos no arquivo .tex"""
    content = Path(tex_file).read_text(encoding="utf-8")
    placeholders = re.findall(r"<<.*?>>", content)
    if placeholders:
        raise RuntimeError(f"Placeholders não resolvidos encontrados no .tex: {placeholders}")

def run_latex_command(emoji, cmd, cwd=None, env=None):
    """Executa comando LaTeX com debug detalhado."""
    
    # tenta identificar o arquivo .tex no comando
    tex_file = None
    for arg in cmd:
        if arg.endswith(".tex"):
            tex_file = Path(cwd or os.getcwd()) / arg
            break

    if tex_file and tex_file.exists():
        check_unresolved_placeholders(tex_file)

    # Sem TTY (ex: chamado pelo LaTeX Workshop a cada Ctrl+S), o VS Code faz
    # parsing por regex do stdout/stderr do build tool: sequências ANSI de
    # estilo do prompt_toolkit corromperiam esse parsing, então usamos texto
    # puro nesse caso.
    if is_tty():
        print_formatted_text(
            HTML(f'<cmd> {emoji} </cmd> <sub-msg> Executando: {' '.join(cmd)} (cwd={cwd or os.getcwd()})" </sub-msg>'),
            style=STYLE,
            file=sys.stderr
        )
    else:
        print(f"{emoji} Executando: {' '.join(cmd)} (cwd={cwd or os.getcwd()})", file=sys.stderr)
        sys.stderr.flush()

    # cria log temporário
    # Garante que o diretório de log temporário exista e o arquivo seja gravado
    log_temp_path = None
    debug_mode = os.getenv("TEXFLOW_DEBUG")

    # Execução do processo
    # capture_output só intercepta o stdout/stderr do PROCESSO latexmk — o
    # build/main.log continua sendo escrito em disco por ele normalmente
    # (é isso que o LaTeX Workshop lê pra popular erros/SyncTeX), mesmo em
    # caso de falha, então esse tratamento customizado não interfere nele.
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True, # Sempre capturamos para poder processar o erro
        check=False
    )

    if result.returncode != 0:
        # 1. Tenta extrair um resumo útil
        # O LaTeX costuma colocar o erro no stdout, não no stderr
        summary = summarize_latex_log(result.stdout)
        
        # 2. Se o resumo for vazio, tenta pegar as últimas linhas do stdout
        if not summary.strip():
            lines = result.stdout.splitlines()
            summary = "\n".join(lines[-10:]) # Pega as últimas 10 linhas como contexto

        # 3. Salva o log completo para inspeção profunda
        with tempfile.NamedTemporaryFile(delete=False, suffix=".log", mode="w") as f:
            f.write("--- STDOUT ---\n")
            f.write(result.stdout or "")
            f.write("\n--- STDERR ---\n")
            f.write(result.stderr or "")
            log_temp_path = f.name

        print(f"\n❌ Erro na execução! Log detalhado: {log_temp_path}", file=sys.stderr)
        sys.stderr.flush()

        # 4. O RAISE: Passamos o resumo para a mensagem principal
        # Usamos 'from None' se não quiser o traceback do subprocess, 
        # ou 'from e' para manter a cadeia.
        raise RuntimeError(
            f"Falha na Compilação LaTeX (Código {result.returncode})\n"
            f"--------------------------------------------------\n"
            f"{summary}\n"
            f"--------------------------------------------------\n"
            f"Log completo em: {log_temp_path}"
        )

    # Se chegou aqui, deu certo. Se quiser ver o output em modo debug:
    if debug_mode:
        print(result.stdout)

def latexmk_build_process(build_dir: Path):
    """Compila via latexmk, que decide sozinho (por mtime/dependência de cada
    \\input, não um hash global) o que precisa ser reprocessado. Cache
    incremental nativo dele vive em build/.fdb_latexmk e build/*.fls e não é
    apagado entre builds — por isso RenderTemplate/CopyTree evitam tocar o
    mtime de arquivos cujo conteúdo não mudou (ver classes/task.py)."""

    env = os.environ.copy()

    # 🔥 TEXINPUTS correto
    env["TEXINPUTS"] = f"{build_dir}{os.pathsep}{env.get('TEXINPUTS','')}"

    cmd = [
        "latexmk",
        "-xelatex",
        "-pdfxe",
        # -f: continua processando mesmo se um passo (ex: uma xelatex run)
        # reportar erro, pra maximizar o que fica atualizado e pra sempre
        # gerar main.log/main.pdf parciais que o LaTeX Workshop possa ler.
        # NÃO é o mesmo que -g (que força rebuild completo ignorando
        # timestamps) — -f não invalida o cache incremental do latexmk.
        "-f",
        "-interaction=nonstopmode", # Evita travar pedindo input
        "-silent",                  # 🔥 Substitui o -quiet e silencia o log
        "-synctex=1",
        "-file-line-error"
    ]

    if os.getenv("TEXFLOW_DEBUG"):
        cmd.append("-verbose")
    else:
        cmd.append("-quiet")

    cmd.append("main.tex")

    # 🔥 cwd dinâmico (adeus "build" hardcoded)
    run_latex_command("⚡", cmd, cwd=str(build_dir), env=env)

def xelatex_build_process():
    # Setup do ambiente
    env = os.environ.copy()
    env["TEXINPUTS"] = f"{BUILD_DIR}:{env.get('TEXINPUTS','')}"

    commands_to_run = [
        ("🐢", ["xelatex", "-interaction=nonstopmode", "main.tex"], "build"),
        ("🚀", ["biber", "main"], "build"),
        ("🐢", ["xelatex", "-interaction=nonstopmode", "main.tex"], "build")
    ]
    
    try:
        for emoji, cmd, cwd in commands_to_run:
            run_latex_command(emoji, cmd, cwd=cwd, env=env)
        
    except RuntimeError as e:
        print(f"\n❌ Erro crítico: {e}", file=sys.stderr)
        print("O processo de compilação foi interrompido.", file=sys.stderr)
        sys.exit(1)

def summarize_latex_log(stdout: str, stderr: str | None = None, max_examples: int = 6) -> str:
    s = (stdout or "") + ("\n" + stderr if stderr else "")
    s.splitlines()

    # 1) Erros LaTeX (linhas que começam com "!")
    errors = []
    for m in re.finditer(r'(?m)^! (.+)$', s):
        msg = m.group(1).strip()
        # tenta achar trecho "l.<num> ..." perto do erro
        tail = s[m.end(): m.end() + 600]
        lm = re.search(r'l\.(\d+)\s*(.*)', tail)
        if not lm:
            # procura a última ocorrência de l.<num> antes do erro
            prev = s[:m.start()]
            prev_l = re.findall(r'l\.(\d+)\s*(.*)', prev)
            if prev_l:
                ln, snippet = prev_l[-1]
            else:
                ln, snippet = None, ""
        else:
            ln, snippet = lm.group(1), lm.group(2).strip()
        errors.append({'msg': msg, 'line': ln, 'snippet': snippet})
    # 2) Placeholders <<...>>
    placeholders = re.findall(r'<<\s*([^<>]+?)\s*>>', s)
    placeholders = list(OrderedDict.fromkeys(placeholders))  # uniq preserve order

    # 3) Missing characters
    missing_chars = re.findall(r'Missing character: There is no (.+?) in font (.+?)!', s)
    # 4) Citations undefined
    cites = re.findall(r"LaTeX Warning: Citation '([^']+)' .*undefined(?: on input line (\d+))?", s)
    cite_keys = list(OrderedDict.fromkeys([c[0] for c in cites]))
    # 5) References undefined
    refs = re.findall(r"LaTeX Warning: Reference `([^`]+)' .* undefined(?: on input line (\d+))?", s)
    ref_keys = list(OrderedDict.fromkeys([r[0] for r in refs]))
    # 6) No .bbl / empty bibliography / biblatex asks to run Biber
    no_bbl = re.findall(r'No file ([\w\./-]+)\.', s)
    empty_bib = 'LaTeX Warning: Empty bibliography' in s
    ask_biber = 'Please (re)run Biber' in s or 'Please (re)run Biber' in s or 'Please (re)run Biber' in s
    # 7) Overfull boxes
    overfull = re.findall(r'Overfull \\hbox.*', s)
    # 8) Output written
    out_written = re.search(r'Output written on (.+?) \((\d+) pages\)\.', s)

    parts = []
    if errors:
        parts.append("Erros LaTeX (primeiros):")
        for e in errors[:max_examples]:
            if e['line']:
                parts.append(f" • linha {e['line']}: {e['msg']}  — trecho: {e['snippet']!s}")
            else:
                parts.append(f" • {e['msg']}")
    if placeholders:
        parts.append("Placeholders não resolvidos:")
        parts.append(" • " + ", ".join(placeholders[:max_examples]))
    if missing_chars:
        groups = {}
        for ch, font in missing_chars:
            groups.setdefault(font.strip(), set()).add(ch.strip())
        parts.append("Caracteres faltando (provavelmente por math-mode):")
        for font, chars in groups.items():
            parts.append(f" • {font}: {', '.join(list(chars)[:10])}")
    if cite_keys:
        parts.append(f"Citações não encontradas ({len(cite_keys)}):")
        parts.append(" • " + ", ".join(cite_keys[:max_examples]))
        if len(cite_keys) > max_examples:
            parts.append(f" • ... +{len(cite_keys)-max_examples} outros")
    if ref_keys:
        parts.append(f"Referências não resolvidas ({len(ref_keys)}):")
        parts.append(" • " + ", ".join(ref_keys[:max_examples]))
    if no_bbl:
        parts.append(f"Aviso: arquivo(s) de bibliografia ausente(s): {', '.join(no_bbl[:max_examples])}")
    if empty_bib:
        parts.append("Bibliografia vazia.")
    if ask_biber:
        parts.append("biblatex pede: rodar `biber output` e recompilar (biber + 2x xelatex).")
    if overfull:
        parts.append(f"Overfull \\hbox: {len(overfull)} ocorrência(s) (avisos de layout).")
    if out_written:
        parts.append(f"PDF gerado: {out_written.group(1)} ({out_written.group(2)} páginas).")
    if not parts:
        return "Nenhuma indicação clara de erro encontrada no stdout."
    return "\n".join(parts)

def _jinja_env(template_arg: str) -> Environment:
    
    p = Path(template_arg)

    # Caso 1 — usuário passou caminho real
    if p.exists() and p.is_dir():
        return Environment(
            loader=FileSystemLoader(str(p)),
            variable_start_string="<<",
            variable_end_string=">>",
            block_start_string="<<%",
            block_end_string="%>>",
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
    else:
        raise FileNotFoundError("Default template não encontrado.\n")

def build(data_path: str, template_folder: str):
    """
    Cria o arquivo .tex com as variáveis passadas
    """
    
    print = print_formatted_text
    with spinner(color="magenta") as sp:
        
        try:
            
            template_path = Path(template_folder).resolve()
            build_dir = template_path / "build"
            build_dir.mkdir(parents=True, exist_ok=True)

            # --- Data ---
            data = Data()
            data.load_from_file(Path(data_path))
            context = data.get_payload()
            
            # --- Jinja ---
            env = _jinja_env(template_folder)
            template = env.get_template("main.tex")
            
            # --- Tasks ---
            tasks: list[Task] = []
            render  = RenderTemplate(        
                template=template,
                context=context,
                output=build_dir / "main.tex",
                dependencies=[]
            )
            # 🔥 symlink em vez de cópia física: são assets binários que
            # raramente mudam entre builds, então não há por que duplicá-los
            # em build/ a cada save.
            copy_images = CopyTree(
                res.files('assets').joinpath('images'),
                build_dir / "images",
                symlink=True,
                dependencies = [render]
            )
            copy_plots  = CopyTree(
                res.files('assets').joinpath('plots'),
                build_dir / "plots",
                symlink=True,
                dependencies = [render]
            )
            copy_files = CopyTree(
                Path(template_folder),
                build_dir,
                ignore_tex=True, 
                dependencies=[render]
            )

            compile_pdf = FnTask(
                latexmk_build_process,
                build_dir,
                mode="chain",
                dependencies=[render, copy_images, copy_plots, copy_files]
            )
            tasks.extend([
                copy_images,
                copy_plots,
                copy_files,
                render,
                compile_pdf
            ]) # append tudo numa vez só
            
            Task.runner(tasks)
            
            sp.ok("✨ Compilação do documento concluída com sucesso! ✨")
        
        except Exception as e:  # noqa: BLE001 - error boundary do build, precisa reportar qualquer falha

            with sp.hidden():
                if is_tty():
                    print(FormattedText([("fg:#ff0000 bold", f"✖ Erro: {e}")]), style=STYLE, file=sys.stderr)
                else:
                    print(f"✖ Erro: {e}", file=sys.stderr)
                    sys.stderr.flush()

            sp.fail("🐛")