#!/usr/bin/env bash
# Compila o TexFlow com o PyInstaller e instala no PATH do usuário.
#
# Por padrão gera uma PASTA (--onedir): o executável fica em
# $TEXFLOW_LIB_DIR (~/.local/lib/texflow) com um symlink em
# $TEXFLOW_INSTALL_DIR (~/.local/bin). Ele parte em ~0,3 s; o arquivo único
# (--onefile) se descompacta a cada execução e leva ~1,3 s, o que pesa em
# cada build ao salvar. TEXFLOW_ONEFILE=1 gera o arquivo único mesmo assim.
#
# Também deixa em dist/ o pacote da release: texflow-<so>-<arch>.tar.gz
# (pasta) ou texflow-<so>-<arch> (arquivo único).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

BIN_NAME="texflow"
INSTALL_DIR="${TEXFLOW_INSTALL_DIR:-$HOME/.local/bin}"
LIB_DIR="${TEXFLOW_LIB_DIR:-$HOME/.local/lib/texflow}"
ONEFILE="${TEXFLOW_ONEFILE:-0}"
ASSET_NAME="texflow-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m | tr '[:upper:]' '[:lower:]')"
# TEXFLOW_BUNDLE_TECTONIC=1 embute o binário do Tectonic no executável,
# pra compilar com --engine tectonic sem TeX Live instalado.
BUNDLE_TECTONIC="${TEXFLOW_BUNDLE_TECTONIC:-0}"

if ! command -v uv >/dev/null 2>&1; then
    echo "❌ uv não encontrado. Instale em https://docs.astral.sh/uv/ e rode este script novamente." >&2
    exit 1
fi

if [ "$BUNDLE_TECTONIC" != "1" ] && { ! command -v xelatex >/dev/null 2>&1 || ! command -v latexmk >/dev/null 2>&1; }; then
    echo "⚠️  xelatex/latexmk não encontrados no PATH. O binário será gerado," >&2
    echo "   mas você precisa de uma distribuição LaTeX (TeX Live/MiKTeX) para compilar documentos." >&2
    echo "   Alternativa: TEXFLOW_BUNDLE_TECTONIC=1 ./install.sh embute o Tectonic (--engine tectonic)." >&2
fi

EXTRA_PYINSTALLER_ARGS=()
if [ "$BUNDLE_TECTONIC" = "1" ]; then
    if [ "$(uname -s)" != "Linux" ] || [ "$(uname -m)" != "x86_64" ]; then
        echo "❌ TEXFLOW_BUNDLE_TECTONIC=1 só é suportado em Linux x86_64." >&2
        exit 1
    fi

    TECTONIC_TMP="$(mktemp -d)"
    trap 'rm -rf "$TECTONIC_TMP"' EXIT

    echo "🦀 Buscando a última release do Tectonic no GitHub..."
    # Build musl: estático, roda em qualquer distro sem depender da glibc/ICU do sistema.
    TECTONIC_URL="$(
        curl -fsSL https://api.github.com/repos/tectonic-typesetting/tectonic/releases/latest \
            | grep -o '"browser_download_url": *"[^"]*x86_64-unknown-linux-musl\.tar\.gz"' \
            | head -n 1 \
            | sed 's/.*"\(https[^"]*\)"/\1/'
    )"
    if [ -z "$TECTONIC_URL" ]; then
        echo "❌ Não encontrei o binário Linux x86_64 (musl) na última release do Tectonic." >&2
        exit 1
    fi

    echo "⬇️  Baixando $TECTONIC_URL"
    curl -fsSL "$TECTONIC_URL" -o "$TECTONIC_TMP/tectonic.tar.gz"
    tar -xzf "$TECTONIC_TMP/tectonic.tar.gz" -C "$TECTONIC_TMP" tectonic
    chmod +x "$TECTONIC_TMP/tectonic"
    echo "   $("$TECTONIC_TMP/tectonic" --version)"

    # Vai pra raiz do sys._MEIPASS, onde resolve_tectonic() procura.
    EXTRA_PYINSTALLER_ARGS+=(--add-binary "$TECTONIC_TMP/tectonic:.")
fi

echo "📦 Sincronizando dependências (incluindo pyinstaller)..."
uv sync --group build

if [ "$ONEFILE" = "1" ]; then
    MODE_ARGS=(--onefile)
else
    MODE_ARGS=(--onedir)
fi

echo "🔨 Compilando com PyInstaller (${MODE_ARGS[0]})..."
rm -rf "dist/$BIN_NAME"
# --strip: o Python do uv vem com símbolos de debug (libpython ~200 MB).
# --exclude-module: matplotlib/pandas são dependências pros scripts do
# usuário, que não importam nada de dentro do binário; o TexFlow não usa.
uv run --group build pyinstaller \
    --noconfirm \
    --clean \
    "${MODE_ARGS[@]}" \
    --strip \
    --name "$BIN_NAME" \
    --paths src \
    --add-data "$REPO_ROOT/assets:assets" \
    --collect-data yaspin \
    --hidden-import ssl \
    --exclude-module matplotlib \
    --exclude-module pandas \
    --exclude-module numpy \
    --exclude-module PIL \
    "${EXTRA_PYINSTALLER_ARGS[@]}" \
    --distpath dist \
    --workpath .pyinstaller-build \
    --specpath .pyinstaller-build \
    src/main.py

mkdir -p "$INSTALL_DIR"
if [ "$ONEFILE" = "1" ]; then
    cp "dist/$BIN_NAME" "dist/$ASSET_NAME"
    # rm antes: se havia um symlink da instalação em pasta, o install
    # escreveria através dele.
    rm -f "$INSTALL_DIR/$BIN_NAME"
    install -m 755 "dist/$BIN_NAME" "$INSTALL_DIR/$BIN_NAME"
    echo "✅ Binário instalado em: $INSTALL_DIR/$BIN_NAME"
else
    tar -C dist -czf "dist/$ASSET_NAME.tar.gz" "$BIN_NAME"
    # Troca a pasta inteira de uma vez: sobra nada da versão anterior. Só
    # apaga uma pasta que seja uma instalação do TexFlow (tem _internal/ e o
    # executável), pra um TEXFLOW_LIB_DIR errado não levar outra coisa junto.
    if [ -e "$LIB_DIR" ] && ! { [ -d "$LIB_DIR/_internal" ] && [ -x "$LIB_DIR/$BIN_NAME" ]; }; then
        echo "❌ $LIB_DIR já existe e não é uma instalação do TexFlow. Aponte TEXFLOW_LIB_DIR pra outra pasta." >&2
        exit 1
    fi
    mkdir -p "$(dirname "$LIB_DIR")"
    rm -rf "$LIB_DIR.new"
    cp -a "dist/$BIN_NAME" "$LIB_DIR.new"
    rm -rf "$LIB_DIR"
    mv "$LIB_DIR.new" "$LIB_DIR"
    ln -sfn "$LIB_DIR/$BIN_NAME" "$INSTALL_DIR/$BIN_NAME"
    echo "✅ Instalado em: $LIB_DIR (symlink em $INSTALL_DIR/$BIN_NAME)"
fi
echo "   Pacote da release: dist/$([ "$ONEFILE" = "1" ] && echo "$ASSET_NAME" || echo "$ASSET_NAME.tar.gz")"

case ":$PATH:" in
    *":$INSTALL_DIR:"*) ;;
    *)
        echo "⚠️  $INSTALL_DIR não está no seu PATH."
        echo "   Adicione ao seu shell rc (ex: ~/.bashrc ou ~/.zshrc):"
        echo "   export PATH=\"$INSTALL_DIR:\$PATH\""
        ;;
esac

echo ""
echo "Teste com: $BIN_NAME --build --input <dados.json> --template <pasta_do_template>"
