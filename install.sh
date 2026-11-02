#!/usr/bin/env bash
# Compila o TexFlow em um binário standalone (PyInstaller) e instala no PATH do usuário.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

BIN_NAME="texflow"
INSTALL_DIR="${TEXFLOW_INSTALL_DIR:-$HOME/.local/bin}"
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

echo "🔨 Compilando binário standalone com PyInstaller..."
uv run --group build pyinstaller \
    --noconfirm \
    --clean \
    --onefile \
    --name "$BIN_NAME" \
    --paths src \
    --add-data "$REPO_ROOT/assets:assets" \
    --collect-data yaspin \
    --hidden-import ssl \
    "${EXTRA_PYINSTALLER_ARGS[@]}" \
    --distpath dist \
    --workpath .pyinstaller-build \
    --specpath .pyinstaller-build \
    src/main.py

mkdir -p "$INSTALL_DIR"
install -m 755 "dist/$BIN_NAME" "$INSTALL_DIR/$BIN_NAME"

echo "✅ Binário instalado em: $INSTALL_DIR/$BIN_NAME"

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
