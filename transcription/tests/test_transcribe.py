"""Tests for the transcription pipeline logic (no real models needed)."""

from __future__ import annotations

import os
import shutil
import time
from importlib import resources
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pyannote.core import Annotation, Segment

from agscribe import recordings as rec
from agscribe.config import Config
from agscribe.pipeline import assign_speakers, speaker_stats, transcribe_recording
from agscribe.render import render_markdown, turns
from agscribe.voices import KNOWN, SUGGESTED, UNKNOWN, VoiceStore, classify

SAMPLE = Path(str(resources.files("agscribe") / "data" / "jfk.flac"))


# ------------------------------------------------------------------ word -> speaker


def test_words_take_the_speaker_of_their_turn():
    words = [(0.1, 0.5, " Hello"), (2.1, 2.5, " Hi"), (2.6, 3.0, " there")]
    turns_ = [(0.0, 1.0, "A"), (2.0, 3.5, "B")]
    assert assign_speakers(words, turns_) == ["A", "B", "B"]


def test_word_in_a_gap_goes_to_the_nearest_turn_when_close():
    words = [(1.1, 1.3, " x")]  # middle 1.2: 0.2 s after A ends, 0.8 s before B
    assert assign_speakers(words, [(0.0, 1.0, "A"), (2.0, 3.0, "B")]) == ["A"]
    words = [(1.7, 1.9, " x")]  # closer to B
    assert assign_speakers(words, [(0.0, 1.0, "A"), (2.0, 3.0, "B")]) == ["B"]


def test_word_far_from_any_turn_keeps_the_previous_speaker():
    words = [(0.2, 0.4, " a"), (5.0, 5.2, " b")]
    assert assign_speakers(words, [(0.0, 1.0, "A"), (10.0, 11.0, "B")]) == ["A", "A"]


def test_words_before_the_first_turn_take_the_first_speaker():
    words = [(0.0, 0.2, " a"), (5.0, 5.2, " b")]
    assert assign_speakers(words, [(5.0, 6.0, "B")]) == ["B", "B"]


def test_no_turns_at_all():
    assert assign_speakers([(0.0, 0.2, " a")], []) == [None]


def test_speakers_are_numbered_by_first_appearance():
    stats = speaker_stats([(5.0, 6.0, "SPEAKER_00"), (1.0, 2.0, "SPEAKER_01"), (7.0, 9.0, "SPEAKER_00")])
    assert stats["SPEAKER_01"]["number"] == 1
    assert stats["SPEAKER_00"]["number"] == 2
    assert stats["SPEAKER_00"]["talk_time"] == 3.0
    assert stats["SPEAKER_00"]["turns"] == 2


# --------------------------------------------------------------------------- voices


def _vector(*values):
    return np.array(values, dtype=np.float32)


def test_classify_known_suggested_unknown(tmp_path):
    store = VoiceStore(tmp_path)
    store.add_person("alice@corp.com", "Alice")
    store.add_sample("alice@corp.com", "r1", _vector(1, 0, 0))
    result = classify(
        {
            "same": _vector(1, 0, 0),                 # cosine 1.0
            "close": _vector(1, 0.9, 0),              # cosine ~0.74
            "other": _vector(0, 0, 1),                # cosine 0
            "empty": _vector(0, 0, 0),                # no voice sample
        },
        store,
        sure=0.8,
        unsure=0.5,
    )
    assert result["same"][0] == KNOWN and result["same"][1].email == "alice@corp.com"
    assert result["close"][0] == SUGGESTED
    assert result["other"][0] == UNKNOWN
    assert result["empty"] == (UNKNOWN, None)


def test_one_person_cannot_be_two_known_speakers(tmp_path):
    store = VoiceStore(tmp_path)
    store.add_sample("alice@corp.com", "r1", _vector(1, 0))
    result = classify({"a": _vector(1, 0.05), "b": _vector(1, 0.2)}, store, sure=0.8, unsure=0.5)
    assert result["a"][0] == KNOWN      # closest stays known
    assert result["b"][0] == SUGGESTED  # the other one is to confirm


def test_people_file_is_written_sorted_and_lowercase(tmp_path):
    store = VoiceStore(tmp_path)
    store.add_person("Zoe@Corp.com", "Zoé")
    store.add_person("alice@corp.com", "Alice")
    assert list(VoiceStore(tmp_path).people) == ["alice@corp.com", "zoe@corp.com"]
    assert VoiceStore(tmp_path).display_name("zoe@corp.com") == "Zoé"


# --------------------------------------------------------------------------- render


def test_turns_join_consecutive_words_and_follow_merges():
    words = [[0, 1, " Hello", "A"], [1, 2, " all.", "A"], [3, 4, " Yes", "B"], [5, 6, " indeed.", "C"]]
    speakers = {"A": {}, "B": {}, "C": {"merged_into": "B"}}
    assert turns(words, speakers) == [("A", 0, "Hello all."), ("B", 3, "Yes indeed.")]


def test_long_speech_is_split_into_paragraphs_at_sentence_ends():
    words = [[0, 1, " First.", "A"], [70, 71, " Second", "A"], [72, 73, " part.", "A"]]
    assert [t[2] for t in turns(words, {"A": {}})] == ["First.", "Second part."]


def test_markdown_header_participants_and_todo(tmp_path):
    store = VoiceStore(tmp_path)
    store.add_person("alice@corp.com", "Alice Martin")
    transcript = {
        "started": "2026-11-12T10:00:00",
        "language": "fr",
        "duration": 125.0,
        "words": [[4, 5, " Bonjour.", "S0"], [11, 12, " Salut.", "S1"], [20, 21, " Oui.", "S2"]],
    }
    speakers = {
        "S0": {"number": 1, "status": KNOWN, "email": "alice@corp.com"},
        "S1": {"number": 2, "status": UNKNOWN, "email": None},
        "S2": {"number": 3, "status": SUGGESTED, "email": "bob@corp.com"},
    }
    text = render_markdown(transcript, speakers, store, r"C:\rec\Recording_x.mp3")
    assert text.startswith("# Recording 2026-11-12 10:00\n")
    assert r"- Recording: C:\rec\Recording_x.mp3" in text
    assert "- Duration: 2:05 · Language: French" in text
    assert (
        "- Participants: Alice Martin <alice@corp.com>, Speaker 2 (unidentified), "
        "bob@corp.com <bob@corp.com> (to confirm)" in text
    )
    assert "> 1 speaker to identify, 1 to confirm: run `agscribe name`" in text
    assert "**[00:00:04] Alice Martin:** Bonjour." in text
    assert "**[00:00:11] Speaker 2:** Salut." in text
    assert "**[00:00:20] bob@corp.com?:** Oui." in text


# ------------------------------------------------------------------- recording state


def _config(tmp_path) -> Config:
    (tmp_path / "recordings").mkdir()
    (tmp_path / "notes").mkdir()
    return Config(recordings_dir=str(tmp_path / "recordings"), transcripts_dir=str(tmp_path / "notes"))


def _add_recording(config: Config, name: str, finished: bool | None = True) -> rec.Recording:
    mp3 = config.recordings_path / f"{name}.mp3"
    shutil.copy(SAMPLE, mp3)  # content doesn't matter for state tests
    if finished is not None:
        log = "Session Started\n" + (rec.SESSION_COMPLETED + "\n" if finished else "")
        mp3.with_suffix(".log").write_text(log)
    return rec.Recording(mp3, config.data_path / "recordings" / name)


def test_status_from_log_and_state(tmp_path):
    config = _config(tmp_path)
    finished = _add_recording(config, "Recording_2026-11-12_100000")
    ongoing = _add_recording(config, "Recording_2026-11-12_110000", finished=False)
    assert finished.status() == rec.NEW
    assert ongoing.status() == rec.IN_PROGRESS
    rec.write_json(finished.state_file, {"status": rec.DONE})
    assert finished.status() == rec.DONE
    rec.write_json(finished.state_file, {"status": rec.FAILED})
    assert finished.status() == rec.FAILED


def test_without_log_a_recording_is_finished_once_quiet(tmp_path):
    config = _config(tmp_path)
    recording = _add_recording(config, "Recording_2026-11-12_100000", finished=None)
    assert recording.status() == rec.IN_PROGRESS  # just written
    old = time.time() - rec.QUIET_SECONDS - 10
    os.utime(recording.mp3, (old, old))
    assert recording.status() == rec.NEW


def test_discover_and_find(tmp_path):
    config = _config(tmp_path)
    _add_recording(config, "Recording_2026-11-12_110000")
    _add_recording(config, "Recording_2026-11-12_100000")
    assert [r.name for r in rec.discover(config)] == [
        "Recording_2026-11-12_100000",
        "Recording_2026-11-12_110000",
    ]
    found = rec.find(config, ["Recording_2026-11-12_110000.mp3", r"C:\x\recording_2026-11-12_100000.MP3"])
    assert [r.name for r in found] == ["Recording_2026-11-12_110000", "Recording_2026-11-12_100000"]
    with pytest.raises(LookupError):
        rec.find(config, ["nope"])


def test_transcript_file_names(tmp_path):
    config = _config(tmp_path)
    first = _add_recording(config, "Recording_2026-11-12_100005")
    second = _add_recording(config, "Recording_2026-11-12_100040")  # same minute
    assert rec.transcript_filename(first, set()) == "2026-11-12 10h00 transcript.md"
    rec.write_json(first.state_file, {"status": rec.DONE, "transcript_file": "2026-11-12 10h00 transcript.md"})
    taken = rec.taken_transcript_names(rec.discover(config), second)
    assert rec.transcript_filename(second, taken) == "2026-11-12 10h00 transcript (2).md"


# ------------------------------------------------------------- full run, fake models


class FakeWhisper:
    def transcribe(self, audio, **kwargs):
        word = lambda s, e, t: SimpleNamespace(start=s, end=e, word=t)  # noqa: E731
        segments = [
            SimpleNamespace(end=2.0, words=[word(0.2, 0.6, " Hello"), word(0.7, 1.2, " everyone.")]),
            SimpleNamespace(end=5.0, words=[word(3.1, 3.5, " Hi"), word(3.6, 4.0, " Alice.")]),
        ]
        return iter(segments), SimpleNamespace(language="en")


class FakeDiarization:
    def __init__(self, fail=False):
        self.fail = fail

    def __call__(self, file, hook=None):
        if self.fail:
            raise RuntimeError("diarization exploded")
        annotation = Annotation()
        annotation[Segment(0.0, 1.5)] = "SPEAKER_00"
        annotation[Segment(3.0, 4.5)] = "SPEAKER_01"
        return SimpleNamespace(
            speaker_diarization=annotation,
            exclusive_speaker_diarization=annotation,
            speaker_embeddings=np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32),
        )


def _loaded(fail=False):
    return SimpleNamespace(whisper=FakeWhisper(), diarization=FakeDiarization(fail))


def test_full_run_writes_everything_and_marks_done(tmp_path):
    config = _config(tmp_path)
    recording = _add_recording(config, "Recording_2026-11-12_100000")
    store = VoiceStore(config.data_path)
    store.add_person("alice@corp.com", "Alice Martin")
    store.add_sample("alice@corp.com", "earlier", np.array([1, 0, 0], dtype=np.float32))

    state = transcribe_recording(recording, rec.discover(config), config, _loaded(), store, lambda *_: None)

    assert state["status"] == rec.DONE
    assert recording.status() == rec.DONE
    assert state["transcript_file"] == "2026-11-12 10h00 transcript.md"
    markdown = (config.transcripts_path / state["transcript_file"]).read_bytes().decode()
    assert "\r\n" in markdown  # Windows line endings
    assert "**[00:00:00] Alice Martin:** Hello everyone." in markdown
    assert "**[00:00:03] Speaker 2:** Hi Alice." in markdown
    speakers = rec.read_json(recording.data_dir / "speakers.json")
    assert speakers["SPEAKER_00"]["status"] == KNOWN
    assert speakers["SPEAKER_01"]["status"] == UNKNOWN
    assert set(np.load(recording.data_dir / "embeddings.npz").files) == {"SPEAKER_00", "SPEAKER_01"}

    # Not proposed again, even when the Markdown is deleted
    (config.transcripts_path / state["transcript_file"]).unlink()
    assert [r for r in rec.discover(config) if r.status() in (rec.NEW, rec.FAILED)] == []


def test_failure_leaves_no_done_state(tmp_path):
    config = _config(tmp_path)
    recording = _add_recording(config, "Recording_2026-11-12_100000")
    with pytest.raises(RuntimeError):
        transcribe_recording(
            recording, rec.discover(config), config, _loaded(fail=True), VoiceStore(config.data_path), lambda *_: None
        )
    assert recording.status() == rec.NEW  # will be retried
    assert not list(config.transcripts_path.iterdir())


def test_redo_keeps_the_same_transcript_file(tmp_path):
    config = _config(tmp_path)
    recording = _add_recording(config, "Recording_2026-11-12_100000")
    store = VoiceStore(config.data_path)
    first = transcribe_recording(recording, rec.discover(config), config, _loaded(), store, lambda *_: None)
    again = transcribe_recording(recording, rec.discover(config), config, _loaded(), store, lambda *_: None)
    assert again["transcript_file"] == first["transcript_file"]
    assert len(list(config.transcripts_path.iterdir())) == 1
