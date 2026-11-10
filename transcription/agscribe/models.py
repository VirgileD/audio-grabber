"""Model download and loading. Downloads happen once (setup); runs are offline."""

from __future__ import annotations

import os
import warnings
from pathlib import Path

import numpy as np

from .config import Config

SAMPLE_RATE = 16000

# pyannote warns at import when torchcodec can't load FFmpeg. We never let
# pyannote decode files (audio is passed in memory), so it doesn't matter.
warnings.filterwarnings("ignore", message=r"(?s).*torchcodec is not installed correctly")


def go_offline() -> None:
    """No network at run time: models come from the local cache only.
    Must run before huggingface_hub is imported."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def check_token(token: str, repo_id: str) -> tuple[bool, str]:
    """Check that the token is valid and the model's terms were accepted."""
    from huggingface_hub import HfApi, hf_hub_download
    from huggingface_hub.errors import GatedRepoError, HfHubHTTPError

    token = token.strip()
    if not token:
        return False, "No token."

    # 1. Is the token itself valid? (A gated model answers "no access" for
    #    invalid tokens too, so check this first.)
    try:
        user = HfApi().whoami(token=token)
    except HfHubHTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 401:
            return False, "The token was rejected (invalid or revoked)."
        return False, f"Hugging Face error: {exc}"
    except Exception as exc:  # noqa: BLE001 - network errors come in many types
        return False, f"Network error: {exc}"
    account = user.get("name", "?")

    # 2. Were the model's terms accepted for this account?
    try:
        hf_hub_download(repo_id, "config.yaml", token=token)
    except GatedRepoError:
        return False, (
            f"The token is valid (account '{account}'), but the terms of {repo_id} "
            "haven't been accepted for this account yet."
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not download from {repo_id}: {exc}"
    return True, f"Token OK (account '{account}'), model access granted."


def download_models(config: Config, token: str) -> None:
    from faster_whisper.utils import download_model
    from huggingface_hub import snapshot_download

    download_model(config.whisper_model)
    snapshot_download(config.diarization_model, token=token)


def cpu_threads() -> int:
    import torch

    # torch defaults to the number of physical cores, the sweet spot for inference
    return max(1, torch.get_num_threads())


def load_whisper(config: Config):
    from faster_whisper import WhisperModel

    return WhisperModel(
        config.whisper_model,
        device="cpu",
        compute_type="int8",
        cpu_threads=cpu_threads(),
        local_files_only=True,
    )


def load_diarization(config: Config, token: str | None):
    from pyannote.audio import Pipeline

    pipeline = Pipeline.from_pretrained(config.diarization_model, token=token)
    if pipeline is None:
        raise RuntimeError(f"Could not load {config.diarization_model}")
    return pipeline


def load_audio(path: Path) -> np.ndarray:
    """Decode any audio file to 16 kHz mono float32 (PyAV, no system FFmpeg needed)."""
    from faster_whisper import decode_audio

    return decode_audio(str(path), sampling_rate=SAMPLE_RATE)


def diarize(pipeline, audio: np.ndarray):
    """Run diarization on in-memory audio. Returns a pyannote Annotation."""
    import torch

    output = pipeline({"waveform": torch.from_numpy(audio)[None, :], "sample_rate": SAMPLE_RATE})
    # pyannote 4 returns an object holding the annotation; older versions return it directly
    return getattr(output, "speaker_diarization", output)
