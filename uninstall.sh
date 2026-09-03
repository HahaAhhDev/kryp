#!/bin/sh
set -e

INSTALL_DIR="${KRYP_INSTALL_DIR:-$HOME/.local/bin}"

echo "→ Uninstalling Kryp..."

if [ -f "$INSTALL_DIR/kryp" ]; then
    rm -f "$INSTALL_DIR/kryp"
    echo "✓ Removed binary"
else
    echo "⚠ Binary not found at $INSTALL_DIR/kryp"
fi

for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    if [ -f "$rc" ] && grep -q "# Kryp" "$rc"; then
        sed -i.bak '/# Kryp/,+1d' "$rc" && rm -f "${rc}.bak"
        echo "✓ Removed PATH entry from $rc"
    fi
done

echo "✓ Kryp uninstalled. Restart terminal to clear PATH."