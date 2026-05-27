#!/bin/bash
# Radarr "Import Using Script" wrapper for mkv_trim.
#
# Setup:
#   Settings > Media Management > Import Using Script: ON
#   Import Script Path: /config/scripts/mkv_trim/radarr_import.sh
#
# mkv_trim reads source file, strips unwanted tracks, writes to destination.
# Radarr handles rename/move after this script exits 0.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MKV_TRIM="$SCRIPT_DIR/mkv_trim"

exec "$MKV_TRIM" smart \
    -a ukr,eng,jpn,und \
    -o "$radarr_destinationpath" \
    "$radarr_sourcepath"
