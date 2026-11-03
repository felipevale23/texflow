"""Cache do biber pro engine Tectonic.

O Tectonic roda o biber a cada build, mesmo quando só o texto mudou. O
latexmk evita isso comparando as entradas; aqui o TexFlow faz o mesmo: põe
na frente do PATH do Tectonic um "biber" (shim, script sh) que calcula um
hash das entradas (o .bcf e os .bib que o Tectonic copia pra pasta
temporária onde roda o biber, mais o caminho/tamanho/data do binário do
biber) e, se for igual ao do último build, devolve o .bbl/.blg guardados em
vez de rodar o biber. Uma citação nova ou um .bib editado mudam o hash e o
biber roda.

O shim é sh puro de propósito: chamar o próprio TexFlow custaria a partida
do binário do PyInstaller (~1 s), quase o tempo do biber que ele economiza.
"""

import os
import shlex
from pathlib import Path

# Dentro de build/ (o CopyTree nunca copia build/, e é oculta).
CACHE_DIRNAME = ".texflow-cache"

SHIM_TEMPLATE = r"""#!/bin/sh
# Gerado pelo TexFlow: cache do biber pro Tectonic (ver scripts/bibcache.py).
# Roda na pasta temporária onde o Tectonic chama o biber.
real={real}
cache={cache}

for last in "$@"; do :; done
stem=$(basename "${{last:-main}}" .bcf)

if command -v sha256sum >/dev/null 2>&1; then
    hash() {{ sha256sum | cut -d' ' -f1; }}
else
    hash() {{ shasum -a 256 | cut -d' ' -f1; }}
fi

# Entradas: o binário do biber (caminho, tamanho, data) e todos os arquivos
# da pasta (menos as saídas), com o caminho relativo de cada um.
digest=$(
    {{
        ls -lnL "$real"
        find . -type f ! -name '*.bbl' ! -name '*.blg' | LC_ALL=C sort | while IFS= read -r f; do
            printf '\n%s\n' "$f"
            cat "$f"
        done
    }} | hash
)

if [ -f "$cache/$stem.bbl" ] && [ "$(cat "$cache/biber.digest" 2>/dev/null)" = "$digest" ]; then
    cp "$cache/$stem.bbl" .
    [ -f "$cache/$stem.blg" ] && cp "$cache/$stem.blg" .
    echo "texflow: entradas do biber iguais ao build anterior; usando o .bbl em cache."
    exit 0
fi

rm -f "$cache/biber.digest"
"$real" "$@"
rc=$?
if [ "$rc" -eq 0 ] && [ -f "$stem.bbl" ]; then
    cp "$stem.bbl" "$cache/"
    [ -f "$stem.blg" ] && cp "$stem.blg" "$cache/"
    printf '%s' "$digest" > "$cache/biber.digest"
fi
exit "$rc"
"""


def cache_enabled() -> bool:
    """TEXFLOW_NO_CACHE=1 desliga o cache. No Windows o shim (script sh)
    não funciona, então fica desligado."""
    return os.getenv("TEXFLOW_NO_CACHE") != "1" and os.name != "nt"


def install_shim(build_dir: Path, real_biber: Path) -> Path:
    """Escreve build/.texflow-cache/bin/biber e devolve a pasta dele, pra ir
    na frente do PATH do Tectonic."""
    cache_dir = (build_dir / CACHE_DIRNAME).resolve()
    bin_dir = cache_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "biber"
    text = SHIM_TEMPLATE.format(
        real=shlex.quote(str(Path(real_biber).resolve())),
        cache=shlex.quote(str(cache_dir)),
    )
    if not shim.is_file() or shim.read_text(encoding="utf-8") != text:
        shim.write_text(text, encoding="utf-8")
    shim.chmod(0o755)
    return bin_dir
