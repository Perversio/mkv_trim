from MKV import MKV, Track
from pathlib import Path
from util import Util
from tqdm import tqdm
import multiprocessing
import humanize
import argparse
import signal
import json
import sys
import os

version = '1.1.3'
args: argparse.Namespace
input_path: Path = Path.cwd()
scan_size: int = 0
result_commands: list[str] = list()
default_weights: dict = {}


def signal_handler(sig, frame):
    sys.exit('Interrupted by user')


BOOL_FLAGS = {'-R', '-S', '-P', '-d', '-L', '-h', '-V', '-I'}
LANG_OPTIONS: set = set()


def load_lang_options() -> set:
    lang_file = Util.resource_path('data/languages.json')
    try:
        with open(lang_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        codes = set()
        for entry in data:
            for key in ('iso2', 'iso3'):  # 3-letter codes only
                code = entry.get(key, '').strip()
                if len(code) == 3:
                    codes.add(code)
        return codes
    except (FileNotFoundError, json.JSONDecodeError):
        return {'eng', 'jpn', 'und'}


def expand_argv(argv):
    result = []
    for arg in argv:
        if len(arg) > 2 and arg[0] == '-' and arg[1] != '-' and all(f'-{c}' in BOOL_FLAGS for c in arg[1:]):
            result.extend(f'-{c}' for c in arg[1:])
        else:
            result.append(arg)
    # treat last arg as input path if it looks like one
    if result and not result[-1].startswith('-'):
        last = result[-1]
        is_path = ('/' in last or '\\' in last or last in ('.', '..') or os.path.exists(last))
        is_lang = all(v.strip() in LANG_OPTIONS for v in last.split(','))
        if is_path and not is_lang:
            result = result[:-1] + ['-i', last]
    return result


def lang_type(value):
    result = []
    for lang in (v.strip() for v in value.split(',')):
        if lang in LANG_OPTIONS:
            result.append(lang)
        else:
            print(f"Warning: unknown language code '{lang}' — skipped", file=sys.stderr)
    return result


def get_arguments(description):
    if not description:
        description = 'Script intake'

    sys.argv[1:] = expand_argv(sys.argv[1:])

    if '-V' in sys.argv or '--version' in sys.argv:
        print(f'ver. {version}')
        sys.exit(0)

    parser = Util.argparse_default(description, add_help=False)
    parser.add_argument('-h', '--help', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('command', choices=['scan', 'smart', 'trim'], help=argparse.SUPPRESS, default=None, nargs='?')
    parser.add_argument('path', type=str, help=argparse.SUPPRESS, default=None, nargs='?')
    parser.add_argument('--audio', '-a', type=lang_type, action='append', help=argparse.SUPPRESS)
    parser.add_argument('--subtitle', '-s', type=lang_type, action='append', help=argparse.SUPPRESS)
    parser.add_argument('--output', '-o', type=str, help=argparse.SUPPRESS)
    parser.add_argument('--recursive', '-R', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--inplace', '-L', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--stats', '-S', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--perfile', '-P', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--weights', '-W', type=str, help=argparse.SUPPRESS)
    parser.add_argument('--interactive', '-I', action='store_true', help=argparse.SUPPRESS)

    global args
    args = parser.parse_args()

    if args.audio:
        args.audio = list(dict.fromkeys(lang for group in args.audio for lang in group))
    if args.subtitle:
        args.subtitle = list(dict.fromkeys(lang for group in args.subtitle for lang in group))

    if args.help:
        print(description)
        sys.exit(0)


def validate_args():
    global input_path
    if not args.command:
        sys.exit('Command required: scan | smart | trim\nSee -h for usage.')

    # Radarr/Sonarr: Test event
    if os.environ.get('radarr_eventtype') == 'Test' or os.environ.get('sonarr_eventtype') == 'Test':
        print('mkv_trim: connection OK')
        sys.exit(0)

    # Radarr/Sonarr: use env var as input if -i / positional not provided
    if not args.input and not args.path:
        arr_path = (os.environ.get('radarr_moviefile_path') or
                    os.environ.get('sonarr_episodefile_path', ''))
        if arr_path:
            args.input = arr_path

    if args.path and not args.input:
        args.input = args.path
    if args.input:
        u_path: str = args.input
        u_path = u_path.strip("'\" ")
        path = Path(u_path)
        if not path.exists():
            path = input_path / u_path
        input_path = path

    if not input_path.exists():
        sys.exit(f"{input_path} not found")

    count: int = 0
    if args.audio:
        count += len(args.audio)
    if args.subtitle:
        count += len(args.subtitle)

    if count == 0:
        sys.exit("Nothing to do, since no audio (-a) or subtitle (-s) attribute specified.\n"
                 "Please refer to --help for usage directions.")


def process_dir(folder: Path, dest: Path) -> int:
    files: list[Path] = Util.list_dir_file_types(folder, extensions=['mkv', 'm4v', 'mp4'], recursive=args.recursive)
    files = [f for f in files if 'Trim' not in f.parts]
    if len(files) == 0:
        print(f'{folder}\n No files to process. Try using -R argument')
    result: int = 0
    count: int = 0

    print(f'Scanning {folder}')
    # Total pbar (position=1, stays). mkvmerge inner bar uses position=0 (transient).
    pbar = tqdm(total=len(files), unit='file', position=1, leave=True, desc='Total')

    smart: bool = args.command == 'scan' or args.command == 'smart'

    for file in files:
        try:
            mkv: MKV = MKV(file, expanded=args.stats or args.perfile)
        except ValueError as e:
            tqdm.write(f'  skipping: {e}')
            pbar.update()
            continue
        mkv.weights = default_weights

        if smart:
            smart_tracks_disable_all(mkv)
            if not mkv.valid:
                pbar.update()
                continue

        # Only audio deltas qualify (subtitle-only changes skipped, even in scan).
        audio_tracks = mkv.tracks_by_type.get('audio', [])
        if smart:
            needs_change = not all(t.enabled for t in audio_tracks)
        elif args.audio:
            needs_change = any(t.language not in args.audio for t in audio_tracks)
        else:
            needs_change = False

        if needs_change:
            count += 1
            rout_object(mkv, dest)
        pbar.update()

    pbar.close()

    if count == 0:
        print('No eligible files found.')
    else:
        print(f'\nProcessed {count} eligible files of {len(files)}')

    return result


def rout_object(mkv: MKV, dest: Path) -> int:
    result: int = 0
    if args.command == 'scan':
        result = scan_object(mkv)
    elif args.command == 'trim':
        result = process_object(mkv, dest)
    elif args.command == 'smart':
        result = smart_object(mkv, dest)
    return result


NAME_MAX = 50


def trunc_mid(s: str, max_len: int = NAME_MAX) -> str:
    if len(s) <= max_len:
        return s
    half = (max_len - 3) // 2
    return s[:half] + '...' + s[-(max_len - 3 - half):]


def format_track_table(tracks: list) -> str:
    HDR = ('', 'Type', 'Score', 'Lang', 'Codec', 'Ch', 'Name')
    rows = []
    for t in tracks:
        typ = Track.TYPE_SHORT.get(t.type, t.type)
        w = '-' if t.weight < 0 else str(t.weight)
        ch = str(t.channels) if t.channels else ''
        name = trunc_mid(t.track_name or '')
        en = '[+]' if t.enabled else '[ ]'
        rows.append((en, typ, w, t.language or '', t.codec or '', ch, name))

    if not rows:
        return '  (none)\n'

    col_w = [max(len(HDR[i]), max(len(r[i]) for r in rows)) for i in range(6)]

    def fmt_row(r):
        return (f'  {r[0]:<{col_w[0]}}  {r[1]:<{col_w[1]}}  {r[2]:>{col_w[2]}}  {r[3]:<{col_w[3]}}'
                f'  {r[4]:<{col_w[4]}}  {r[5]:<{col_w[5]}}  {r[6]}')

    header = fmt_row(HDR)
    all_rows = [fmt_row(r) for r in rows]
    section_w = max(len(header), max(len(r) for r in all_rows)) - 2
    divider = '  ' + '-' * section_w
    return header + '\n' + divider + '\n' + '\n'.join(all_rows) + '\n'


def scan_object(mkv: MKV) -> bool:
    import shutil
    global scan_size
    all_tracks = sorted(mkv.tracks_non_video, key=lambda t: not t.enabled)
    if not any(t.enabled for t in all_tracks if t.type == 'subtitles'):
        all_tracks = [t for t in all_tracks if t.type != 'subtitles']
    for track in all_tracks:
        if not track.enabled:
            scan_size += track.size

    term_w = shutil.get_terminal_size().columns
    sep = '=' * min(term_w, 100)

    out = f'\n{mkv.file_path.name}\n'
    out += format_track_table(all_tracks)
    out += f'\n{sep}'
    tqdm.write(out)
    return False


def smart_object(mkv: MKV, dest: Path) -> int:
    # Only audio changes trigger reprocessing; subtitle-only deltas skipped.
    audio_tracks = mkv.tracks_by_type.get('audio', [])
    if all(t.enabled for t in audio_tracks):
        return 0

    return finish_object(mkv, dest)


def process_object(mkv: MKV, dest: Path) -> int:
    enabled: list[Track] = []
    if args.audio:
        enabled.extend([t for t in mkv.tracks_by_type.get('audio', []) if t.language in args.audio])
    if args.subtitle:
        enabled.extend([t for t in mkv.tracks_by_type.get('subtitles', []) if t.language in args.subtitle])
    # no -s → all subtitles removed (same behaviour as smart)

    # Skip if audio set unchanged (subtitle-only diffs do not qualify).
    current_audio = {t for t in mkv.tracks_non_video if t.enabled and t.type == 'audio'}
    target_audio = {t for t in enabled if t.type == 'audio'}
    if current_audio == target_audio:
        return 0

    for track in mkv.tracks_non_video:
        track.enabled = track in enabled

    ensure_min_enabled(mkv, 'audio', args.audio)
    ensure_min_enabled(mkv, 'subtitles', args.subtitle)

    return finish_object(mkv, dest)


def finish_object(mkv: MKV, dest: Path) -> int:
    if args.output:
        dest_l = Path(args.output).with_suffix('.mkv')
    elif args.inplace and not args.dry:
        dest_l = mkv.file_path.with_suffix('.temp.mkv')
        if os.path.isfile(dest_l):
            os.remove(dest_l)
    else:
        relative_name = mkv.file_path.relative_to(input_path)
        dest_l = dest / relative_name

    command = mkv.command(dest_l, use_langs=args.command == 'trim')
    command.append(f'{str(mkv.file_path)}')

    result_commands.append(' '.join(command) + ';')

    if not args.dry:
        enabled_tracks = [track for track in mkv.tracks_non_video if track.enabled]
        name = trunc_mid(mkv.file_path.name)
        tqdm.write(f'\n{name}')
        tqdm.write('Selected:')
        for track in enabled_tracks:
            tqdm.write(f'  {track.description}')
        if args.interactive and not Util.ask_yes_no('Process?'):
            tqdm.write('  Skipped.')
            return 0
        before_size = mkv.file_path.stat().st_size if args.perfile else 0
        error = Util.run_command_live(command)
        if args.inplace and not error:
            if args.perfile:
                after_size = dest_l.stat().st_size if dest_l.exists() else 0
            Util.replace_file(dest_l, mkv.file_path)
        elif error:
            tqdm.write(f'\033[91m  Error: {error}\033[0m')
            return 0
        else:
            if args.perfile:
                after_size = dest_l.stat().st_size if dest_l.exists() else 0
        if args.perfile and before_size:
            diff = before_size - after_size
            sign = '-' if diff >= 0 else '+'
            tqdm.write(f'  Approx space diff ~ {sign}{humanize.naturalsize(abs(diff), binary=True)}')

    return 0


def ensure_min_enabled(mkv: MKV, track_type: str, track_langs: list = None):
    if track_langs:
        for lang in track_langs:
            by_lang = mkv.tracks_by_type_lang.get(track_type, {}).get(lang, [])
            if by_lang and not any(t.enabled for t in by_lang):
                by_lang[0].enabled = True
        all_tracks = mkv.tracks_by_type.get(track_type, [])
        if all_tracks and not any(t.enabled for t in all_tracks):
            all_tracks[0].enabled = True
    elif track_type == 'audio':
        all_tracks = mkv.tracks_by_type.get(track_type, [])
        if all_tracks and not any(t.enabled for t in all_tracks):
            all_tracks[0].enabled = True


def smart_tracks_disable_all(mkv: MKV):
    smart_tracks_disable(mkv, track_type='audio', track_langs=args.audio)
    ensure_min_enabled(mkv, 'audio', args.audio)
    if args.subtitle:
        smart_tracks_disable(mkv, track_type='subtitles', track_langs=args.subtitle)
    else:
        for track in mkv.tracks_by_type.get('subtitles', []):
            track.enabled = False
    ensure_min_enabled(mkv, 'subtitles', args.subtitle)


def smart_tracks_disable(mkv: MKV, track_type: str = None, track_langs: list = None):
    if track_type is None or track_langs is None:
        return
    tracks = mkv.tracks_by_type_lang.get(track_type, {})
    for lang in tracks:
        by_lang: list[Track] = mkv.tracks_by_type_lang.get(track_type, {}).get(lang, None)
        if by_lang is None or len(by_lang) == 0:
            continue
        keep_lang = lang in track_langs
        best_named_set = False
        for track in by_lang:
            if not track.track_name:
                track.enabled = True
            elif keep_lang and not best_named_set:
                track.enabled = True
                best_named_set = True
            else:
                track.enabled = False


def load_weights() -> dict:
    if args.weights:
        weights_path = Path(args.weights)
        if not weights_path.exists():
            sys.exit(f'Weights file not found: {weights_path}')
        with open(weights_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    bundled = Util.resource_path('data/default_weights.json')
    try:
        with open(bundled, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def main():
    global default_weights, LANG_OPTIONS
    # Force line-buffered stdout/stderr so tqdm.write output flushes
    # immediately in PyInstaller frozen bundles (where default may be block-buffered).
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except AttributeError:
        pass
    # When running as a frozen bundle, prefer the bundled mkvmerge
    if getattr(sys, 'frozen', False):
        bundle_dir = getattr(sys, '_MEIPASS', str(Path(sys.executable).parent))
        os.environ['PATH'] = bundle_dir + os.pathsep + os.environ.get('PATH', '')
    Util.check_dependency(['mkvmerge'])
    LANG_OPTIONS = load_lang_options()
    help_path = Util.resource_path('data/help.txt')
    with open(help_path, 'r', encoding='utf-8') as file:
        get_arguments(file.read())

    validate_args()
    default_weights = load_weights()

    print('\nStart mkv_trim' + ' Dry Run' if args.dry else '')

    signal.signal(signal.SIGINT, signal_handler)

    if args.dry or args.command == 'scan':
        dest = input_path if input_path.is_dir() else input_path.parent
        dest = dest.joinpath('Trim')
    elif not args.inplace:
        dest = Util.make_dir(relative_path='Trim', base_path=input_path if input_path.is_dir() else input_path.parent)
    else:
        dest = input_path

    input_size = 0
    if args.stats and not args.dry:
        input_size = Util.get_size(input_path)

    if input_path.is_file():
        if input_path.suffix.lower().lstrip('.') not in ('mkv', 'm4v', 'mp4'):
            sys.exit(0)
        print(f"Scanning {input_path}\n")
        try:
            mkv = MKV(input_path, expanded=args.stats or args.perfile)
        except ValueError as e:
            sys.exit(f'Error: {e}')
        if args.command != 'trim':
            smart_tracks_disable_all(mkv)
        rout_object(mkv, dest)
    else:
        process_dir(input_path, dest)

    if args.dry:
        print('\n'.join(result_commands))
    elif args.stats:
        if args.command == 'scan':
            input_size = scan_size
        else:
            if args.inplace:
                input_size -= Util.get_size(input_path)
            else:
                input_size -= Util.get_size(dest)
        print(f'\nApprox space diff ~ {humanize.naturalsize(input_size, binary=True)}')

    print('\nEnd trim_audio' + ' Dry Run' if args.dry else '')


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
