#!/bin/bash
# connect.sh — mkv_trim wrapper for Radarr/Sonarr "Connect > Custom Script" mode
#              when the UI does not provide an Arguments field.
#
# Radarr:  Settings > Connect > Custom Script  (Path: /path/to/mkv_trim/connect.sh)
# Sonarr:  Settings > Connect > Custom Script  (Path: /path/to/mkv_trim/connect.sh)
# Triggers: On File Import, On File Upgrade
#
# Edit -a to match your language preferences.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec "$SCRIPT_DIR/mkv_trim" smart -a ukr,eng,jpn,und -L
