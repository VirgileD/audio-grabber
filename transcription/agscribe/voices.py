"""Known people and their voice samples.

<data>/people.json            {"alice@corp.com": {"name": "Alice Martin"}, ...}  (editable)
<data>/voices/<email>/*.npy   voice samples (speaker embeddings), one per recording
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .recordings import read_json, write_json

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

KNOWN = "known"          # matched automatically (or named by the user)
SUGGESTED = "suggested"  # probably someone: to confirm
UNKNOWN = "unknown"      # nobody we know


def is_email(text: str) -> bool:
    return bool(EMAIL.match(text.strip()))


def normalize(vector: np.ndarray) -> np.ndarray | None:
    """Unit-length copy, or None for an empty (all-zero) embedding."""
    vector = np.asarray(vector, dtype=np.float32).ravel()
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm < 1e-6:
        return None
    return vector / norm


@dataclass
class Match:
    email: str
    score: float  # cosine similarity, 1.0 = identical


class VoiceStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.people_file = data_dir / "people.json"
        self.voices_dir = data_dir / "voices"
        self.people: dict[str, dict] = read_json(self.people_file) or {}
        self._samples: dict[str, np.ndarray] | None = None

    # ------------------------------------------------------------------ people

    def display_name(self, email: str) -> str:
        return (self.people.get(email) or {}).get("name") or email

    def add_person(self, email: str, name: str | None = None) -> None:
        email = email.strip().lower()
        entry = self.people.setdefault(email, {})
        if name:
            entry["name"] = name.strip()
        write_json(self.people_file, dict(sorted(self.people.items())))

    # ------------------------------------------------------------------ voices

    def add_sample(self, email: str, sample_id: str, embedding: np.ndarray) -> bool:
        """Store a voice sample for a person; False if the embedding is empty."""
        vector = normalize(embedding)
        if vector is None:
            return False
        folder = self.voices_dir / email.strip().lower()
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder / f"{sample_id}.npy", vector)
        self._samples = None
        return True

    def samples(self) -> dict[str, np.ndarray]:
        """email -> (n_samples, dim) matrix of unit vectors."""
        if self._samples is None:
            self._samples = {}
            if self.voices_dir.is_dir():
                for folder in sorted(self.voices_dir.iterdir()):
                    vectors = [
                        v for v in (normalize(np.load(f)) for f in sorted(folder.glob("*.npy")))
                        if v is not None
                    ]
                    if vectors:
                        self._samples[folder.name] = np.vstack(vectors)
        return self._samples

    def best_match(self, embedding: np.ndarray, exclude: set[str] = frozenset()) -> Match | None:
        """Closest known person (best of each person's samples)."""
        vector = normalize(embedding)
        if vector is None:
            return None
        best: Match | None = None
        for email, matrix in self.samples().items():
            if email in exclude or matrix.shape[1] != vector.shape[0]:
                continue
            score = float(np.max(matrix @ vector))
            if best is None or score > best.score:
                best = Match(email, score)
        return best


def classify(
    embeddings: dict[str, np.ndarray], store: VoiceStore, sure: float, unsure: float
) -> dict[str, tuple[str, Match | None]]:
    """Speaker label -> (KNOWN / SUGGESTED / UNKNOWN, match).

    One person can't be two speakers of the same recording: if two speakers match
    the same person, only the closest stays KNOWN, the other becomes SUGGESTED
    (often the same voice split in two: the user can merge them)."""
    result: dict[str, tuple[str, Match | None]] = {}
    for label, embedding in embeddings.items():
        match = store.best_match(embedding)
        if match is None or match.score < unsure:
            result[label] = (UNKNOWN, match)
        elif match.score >= sure:
            result[label] = (KNOWN, match)
        else:
            result[label] = (SUGGESTED, match)

    by_person: dict[str, list[str]] = {}
    for label, (status, match) in result.items():
        if status == KNOWN and match:
            by_person.setdefault(match.email, []).append(label)
    for labels in by_person.values():
        labels.sort(key=lambda label: result[label][1].score, reverse=True)
        for label in labels[1:]:
            result[label] = (SUGGESTED, result[label][1])
    return result
