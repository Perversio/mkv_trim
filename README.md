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
3. Bundle a single self-contained binary with `mkvmerge` + data files via PyInstaller (`--onefile`)
4. Ad-hoc codesign the binary (satisfies macOS Gatekeeper without a paid Developer ID)
5. Install to `/usr/local/bin/mkv_trim`

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
3. Bundle a single self-contained binary with `mkvmerge` + data files via PyInstaller (`--onefile`)
4. Install to `/usr/local/bin/mkv_trim`

### Docker

The built binary bundles `mkvmerge` — no MKVToolNix installation needed in the container.
Build on the host (matching target OS architecture), then copy the single binary:

```dockerfile
FROM debian:bookworm-slim

COPY dist/mkv_trim /usr/local/bin/mkv_trim
RUN chmod +x /usr/local/bin/mkv_trim

ENTRYPOINT ["mkv_trim"]
```

> Build the binary on a Linux machine first (`bash deploy.sh`), then use `dist/mkv_trim` as the `COPY` source. For Alpine-based images (e.g. linuxserver.io), use `bash deploy_alpine.sh` for a musl-compatible binary.

### *arr Integration (Radarr / Sonarr)

`arr/import.sh` integrates with Radarr and Sonarr without the mkv_trim binary.
Only dependency: **mkvtoolnix** (`mkvmerge`).

Copy `arr/import.sh` and `arr/mkv_trim.conf` into your container's config directory
(e.g. `/config/scripts/`). Edit `mkv_trim.conf` for your language preferences.

**docker-compose.yml** — add to your existing *arr service:

```yaml
services:
  radarr:
    image: lscr.io/linuxserver/radarr:latest
    environment:
      - DOCKER_MODS=linuxserver/mods:universal-package-install
      - INSTALL_PACKAGES=mkvtoolnix
    volumes:
      - /config/radarr:/config
      - /movies:/movies
    # mkvtoolnix is re-installed automatically on every container update
```

Configure in the Radarr/Sonarr UI — the same script handles both integration modes:

| Mode | Location | Path |
|------|----------|------|
| Import Using Script | `Settings > Media Management > Import Using Script` | `/config/scripts/import.sh` |
| Custom Script | `Settings > Connect > Custom Script` (On Import / On Upgrade) | `/config/scripts/import.sh` |

The script auto-detects which mode is active from the environment variables *arr provides.
If mkvmerge cannot process the file (non-MKV format, etc.), it falls back to a plain copy.

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
| `-a` | `--audio` | Audio languages to keep. Comma-separated: `-a eng,jpn`. 3-letter ISO 639-2/3 codes. Invalid codes skipped. |
| `-s` | `--subtitle` | Subtitle languages to keep. Omit to remove all subtitles. 3-letter ISO 639-2/3 codes. |
| `-o` | `--output` | Output file path (overrides default `Trim/` folder) |
| `-W` | `--weights` | Path to custom JSON weights file |
| `-R` | `--recursive` | Scan subdirectories |
| `-L` | `--inplace` | Replace files in place (no `Trim/` folder) |
| `-S` | `--stats` | Print approximate total disk space saved |
| `-P` | `--perfile` | Show per-file `[diff]` prefix (estimated space saved) |
| `-M` | `--min SIZE` | Minimum estimated diff to process file (e.g. `500M`, `1G`, `1.5GiB`) |
| `-d` | `--dry` | Print `mkvmerge` commands without executing |
| `-I` | `--interactive` | Ask confirmation before each file |
| `-V` | `--version` | Print version and exit |

3-letter ISO 639-2/3 codes only (e.g. `eng`, `jpn`, `und`). Invalid codes skipped with a warning. Full list in `data/languages.json`.

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

