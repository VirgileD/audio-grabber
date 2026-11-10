"""Windows-side helpers: path conversion and AudioGrabber settings detection."""

from __future__ import annotations

import json
import ntpath
import re
import subprocess
from pathlib import Path

_WINDOWS_PATH = re.compile(r"^([A-Za-z]:[\\/]|\\\\)")
_RUN_KEY = r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"


def _run_windows(args: list[str]) -> str | None:
    """Run a Windows executable from WSL; None if it fails or isn't available."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=20,
            # Never let Windows programs read our stdin: they would swallow the
            # user's answers to the next prompt
            stdin=subprocess.DEVNULL,
            # Windows tools complain when started from a \\wsl$ working directory
            cwd="/mnt/c" if Path("/mnt/c").is_dir() else None,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.replace("\r", "")


def is_windows_path(path: str) -> bool:
    return bool(_WINDOWS_PATH.match(path.strip()))


def to_wsl_path(windows_path: str) -> Path | None:
    """C:\\Users\\x -> /mnt/c/Users/x (via wslpath)."""
    try:
        result = subprocess.run(
            ["wslpath", "-u", windows_path], capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = result.stdout.strip()
    return Path(out) if result.returncode == 0 and out else None


def to_windows_path(wsl_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["wslpath", "-w", str(wsl_path)], capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = result.stdout.strip()
    return out if result.returncode == 0 and out else None


def user_path(text: str) -> Path | None:
    """Turn what the user typed (Windows or Linux path) into a WSL path."""
    text = text.strip().strip('"')
    if is_windows_path(text):
        return to_wsl_path(text)
    return Path(text).expanduser().resolve()


def windows_user_profile() -> Path | None:
    out = _run_windows(["cmd.exe", "/c", "echo %USERPROFILE%"])
    if not out or "%USERPROFILE%" in out:
        return None
    return to_wsl_path(out.strip())


def windows_temp_dir() -> Path | None:
    out = _run_windows(["cmd.exe", "/c", "echo %TEMP%"])
    if not out or "%TEMP%" in out:
        return None
    return to_wsl_path(out.strip())


def audiograbber_exe_dir() -> str | None:
    """Folder of AudioGrabber.exe, from its 'start with Windows' registry entry."""
    out = _run_windows(["reg.exe", "query", _RUN_KEY, "/v", "AudioGrabber"])
    if not out:
        return None
    match = re.search(r"AudioGrabber\s+REG_SZ\s+(.+)", out)
    if not match:
        return None
    exe = match.group(1).strip().strip('"')
    return ntpath.dirname(exe)


def detect_recordings_dir() -> tuple[Path | None, str]:
    """Find AudioGrabber's output folder. Returns (path or None, explanation)."""
    profile = windows_user_profile()
    if profile is None:
        return None, "Windows user profile not found (is this WSL?)"

    settings_file = profile / "AppData" / "Roaming" / "AudioGrabber" / "settings.json"
    if not settings_file.exists():
        return None, f"AudioGrabber settings not found ({settings_file})"

    try:
        settings = json.loads(settings_file.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"Could not read {settings_file}: {exc}"

    folder = str(settings.get("OutputFolder") or "./")
    if is_windows_path(folder):
        path = to_wsl_path(folder)
        return path, f"from AudioGrabber settings ({folder})"

    # Relative folder: AudioGrabber resolves it against the folder of its exe
    exe_dir = audiograbber_exe_dir()
    if exe_dir is None:
        return None, (
            f'AudioGrabber records to "{folder}" (relative to AudioGrabber.exe), but the '
            "exe location is unknown (no 'start with Windows' entry)"
        )
    windows_folder = ntpath.normpath(ntpath.join(exe_dir, folder))
    path = to_wsl_path(windows_folder)
    return path, f'from AudioGrabber settings ("{folder}" next to {exe_dir}\\AudioGrabber.exe)'
