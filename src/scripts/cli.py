import os
import sys
import time
import argparse
from pathlib import Path
from .builder import build
from yaspin import yaspin
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText, HTML
from prompt_toolkit.shortcuts import print_formatted_text

LOGO = [
    "  TTTTTTTTTTTTTTTTTTTTTTT                                  FFFFFFFFFFFFFFFFFFFFFFlllllll                                                           ",
    "  T:::::::::::::::::::::T                                  F::::::::::::::::::::Fl:::::l                                                           ",
    "  T:::::::::::::::::::::T                                  F::::::::::::::::::::Fl:::::l                                                           ",
    "  T:::::TT:::::::TT:::::T                                  FF::::::FFFFFFFFF::::Fl:::::l                                                           ",
    "  TTTTTT  T:::::T  TTTTTTeeeeeeeeeeee  xxxxxxx      xxxxxxx  F:::::F       FFFFFF l::::l    ooooooooooo wwwwwww           wwwww           wwwwwww  ",
    "          T:::::T      ee::::::::::::ee x:::::x    x:::::x   F:::::F              l::::l  oo:::::::::::oow:::::w         w:::::w         w:::::w   ",
    "          T:::::T     e::::::eeeee:::::eex:::::x  x:::::x    F::::::FFFFFFFFFF    l::::l o:::::::::::::::ow:::::w       w:::::::w       w:::::w    ",
    "          T:::::T    e::::::e     e:::::e x:::::xx:::::x     F:::::::::::::::F    l::::l o:::::ooooo:::::o w:::::w     w:::::::::w     w:::::w     ",
    "          T:::::T    e:::::::eeeee::::::e  x::::::::::x      F:::::::::::::::F    l::::l o::::o     o::::o  w:::::w   w:::::w:::::w   w:::::w      ",
    "          T:::::T    e:::::::::::::::::e    x::::::::x       F::::::FFFFFFFFFF    l::::l o::::o     o::::o   w:::::w w:::::w w:::::w w:::::w       ",
    "          T:::::T    e::::::eeeeeeeeeee     x::::::::x       F:::::F              l::::l o::::o     o::::o    w:::::w:::::w   w:::::w:::::w        ",
    "          T:::::T    e:::::::e             x::::::::::x      F:::::F              l::::l o::::o     o::::o     w:::::::::w     w:::::::::w         ",
    "        TT:::::::TT  e::::::::e           x:::::xx:::::x   FF:::::::FF           l::::::lo:::::ooooo:::::o      w:::::::w       w:::::::w          ",
    "        T:::::::::T   e::::::::eeeeeeee  x:::::x  x:::::x  F::::::::FF           l::::::lo:::::::::::::::o       w:::::w         w:::::w           ",
    "        T:::::::::T    ee:::::::::::::e x:::::x    x:::::x F::::::::FF           l::::::l oo:::::::::::oo         w:::w           w:::w            ",
    "        TTTTTTTTTTT      eeeeeeeeeeeeeexxxxxxx      xxxxxxxFFFFFFFFFFF           llllllll   ooooooooooo            www             www             "
]

# override print with feature-rich ``print_formatted_text`` from prompt_toolkit
print = print_formatted_text

# Estilo para mensagens com HTML customizado
style = Style.from_dict({
    # Mensagem principal
    'msg':        'bold #93FF96',   # verde + negrito
    # Mensagem principal
    'cmd':        'bold #AA7DCE',   # magenta
    # Sub-mensagem ou descrição
    'sub-msg':    'italic #616161', # cinza + itálico
    # Mensagem de aviso
    'warning':    'bold #ff9800',   # laranja
    # Mensagem de erro
    'error':      'bold #f44336',   # vermelho
    # Mensagem de erro
    'error-msg':    'italic #f44336', # cinza + itálico
    # Cabeçalhos ou títulos
    'header':     'bold underline #2196f3'  # azul + sublinhado
})

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
            
            # cores por linha (pode usar quantas quiser, vai ciclar)
            cores = [
                "#ff0000", "#ff7f00", "#ffff00", "#7fff00",
                "#00ff00", "#00ff7f", "#00ffff", "#007fff",
                "#0000ff", "#7f00ff", "#ff00ff", "#ff007f"
            ]
            
            for i, line in enumerate(LOGO):
                cor = cores[i % len(cores)]
                # FormattedText é confiável: tuple (style, text)
                ft = FormattedText([(f"fg:{cor} bold", line)])
                with sp.hidden():
                    print_formatted_text(ft, style=style)
                time.sleep(0.01)
            
            sp.stop()
        
        except TypeError as e:
            print(HTML(
                f'<error> > </error> <error> Erro: </error>'
                f'<error-msg> {e} </error-msg>'
            ), style=style)
            sp.fail("🐛")
        
        except Exception as e:
            sp.fail("✖")
            with sp.hidden():
                print_formatted_text(FormattedText([("fg:#ff0000 bold", f"Erro: {e}")]), style=style)
            sp.fail("🐛")

# Obtém o caminho absoluto da pasta onde o script está sendo executado
root_path = Path(__file__).resolve().parent

def cli():
    
    # 1. Cria um objeto ArgumentParser
    parser = argparse.ArgumentParser(
        description="Este script faz simulações de geração fotovoltaica e cria documentos com base nos dados obtidos",
        epilog="Use com sabedoria!"
    )
    
    # 2. Argumento opcional com flag curta e longa
    parser.add_argument(
        "-b", "--build",
        action="store_true",
        help="Faz o build com base no template latex. O valor será 'True' se esta flag for usada."
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

        elif args.build:
            welcome()
            build()
        
        else:
            raise Exception("[❌]\n")
    
    except Exception as e:
        # Se você quiser que o script encerre ou mostre a ajuda aqui, você teria que fazer explicitamente:
        print(f"{e}")
        parser.print_help()
        sys.exit(1)             # Encerra com código de erro