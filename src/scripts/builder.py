import os
import re
import sys
import tempfile
import subprocess
import importlib.resources as res

from pathlib import Path
from collections import OrderedDict
from jinja2 import Environment, PackageLoader, FileSystemLoader
from yaspin import yaspin
from prompt_toolkit.formatted_text import FormattedText, HTML
from prompt_toolkit.shortcuts import print_formatted_text

from classes.data import Data
from configs.style import STYLE
from configs.paths import BUILD_DIR
from configs.templates import builtin_templates
from classes.task import Task, CleanBuild, RenderTemplate, CopyTree, FnTask

def check_unresolved_placeholders(tex_file):
    """Verifica se ainda existem placeholders não resolvidos no arquivo .tex"""
    content = Path(tex_file).read_text(encoding="utf-8")
    placeholders = re.findall(r"<<.*?>>", content)
    if placeholders:
        raise RuntimeError(
            f"Placeholders não resolvidos encontrados no .tex: {placeholders}"
        )

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
    
    print_formatted_text(
        HTML(f'<cmd> {emoji} </cmd> <sub-msg> Executando: {' '.join(cmd)} (cwd={cwd or os.getcwd()})" </sub-msg>'), style=STYLE
    )

    # cria log temporário
    log_file = tempfile.NamedTemporaryFile(delete=False, suffix=".log")

    try:
        subprocess.run(
            cmd,
            check=True,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        print("\n❌ Erro na execução!")
        summary = summarize_latex_log(e.stdout, e.stderr)
        # salva log detalhado se quiser
        log_file.write(((e.stdout or "") + "\n" + (e.stderr or "")).encode())
        log_file.close()
        # levanta erro com resumo curto e caminho do log completo
        raise RuntimeError(
            f"Compilação falhou — resumo:\n{summary}\n\nLog completo: {log_file.name}"
        ) from e

def xelatex_build_process():
    # Setup do ambiente
    env = os.environ.copy()
    env["TEXINPUTS"] = f"{BUILD_DIR}:"

    commands_to_run = [
        ("🐢", ["xelatex", "-interaction=nonstopmode", "main.tex"], "build"),
        ("🚀", ["biber", "main"], "build"),
        ("🐢", ["xelatex", "-interaction=nonstopmode", "main.tex"], "build")
    ]
    
    try:
        for emoji, cmd, cwd in commands_to_run:
            run_latex_command(emoji, cmd, cwd=cwd, env=env)
        
    except RuntimeError as e:
        print(f"\n❌ Erro crítico: {e}")
        print("O processo de compilação foi interrompido.")
        sys.exit(1)

def summarize_latex_log(stdout: str, stderr: str = None, max_examples: int = 6) -> str: # type: ignore
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
        # 1. Instancia o PackageLoader:
        # O loader irá procurar templates dentro da pasta 'templates'
        # que está dentro do pacote 'assets'.
        if template_arg in builtin_templates:
            return Environment(
                loader=PackageLoader(package_name="assets", package_path=f"templates/{template_arg}"),
                variable_start_string="<<",
                variable_end_string=">>",
                block_start_string="<<%",
                block_end_string="%>>",
                autoescape=False,
                trim_blocks=True,
                lstrip_blocks=True,
            )
        else:
            raise Exception("Default template não encontrado.\n")

def build(data_path: str, template_folder: str):
    """
    Cria o arquivo .tex com as variáveis passadas
    """
    
    print = print_formatted_text

    with yaspin(color="magenta") as sp:
        
        try:
            
            BUILD_DIR.mkdir(exist_ok=True)

            # --- Data ---
            data = Data()
            data.load_from_file(Path(data_path))
            context = data.get_payload()
            
            # --- Jinja ---
            env = _jinja_env(template_folder)
            template = env.get_template("main.tex")
            
            # --- Tasks ---
            tasks: list[Task] = []
            clean   = CleanBuild()
            render  = RenderTemplate(        
                template=template,
                context=context,
                output=BUILD_DIR / "main.tex",
                dependencies=[clean]
            )
            copy_images = CopyTree(
                res.files('assets').joinpath('images'), 
                BUILD_DIR / "images", 
                dependencies = [clean]
            )
            copy_plots  = CopyTree(
                res.files('assets').joinpath('plots'), 
                BUILD_DIR / "plots", 
                dependencies = [clean]
            )
            copy_files = CopyTree(
                res.files('assets').joinpath('templates', template_folder)
                if template_folder in builtin_templates
                else Path(template_folder),
                BUILD_DIR,
                ignore_tex=True,
                dependencies=[clean]
            )
            compile_pdf = FnTask(xelatex_build_process,
                mode="chain",
                dependencies=[clean, render, copy_images, copy_plots, copy_files]
            )
            tasks.extend([
                clean,
                render,
                copy_images,
                copy_plots,
                copy_files,
                compile_pdf
            ]) # append tudo numa vez só
            
            Task.runner(tasks)
            
            sp.ok("✨ Compilação do documento concluída com sucesso! ✨")
        
        except Exception as e:
            
            with sp.hidden():
                print(FormattedText([("fg:#ff0000 bold", f"✖ Erro: {e}")]), style=STYLE)
            
            sp.fail("🐛")