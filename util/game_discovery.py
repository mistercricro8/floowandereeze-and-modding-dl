"""Locate Duel Links account data in registered Steam libraries."""

import os
import re
from ntpath import normcase, normpath
from os.path import exists, join
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None


def normalize_game_path(folder):
    """Resolve an account directory, LocalData, or game installation directory."""
    path = Path(folder).expanduser()
    candidates = [path]
    local_data = path if path.name.lower() == "localdata" else path / "LocalData"
    if local_data.is_dir():
        candidates.extend(sorted(local_data.iterdir()))
    for candidate in candidates:
        if (
            candidate.is_dir()
            and candidate.parent.name.lower() == "localdata"
            and candidate.name != "00000000"
            and (candidate.parent.parent / "dlpc_Data" / "data.unity3d").is_file()
        ):
            return str(candidate.resolve())
    return None


def find_steam_duel_links_paths():
    """Find each valid account, including installations in secondary libraries."""
    found = {}
    for library in _get_steam_library_paths():
        common = Path(library) / "steamapps" / "common"
        game_roots = [common / "Yu-Gi-Oh! Duel Links"]
        manifest = Path(library) / "steamapps" / "appmanifest_601510.acf"
        try:
            match = re.search(
                r'"installdir"\s+"([^"/\\]+)"', manifest.read_text(encoding="utf-8")
            )
            if match:
                game_roots.append(common / match.group(1))
        except OSError:
            pass
        for game_root in game_roots:
            local_data = game_root / "LocalData"
            try:
                accounts = sorted(local_data.iterdir())
            except OSError:
                continue
            for account in accounts:
                path = normalize_game_path(str(account))
                if path:
                    found[_path_key(path)] = path
    return list(found.values())


def _get_steam_library_paths() -> list[str]:
    """Find Steam's main install directory and configured library directories."""
    steam_paths = _get_steam_install_paths()
    library_paths = []
    library_path_keys = set()

    for steam_path in steam_paths:
        if _path_key(steam_path) not in library_path_keys:
            library_paths.append(steam_path)
            library_path_keys.add(_path_key(steam_path))

        library_file = join(steam_path, "steamapps", "libraryfolders.vdf")
        if not exists(library_file):
            continue

        try:
            with open(library_file, encoding="utf-8") as file:
                contents = file.read()
        except OSError:
            continue

        library_matches = re.findall(r'"path"\s+"([^"]+)"', contents)
        library_matches.extend(
            re.findall(r'^\s*"\d+"\s+"([A-Za-z]:[^"]+)"', contents, re.MULTILINE)
        )
        for library_path in library_matches:
            library_path = library_path.replace("\\\\", "\\")
            if _path_key(library_path) not in library_path_keys:
                library_paths.append(library_path)
                library_path_keys.add(_path_key(library_path))

    return library_paths


def _get_steam_install_paths() -> list[str]:
    """Return likely Steam install paths, including the Windows registry value."""
    steam_paths = []

    if winreg:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"
            ) as key:
                for value_name in ("SteamPath", "InstallPath"):
                    try:
                        steam_path = winreg.QueryValueEx(key, value_name)[0]
                    except FileNotFoundError:
                        continue
                    if steam_path:
                        steam_paths.append(steam_path)
        except OSError:
            pass

    for environment_variable in ("ProgramFiles(x86)", "ProgramFiles"):
        program_files = os.environ.get(environment_variable)
        if program_files:
            steam_paths.append(join(program_files, "Steam"))

    return list(dict.fromkeys(steam_paths))


def _path_key(path: str) -> str:
    """Return a Windows-normalized key for case-insensitive path comparisons."""
    return normcase(normpath(path))
