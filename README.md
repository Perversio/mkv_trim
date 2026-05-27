# mkv_trim


> **Note from the author:**
> This tool does what I need it to do. I am not accepting feature requests,
> bug reports, or pull requests. Issues and discussions will be ignored.
> Fork it if you want something different.

---

Lazy MKV remuxer. Scans MKV files and strips unwanted audio/subtitle tracks
using `mkvmerge`. No transcoding — pure stream copy, fast.

## Contents

- [Features](#features)
- [Requirements](#requirements-build-machine-only)
- [Installation](#installation)
  - [macOS](#macos)
  - [Linux](#linux)
  - [Docker](#docker)
- [Usage](#usage)
  - [Commands](#commands)
  - [Options](#options)
  - [Examples](#examples)
- [Track Scoring](#track-scoring-smart-command)
- [Radarr / Sonarr / \*arr Integration](#radarr--sonarr--arr-integration)
  - [Connect: Custom Script](#radarr-setup)
  - [Import Using Script](#radarr--sonarr-import-using-script-alternative)

## Features

- **scan** — preview which tracks would be kept/removed, no files touched
- **smart** — keep the highest-scoring track per language (weighted by codec, channel count, name keywords)
- **trim** — keep only tracks matching specified languages
- Recursive directory processing
- In-place replace or separate output folder
- Bundled `mkvmerge` — runs without MKVToolNix installed on target machine
- Radarr/Sonarr integration via custom script hook

---

## Requirements (build machine only)

- Python 3.10+
- `mkvmerge` (MKVToolNix) — bundled into the binary at build time
- Python packages (`pyinstaller`, `tqdm`, `humanize`) — installed automatically by deploy script

---

## Installation

### macOS

```bash
# Install dependencies
brew install python mkvtoolnix

# Clone and deploy
git clone https://github.com/Perversio/mkv_trim.git
cd mkv_trim
bash deploy_mac.sh
```

The script will:
1. Check `mkvmerge` and `python3` are present
2. Create `.venv` and install Python packages automatically
3. Bundle the binary + `mkvmerge` + data files via PyInstaller (`--onedir`)
4. Ad-hoc codesign the bundle (satisfies macOS Gatekeeper without a paid Developer ID)
5. Install to `/usr/local/lib/mkv_trim/` and symlink to `/usr/local/bin/mkv_trim`

### Linux

```bash
# Install dependencies
sudo apt install python3 python3-venv mkvtoolnix   # Ubuntu/Debian
# sudo dnf install python3 mkvtoolnix              # Fedora/RHEL
# sudo pacman -S python mkvtoolnix-cli             # Arch

# Clone and deploy
git clone https://github.com/Perversio/mkv_trim.git
cd mkv_trim
bash deploy.sh
```

The script will:
1. Check `mkvmerge` and `python3` are present
2. Create `.venv` and install Python packages automatically
3. Bundle the binary + `mkvmerge` + data files via PyInstaller (`--onedir`)
4. Install to `/usr/local/lib/mkv_trim/` and symlink to `/usr/local/bin/mkv_trim`

### Docker

The built binary bundles `mkvmerge` — no MKVToolNix installation needed in the container.
Build on the host (matching target OS architecture), then copy the output directory:

```dockerfile
FROM debian:bookworm-slim

COPY dist/mkv_trim /opt/mkv_trim
RUN ln -s /opt/mkv_trim/mkv_trim /usr/local/bin/mkv_trim

ENTRYPOINT ["mkv_trim"]
```

> Build the binary on a Linux machine first (`bash deploy.sh`), then use `dist/mkv_trim/` as the `COPY` source.

---

## Usage

```
mkv_trim <command> [options] [path]
```

### Commands

| Command | Description |
|---------|-------------|
| `scan`  | Print track table with enable/disable preview. No files modified. |
| `smart` | Keep highest-scoring track per language per type. |
| `trim`  | Keep tracks matching specified languages exactly. |

### Options

| Flag | Long | Description |
|------|------|-------------|
| `-a` | `--audio` | Audio languages to keep. Comma-separated: `-a eng,jpn` |
| `-s` | `--subtitle` | Subtitle languages to keep. Omit to remove all subtitles. |
| `-o` | `--output` | Output file path (overrides default `Trim/` folder) |
| `-W` | `--weights` | Path to custom JSON weights file |
| `-R` | `--recursive` | Scan subdirectories |
| `-L` | `--inplace` | Replace files in place (no `Trim/` folder) |
| `-S` | `--stats` | Print approximate disk space saved |
| `-d` | `--dry` | Print `mkvmerge` commands without executing |
| `-I` | `--interactive` | Ask confirmation before each file |
| `-V` | `--version` | Print version and exit |

Accepts ISO 639-1 (`en`), ISO 639-2 (`eng`), or ISO 639-3 codes. Full list in `data/languages.json`.

### Usage notes

- Input path can be the last argument without `-i`: `mkv_trim scan -Ra eng /path`
- Boolean flags can be combined: `-RS`, `-Rd`, `-RSd`, `-RId`
- Multiple `-a`/`-s` flags are merged: `-a eng -a jpn` → `[eng, jpn]`
- At least one audio track is always preserved (even if language not in `-a` list)
- Without `-s`, all subtitles are removed

### Examples

```bash
mkv_trim scan -Ra eng,jpn /movies        # preview track table, recursive
mkv_trim smart -Ra eng,jpn /movies       # smart-select best eng+jpn audio
mkv_trim smart -Ra eng -s eng,jpn /f     # smart audio eng, keep eng+jpn subs
mkv_trim trim -a eng,jpn -s eng /f       # explicit trim: keep eng+jpn audio, eng subs
mkv_trim smart -RLa eng,jpn /movies      # smart select, replace files in place
mkv_trim smart -RSda eng,jpn /movies     # dry run with space diff stats
```

---

## Track Scoring (smart command)

Score = channel count + forced/default flags + name keyword match + codec match.

Highest-scoring track per language is kept. Unnamed tracks are always kept.
Negative scores (e.g. commentary tracks) are disabled.

### Default weights

```json
{
  "track_name": {
    "dub":     100,
    "orig":    100,
    "comment": -1000
  },
  "audio_codec": {
    "TrueHD": 7, "Atmos": 6, "DTS": 5, "AC3": 4, "AC-3": 3
  },
  "subtitle_codec": {
    "ass": 20, "SubStationAlpha": 20, "srt": 10
  }
}
```

### Custom weights

```bash
mkv_trim smart -a eng,jpn -W /path/to/weights.json /movies
```

Supported top-level keys: `track_name`, `audio_codec`, `subtitle_codec`.
Values are additive integers (positive = prefer, negative = penalize).

---

## Radarr / Sonarr / \*arr Integration

`mkv_trim` can run as a custom script on import/upgrade events.
The file path is read from the `radarr_moviefile_path` / `sonarr_episodefile_path`
environment variable automatically — no special command needed.

### Radarr setup

1. **Settings → Connect → Custom Script**
2. Set fields:

   | Field | Value |
   |-------|-------|
   | Name | `mkv_trim` |
   | Path | `/path/to/mkv_trim` |
   | Arguments | `smart -a eng,jpn -L` |
   | Notification Triggers | ✅ On Import  ✅ On Upgrade |

3. Click **Test** — should return `mkv_trim: Radarr connection OK`.

### Sonarr setup

Same as Radarr. Sonarr passes `sonarr_episodefile_path` — supported out of the box.

### Arguments reference for \*arr

| Scenario | Arguments |
|----------|-----------|
| In-place, smart select | `smart -a eng,jpn -L` |
| In-place, keep subs | `smart -a eng,jpn -s eng,jpn -L` |
| Output to specific path | `smart -a eng,jpn -o /output/file.mkv` |

> **`-L` is required for \*arr integrations.**
>
> Radarr/Sonarr track the imported file by its exact path. Without `-L`, mkv_trim writes
> the output to a `Trim/` subfolder and leaves the original untouched — the media manager
> never sees the trimmed file and the original remains bloated in the library.
>
> With `-L`, mkv_trim replaces the library file in place. If hardlinks are enabled,
> the original file in the download folder is **not affected** — the hardlink is broken
> cleanly and seeding continues uninterrupted.

### Test connection event

`radarr_eventtype=Test` is handled automatically — exits 0 with a confirmation message.
No manual handling required.

---

### Radarr / Sonarr: Import Using Script (alternative)

Both Radarr and Sonarr support **Settings → Media Management → Import Using Script**.
In this mode there is no arguments field — the script receives source/destination via env vars
and is responsible for writing the output file itself.

Use the included `import.sh` wrapper:

```
Import Script Path: /path/to/mkv_trim/import.sh
```

```bash
#!/bin/bash
# import.sh — edit -a to match your language preferences

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Radarr:  radarr_sourcepath / radarr_destinationpath
# Sonarr:  sonarr_sourcepath / sonarr_destinationpath
SOURCE="${radarr_sourcepath:-$sonarr_sourcepath}"
DEST="${radarr_destinationpath:-$sonarr_destinationpath}"

exec "$SCRIPT_DIR/mkv_trim" smart \
    -a ukr,eng,jpn,und \
    -o "$DEST" \
    "$SOURCE"
```

Copy `import.sh` alongside the `mkv_trim` binary and make it executable:

```bash
chmod +x /path/to/mkv_trim/import.sh
```

> Do **not** use `-L` here — destination path is provided explicitly by \*arr.
