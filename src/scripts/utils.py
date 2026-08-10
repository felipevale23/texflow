import os
import re
import sys
import tempfile
from pathlib import Path


def debug(msg):
    if os.getenv("TEXFLOW_DEBUG"):
        print(f"[DEBUG] {msg}", file=sys.stderr)

def is_tty():
    return sys.stderr.isatty()

def confirm(prompt: str, auto_yes: bool) -> bool:
    if auto_yes:
        return True
    if not is_tty():
        print(f"{prompt} (rode novamente com -y/--yes para confirmar automaticamente)", file=sys.stderr)
        return False
    resposta = input(f"{prompt} [y/N] ").strip().lower()
    return resposta in ("y", "yes", "s", "sim")

def is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=path):
            pass
        return True
    except OSError:
        return False

def parse_money(s: str) -> float:
    s = str(s).strip()
    s = re.sub(r"[^\d,.\-]", "", s)  # remove tudo que não é dígito, vírgula, ponto ou sinal
    if s == "":
        return 0.0
    # caso contenha both '.' and ',': decide qual é decimal olhando a última ocorrência
    if "," in s and "." in s:
        if s.rfind(".") > s.rfind(","):       # ponto aparece depois -> ponto = decimal, vírgula = milhares
            s = s.replace(",", "")
        else:                                 # vírgula aparece depois -> vírgula = decimal, ponto = milhares
            s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # se parte decimal tem 2 dígitos, assume vírgula decimal
        part = s.split(",")[-1]
        if len(part) == 2:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    # else: só ponto -> assume ponto decimal
    try:
        return float(s)
    except ValueError:
        return 0.0
