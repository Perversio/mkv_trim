from pathlib import Path
from enum import Enum
from util import Util
import subprocess
import json


class Track:
    def __init__(self, data: [dict]):
        self._raw = data
        self.codec = data['codec']
        self.id = data['id']
        self.type = data['type']
        if self.type == 'video':
            self.is_video = True
        elif self.type == 'audio':
            self.is_audio = True
        else:
            self.is_subtitle = True
        self.codec = data['codec']
        self.weight = 0

        props: [dict] = data['properties']

        self.number = props['number']
        self.language = props['language']
        self.track_name = props.get('track_name', None)
        self.default: bool = bool(props.get('default_track', False))
        self.forced: bool = bool(props.get('forced_track', False))
        self.enabled: bool = bool(props.get('enabled_track', True))

        self.channels = props.get('audio_channels', None)
        self.sampling = props.get('audio_bits_per_sample', None)
        self.frequency = props.get('audio_sampling_frequency', None)

        self.size = int(props.get('tag_number_of_bytes', 0))
        self.bitrate = int(props.get('tag_bits_per_second', 0))
        self.new_name: str = None  # Override track name in output (mkvmerge --track-name)

    def __repr__(self):
        return repr(self.__dict__)

    TYPE_SHORT = {'audio': 'a', 'subtitles': 's', 'video': 'v'}

    @property
    def description(self) -> str:
        t = self.TYPE_SHORT.get(self.type, self.type)
        w = '-' if self.weight < 0 else str(self.weight)
        ch = str(self.channels) if self.channels else ''
        name = Util.trunc_mid(self.track_name or '')
        return f'[{t}] [{w:>4}]  {self.language:<4}  {self.codec:<22}  {ch:<3}  \'{name}\''

    def calc_weight(self, weights=None) -> int:
        if weights is None:
            weights = {}
        self.weight = 0
        if self.channels:
            self.weight = int(self.channels)

        # Generic: keys are mkvmerge -J field paths (dot-separated).
        # Navigate self._raw and substring-match each pattern against the field value.
        for path, matches in weights.items():
            val = self._raw
            for key in path.split('.'):
                val = val.get(key, '') if isinstance(val, dict) else ''
            val_str = str(val).casefold()
            for match_key, score in matches.items():
                if str(match_key).casefold() in val_str:
                    self.weight += int(score)

        return self.weight


class MKV:
    def __init__(self, path: [Path] = None, expanded: bool = False):
        self.tracks: list[Track] = []
        self.tracks_non_video: list[Track] = []
        self.weights = {}
        self.tracks_by_lang: dict[str:list[Track]] = {}
        self.tracks_by_type: dict[str:list[Track]] = {}
        self.tracks_by_type_lang: dict[str:dict[str:list[Track]]] = {}
        self.expand = expanded
        if path:
            self.file_path = path

    def parse_file(self):
        cmd = ['mkvmerge']
        if self.expand:
            cmd.extend(['--engage', 'keep_track_statistics_tags'])
        cmd.extend(['-J', self.file_path])
        output = subprocess.run(cmd, capture_output=True, text=True)
        if output.returncode not in (0, 1):  # 0=ok, 1=warnings; 2+=error
            raise ValueError(f'mkvmerge cannot read file: {self.file_path}')
        try:
            json_data = json.loads(output.stdout)
        except json.JSONDecodeError as e:
            raise ValueError(f'mkvmerge returned invalid data for: {self.file_path}') from e
        for track_data in json_data['tracks']:
            track = Track(track_data)
            by_type_l: dict
            if track:
                self.tracks.append(track)
                if track.type:
                    by_type: list = self.tracks_by_type.get(track.type, [])
                    by_type_l = self.tracks_by_type_lang.get(track.type, dict())
                    if len(by_type) == 0:
                        self.tracks_by_type[track.type] = by_type
                        self.tracks_by_type_lang[track.type] = by_type_l
                    by_type.append(track)
                    if track.type != 'video':
                        self.tracks_non_video.append(track)
                else:
                    continue
                if track.language:
                    if by_type_l is not None:
                        by_lang_l: list = by_type_l.get(track.language, [])
                        if len(by_lang_l) == 0:
                            by_type_l[track.language] = by_lang_l
                        by_lang_l.append(track)
                    by_lang: list = self.tracks_by_lang.get(track.language, [])
                    if len(by_lang) == 0:
                        self.tracks_by_lang[track.language] = by_lang
                    by_lang.append(track)

        self.calc_weights()

    def calc_weights(self):
        if len(self.tracks) <= 0:
            return
        for track in self.tracks:
            track.calc_weight(self.weights)
        audio_by_size: list[Track] = sorted(self.tracks_by_type.get('audio', []),  key=lambda t: t.size)
        audio_by_size.pop().weight += 1
        # Tiebreaker: higher bitrate wins when weights match.
        sort_key = lambda t: (t.weight, t.bitrate)
        for key in self.tracks_by_lang.keys():
            self.tracks_by_lang[key] = sorted(self.tracks_by_lang[key], key=sort_key, reverse=True)
        for key in self.tracks_by_type.keys():
            self.tracks_by_type[key] = sorted(self.tracks_by_type[key], key=sort_key, reverse=True)
        for key in self.tracks_by_type_lang.keys():
            for key_l in self.tracks_by_type_lang[key].keys():
                self.tracks_by_type_lang[key][key_l] = sorted(self.tracks_by_type_lang[key][key_l],
                                                              key=sort_key, reverse=True)

    def command(self, dest: Path, use_langs: bool = False) -> list[str]:
        dest_l = dest.with_suffix('.mkv')
        result = ['mkvmerge', '-o', str(dest_l)]

        # Per-track name overrides (applied before input file argument).
        for t in self.tracks:
            if t.new_name:
                result.extend(['--track-name', f'{t.id}:{t.new_name}'])

        if use_langs:
            audio_langs = list(dict.fromkeys(
                t.language for t in self.tracks_by_type.get('audio', [])
                if t.enabled and t.language))
            sub_langs = list(dict.fromkeys(
                t.language for t in self.tracks_by_type.get('subtitles', [])
                if t.enabled and t.language))
            if audio_langs:
                result.extend(['-a', ','.join(audio_langs)])
            if sub_langs:
                result.extend(['-s', ','.join(sub_langs)])
            else:
                result.append('--no-subtitles')
        else:
            audio_to_keep = sorted(
                str(t.id) for t in self.tracks_by_type.get('audio', [])
                if t.language is not None and t.enabled)
            subs_to_keep = sorted(
                str(t.id) for t in self.tracks_by_type.get('subtitles', [])
                if t.language is not None and t.enabled)
            if audio_to_keep:
                result.extend(['-a', ','.join(audio_to_keep)])
            if subs_to_keep:
                result.extend(['-s', ','.join(subs_to_keep)])
            else:
                result.append('--no-subtitles')

        return result

    def len_tracks(self, types: list[str] = None, langs: list[str] = None, enabled: bool = False) -> int:
        result: list = []
        if isinstance(types, list):
            for t_type in types:
                if isinstance(langs, list):
                    for lang in langs:
                        result.extend(self.tracks_by_type_lang.get(t_type, {}).get(lang, []))
                else:
                    result.extend(self.tracks_by_type.get(t_type, []))
        elif isinstance(langs, list):
            for lang in langs:
                result.extend(self.tracks_by_lang.get(lang, []))
        else:
            result.extend(self.tracks)
        if enabled:
            result = [track for track in result if track.enabled]
        return len(result)

    @property
    def valid(self) -> bool:
        has_audio = self.len_tracks(types=['audio'], enabled=True) > 0
        has_video = self.len_tracks(types=['video']) > 0
        return has_video and has_audio

    @property
    def weights(self):
        return self._weights

    @weights.setter
    def weights(self, weights):
        self._weights = weights
        self.calc_weights()

    @property
    def file_path(self) -> Path:
        return self._file_path

    @file_path.setter
    def file_path(self, path: Path):
        self._file_path = path
        self.parse_file()

    def __repr__(self):
        return repr(self.__dict__)
