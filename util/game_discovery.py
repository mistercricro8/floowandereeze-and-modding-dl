"""Locate Duel Links account data in registered Steam libraries."""

import contextlib
import os
import re
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None


def resolve_game_root(account_or_game_path: str | Path | None) -> Path | None:
    """Resolve the game installation root containing dlpc_Data/data.unity3d."""
    if not account_or_game_path:
        return None
    cleaned = str(account_or_game_path).strip().strip("'\"")
    if not cleaned:
        return None
    p = Path(cleaned).expanduser()
    try:
        resolved = p.resolve()
    except (OSError, RuntimeError):
        resolved = p

    if resolved.parent.name.lower() == "localdata":
        candidate = resolved.parent.parent
        if (candidate / "dlpc_Data" / "data.unity3d").is_file():
            return candidate

    if resolved.name.lower() == "localdata":
        candidate = resolved.parent
        if (candidate / "dlpc_Data" / "data.unity3d").is_file():
            return candidate

    if (resolved / "dlpc_Data" / "data.unity3d").is_file():
        return resolved

    return None


def normalize_game_path(folder: str | Path | None) -> str | None:
    """Resolve an account directory, LocalData, or game installation directory."""
    if not folder:
        return None
    cleaned = str(folder).strip().strip("'\"")
    if not cleaned:
        return None
    path = Path(cleaned).expanduser()
    try:
        resolved_path = path.resolve()
    except (OSError, RuntimeError):
        resolved_path = path

    candidates = [resolved_path]
    local_data = (
        resolved_path
        if resolved_path.name.lower() == "localdata"
        else resolved_path / "LocalData"
    )
    if local_data.is_dir():
        with contextlib.suppress(OSError):
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


def find_steam_duel_links_paths() -> list[str]:
    """Find each valid account, including installations in secondary libraries."""
    found: dict[str, str] = {}
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
    library_paths: list[str] = []
    library_path_keys: set[str] = set()

    for steam_path in steam_paths:
        key = _path_key(steam_path)
        if key not in library_path_keys:
            library_paths.append(steam_path)
            library_path_keys.add(key)

        for vdf_subpath in (
            ("steamapps", "libraryfolders.vdf"),
            ("config", "libraryfolders.vdf"),
        ):
            library_file = Path(steam_path).joinpath(*vdf_subpath)
            if not library_file.is_file():
                continue

            try:
                contents = library_file.read_text(encoding="utf-8")
            except OSError:
                continue

            library_matches = re.findall(r'"path"\s+"([^"]+)"', contents)
            library_matches.extend(
                re.findall(
                    r'^\s*"\d+"\s+"([A-Za-z]:[^"]+|/[^"]+)"', contents, re.MULTILINE
                )
            )
            for library_path in library_matches:
                normalized_path = library_path.replace("\\\\", "\\")
                cand_str = str(Path(normalized_path))
                cand_key = _path_key(cand_str)
                if cand_key not in library_path_keys:
                    library_paths.append(cand_str)
                    library_path_keys.add(cand_key)

    return library_paths


def _get_steam_install_paths() -> list[str]:
    """Return likely Steam install paths across Windows, Linux, and Wine."""
    steam_paths: list[str] = []

    if winreg:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"
            ) as key:
                for value_name in ("SteamPath", "InstallPath"):
                    try:
                        steam_path = winreg.QueryValueEx(key, value_name)[0]
                        if steam_path:
                            steam_paths.append(str(Path(steam_path).expanduser()))
                    except FileNotFoundError:
                        continue
        except OSError:
            pass

    for environment_variable in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        program_files = os.environ.get(environment_variable)
        if program_files:
            candidate = Path(program_files) / "Steam"
            if candidate.is_dir():
                steam_paths.append(str(candidate))

    home = Path.home()
    linux_candidates = [
        # Native
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".steam/root",
        # Flatpak Steam
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        home / ".var/app/com.valvesoftware.Steam/.steam/steam",
        home / ".var/app/com.valvesoftware.Steam/data/Steam",
        # Snap Steam
        home / "snap/steam/common/.local/share/Steam",
        home / "snap/steam/common/.steam/steam",
    ]

    for env_var in ("STEAM_DIR", "STEAM_HOME", "STEAM_PATH"):
        val = os.environ.get(env_var)
        if val:
            linux_candidates.append(Path(val).expanduser())

    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        linux_candidates.append(Path(xdg_data).expanduser() / "Steam")

    if Path("Z:/").is_dir():
        for subpath in (
            ".local/share/Steam",
            ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        ):
            wine_glob = list(Path("Z:/home").glob(f"*/{subpath}"))
            linux_candidates.extend(wine_glob)

    for candidate in linux_candidates:
        if candidate.is_dir():
            steam_paths.append(str(candidate.resolve()))

    return list(dict.fromkeys(steam_paths))


def _path_key(path: str) -> str:
    """Return a normalized key for cross-platform path comparisons."""
    p = Path(path).expanduser()
    try:
        resolved = str(p.resolve())
    except (OSError, RuntimeError):
        resolved = str(p)
    return os.path.normcase(os.path.normpath(resolved))
