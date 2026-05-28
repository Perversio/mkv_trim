#!/bin/bash
# deploy_alpine.sh — build mkv_trim inside an Alpine container.
# Use this when the target runs Alpine Linux (e.g. linuxserver.io Docker images).
# Output: dist/mkv_trim/  (Alpine-compatible binary)
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker run --rm \
    -v "$SCRIPT_DIR":/src \
    -w /src \
    alpine:3.21 sh -c '
        set -e
        apk add --no-cache python3 py3-pip py3-venv mkvtoolnix binutils

        echo "mkvmerge: $(which mkvmerge) ($(mkvmerge --version | head -1))"

        PY_VER=$(python3 -c "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")")
        echo "python3: $(which python3) ($PY_VER)"

        python3 -m venv .venv_alpine
        .venv_alpine/bin/pip install --quiet --upgrade pip
        .venv_alpine/bin/pip install --quiet pyinstaller tqdm humanize pyyaml

        rm -rf build/ dist/ mkv_trim.spec

        .venv_alpine/bin/pyinstaller --onefile --strip --noconfirm \
            --add-data data/help.txt:data \
            --add-data data/default_weights.yaml:data \
            --add-data data/languages.json:data \
            --add-binary "$(which mkvmerge):." \
            mkv_trim.py

        echo "Build complete."
    '

echo "Done. Alpine binary at $SCRIPT_DIR/dist/mkv_trim"
echo "Copy dist/mkv_trim to your container scripts folder."
