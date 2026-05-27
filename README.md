# mkv_trim

> **MIT License** — provided "as is", without warranty of any kind.
> Use at your own risk. No support, no guarantees, no roadmap.

---

> **Note from the author:**
> This tool does what I need it to do. I am not accepting feature requests,
> bug reports, or pull requests. Issues and discussions will be ignored.
> Fork it if you want something different.

---

Lazy MKV remuxer. Scans MKV files and strips unwanted audio/subtitle tracks
using `mkvmerge`. No transcoding — pure stream copy, fast.

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
- `pyinstaller`, `tqdm`, `humanize` Python packages

---

## Installation

### macOS

```bash
# Install mkvmerge (required at build time)
brew install mkvtoolnix

# Clone and set up venv
git clone <repo>
cd mkv_trim
python3 -m venv .venv
.venv/bin/pip install pyinstaller tqdm humanize

# Build and install to /usr/local/bin/mkv_trim
bash deploy_mac.sh
```

The script will:
1. Check `mkvmerge` is present and print its version
2. Bundle the binary + `mkvmerge` + data files via PyInstaller (`--onedir`)
3. Ad-hoc codesign the bundle (satisfies macOS Gatekeeper without a paid Developer ID)
4. Install to `/usr/local/lib/mkv_trim/` and symlink to `/usr/local/bin/mkv_trim`

### Linux

```bash
# Install mkvmerge (required at build time)
sudo apt install mkvtoolnix          # Ubuntu/Debian
# sudo dnf install mkvtoolnix        # Fedora/RHEL
# sudo pacman -S mkvtoolnix-cli      # Arch

# Clone and set up venv
git clone <repo>
cd mkv_trim
python3 -m venv .venv
.venv/bin/pip install pyinstaller tqdm humanize

# Build and install to /usr/local/bin/mkv_trim
sudo bash deploy.sh
```

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
| `-a` | `--audio` | Audio languages to keep. Comma-separated: `-a ukr,rus` |
| `-s` | `--subtitle` | Subtitle languages to keep. Omit to remove all subtitles. |
| `-o` | `--output` | Output file path (overrides default `Trim/` folder) |
| `-W` | `--weights` | Path to custom JSON weights file |
| `-R` | `--recursive` | Scan subdirectories |
| `-L` | `--inplace` | Replace files in place (no `Trim/` folder) |
| `-S` | `--stats` | Print approximate disk space saved |
| `-d` | `--dry` | Print `mkvmerge` commands without executing |
| `-I` | `--interactive` | Ask confirmation before each file |
| `-V` | `--version` | Print version and exit |

Language choices: `ukr` `eng` `jpn` `rus` `und`

### Usage notes

- Input path can be the last argument without `-i`: `mkv_trim scan -Ra ukr /path`
- Boolean flags can be combined: `-RS`, `-Rd`, `-RSd`, `-RId`
- Multiple `-a`/`-s` flags are merged: `-a ukr -a rus` → `[ukr, rus]`
- At least one audio track is always preserved (even if language not in `-a` list)
- Without `-s`, all subtitles are removed

### Examples

```bash
mkv_trim scan -Ra ukr,rus /movies        # preview track table, recursive
mkv_trim smart -Ra ukr,rus /movies       # smart-select best ukr+rus audio
mkv_trim smart -Ra ukr -s ukr,rus /f     # smart audio ukr, keep ukr+rus subs
mkv_trim trim -a ukr,rus -s ukr /f       # explicit trim: keep ukr+rus audio, ukr subs
mkv_trim smart -RLa ukr,rus /movies      # smart select, replace files in place
mkv_trim smart -RSda ukr,rus /movies     # dry run with space diff stats
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
    "dub":   100,  "orig":    100,
    "mvo":    50,  "много":    50,
    "dvo":    40,  "двух":     40,
    "vo":    -40,  "одно":    -50,
    "comment": -1000, "Авторский": -1000
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
mkv_trim smart -a ukr,rus -W /path/to/weights.json /movies
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
   | Path | `/usr/local/bin/mkv_trim` |
   | Arguments | `smart -a ukr,rus -L` |
   | Notification Triggers | ✅ On Import  ✅ On Upgrade |

3. Click **Test** — should return `mkv_trim: Radarr connection OK`.

### Sonarr setup

Same as Radarr. Sonarr passes `sonarr_episodefile_path` — supported out of the box.

### Arguments reference for \*arr

| Scenario | Arguments |
|----------|-----------|
| In-place, smart select | `smart -a ukr,rus -L` |
| In-place, keep subs | `smart -a ukr,rus -s ukr,rus -L` |
| Output to specific path | `smart -a ukr,rus -o /output/file.mkv` |

> **Note:** Use `-L` (in-place) for \*arr integrations — Radarr/Sonarr track the original
> file path. Writing to a `Trim/` subfolder will cause the media manager to lose track of the file.

### Test connection event

`radarr_eventtype=Test` is handled automatically — exits 0 with a confirmation message.
No manual handling required.
