#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v mkvmerge &>/dev/null; then
    echo "ERROR: mkvmerge not found."
    echo "Install via Homebrew:"
    echo "  brew install mkvtoolnix"
    exit 1
fi
echo "mkvmerge: $(which mkvmerge) ($(mkvmerge --version | head -1))"

source "$SCRIPT_DIR"/.venv/bin/activate
rm -rf "$SCRIPT_DIR"/build/
rm -rf "$SCRIPT_DIR"/dist/
rm -rf "$SCRIPT_DIR"/mkv_trim.spec

bin=$(which pyinstaller)
echo "$bin"

"$bin" --onedir --strip --noconfirm \
    --add-data "$SCRIPT_DIR/data/help.txt:data" \
    --add-data "$SCRIPT_DIR/data/default_weights.json:data" \
    --add-binary "$(which mkvmerge):." \
    "$SCRIPT_DIR"/mkv_trim.py

deactivate

DIST_DIR="$SCRIPT_DIR/dist/mkv_trim"
INSTALL_DIR="/usr/local/lib/mkv_trim"

# ad-hoc sign — satisfies Gatekeeper without a paid Developer ID
codesign --force --deep --sign - "$DIST_DIR/mkv_trim"

# strip quarantine flag
xattr -cr "$DIST_DIR"

rm -rf "$INSTALL_DIR"
cp -r "$DIST_DIR" "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/mkv_trim"

rm -f /usr/local/bin/mkv_trim
ln -s "$INSTALL_DIR/mkv_trim" /usr/local/bin/mkv_trim
