#!/bin/sh
set -e

REPO="https://github.com/hahaahhdev/kryp.git"
INSTALL_DIR="${KRYP_INSTALL_DIR:-$HOME/.local/bin}"
BUILD_DIR="$(mktemp -d)"

cleanup() { rm -rf "$BUILD_DIR"; }
trap cleanup EXIT

# Detect OS
case "$(uname -s)" in
    Linux*)               PKG_MGR="linux";;
    Darwin*)              PKG_MGR="macos";;
    MINGW*|MSYS*|CYGWIN*) PKG_MGR="windows";;
    *) echo "✗ Unsupported OS: $(uname -s)"; exit 1;;
esac
echo "→ Detected: $PKG_MGR"

# Install dependencies
install_deps() {
    case "$PKG_MGR" in
        linux)
            if command -v apt >/dev/null 2>&1; then
                sudo apt update && sudo apt install -y zig python3.12-dev python3-pip git
            elif command -v dnf >/dev/null 2>&1; then
                sudo dnf install -y zig python3.12-devel python3-pip git
            elif command -v pacman >/dev/null 2>&1; then
                sudo pacman -Sy --noconfirm zig python python-pip git
            elif command -v apk >/dev/null 2>&1; then
                sudo apk add zig python3-dev py3-pip git
            else
                echo "✗ No supported package manager. Install zig, python3.12-dev, pip, git manually."
                exit 1
            fi
            ;;
        macos)
            if ! command -v brew >/dev/null 2>&1; then
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            fi
            brew install zig python@3.12 git
            ;;
        windows)
            echo "→ Windows detected. Use WSL/Git Bash to run this script."
            echo "  Native: winget install zig.python, then build manually."
            exit 0
            ;;
    esac
}

# Build & install
build_kryp() {
    echo "→ Cloning Kryp..."
    git clone "$REPO" "$BUILD_DIR/kryp"
    cd "$BUILD_DIR/kryp"

    echo "→ Building (ReleaseFast)..."
    zig build -Doptimize=ReleaseFast

    echo "→ Installing to $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    cp zig-out/bin/kryp "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/kryp"
}

# Add to PATH persistently
setup_path() {
    case ":$PATH:" in
        *":$INSTALL_DIR:"*) echo "→ Already in PATH";;
        *)
            if [ -n "$ZSH_VERSION" ] || [ "$(basename "$SHELL")" = "zsh" ]; then
                RC="$HOME/.zshrc"
            elif [ -f "$HOME/.bashrc" ]; then
                RC="$HOME/.bashrc"
            else
                RC="$HOME/.profile"
            fi
            printf '\n# Kryp language executor\nexport PATH="%s:$PATH"\n' "$INSTALL_DIR" >> "$RC"
            export PATH="$INSTALL_DIR:$PATH"
            echo "→ Added to $RC — restart terminal or run: source $RC"
            ;;
    esac
}

# Main
install_deps
build_kryp
setup_path

echo ""
echo "✓ Kryp installed!"
echo "  kryp run <file.kryp>      Interpret source"
echo "  kryp compile <file.kryp>  Obfuscate to .kryc"
echo "  kryp run <file.kryc>      Run compiled"
echo "  kryp install <pkg>        Install Python package"