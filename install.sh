#!/bin/sh
set -e

INSTALL_DIR="${KRYP_INSTALL_DIR:-$HOME/.local/bin}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_INCLUDE="/usr/local/include/python3.12"
PYTHON_LIB="/usr/local/lib"

echo "→ Building Kryp..."
gcc -O2 -o kryp "$SCRIPT_DIR/kryp.c" \
    -I"$PYTHON_INCLUDE" \
    -L"$PYTHON_LIB" \
    -lpython3.12 \
    -lm \
    -Wl,-rpath,"$PYTHON_LIB"

echo "→ Installing to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp kryp "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/kryp"
rm -f kryp

# Add to PATH if needed
case ":$PATH:" in
    *":$INSTALL_DIR:"*) ;;
    *)
        RC="$HOME/.bashrc"
        [ -n "$ZSH_VERSION" ] && RC="$HOME/.zshrc"
        printf '\n# Kryp\nexport PATH="%s:$PATH"\n' "$INSTALL_DIR" >> "$RC"
        echo "→ Added to $RC — restart terminal or: source $RC"
        ;;
esac

echo "✓ Kryp installed! Run: kryp run <file.kryp>"