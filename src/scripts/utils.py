import re
import tempfile
from pathlib import Path

def is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=path):
            pass
        return True
    except Exception:
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
