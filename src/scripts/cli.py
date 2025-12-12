import os
import sys
import time
import argparse

from pathlib import Path
from .builder import build
from yaspin import yaspin
from prompt_toolkit.formatted_text import FormattedText, HTML
from prompt_toolkit.shortcuts import print_formatted_text
from configs.style import LOGO, LOGO_PALLET, STYLE                          

# override print with feature-rich ``print_formatted_text`` from prompt_toolkit
print = print_formatted_text

def welcome():
    """
    Cria uma animação em console para a arte ASCII "TexFlow".
    """
    # A arte ASCII é dividida em linhas para animar a exibição.

    # Limpa o console
    os.system('cls' if os.name == 'nt' else 'clear')
    
    with yaspin() as sp:
        
        try:
            
            os.system('cls' if os.name == 'nt' else 'clear')
            
            for i, line in enumerate(LOGO):
                cor = LOGO_PALLET[i % len(LOGO_PALLET)]
                # FormattedText é confiável: tuple (style, text)
                ft = FormattedText([(f"fg:{cor} bold", line)])
                with sp.hidden():
                    print_formatted_text(ft, style=STYLE)
                time.sleep(0.01)
            
            sp.stop()
        
        except TypeError as e:
            print(HTML(
                f'<error> > </error> <error> Erro: </error>'
                f'<error-msg> {e} </error-msg>'
            ), style=STYLE)
            sp.fail("🐛")
        
        except Exception as e:
            sp.fail("✖")
            with sp.hidden():
                print_formatted_text(FormattedText([("fg:#ff0000 bold", f"Erro: {e}")]), style=STYLE)
            sp.fail("🐛")

# Obtém o caminho absoluto da pasta onde o script está sendo executado
root_path = Path(__file__).resolve().parent

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
        
        if passed_args == 0:
            welcome()
            raise Exception()

        elif args.build and args.input:
            welcome()
            build(args.input, args.template)
        
        else:
            raise Exception("[❌]\n")
    
    except Exception as e:
        # Se você quiser que o script encerre ou mostre a ajuda aqui, você teria que fazer explicitamente:
        print(f"{e}")
        parser.print_help()
        sys.exit(1)             # Encerra com código de erro