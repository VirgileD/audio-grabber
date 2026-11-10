"""Configuration: ~/.config/agscribe/config.toml and the Hugging Face token."""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

import tomli_w

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "agscribe"
CONFIG_FILE = CONFIG_DIR / "config.toml"
TOKEN_FILE = CONFIG_DIR / "hf_token"

# Name of the folder, inside the recordings folder, holding everything agscribe generates
DATA_DIR_NAME = "transcripts-data"

WHISPER_MODEL = "large-v3-turbo"
DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"
DIARIZATION_TERMS_URL = f"https://huggingface.co/{DIARIZATION_MODEL}"
TOKEN_URL = "https://huggingface.co/settings/tokens"


@dataclass
class MatchingConfig:
    # Cosine similarity between a speaker's voice and a known person's voice.
    # Starting values, to be calibrated on real recordings.
    sure: float = 0.75     # at or above: named automatically
    unsure: float = 0.55   # between unsure and sure: suggested, confirmed by the user


@dataclass
class Config:
    recordings_dir: str = ""
    whisper_model: str = WHISPER_MODEL
    diarization_model: str = DIARIZATION_MODEL
    # "wsl": play clips in the terminal through WSLg; "windows": open them in the Windows player
    playback: str = "wsl"
    playback_tested: bool = False
    matching: MatchingConfig = field(default_factory=MatchingConfig)

    @property
    def recordings_path(self) -> Path:
        return Path(self.recordings_dir)

    @property
    def data_path(self) -> Path:
        return self.recordings_path / DATA_DIR_NAME


def load_config() -> Config | None:
    """Return the saved configuration, or None if agscribe isn't configured yet."""
    if not CONFIG_FILE.exists():
        return None
    raw = tomllib.loads(CONFIG_FILE.read_text())
    matching = MatchingConfig(**raw.pop("matching", {}))
    known = {k: v for k, v in raw.items() if k in Config.__dataclass_fields__}
    return Config(**known, matching=matching)


def save_config(config: Config) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        "# agscribe configuration - written by `agscribe configure`, safe to edit.\n"
        + tomli_w.dumps(asdict(config))
    )


def load_token() -> str | None:
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        return token or None
    return None


def save_token(token: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Create with owner-only permissions before writing the secret
    TOKEN_FILE.touch(mode=0o600, exist_ok=True)
    TOKEN_FILE.chmod(0o600)
    TOKEN_FILE.write_text(token.strip() + "\n")
