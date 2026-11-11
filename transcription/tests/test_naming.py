"""Tests for speaker naming, deleted audio and cleanup (scripted answers, fake player)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from pyannote.core import Annotation, Segment
from typer.testing import CliRunner

from agscribe import cli
from agscribe import recordings as rec
from agscribe.naming import NamingSession, RecordingData, guess_name, speaker_clips
from agscribe.pipeline import transcribe_recording
from agscribe.voices import KNOWN, SUGGESTED, UNKNOWN, VoiceStore
from test_transcribe import FakeWhisper, _add_recording, _config

ALICE = np.array([1, 0, 0], dtype=np.float32)
BOB = np.array([0, 1, 0], dtype=np.float32)


class TwoSpeakers:
    """Diarization stand-in: SPEAKER_00 talks 0-1.5 s, SPEAKER_01 3-4.5 s."""

    def __init__(self, first=ALICE, second=BOB):
        self.embeddings = np.vstack([first, second])

    def __call__(self, file, hook=None):
        annotation = Annotation()
        annotation[Segment(0.0, 1.5)] = "SPEAKER_00"
        annotation[Segment(3.0, 4.5)] = "SPEAKER_01"
        return SimpleNamespace(
            speaker_diarization=annotation,
            exclusive_speaker_diarization=annotation,
            speaker_embeddings=self.embeddings,
        )


class ScriptedUI:
    def __init__(self, answers):
        self.answers = list(answers)
        self.output: list[str] = []
        self.prompts: list[str] = []

    def say(self, text):
        self.output.append(text)

    def ask(self, prompt, completions=None):
        self.prompts.append(prompt)
        assert self.answers, f"unexpected question: {prompt}"
        return self.answers.pop(0)


class FakePlayer:
    def __init__(self):
        self.played = 0

    def play(self, samples, sample_rate, wait=False):
        self.played += 1

    def stop(self):
        pass


def _transcribed(config, store, name, diarization=None):
    recording = _add_recording(config, name)
    loaded = SimpleNamespace(whisper=FakeWhisper(), diarization=diarization or TwoSpeakers())
    transcribe_recording(recording, rec.discover(config), config, loaded, store, lambda *_: None)
    return recording


def _session(config, store, answers, player=None):
    ui = ScriptedUI(answers)
    loads = []

    def loader(path, start, end):
        loads.append((path.name, start, end))
        return np.zeros(1600, dtype=np.float32)

    session = NamingSession(config, store, rec.discover(config), ui, player or FakePlayer(), clip_loader=loader)
    return session, ui, loads


def _speakers(recording):
    return rec.read_json(recording.data_dir / "speakers.json")


def _markdown(config, recording):
    state = recording.state()
    return (config.transcripts_path / state["transcript_file"]).read_text(encoding="utf-8")


# ----------------------------------------------------------------------------- basics


def test_guess_name():
    assert guess_name("alice.martin@corp.com") == "Alice Martin"
    assert guess_name("bob_durand-jr@x.io") == "Bob Durand Jr"


def test_clips_are_the_speakers_longest_stretches(tmp_path):
    config = _config(tmp_path)
    store = VoiceStore(config.data_path)
    recording = _transcribed(config, store, "Recording_2026-11-12_100000")
    clips = speaker_clips(RecordingData.load(recording), "SPEAKER_01")
    assert [(c.start, c.text) for c in clips] == [(3.1, "Hi Alice.")]


# ----------------------------------------------------------------------------- naming


def test_naming_a_new_person(tmp_path):
    config = _config(tmp_path)
    store = VoiceStore(config.data_path)
    recording = _transcribed(config, store, "Recording_2026-11-12_100000")
    player = FakePlayer()
    # SPEAKER_00 and SPEAKER_01 talk as long: both asked, in order
    session, ui, loads = _session(
        config, store, ["alice@corp.com", "Alice Martin", "bob@corp.com", ""], player
    )
    assert session.run([recording]) == 2

    speakers = _speakers(recording)
    assert speakers["SPEAKER_00"]["status"] == KNOWN and speakers["SPEAKER_00"]["email"] == "alice@corp.com"
    assert speakers["SPEAKER_01"]["email"] == "bob@corp.com"
    assert VoiceStore(config.data_path).people == {
        "alice@corp.com": {"name": "Alice Martin"},
        "bob@corp.com": {"name": "Bob"},  # Enter accepted the guessed name
    }
    assert (config.data_path / "voices" / "alice@corp.com").is_dir()
    markdown = _markdown(config, recording)
    assert "**[00:00:00] Alice Martin:** Hello everyone." in markdown
    assert "**[00:00:03] Bob:** Hi Alice." in markdown
    assert "to identify" not in markdown
    assert player.played == 2 and loads[0][0] == recording.mp3.name


def test_a_known_voice_is_recognized_in_the_next_recording(tmp_path):
    config = _config(tmp_path)
    store = VoiceStore(config.data_path)
    first = _transcribed(config, store, "Recording_2026-11-12_100000")
    session, _, _ = _session(config, store, ["alice@corp.com", "Alice", "s"])
    session.run([first])

    second = _transcribed(config, VoiceStore(config.data_path), "Recording_2026-11-13_100000")
    speakers = _speakers(second)
    assert speakers["SPEAKER_00"]["status"] == KNOWN
    assert speakers["SPEAKER_00"]["email"] == "alice@corp.com"


def test_confirming_and_rejecting_a_suggestion(tmp_path):
    config = _config(tmp_path)
    store = VoiceStore(config.data_path)
    store.add_person("alice@corp.com", "Alice")
    # Close to both speakers' voices, but not sure: both suggested as Alice
    store.add_sample("alice@corp.com", "earlier", np.array([1, 1, 0.2], dtype=np.float32))
    recording = _transcribed(config, store, "Recording_2026-11-12_100000")
    speakers = _speakers(recording)
    assert speakers["SPEAKER_00"]["status"] == SUGGESTED
    assert speakers["SPEAKER_01"]["status"] == SUGGESTED

    # First: Enter = yes. Second: n = not Alice, then an email
    session, ui, _ = _session(config, store, ["", "n", "bob@corp.com", "Bob"])
    session.run([recording])
    speakers = _speakers(recording)
    assert speakers["SPEAKER_00"]["status"] == KNOWN and speakers["SPEAKER_00"]["email"] == "alice@corp.com"
    assert speakers["SPEAKER_01"]["email"] == "bob@corp.com"
    assert speakers["SPEAKER_01"]["rejected"] == ["alice@corp.com"]
    assert any("Is this Alice?" in prompt for prompt in ui.prompts)


def test_merging_two_speakers(tmp_path):
    config = _config(tmp_path)
    store = VoiceStore(config.data_path)
    recording = _transcribed(config, store, "Recording_2026-11-12_100000")
    # Speaker 1 is the same person as speaker 2; then name speaker 2
    session, _, _ = _session(config, store, ["m", "2", "bob@corp.com", "Bob"])
    session.run([recording])
    speakers = _speakers(recording)
    assert speakers["SPEAKER_00"]["merged_into"] == "SPEAKER_01"
    markdown = _markdown(config, recording)
    assert "**[00:00:00] Bob:** Hello everyone. Hi Alice." in markdown


def test_invalid_answer_asks_again(tmp_path):
    config = _config(tmp_path)
    store = VoiceStore(config.data_path)
    recording = _transcribed(config, store, "Recording_2026-11-12_100000")
    session, ui, _ = _session(config, store, ["not an email", "?", "q"])
    session.run([recording])
    assert any("Not an email" in line for line in ui.output)
    assert _speakers(recording)["SPEAKER_00"]["status"] == UNKNOWN


def test_known_display_name_can_be_typed_instead_of_email(tmp_path):
    config = _config(tmp_path)
    store = VoiceStore(config.data_path)
    store.add_person("alice@corp.com", "Alice Martin")
    recording = _transcribed(config, store, "Recording_2026-11-12_100000")
    session, _, _ = _session(config, store, ["alice martin", "q"])
    session.run([recording])
    assert _speakers(recording)["SPEAKER_00"]["email"] == "alice@corp.com"


# ---------------------------------------------------------------------------- backfill


def test_naming_someone_proposes_them_in_other_recordings(tmp_path):
    config = _config(tmp_path)
    store = VoiceStore(config.data_path)
    older = _transcribed(config, store, "Recording_2026-11-12_100000")
    newer = _transcribed(config, store, "Recording_2026-11-13_100000")
    # Name SPEAKER_00 of the newer one: the older one's SPEAKER_00 has the same
    # voice and is proposed -> yes. Then skip the rest.
    session, ui, _ = _session(config, store, ["alice@corp.com", "Alice", "y", "s", "s"])
    session.run([newer, older])
    assert _speakers(older)["SPEAKER_00"]["email"] == "alice@corp.com"
    assert any("may be Alice" in line for line in ui.output)
    assert "Alice:" in _markdown(config, older)


def test_a_rejected_proposal_is_not_proposed_again(tmp_path):
    config = _config(tmp_path)
    store = VoiceStore(config.data_path)
    older = _transcribed(config, store, "Recording_2026-11-12_100000")
    newer = _transcribed(config, store, "Recording_2026-11-13_100000")
    session, _, _ = _session(config, store, ["alice@corp.com", "Alice", "n", "q"])
    session.run([newer])
    assert _speakers(older)["SPEAKER_00"]["rejected"] == ["alice@corp.com"]
    # Naming Alice again elsewhere doesn't bring the rejected speaker back
    session, ui, _ = _session(config, store, ["q"])
    session.backfill("alice@corp.com", exclude=("x", "y"))
    assert not any("may be Alice" in line for line in ui.output)


# ------------------------------------------------------------------------ deleted audio


def test_deleted_audio_keeps_the_recording_and_names_from_quotes(tmp_path):
    config = _config(tmp_path)
    store = VoiceStore(config.data_path)
    recording = _transcribed(config, store, "Recording_2026-11-12_100000")
    recording.mp3.unlink()
    recording.log.unlink()

    [found] = rec.discover(config)
    assert found.name == recording.name and found.status() == rec.DONE and not found.has_audio

    player = FakePlayer()
    session, ui, loads = _session(config, store, ["alice@corp.com", "Alice", "q"], player)
    session.run([found])
    assert player.played == 0 and loads == []  # quotes only
    assert any('"Hello everyone."' in line for line in ui.output)
    markdown = _markdown(config, found)
    assert "(audio deleted)" in markdown and "Alice:" in markdown


def test_unfinished_recordings_without_audio_are_forgotten(tmp_path):
    config = _config(tmp_path)
    recording = _add_recording(config, "Recording_2026-11-12_100000")
    recording.data_dir.mkdir(parents=True)
    recording.mp3.unlink()
    assert rec.discover(config) == []


# ----------------------------------------------------------------------------- cleanup


def test_cleanup_deletes_only_fully_named_recordings(tmp_path, monkeypatch):
    config = _config(tmp_path)
    store = VoiceStore(config.data_path)
    named = _transcribed(config, store, "Recording_2026-11-12_100000")
    unnamed = _transcribed(config, store, "Recording_2026-11-13_100000", TwoSpeakers(BOB * -1, ALICE * -1))
    new = _add_recording(config, "Recording_2026-11-14_100000")
    session, _, _ = _session(config, store, ["alice@corp.com", "Alice", "bob@corp.com", "Bob"])
    session.run([named])

    monkeypatch.setattr(cli, "_require_config", lambda: config)
    result = CliRunner().invoke(cli.app, ["cleanup", "--older-than", "0", "--yes"])
    assert result.exit_code == 0, result.output
    assert not named.mp3.exists() and not named.log.exists()
    assert unnamed.mp3.exists()  # speakers still to name
    assert new.mp3.exists()      # not transcribed yet
    assert "kept: speakers still to name" in result.output
    assert named.state()["audio_deleted"]
    assert "(audio deleted)" in _markdown(config, named)

    result = CliRunner().invoke(cli.app, ["cleanup", "--older-than", "0", "--yes"])
    assert "No fully named recording" in result.output


def test_cleanup_respects_the_age_limit(tmp_path, monkeypatch):
    config = _config(tmp_path)
    store = VoiceStore(config.data_path)
    recording = _transcribed(config, store, "Recording_2099-01-01_100000")  # in the future
    session, _, _ = _session(config, store, ["alice@corp.com", "Alice", "bob@corp.com", "Bob"])
    session.run([recording])
    monkeypatch.setattr(cli, "_require_config", lambda: config)
    result = CliRunner().invoke(cli.app, ["cleanup", "--yes"])
    assert recording.mp3.exists()
    assert "older than 30 days" in result.output
