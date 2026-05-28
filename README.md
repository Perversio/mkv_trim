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
- [*arr Integration](#arr-integration-radarr--sonarr)

## Features

- **scan** — preview which tracks would be kept/removed, no files touched
- **smart** — keep the highest-scoring track per language (weighted by codec, channel count, name keywords)
- **trim** — keep only tracks matching specified languages
- Recursive directory processing
- In-place replace or separate output folder
- Bundled `mkvmerge` — runs without MKVToolNix installed on target machine
- Radarr/Sonarr integration via shell script hook (no binary needed)

---

## Requirements (build machine only)

- Python 3.10+
- `mkvmerge` (MKVToolNix) — bundled into the binary at build time
- Python packages (`pyinstaller`, `tqdm`, `humanize`, `pyyaml`) — installed automatically by deploy script

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
| `-W` | `--weights` | Path to custom YAML weights file |
| `-R` | `--recursive` | Scan subdirectories |
| `-L` | `--inplace` | Replace files in place (no `Trim/` folder) |
| `-S` | `--stats` | Print approximate total disk space saved |
| `-P` | `--perfile` | Show per-file `[diff]` prefix (estimated space saved) |
| `-M` | `--min SIZE` | Minimum estimated diff to process file (e.g. `500M`, `1G`, `1.5GiB`) |
| `-d` | `--dry` | Print `mkvmerge` commands without executing |
| `-I` | `--interactive` | Ask confirmation before each file |
|      | `--log [PATH]` | Mirror output to log file. Bare `--log` writes `mkv_trim.log` in cwd. |
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

Score = channel count + name keyword match + codec match + forced/default flag bonus.

Highest-scoring track per language is kept. Unnamed tracks are always kept.
Negative scores (e.g. commentary tracks) are disabled.

Weights are defined in YAML. Keys are **mkvmerge -J field paths** (dot-separated) —
any track property can be used as a scoring axis.

### Default weights (`data/default_weights.yaml`)

```yaml
properties.forced_track:
  "true": 1

properties.default_track:
  "true": 1

codec:
  TrueHD: 7          # matches "TrueHD Atmos" too
  DTS: 5
  AC3: 4
  AC-3: 3
  SubStationAlpha: 2
  ass: 2
  srt: 1

properties.track_name:
  dub: 100
  orig: 100
  full: 50
  forced: 50
  mvo: 50
  comment: -1000
  director: -1000
  # ... see data/default_weights.yaml for full list
```

### Custom weights

```bash
mkv_trim smart -a eng,jpn -W /path/to/weights.yaml /movies
```

Any mkvmerge track property path works as a key. Example `weights.yaml`:

```yaml
properties.track_name:
  comment: -1000
  dub: 100

codec:
  TrueHD: 7
  DTS: 5

# Free weights — any mkvmerge -J field path
properties.audio_channels:
  "8": 2    # extra +2 for 8-channel tracks
```

See `example_weights.yaml` for a fully annotated reference.

---

## *arr Integration (Radarr / Sonarr)

`arr/import.sh` strips unwanted tracks on import without the mkv_trim binary.
Only requirement: `mkvmerge` in PATH.

### 1. Install mkvtoolnix in the container

Add to your existing *arr service in `docker-compose.yml`:

```yaml
services:
  radarr:                                          # or sonarr, lidarr, etc.
    image: lscr.io/linuxserver/radarr:latest
    environment:
      - DOCKER_MODS=linuxserver/mods:universal-package-install
      - INSTALL_PACKAGES=mkvtoolnix
    volumes:
      - /path/to/config:/config
      - /path/to/movies:/movies
```

`mkvtoolnix` is reinstalled automatically on every container update via the mod.

### 2. Copy scripts

Copy `arr/import.sh` and `arr/mkv_trim.conf` into the container's config directory:

```bash
cp arr/import.sh arr/mkv_trim.conf /path/to/config/scripts/
chmod +x /path/to/config/scripts/import.sh
```

### 3. Edit `mkv_trim.conf`

```bash
# Audio languages to keep (comma-separated ISO 639-2 codes)
AUDIO_LANGS="eng,jpn,und"

# Subtitle languages to keep (leave empty to remove all)
SUBTITLE_LANGS=""

# Track name scoring (pattern:score, space-separated, case-insensitive)
NAME_WEIGHTS="dub:100 orig:100 comment:-1000 director:-1000"

# Codec scoring
CODEC_WEIGHTS="TrueHD:7 DTS:5 AC3:4 SubStationAlpha:2 ass:2 srt:1"
```

### 4. Configure in Radarr / Sonarr

The same `import.sh` handles both integration modes — configure whichever fits your setup:

| Mode | Where | Triggers |
|------|-------|----------|
| **Import Using Script** | `Settings › Media Management › Import Using Script` | Replaces the normal import copy/move. Script receives source + destination paths. |
| **Custom Script** | `Settings › Connect › Custom Script` | Fires after import. Set events: **On File Import** + **On File Upgrade**. Modifies file in place. |

> **Import Using Script** is preferred — it processes the file before it lands in the library,
> so Plex/Jellyfin never sees the unstripped version.

### 5. Test the connection

Use the **Test** button in the Radarr/Sonarr UI after adding the script.
The script will verify `mkvmerge` is reachable and print its version:

```
import.sh: connection OK
  mkvmerge: mkvmerge v82.0 ...
  config:   /config/scripts/mkv_trim.conf
  audio:    eng,jpn,und
  subs:     none
```

If `mkvmerge not found in PATH` is printed, check that `INSTALL_PACKAGES=mkvtoolnix`
is set and the container has been restarted at least once after adding the mod.

### Fallback behaviour

- **Import Using Script**: if mkvmerge fails or produces no output, the original file is copied as-is.
- **Custom Script**: if mkvmerge fails, the original file is left untouched.
- Non-MKV files (`.mp4`, `.avi`, etc.) are passed through unchanged.
