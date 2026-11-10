"""Recordings on disk and their transcription state.

Each recording has a working folder: <recordings>/transcripts-data/recordings/<name>/
holding transcript.json, speakers.json, embeddings.npz and state.json. state.json is
written last, so a run interrupted half-way leaves no state and is simply redone.
The Markdown in the transcripts folder is an output only: moving or deleting it
never triggers a new transcription.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Config

# AudioGrabber writes this line at the end of the .log when a recording is finished
SESSION_COMPLETED = "Session completed successfully"
# Without a .log, a recording is considered finished once unchanged for this long
QUIET_SECONDS = 120

_TIMESTAMP = re.compile(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})")

# Recording states
NEW = "new"
IN_PROGRESS = "recording"
DONE = "done"
FAILED = "failed"


@dataclass
class Recording:
    mp3: Path
    data_dir: Path  # working folder for this recording

    @property
    def name(self) -> str:
        return self.mp3.stem

    @property
    def log(self) -> Path:
        return self.mp3.with_suffix(".log")

    @property
    def started(self) -> datetime:
        """Start time from the file name (Recording_2026-11-12_100000), else file time."""
        match = _TIMESTAMP.search(self.name)
        if match:
            try:
                return datetime(*(int(part) for part in match.groups()))
            except ValueError:
                pass
        return datetime.fromtimestamp(self.mp3.stat().st_mtime)

    @property
    def state_file(self) -> Path:
        return self.data_dir / "state.json"

    def state(self) -> dict[str, Any] | None:
        return read_json(self.state_file)

    def status(self) -> str:
        state = self.state()
        if state and state.get("status") in (DONE, FAILED):
            return state["status"]
        if not self.is_finished():
            return IN_PROGRESS
        return NEW

    def is_finished(self) -> bool:
        """False while AudioGrabber is still writing this recording."""
        try:
            if self.log.exists():
                return SESSION_COMPLETED in self.log.read_text(encoding="utf-8", errors="replace")
            return time.time() - self.mp3.stat().st_mtime > QUIET_SECONDS
        except OSError:
            return False


def discover(config: Config) -> list[Recording]:
    """All MP3 recordings in the recordings folder, oldest first."""
    folder = config.recordings_path
    if not folder.is_dir():
        return []
    recordings = [
        Recording(mp3, config.data_path / "recordings" / mp3.stem)
        for mp3 in folder.iterdir()
        if mp3.suffix.lower() == ".mp3" and mp3.is_file()
    ]
    return sorted(recordings, key=lambda r: (r.started, r.name))


def find(config: Config, names: list[str]) -> list[Recording]:
    """Recordings matching names given on the command line (file name, stem or path)."""
    by_name = {r.name.lower(): r for r in discover(config)}
    found, missing = [], []
    for name in names:
        key = Path(name.replace("\\", "/")).stem.lower()
        if key in by_name:
            found.append(by_name[key])
        else:
            missing.append(name)
    if missing:
        raise LookupError(f"Recording(s) not found in {config.recordings_path}: {', '.join(missing)}")
    return found


def transcript_filename(recording: Recording, taken: set[str]) -> str:
    """'2026-11-12 10h00 transcript.md', with ' (2)', ' (3)'... if already taken."""
    base = f"{recording.started:%Y-%m-%d %Hh%M} transcript"
    name, counter = f"{base}.md", 2
    while name.lower() in taken:
        name = f"{base} ({counter}).md"
        counter += 1
    return name


def taken_transcript_names(recordings: list[Recording], exclude: Recording) -> set[str]:
    """Transcript file names already used by other recordings."""
    taken = set()
    for recording in recordings:
        if recording.name == exclude.name:
            continue
        state = recording.state() or {}
        if state.get("transcript_file"):
            taken.add(state["transcript_file"].lower())
    return taken


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, data: Any) -> None:
    """Write atomically: a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
