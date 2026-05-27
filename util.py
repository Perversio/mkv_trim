from pathlib import Path
from functools import lru_cache
from tqdm import tqdm
import subprocess
import argparse
import shutil
import sys
import os
import re


class Util:
    @staticmethod
    def argparse_default(prompt: str = 'Default script description', add_help: bool = True) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description=prompt, formatter_class=argparse.RawDescriptionHelpFormatter, add_help=add_help)
        parser.add_argument('--input', '-i', help='Input file/folder', type=str)
        parser.add_argument('--dry', '-d', help='Produce a list of commands, no processing', action='store_true')
        return parser

    @staticmethod
    def validate_args_input(args: argparse.Namespace) -> Path:
        input_path: Path = Path.cwd()
        if args.input:
            u_path: str = args.input
            u_path = u_path.strip("'\" ")
            path = Path(u_path)
            if not path.exists():
                path = input_path / u_path
            input_path = path

        if not input_path.exists():
            sys.exit(f"{input_path} not found")

        return input_path

    @staticmethod
    @lru_cache(maxsize=5)
    def list_dir(dir_path, recursive=False) -> list:
        assert isinstance(dir_path, (str, Path))
        path = Path(dir_path)
        result: list[Path] = [file for file in path.iterdir() if os.access(file, os.R_OK)]

        if recursive:
            result_dirs = [file for file in result if file.is_dir()]
            for file in result_dirs:
                result.extend(Util.list_dir(file, recursive))

        return result

    @staticmethod
    def list_dir_files(dir_path, recursive=False) -> list:
        result: list[Path] = [file for file in Util.list_dir(dir_path, recursive) if
                              file.is_file() and not file.name.startswith(".")]
        return result

    @staticmethod
    def list_dir_file_type(dir_path, extension, recursive=False) -> list:
        return Util.list_dir_file_types(dir_path, extensions=[extension], recursive=recursive)

    @staticmethod
    def list_dir_file_types(dir_path, extensions: list[str], recursive=False) -> list:
        sub_result = Util.list_dir_files(dir_path, recursive)
        assert isinstance(extensions, list)

        ext_local: list[str] = [ext.lower().removeprefix(".") for ext in extensions]

        result = [file for file in sub_result if file.name.split('.')[-1] in ext_local]
        # list(filter(lambda file: file.name.endswith("." + ext_local), sub_result))

        result.sort(key=lambda f: f.name)

        return result

    @staticmethod
    def make_dir(relative_path: str, base_path: Path = Path.cwd()) -> Path:
        assert isinstance(relative_path, str)

        result: Path = base_path / relative_path
        if not result.exists():
            print("Created output directory at " + str(result))
            result.mkdir()
        return result

    @staticmethod
    def ask_yes_no(disclamer: str) -> bool:
        options = ['Y', 'n']
        result = ''
        fuse = 3

        while result not in options and fuse > 0:
            result = input(f'{disclamer} (Y/n) ')
            fuse -= 1

        return result != 'n'

    @staticmethod
    def replace_file(source_path: Path, target_path: Path):
        if not os.path.isfile(source_path) or not os.path.isfile(target_path):
            return
        os.remove(target_path)
        target_path.with_suffix('.mkv')
        os.rename(source_path, target_path.with_suffix('.mkv'))

    @staticmethod
    def get_size(path: Path) -> int:
        result = 0
        if path.is_dir():
            for dirpath, dirnames, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):  # Skip if it is a symlink
                        result += os.path.getsize(fp)
        return result

    @staticmethod
    def resource_path(relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, relative_path)

    @staticmethod
    def run_command_live(command) -> str:
        result = None
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        pbar = tqdm(total=100, unit="%", bar_format="{l_bar}{bar} | {postfix}", position=0, leave=True)

        try:
            while True:
                output = process.stdout.readline()
                if output == "" and process.poll() is not None:
                    break
                if output:
                    strip = output.strip()
                    match = re.search(r'Progress: (\d+)%', strip)
                    if match:
                        progress = int(match.group(1))
                        pbar.n = progress  # Update progress bar to the current progress value
                        pbar.refresh()

            rc = process.poll()
            if rc != 0:
                result = process.stderr.read().strip()

        finally:
            pbar.close()
        return result

    @staticmethod
    def print(text: str):
        term_width = shutil.get_terminal_size().columns
        if len(text) <= term_width:
            print(text)
            return
        part_length = (term_width - 3) // 2
        print(text[:part_length] + '...' + text[-part_length:])

    @staticmethod
    def check_dependency(dep: list[str]):
        for d in dep:
            if not shutil.which(d):
                sys.exit(f'{d} not found.  MediaInfo must be installed and available in PATH.')
