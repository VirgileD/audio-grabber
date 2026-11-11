"""Play audio clips: in the terminal through WSLg, or with the Windows player."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from . import windows


def write_wav(samples: np.ndarray, sample_rate: int, path: Path) -> None:
    """Write mono float samples (-1..1) as 16-bit PCM WAV."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm.tobytes())


def test_tone(sample_rate: int = 16000) -> np.ndarray:
    """Two short beeps."""
    t = np.arange(int(sample_rate * 0.25)) / sample_rate
    beep = 0.3 * np.sin(2 * np.pi * 880 * t) * np.hanning(t.size)
    gap = np.zeros(int(sample_rate * 0.15))
    return np.concatenate([beep, gap, beep]).astype(np.float32)


def load_clip(path: Path, start: float, end: float, sample_rate: int = 16000) -> np.ndarray:
    """Decode only [start, end] seconds of an audio file, as mono float samples.
    (ffmpeg seeks directly to the start: no need to decode a whole meeting.)"""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is missing (run ./setup.sh to install it)")
    result = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error",
            "-ss", f"{max(0.0, start):.2f}", "-t", f"{max(0.1, end - start):.2f}",
            "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sample_rate), "-",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg could not read {path.name}: {result.stderr.decode(errors='replace').strip()}")
    return np.frombuffer(result.stdout, dtype="<f4").copy()


def wsl_playback_available() -> bool:
    return shutil.which("ffplay") is not None


class Player:
    """Plays one clip at a time; playing a new clip stops the previous one."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self._process: subprocess.Popen | None = None
        self._tmp = Path(tempfile.mkdtemp(prefix="agscribe-"))

    def play(self, samples: np.ndarray, sample_rate: int, wait: bool = False) -> None:
        self.stop()
        if self.mode == "windows":
            self._play_windows(samples, sample_rate)
            return
        clip = self._tmp / "clip.wav"
        write_wav(samples, sample_rate, clip)
        self._process = subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", str(clip)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if wait:
            self._process.wait()

    def _play_windows(self, samples: np.ndarray, sample_rate: int) -> None:
        temp = windows.windows_temp_dir()
        if temp is None:
            raise RuntimeError("Windows temp folder not found")
        folder = temp / "agscribe"
        folder.mkdir(exist_ok=True)
        clip = folder / "clip.wav"
        write_wav(samples, sample_rate, clip)
        windows_clip = windows.to_windows_path(clip)
        if windows_clip is None:
            raise RuntimeError(f"Cannot convert {clip} to a Windows path")
        # Explorer opens the file with the default player and returns immediately
        subprocess.run(
            ["explorer.exe", windows_clip], cwd="/mnt/c", check=False, stdin=subprocess.DEVNULL
        )

    def stop(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    def close(self) -> None:
        self.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)
