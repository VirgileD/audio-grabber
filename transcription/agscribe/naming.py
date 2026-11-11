"""Interactive speaker naming (agscribe name).

For each unidentified or uncertain speaker: show what they said, play clips of
their voice (quotes only if the recording's audio was deleted), and ask for an
email. Naming someone stores their voice, updates the transcript, then proposes
the same voice in other transcripts (backfill).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
from rich.markup import escape

from . import pipeline
from .config import Config
from .recordings import DONE, Recording, read_json, write_json
from .render import clock, resolve, short_duration
from .voices import KNOWN, SUGGESTED, UNKNOWN, VoiceStore, is_email, normalize

CLIPS_PER_SPEAKER = 3
CLIP_SECONDS = 10.0
QUOTE_CHARS = 160

HELP = (
    "  [dim]Type an email (Tab completes known people), or: "
    "\\[r] replay  \\[c] another clip  \\[m] same person as another speaker  \\[s] skip  \\[q] quit[/dim]"
)


class UI(Protocol):
    def say(self, text: str) -> None: ...
    def ask(self, prompt: str, completions: dict[str, str] | None = None) -> str: ...


class AudioPlayer(Protocol):
    def play(self, samples: np.ndarray, sample_rate: int, wait: bool = False) -> None: ...
    def stop(self) -> None: ...


@dataclass
class Clip:
    start: float
    end: float
    text: str


@dataclass
class RecordingData:
    """One transcribed recording, loaded for naming."""

    recording: Recording
    transcript: dict[str, Any]
    speakers: dict[str, Any]
    embeddings: dict[str, np.ndarray] = field(default_factory=dict)

    @classmethod
    def load(cls, recording: Recording) -> RecordingData | None:
        state = recording.state() or {}
        transcript = read_json(recording.data_dir / "transcript.json")
        speakers = read_json(recording.data_dir / "speakers.json")
        if state.get("status") != DONE or transcript is None or speakers is None:
            return None
        embeddings = {}
        npz = recording.data_dir / "embeddings.npz"
        if npz.is_file():
            with np.load(npz) as data:
                embeddings = {label: data[label] for label in data.files}
        return cls(recording, transcript, speakers, embeddings)

    def pending_labels(self) -> list[str]:
        """Speakers still to identify or confirm, most talkative first."""
        labels = [
            label for label, info in self.speakers.items()
            if not info.get("merged_into") and info.get("status") in (UNKNOWN, SUGGESTED, None)
            and self.speaks(label)
        ]
        return sorted(labels, key=lambda l: self.speakers[l].get("talk_time", 0), reverse=True)

    def speaks(self, label: str) -> bool:
        """True if at least one transcribed word is attributed to this speaker."""
        return any(resolve(w[3], self.speakers) == label for w in self.transcript.get("words", []))

    def title(self, label: str) -> str:
        info = self.speakers.get(label, {})
        return f"Speaker {info.get('number', '?')}"


# ------------------------------------------------------------------------- clips


def speaker_clips(data: RecordingData, label: str, count: int = CLIPS_PER_SPEAKER) -> list[Clip]:
    """The longest stretches of speech of a speaker (up to CLIP_SECONDS each)."""
    runs: list[list] = []  # [start, end, [words]]
    for start, end, text, word_label in data.transcript.get("words", []):
        if resolve(word_label, data.speakers) != label:
            if runs and runs[-1][3]:
                runs[-1][3] = False  # close the current run
            continue
        if runs and runs[-1][3] and start - runs[-1][1] < 1.5:
            runs[-1][1] = end
            runs[-1][2].append((start, text))
        else:
            runs.append([start, end, [(start, text)], True])

    longest = sorted(runs, key=lambda r: r[1] - r[0], reverse=True)[:count]
    clips = []
    for start, end, words, _ in sorted(longest, key=lambda r: r[0]):
        clip_end = min(end, start + CLIP_SECONDS)
        text = "".join(t for s, t in words if s < clip_end).strip()
        if len(text) > QUOTE_CHARS:
            text = text[: QUOTE_CHARS - 1].rsplit(" ", 1)[0] + "…"
        clips.append(Clip(start, clip_end, text))
    return clips


# ----------------------------------------------------------------------- session


def guess_name(email: str) -> str:
    """alice.martin@corp.com -> Alice Martin"""
    local = email.split("@", 1)[0]
    return " ".join(part.capitalize() for part in local.replace("_", ".").replace("-", ".").split(".") if part)


class NamingSession:
    def __init__(
        self,
        config: Config,
        store: VoiceStore,
        recordings: list[Recording],
        ui: UI,
        player: AudioPlayer | None,
        clip_loader=None,
    ) -> None:
        self.config = config
        self.store = store
        self.recordings = recordings
        self.ui = ui
        self.player = player
        self.clip_loader = clip_loader
        self.named = 0

    # ---------------------------------------------------------------- main loop

    def run(self, targets: list[Recording]) -> int:
        """Name speakers in the given recordings. Returns how many were named."""
        for recording in targets:
            data = RecordingData.load(recording)
            if data is None:
                continue
            labels = data.pending_labels()
            if not labels:
                continue
            self.ui.say(
                f"\n[bold]{recording.name}[/bold]  ({recording.started:%Y-%m-%d %H:%M}, "
                f"{len(labels)} to name){'' if recording.has_audio else '  [dim]audio deleted: quotes only[/dim]'}"
            )
            for label in labels:
                # The speaker may have been merged or named meanwhile (backfill)
                info = data.speakers.get(label, {})
                if info.get("merged_into") or info.get("status") == KNOWN:
                    continue
                if self.name_speaker(data, label) == "quit":
                    return self.named
        return self.named

    def name_speaker(self, data: RecordingData, label: str) -> str:
        info = data.speakers[label]
        clips = speaker_clips(data, label)
        talk = short_duration(info.get("talk_time", 0))
        self.ui.say(f"\n  [bold]{data.title(label)}[/bold] ({talk} of speech, {info.get('turns', 0)} turn{'s' if info.get('turns', 0) != 1 else ''})")
        for clip in clips:
            self.ui.say(f"    [{clock(clip.start)}] \"{escape(clip.text)}\"")

        clip_index = 0
        self._play(data, clips, clip_index)
        suggested = info.get("status") == SUGGESTED and info.get("email")
        if suggested:
            score = f" [dim](similarity {info.get('score', 0):.2f})[/dim]" if info.get("score") else ""
            self.ui.say(f"  Sounds like [bold]{self.store.display_name(info['email'])}[/bold] <{info['email']}>{score}")
        self.ui.say(HELP)

        while True:
            if suggested:
                prompt = f"  Is this {self.store.display_name(info['email'])}? [Y/n] or email"
            else:
                prompt = "  Email"
            answer = self.ui.ask(prompt, self._completions()).strip()
            command = answer.lower()

            if suggested and command in ("", "y", "yes"):
                self.assign(data, label, info["email"])
                return "named"
            if suggested and command in ("n", "no"):
                self._reject(data, label, info["email"])
                suggested = False
                continue
            if command == "":
                continue
            if command == "r":
                self._play(data, clips, clip_index)
            elif command == "c":
                if len(clips) > 1:
                    clip_index = (clip_index + 1) % len(clips)
                    self.ui.say(f"    [{clock(clips[clip_index].start)}] \"{escape(clips[clip_index].text)}\"")
                self._play(data, clips, clip_index)
            elif command == "m":
                if self.merge(data, label):
                    return "merged"
            elif command == "s":
                self._stop()
                return "skip"
            elif command == "q":
                self._stop()
                return "quit"
            elif command in ("?", "h", "help"):
                self.ui.say(HELP)
            else:
                email = self._resolve_person(answer)
                if email is None:
                    self.ui.say("  [red]✗[/red] Not an email (nor a known person's name). [?] for help")
                    continue
                self.assign(data, label, email)
                return "named"

    # ----------------------------------------------------------------- actions

    def assign(self, data: RecordingData, label: str, email: str, backfill: bool = True) -> None:
        self._stop()
        email = email.strip().lower()
        if email not in self.store.people:
            default = guess_name(email)
            name = self.ui.ask(f"  New person: display name [{default}]").strip() or default
            self.store.add_person(email, name)

        info = data.speakers[label]
        info.update(status=KNOWN, email=email, named_by="user")
        learned = False
        embedding = data.embeddings.get(label)
        if embedding is not None:
            learned = self.store.add_sample(email, f"{data.recording.name}__{label}", embedding)
        self._save(data)
        self.named += 1
        note = "" if learned else " [dim](voice too short to learn from)[/dim]"
        self.ui.say(f"  [green]✓[/green] {self.store.display_name(email)} <{email}>{note}")

        if backfill and learned:
            self.backfill(email, exclude=(data.recording.name, label))

    def merge(self, data: RecordingData, label: str) -> bool:
        """Mark this speaker as the same person as another speaker of the recording."""
        others = [
            other for other, info in data.speakers.items()
            if other != label and not info.get("merged_into") and data.speaks(other)
        ]
        if not others:
            self.ui.say("  No other speaker in this recording.")
            return False
        by_number = {}
        for other in others:
            info = data.speakers[other]
            name = (
                f" = {self.store.display_name(info['email'])}"
                if info.get("status") == KNOWN and info.get("email") else ""
            )
            by_number[str(info.get("number"))] = other
            self.ui.say(f"    {info.get('number')}) {data.title(other)}{name}")
        answer = self.ui.ask("  Same person as speaker number (empty to cancel)").strip()
        target = by_number.get(answer)
        if target is None:
            return False
        data.speakers[label]["merged_into"] = target
        self._save(data)
        self.ui.say(f"  [green]✓[/green] {data.title(label)} merged into {data.title(target)}")
        return True

    def backfill(self, email: str, exclude: tuple[str, str]) -> None:
        """Propose unnamed speakers of other recordings that sound like this person."""
        samples = self.store.samples().get(email)
        if samples is None:
            return
        candidates = []
        for recording in self.recordings:
            data = RecordingData.load(recording)
            if data is None:
                continue
            # Other recordings only: in the same recording, one person can't be two
            # speakers (a voice split in two is fixed with "m", merge)
            if recording.name == exclude[0]:
                continue
            for label in data.pending_labels():
                if email in data.speakers[label].get("rejected", []):
                    continue
                vector = normalize(data.embeddings[label]) if label in data.embeddings else None
                if vector is None or samples.shape[1] != vector.shape[0]:
                    continue
                score = float(np.max(samples @ vector))
                if score >= self.config.matching.unsure:
                    candidates.append((score, data, label))
        if not candidates:
            return

        name = self.store.display_name(email)
        self.ui.say(f"\n  {len(candidates)} speaker(s) in other recordings may be {name}:")
        for score, data, label in sorted(candidates, key=lambda c: c[0], reverse=True):
            clips = speaker_clips(data, label, count=1)
            self.ui.say(
                f"\n  {data.recording.name} - {data.title(label)} sounds like {name} "
                f"[dim](similarity {score:.2f}){'' if data.recording.has_audio else ', audio deleted'}[/dim]"
            )
            for clip in clips:
                self.ui.say(f"    [{clock(clip.start)}] \"{escape(clip.text)}\"")
            self._play(data, clips, 0)
            while True:
                answer = self.ui.ask(f"  Same person ({name})? [y/N, r = replay]").strip().lower()
                if answer == "r":
                    self._play(data, clips, 0)
                    continue
                break
            if answer in ("y", "yes"):
                self.assign(data, label, email, backfill=False)
            else:
                self._stop()
                self._reject(data, label, email)

    # ----------------------------------------------------------------- helpers

    def _reject(self, data: RecordingData, label: str, email: str) -> None:
        """Remember that this speaker is not this person (never proposed again)."""
        info = data.speakers[label]
        rejected = info.setdefault("rejected", [])
        if email not in rejected:
            rejected.append(email)
        if info.get("status") == SUGGESTED and info.get("email") == email:
            info.update(status=UNKNOWN, email=None)
        self._save(data)

    def _save(self, data: RecordingData) -> None:
        write_json(data.recording.data_dir / "speakers.json", data.speakers)
        pipeline.render_recording(data.recording, self.config, self.store)

    def _resolve_person(self, answer: str) -> str | None:
        if is_email(answer):
            return answer.strip().lower()
        # A known person's display name works too
        for email, info in self.store.people.items():
            if (info.get("name") or "").strip().lower() == answer.strip().lower():
                return email
        return None

    def _completions(self) -> dict[str, str]:
        return {email: info.get("name", "") for email, info in self.store.people.items()}

    def _play(self, data: RecordingData, clips: list[Clip], index: int) -> None:
        if not clips or self.player is None or not data.recording.has_audio or self.clip_loader is None:
            return
        clip = clips[index]
        try:
            samples = self.clip_loader(data.recording.mp3, clip.start, clip.end)
            self.player.play(samples, 16000)
        except Exception as exc:  # noqa: BLE001 - playback problems must not stop naming
            self.ui.say(f"  [yellow]![/yellow] Can't play the clip: {exc}")

    def _stop(self) -> None:
        if self.player is not None:
            self.player.stop()

