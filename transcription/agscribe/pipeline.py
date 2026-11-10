"""Transcribe one recording: speech-to-text, who spoke when, voice matching, Markdown."""

from __future__ import annotations

import bisect
import os
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import numpy as np

from . import models, windows
from .config import Config
from .recordings import (
    DONE,
    Recording,
    read_json,
    taken_transcript_names,
    transcript_filename,
    write_json,
)
from .render import render_markdown
from .voices import VoiceStore, classify

# progress(phase, fraction or None)
Progress = Callable[[str, float | None], None]

# A word whose middle falls in no speech turn goes to the nearest turn within this
# distance (seconds), else to the previous word's speaker
NEAREST_TURN_SECONDS = 1.0

DEFAULT_SECONDS_PER_AUDIO_SECOND = 0.5


class Models:
    """Loads the models once, on first use, for all recordings of a run."""

    def __init__(self, config: Config, token: str | None) -> None:
        self.config = config
        self.token = token
        self._whisper = None
        self._diarization = None

    @property
    def whisper(self):
        if self._whisper is None:
            self._whisper = models.load_whisper(self.config)
        return self._whisper

    @property
    def diarization(self):
        if self._diarization is None:
            self._diarization = models.load_diarization(self.config, self.token)
        return self._diarization


# ------------------------------------------------------------------- word -> speaker


def assign_speakers(
    words: list[tuple[float, float, str]], turns: list[tuple[float, float, str]]
) -> list[str | None]:
    """Speaker label for each word, from non-overlapping speech turns (start, end, label)."""
    turns = sorted(turns)
    starts = [turn[0] for turn in turns]
    labels: list[str | None] = []
    previous: str | None = None
    for start, end, _ in words:
        middle = (start + end) / 2
        index = bisect.bisect_right(starts, middle) - 1
        label = None
        # The turn containing the middle of the word
        if index >= 0 and turns[index][0] <= middle <= turns[index][1]:
            label = turns[index][2]
        else:
            # Otherwise the nearest turn (before or after), if close enough
            candidates = []
            if index >= 0:
                candidates.append((middle - turns[index][1], turns[index][2]))
            if index + 1 < len(turns):
                candidates.append((turns[index + 1][0] - middle, turns[index + 1][2]))
            candidates = [c for c in candidates if c[0] <= NEAREST_TURN_SECONDS]
            if candidates:
                label = min(candidates)[1]
        label = label or previous
        labels.append(label)
        previous = label
    # Words before the first identified one take the first known label
    first = next((label for label in labels if label), None)
    return [label or first for label in labels]


def speaker_stats(turns: list[tuple[float, float, str]]) -> dict[str, dict[str, Any]]:
    """Talk time, number of turns and first appearance per speaker; numbered 1, 2, ...
    in order of first appearance (numbers never change afterwards)."""
    stats: dict[str, dict[str, Any]] = {}
    for start, end, label in sorted(turns):
        info = stats.setdefault(label, {"talk_time": 0.0, "turns": 0, "first_seen": start})
        info["talk_time"] += end - start
        info["turns"] += 1
    for number, label in enumerate(sorted(stats, key=lambda l: stats[l]["first_seen"]), start=1):
        stats[label]["number"] = number
        stats[label]["talk_time"] = round(stats[label]["talk_time"], 2)
        stats[label]["first_seen"] = round(stats[label]["first_seen"], 2)
    return stats


# ------------------------------------------------------------------------ pipeline


def transcribe_recording(
    recording: Recording,
    all_recordings: list[Recording],
    config: Config,
    loaded: Models,
    store: VoiceStore,
    progress: Progress,
) -> dict[str, Any]:
    started = time.perf_counter()

    progress("Reading audio", None)
    audio = models.load_audio(recording.mp3)
    duration = len(audio) / models.SAMPLE_RATE

    # 1. Speech to text, with word timestamps
    progress("Transcribing", 0.0)
    segments, info = loaded.whisper.transcribe(
        audio,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        # Each window decoded independently: avoids the repetition loops long
        # recordings can fall into
        condition_on_previous_text=False,
    )
    words: list[tuple[float, float, str]] = []
    for segment in segments:
        for word in segment.words or []:
            words.append((round(word.start, 2), round(word.end, 2), word.word))
        progress("Transcribing", min(1.0, segment.end / duration) if duration else None)

    # 2. Who spoke when (+ one voice embedding per speaker)
    progress("Identifying speakers", None)
    output = loaded.diarization(
        {"waveform": _torch_waveform(audio), "sample_rate": models.SAMPLE_RATE},
        hook=_diarization_hook(progress),
    )
    # (an empty Annotation is falsy: test the attribute, not the value)
    if hasattr(output, "exclusive_speaker_diarization"):
        exclusive, full = output.exclusive_speaker_diarization, output.speaker_diarization
    else:  # older pyannote: the output is the annotation itself
        exclusive = full = output
    all_labels = list(full.labels())
    turns = [
        (round(turn.start, 2), round(turn.end, 2), label)
        for turn, _, label in exclusive.itertracks(yield_label=True)
    ]
    embeddings_matrix = getattr(output, "speaker_embeddings", None)
    embeddings = {}
    if embeddings_matrix is not None:
        embeddings = {label: embeddings_matrix[i] for i, label in enumerate(all_labels)}

    # 3. Words -> speakers, speaker info, voice matching
    word_labels = assign_speakers(words, turns)
    speakers = speaker_stats(turns)
    matches = classify(
        {label: embeddings[label] for label in speakers if label in embeddings},
        store,
        config.matching.sure,
        config.matching.unsure,
    )
    for label, info_ in speakers.items():
        status, match = matches.get(label, ("unknown", None))
        info_["status"] = status
        info_["email"] = match.email if match and status != "unknown" else None
        info_["score"] = round(match.score, 3) if match else None
        info_["merged_into"] = None

    # 4. Save (state.json last: an interrupted run leaves no state and is redone)
    transcript = {
        "recording": recording.name,
        "started": recording.started.isoformat(timespec="seconds"),
        "language": info.language,
        "duration": round(duration, 2),
        "whisper_model": config.whisper_model,
        "diarization_model": config.diarization_model,
        "words": [[s, e, text, label] for (s, e, text), label in zip(words, word_labels)],
    }
    write_json(recording.data_dir / "transcript.json", transcript)
    write_json(recording.data_dir / "speakers.json", speakers)
    _save_embeddings(recording, {l: e for l, e in embeddings.items() if l in speakers})

    previous = recording.state() or {}
    transcript_file = previous.get("transcript_file") or transcript_filename(
        recording, taken_transcript_names(all_recordings, recording)
    )
    write_markdown(recording, config, store, transcript_file, transcript, speakers)

    elapsed = time.perf_counter() - started
    state = {
        "status": DONE,
        "updated": datetime.now().isoformat(timespec="seconds"),
        "transcript_file": transcript_file,
        "language": info.language,
        "duration": round(duration, 2),
        "processing_seconds": round(elapsed, 1),
    }
    write_json(recording.state_file, state)
    _update_speed(config, duration, elapsed)
    return state


def render_recording(recording: Recording, config: Config, store: VoiceStore) -> str | None:
    """Regenerate the Markdown from saved data. Returns the file name, or None."""
    state = recording.state() or {}
    transcript = read_json(recording.data_dir / "transcript.json")
    speakers = read_json(recording.data_dir / "speakers.json")
    if state.get("status") != DONE or transcript is None or speakers is None:
        return None
    write_markdown(recording, config, store, state["transcript_file"], transcript, speakers)
    return state["transcript_file"]


def write_markdown(
    recording: Recording,
    config: Config,
    store: VoiceStore,
    filename: str,
    transcript: dict[str, Any],
    speakers: dict[str, Any],
) -> None:
    mp3_windows = windows.to_windows_path(recording.mp3) or str(recording.mp3)
    text = render_markdown(transcript, speakers, store, mp3_windows)
    target = config.transcripts_path / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    # Windows line endings: the transcripts are read on Windows
    tmp.write_text(text, encoding="utf-8", newline="\r\n")
    os.replace(tmp, target)


# ------------------------------------------------------------------ time estimate


def seconds_per_audio_second(config: Config) -> float:
    stats = read_json(config.data_path / "stats.json") or {}
    return float(stats.get("seconds_per_audio_second", DEFAULT_SECONDS_PER_AUDIO_SECOND))


def _update_speed(config: Config, duration: float, elapsed: float) -> None:
    """Running average of processing speed, for the time estimates."""
    if duration < 60:  # short files are dominated by fixed costs
        return
    current = seconds_per_audio_second(config)
    measured = elapsed / duration
    stats = read_json(config.data_path / "stats.json") or {}
    stats["seconds_per_audio_second"] = round(0.6 * current + 0.4 * measured, 3) if "seconds_per_audio_second" in stats else round(measured, 3)
    write_json(config.data_path / "stats.json", stats)


def audio_duration(recording: Recording) -> float | None:
    """Duration in seconds from the MP3 header (fast, no decoding)."""
    import av

    try:
        with av.open(str(recording.mp3)) as container:
            if container.duration:
                return container.duration / 1_000_000
    except Exception:  # noqa: BLE001 - unreadable file: no estimate
        return None
    return None


# ------------------------------------------------------------------------- helpers


def _torch_waveform(audio: np.ndarray):
    import torch

    return torch.from_numpy(audio)[None, :]


def _diarization_hook(progress: Progress):
    """pyannote reports its steps through a hook: forward them as progress."""

    def hook(step_name, step_artifact, file=None, total=None, completed=None):  # noqa: ARG001
        fraction = completed / total if total and completed is not None else None
        progress("Identifying speakers", fraction)

    return hook


def _save_embeddings(recording: Recording, embeddings: dict[str, np.ndarray]) -> None:
    path = recording.data_dir / "embeddings.npz"
    tmp = path.with_name("embeddings.tmp.npz")
    np.savez(tmp, **{label: np.asarray(vector, dtype=np.float32) for label, vector in embeddings.items()})
    os.replace(tmp, path)
