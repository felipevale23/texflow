#!/usr/bin/env bash
# Compila o TexFlow em um binário standalone (PyInstaller) e instala no PATH do usuário.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

BIN_NAME="texflow"
INSTALL_DIR="${TEXFLOW_INSTALL_DIR:-$HOME/.local/bin}"

if ! command -v uv >/dev/null 2>&1; then
    echo "❌ uv não encontrado. Instale em https://docs.astral.sh/uv/ e rode este script novamente." >&2
    exit 1
fi

if ! command -v xelatex >/dev/null 2>&1 || ! command -v latexmk >/dev/null 2>&1; then
    echo "⚠️  xelatex/latexmk não encontrados no PATH. O binário será gerado," >&2
    echo "   mas você precisa de uma distribuição LaTeX (TeX Live/MiKTeX) para compilar documentos." >&2
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
