#!/bin/sh
set -e

INSTALL_DIR="${KRYP_INSTALL_DIR:-$HOME/.local/bin}"
BINARY="$INSTALL_DIR/kryp"

echo "→ Uninstalling Kryp..."

# Remove binary
if [ -f "$BINARY" ]; then
    rm -f "$BINARY"
    echo "✓ Removed $BINARY"
else
    echo "⚠ Binary not found at $BINARY"
fi

# Remove PATH entry from shell configs
for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    if [ -f "$rc" ] && grep -q "# Kryp language executor" "$rc"; then
        # Remove the comment + export line (2 lines)
        sed -i.bak '/# Kryp language executor/,+1d' "$rc" && rm -f "${rc}.bak"
        echo "✓ Removed PATH entry from $rc"
    fi
done

# Remove local venv if exists
VENV_DIR="$HOME/.kryp_venv"
if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
    echo "✓ Removed virtual environment $VENV_DIR"
fi

# Remove cached packages metadata
CACHE_DIR="$HOME/.cache/kryp"
if [ -d "$CACHE_DIR" ]; then
    rm -rf "$CACHE_DIR"
    echo "✓ Removed cache $CACHE_DIR"
fi

echo ""
echo "✓ Kryp uninstalled completely."
echo "  Restart your terminal to clear PATH changes."