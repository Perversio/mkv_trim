#!/bin/bash
# import.sh — mkv_trim wrapper for Radarr/Sonarr "Import Using Script" mode.
#
# Radarr:  Settings > Media Management > Import Using Script
# Sonarr:  Settings > Media Management > Import Using Script
# Path:    /path/to/mkv_trim/import.sh
#
# Edit -a to match your language preferences.
# Do NOT use -L here — destination is provided by *arr via env var.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MKV_TRIM="$SCRIPT_DIR/mkv_trim"

# Radarr uses radarr_sourcepath / radarr_destinationpath
# Sonarr uses sonarr_sourcepath / sonarr_destinationpath
SOURCE="${radarr_sourcepath:-$sonarr_sourcepath}"
DEST="${radarr_destinationpath:-$sonarr_destinationpath}"

if [ -z "$SOURCE" ] || [ -z "$DEST" ]; then
    echo "Error: source or destination path not set by *arr" >&2
    exit 1
fi

"$MKV_TRIM" smart \
    -a ukr,eng,jpn,und \
    -o "$DEST" \
    "$SOURCE"

# If mkv_trim skipped the file (unsupported format, etc.) and destination
# was not written, fall back to plain copy so *arr import succeeds.
if [ ! -f "$DEST" ]; then
    cp "$SOURCE" "$DEST"
fi
