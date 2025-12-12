from prompt_toolkit.styles import Style

LOGO_PALLET = [
    "#ff0000", "#ff7f00", "#ffff00", "#7fff00",
    "#00ff00", "#00ff7f", "#00ffff", "#007fff",
    "#0000ff", "#7f00ff", "#ff00ff", "#ff007f"
]

# Estilo para mensagens com HTML customizado
STYLE = Style.from_dict({
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
    'error-msg':  'italic #f44336', # cinza + itálico
    # Cabeçalhos ou títulos
    'header':     'bold underline #2196f3'  # azul + sublinhado
})

LOGO = [                                        
    "TTTTTTTT                      FFFFFFFF  LLLL                         ",
    "########                      ########  ####                         ",
    "   ##                         ##          ##                         ",
    "   ##      .eeee:   xxx  xxx  ##          ##       .OOOO.  WW      WW",
    "   ##     .######:   ##::##   ##          ##      .######. ##.    .##",
    "   ##     ##:  :##   :####:   #######     ##      ###  ###  #: ## :# ",
    "   ##     ########    ####    #######     ##      ##.  .## :#:.##.:#:",
    "   ##     ########    :##:    ##          ##      ##    ##  # :##:## ",
    "   ##     ##          ####    ##          ##      ##.  .##  ## ## ## ",
    "   ##     ###.  :#   :####:   ##          ##:     ###  ###  ###::##  ",
    "   ##     .#######   ##::##   ##          #####   .######.  :##..##: ",
    "   ##      .#####:  ###  ###  ##          .####    .####.   .##  ##  \n"
]