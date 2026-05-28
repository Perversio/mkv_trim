#!/bin/bash
# import.sh — *arr integration for Radarr and Sonarr.
#
# Requires: mkvtoolnix (mkvmerge in PATH). No mkv_trim binary needed.
#
# Mode A — Import Using Script:
#   Radarr:  Settings > Media Management > Import Using Script
#   Sonarr:  Settings > Media Management > Import Using Script
#   File path is passed via radarr_sourcepath / sonarr_sourcepath.
#   Output path via radarr_destinationpath / sonarr_destinationpath.
#
# Mode B — Custom Script (Connect):
#   Radarr/Sonarr:  Settings > Connect > Custom Script
#   Triggers:       On File Import, On File Upgrade
#   File path via radarr_moviefile_path / sonarr_episodefile_path.
#   Modified in place via a temp file.
#
# Edit mkv_trim.conf (same directory) for language and weight preferences.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${SCRIPT_DIR}/mkv_trim.conf"

# --- Load config ---
AUDIO_LANGS="eng"
SUBTITLE_LANGS=""
NAME_WEIGHTS="comment:-1000 dub:100 orig:100"
CODEC_WEIGHTS="TrueHD:7 Atmos:6 DTS:5 AC3:4 SubStationAlpha:20 ass:20 srt:10"

if [ -f "$CONFIG" ]; then
    # shellcheck source=/dev/null
    . "$CONFIG"
fi

# --- Test event (connection check) ---
EVENT="${radarr_eventtype:-${sonarr_eventtype:-}}"
if [ "$EVENT" = "Test" ]; then
    if ! command -v mkvmerge >/dev/null 2>&1; then
        echo "import.sh: ERROR — mkvmerge not found in PATH" >&2
        echo "  Install via: apk add mkvtoolnix  (Alpine)"
        echo "               apt install mkvtoolnix  (Debian/Ubuntu)"
        exit 1
    fi
    MKV_VER="$(mkvmerge --version 2>&1 | head -1)"
    echo "import.sh: connection OK"
    echo "  mkvmerge: ${MKV_VER}"
    echo "  config:   ${CONFIG}"
    echo "  audio:    ${AUDIO_LANGS}"
    echo "  subs:     ${SUBTITLE_LANGS:-none}"
    exit 0
fi

# --- Mode detection ---
SOURCE="${radarr_sourcepath:-${sonarr_sourcepath:-}}"
DEST="${radarr_destinationpath:-${sonarr_destinationpath:-}}"
INPLACE="${radarr_moviefile_path:-${sonarr_episodefile_path:-}}"

if [ -z "$SOURCE" ] && [ -z "$INPLACE" ]; then
    echo "import.sh: no *arr env vars detected" >&2
    exit 1
fi

# --- Track selection via awk scoring ---
# Parses mkvmerge -J JSON (pretty-printed, one key per line).
# Returns two lines: AUDIO_IDS=id,id,... and SUB_IDS=id,id,...
select_tracks() {
    local file="$1"
    mkvmerge -J "$file" 2>/dev/null | awk \
        -v audio_langs="$AUDIO_LANGS" \
        -v sub_langs="$SUBTITLE_LANGS" \
        -v name_weights="$NAME_WEIGHTS" \
        -v codec_weights="$CODEC_WEIGHTS" \
    '
    BEGIN {
        # Parse wanted langs into arrays
        n = split(audio_langs, al, ",")
        for (i = 1; i <= n; i++) wanted_audio[al[i]] = 1

        n = split(sub_langs, sl, ",")
        for (i = 1; i <= n; i++) wanted_sub[sl[i]] = 1

        # Parse weight specs: "pattern:score pattern:score ..."
        n = split(name_weights, nw, " ")
        for (i = 1; i <= n; i++) {
            split(nw[i], kv, ":")
            nw_key[i] = tolower(kv[1])
            nw_val[i] = kv[2] + 0
            nw_count = i
        }
        n = split(codec_weights, cw, " ")
        for (i = 1; i <= n; i++) {
            split(cw[i], kv, ":")
            cw_key[i] = tolower(kv[1])
            cw_val[i] = kv[2] + 0
            cw_count = i
        }
        cur_id = -1; cur_type = ""; cur_lang = "und"; cur_codec = ""
        cur_channels = 0; cur_forced = 0; cur_default = 0; cur_name = ""
        in_props = 0
        track_count = 0
    }

    # Detect track boundary start
    /^[[:space:]]+\{/ {
        if (cur_id >= 0) save_track()
        cur_id = -1; cur_type = ""; cur_lang = "und"; cur_codec = ""
        cur_channels = 0; cur_forced = 0; cur_default = 0; cur_name = ""
    }

    # Extract fields (mkvmerge -J pretty-prints one key:value per line)
    /"id":[[:space:]]*[0-9]/ {
        match($0, /[0-9]+/)
        if (cur_id < 0) cur_id = substr($0, RSTART, RLENGTH) + 0
    }
    /"type":[[:space:]]*"/ {
        match($0, /"type":[[:space:]]*"[^"]*"/)
        s = substr($0, RSTART, RLENGTH)
        gsub(/"type":[[:space:]]*"/, "", s); gsub(/"/, "", s)
        cur_type = s
    }
    /"codec":[[:space:]]*"/ && !/codec_id/ && !/codec_private/ {
        match($0, /"codec":[[:space:]]*"[^"]*"/)
        s = substr($0, RSTART, RLENGTH)
        gsub(/"codec":[[:space:]]*"/, "", s); gsub(/"/, "", s)
        cur_codec = s
    }
    /"language":[[:space:]]*"/ {
        match($0, /"language":[[:space:]]*"[^"]*"/)
        s = substr($0, RSTART, RLENGTH)
        gsub(/"language":[[:space:]]*"/, "", s); gsub(/"/, "", s)
        cur_lang = s
    }
    /"track_name":[[:space:]]*"/ {
        match($0, /"track_name":[[:space:]]*"[^"]*"/)
        s = substr($0, RSTART, RLENGTH)
        gsub(/"track_name":[[:space:]]*"/, "", s); gsub(/"$/, "", s)
        cur_name = s
    }
    /"audio_channels":[[:space:]]*[0-9]/ {
        match($0, /[0-9]+/)
        cur_channels = substr($0, RSTART, RLENGTH) + 0
    }
    /"forced_track":[[:space:]]*true/ { cur_forced = 1 }
    /"default_track":[[:space:]]*true/ { cur_default = 1 }

    END { if (cur_id >= 0) save_track(); output_ids() }

    function save_track(    w, i, nl, cl) {
        if (cur_type != "audio" && cur_type != "subtitles") return

        # Base weight
        w = cur_forced + cur_default
        if (cur_type == "audio") w += cur_channels

        # Name keyword weights
        nl = tolower(cur_name)
        for (i = 1; i <= nw_count; i++)
            if (index(nl, nw_key[i])) w += nw_val[i]

        # Codec weights (same pool for audio and subtitle)
        cl = tolower(cur_codec)
        for (i = 1; i <= cw_count; i++)
            if (index(cl, cw_key[i])) w += cw_val[i]

        track_count++
        t_id[track_count]       = cur_id
        t_type[track_count]     = cur_type
        t_lang[track_count]     = cur_lang
        t_weight[track_count]   = w
    }

    function output_ids(    i, j, lang, best_w, best_id, audio_ids, sub_ids, n_audio, n_sub) {
        audio_ids = ""; sub_ids = ""
        n_audio = 0; n_sub = 0

        # For each wanted audio lang: pick highest-weight non-negative track
        for (lang in wanted_audio) {
            best_w = -99999; best_id = -1
            for (i = 1; i <= track_count; i++) {
                if (t_type[i] == "audio" && t_lang[i] == lang && t_weight[i] >= 0) {
                    if (t_weight[i] > best_w || best_id < 0) {
                        best_w = t_weight[i]; best_id = t_id[i]
                    }
                }
            }
            if (best_id >= 0) {
                audio_ids = (audio_ids == "" ? best_id : audio_ids "," best_id)
                n_audio++
            }
        }

        # Safety: if no audio selected, pick first available audio track
        if (n_audio == 0) {
            for (i = 1; i <= track_count; i++) {
                if (t_type[i] == "audio") {
                    audio_ids = t_id[i]
                    break
                }
            }
        }

        # For each wanted sub lang: pick highest-weight non-negative track
        if (sub_langs != "") {
            for (lang in wanted_sub) {
                best_w = -99999; best_id = -1
                for (i = 1; i <= track_count; i++) {
                    if (t_type[i] == "subtitles" && t_lang[i] == lang && t_weight[i] >= 0) {
                        if (t_weight[i] > best_w || best_id < 0) {
                            best_w = t_weight[i]; best_id = t_id[i]
                        }
                    }
                }
                if (best_id >= 0) {
                    sub_ids = (sub_ids == "" ? best_id : sub_ids "," best_id)
                }
            }
        }

        print "AUDIO_IDS=" audio_ids
        print "SUB_IDS=" sub_ids
    }
    '
}

# Run mkvmerge with selected track IDs
run_mkvmerge() {
    local input="$1" output="$2"
    local selection audio_ids sub_ids

    selection="$(select_tracks "$input")"
    audio_ids="$(echo "$selection" | grep '^AUDIO_IDS=' | cut -d= -f2)"
    sub_ids="$(echo   "$selection" | grep '^SUB_IDS='   | cut -d= -f2)"

    local cmd=(mkvmerge -o "$output")

    if [ -n "$audio_ids" ]; then
        cmd+=(--audio-tracks "$audio_ids")
    else
        cmd+=(--no-audio)
    fi

    if [ -n "$sub_ids" ]; then
        cmd+=(--subtitle-tracks "$sub_ids")
    else
        cmd+=(--no-subtitles)
    fi

    cmd+=("$input")
    "${cmd[@]}"
}

# --- Mode A: Import Using Script ---
if [ -n "$SOURCE" ] && [ -n "$DEST" ]; then
    run_mkvmerge "$SOURCE" "$DEST" || true
    if [ ! -f "$DEST" ]; then
        echo "import.sh: mkvmerge produced no output — copying source" >&2
        cp "$SOURCE" "$DEST"
    fi
    exit 0
fi

# --- Mode B: Custom Script (inplace via temp file) ---
if [ -n "$INPLACE" ]; then
    TMPFILE="${INPLACE}.tmp.mkv"
    run_mkvmerge "$INPLACE" "$TMPFILE" || true
    if [ -f "$TMPFILE" ]; then
        mv "$TMPFILE" "$INPLACE"
    fi
    # No copy fallback — original stays untouched if mkvmerge skipped/failed
    exit 0
fi
