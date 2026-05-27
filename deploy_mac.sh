#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- check mkvmerge ---
if ! command -v mkvmerge &>/dev/null; then
    echo "ERROR: mkvmerge not found."
    echo "Install via Homebrew:"
    echo "  brew install mkvtoolnix"
    exit 1
fi
echo "mkvmerge: $(which mkvmerge) ($(mkvmerge --version | head -1))"

# --- check python3 ---
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    echo "Install via Homebrew:"
    echo "  brew install python"
    exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MIN="3.10"
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"; then
    echo "ERROR: Python $PY_MIN+ required, found $PY_VER"
    echo "Install via Homebrew:"
    echo "  brew install python"
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

rm -rf "$SCRIPT_DIR"/build/
rm -rf "$SCRIPT_DIR"/dist/
rm -rf "$SCRIPT_DIR"/mkv_trim.spec

bin=$(which pyinstaller)
echo "pyinstaller: $bin"

"$bin" --onefile --strip --noconfirm \
    --add-data "$SCRIPT_DIR/data/help.txt:data" \
    --add-data "$SCRIPT_DIR/data/default_weights.json:data" \
    --add-data "$SCRIPT_DIR/data/languages.json:data" \
    --add-binary "$(which mkvmerge):." \
    "$SCRIPT_DIR"/mkv_trim.py

deactivate

DIST_BIN="$SCRIPT_DIR/dist/mkv_trim"
INSTALL_BIN="/usr/local/bin/mkv_trim"

# ad-hoc sign — satisfies Gatekeeper without a paid Developer ID
codesign --force --sign - "$DIST_BIN"

# strip quarantine flag
xattr -c "$DIST_BIN"

# Remove any prior install (older dir-layout + symlink).
rm -rf /usr/local/lib/mkv_trim
rm -f "$INSTALL_BIN"

install -m 0755 "$DIST_BIN" "$INSTALL_BIN"

echo "Done. mkv_trim installed at $INSTALL_BIN"
