#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- check mkvmerge ---
if ! command -v mkvmerge &>/dev/null; then
    echo "ERROR: mkvmerge not found."
    echo "Install via package manager:"
    echo "  Ubuntu/Debian: sudo apt install mkvtoolnix"
    echo "  Fedora/RHEL:   sudo dnf install mkvtoolnix"
    echo "  Arch:          sudo pacman -S mkvtoolnix-cli"
    exit 1
fi
echo "mkvmerge: $(which mkvmerge) ($(mkvmerge --version | head -1))"

# --- check python3 ---
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    echo "Install via package manager:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv"
    echo "  Fedora/RHEL:   sudo dnf install python3"
    echo "  Arch:          sudo pacman -S python"
    exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MIN="3.10"
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"; then
    echo "ERROR: Python $PY_MIN+ required, found $PY_VER"
    echo "Install via package manager:"
    echo "  Ubuntu/Debian: sudo apt install python3.10"
    echo "  Fedora/RHEL:   sudo dnf install python3.10"
    echo "  Arch:          sudo pacman -S python"
    exit 1
fi
echo "python3: $(which python3) ($PY_VER)"

# --- create venv if missing ---
if [ ! -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/.venv"
fi

source "$SCRIPT_DIR/.venv/bin/activate"

# --- install / upgrade dependencies ---
echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet pyinstaller tqdm humanize

sudo rm -rf "$SCRIPT_DIR"/build/
sudo rm -rf "$SCRIPT_DIR"/dist/
sudo rm -rf "$SCRIPT_DIR"/mkv_trim.spec

bin=$(which pyinstaller)
echo "pyinstaller: $bin"

"$bin" --onedir --strip --noconfirm \
    --add-data "$SCRIPT_DIR/data/help.txt:data" \
    --add-data "$SCRIPT_DIR/data/default_weights.json:data" \
    --add-data "$SCRIPT_DIR/data/languages.json:data" \
    --add-binary "$(which mkvmerge):." \
    "$SCRIPT_DIR"/mkv_trim.py

deactivate

DIST_DIR="$SCRIPT_DIR/dist/mkv_trim"
INSTALL_DIR="/usr/local/lib/mkv_trim"

# --- install (requires root) ---
if [ "$(id -u)" -ne 0 ]; then
    echo "Installing to $INSTALL_DIR (requires sudo)..."
    SUDO=sudo
else
    SUDO=""
fi

$SUDO rm -rf "$INSTALL_DIR"
$SUDO cp -r "$DIST_DIR" "$INSTALL_DIR"
$SUDO chmod +x "$INSTALL_DIR/mkv_trim"

$SUDO rm -f /usr/local/bin/mkv_trim
$SUDO ln -s "$INSTALL_DIR/mkv_trim" /usr/local/bin/mkv_trim

echo "Done. mkv_trim installed at /usr/local/bin/mkv_trim"
