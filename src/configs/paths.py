from pathlib import Path
from importlib.resources import files

BUILD_DIR = Path("build")  # OK: é diretório do usuário, não do pacote

# Pacote assets dentro do wheel (não é Path físico)
ASSETS_DIR = files("assets")

# Diretório de templates empacotados
TEMPLATE_DIR = ASSETS_DIR.joinpath("templates")