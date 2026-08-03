import argparse
import os
import sys
import time
from pathlib import Path

from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.shortcuts import print_formatted_text

from configs.spinner import spinner
from configs.style import LOGO, LOGO_PALLET, STYLE

from .builder import build

# override print with feature-rich ``print_formatted_text`` from prompt_toolkit
print = print_formatted_text

def welcome():
    """
    Cria uma animação em console para a arte ASCII "TexFlow".
    """
    # A arte ASCII é dividida em linhas para animar a exibição.

    # Limpa o console
    os.system('cls' if os.name == 'nt' else 'clear')
    
    with spinner() as sp:
        
        try:
            
            os.system('cls' if os.name == 'nt' else 'clear')
            
            for i, line in enumerate(LOGO):
                cor = LOGO_PALLET[i % len(LOGO_PALLET)]
                # FormattedText é confiável: tuple (style, text)
                ft = FormattedText([(f"fg:{cor} bold", line)])
                with sp.hidden():
                    print_formatted_text(ft, style=STYLE, file=sys.stderr)
                time.sleep(0.01)
            
            sp.stop()
        
        except TypeError as e:
            print(HTML(
                f'<error> > </error> <error> Erro: </error>'
                f'<error-msg> {e} </error-msg>'
            ), style=STYLE, file=sys.stderr)
            sp.fail("🐛")
        
        except Exception as e:  # noqa: BLE001 - error boundary da animação, precisa reportar qualquer falha
            sp.fail("✖")
            with sp.hidden():
                print_formatted_text(FormattedText([("fg:#ff0000 bold", f"Erro: {e}")]), style=STYLE, file=sys.stderr)
            sp.fail("🐛")

# Obtém o caminho absoluto da pasta onde o script está sendo executado
root_path = Path(__file__).resolve().parent

class UsageError(Exception):
    """Argumentos de linha de comando ausentes ou inválidos."""

def cli():
    
    # 1. Cria um objeto ArgumentParser
    parser = argparse.ArgumentParser(
        description="Este script cria documentos com base nos dados inseridos",
        epilog="Use com sabedoria!"
    )
    
    # 2. Argumento opcional com flag curta e longa
    parser.add_argument(
        "-b", "--build",
        action="store_true",
        help="Faz o build com base no template latex. O valor será 'True' se esta flag for usada."
    )
    
    # Argumento opcional com flag curta e longa
    parser.add_argument(
        "-i", "--input",
        type=str,
        nargs='?',
        help="Arquivo JSON de input"
    )
    
    # Argumento opcional com flag curta e longa
    parser.add_argument(
        "-t", "--template",
        type=str,
        default="journal",
        nargs='?',
        help="Caminho para a PASTA do template"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Mostra logs detalhados"
    )
    
    # 3. Faz o parsing dos argumentos da linha de comando
    args = parser.parse_args()
    
    # Método correto para contar argumentos passados
    def count_passed_args(args, parser):
        count = 0
        for dest, value in vars(args).items():
            # Obtém o valor padrão do parser usando o nome do atributo (dest)
            default = parser.get_default(dest)
            if value != default:
                count += 1
        return count
    
    try:
        passed_args = count_passed_args(args, parser)
        
        if args.debug:
            os.environ["TEXFLOW_DEBUG"] = "1"
    
        if passed_args == 0:
            welcome()
            raise UsageError()

        elif args.build and args.input:
            welcome()
            build(args.input, args.template)

        else:
            raise UsageError("[❌]\n")

    except Exception as e:  # noqa: BLE001 - também precisa capturar falhas de build(), não só UsageError
        # Se você quiser que o script encerre ou mostre a ajuda aqui, você teria que fazer explicitamente:
        print(f"{e}", file=sys.stderr)
        parser.print_help()
        sys.exit(1)             # Encerra com código de erro