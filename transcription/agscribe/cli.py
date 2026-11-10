"""agscribe command line."""

from __future__ import annotations

import time
from importlib import resources
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt

from . import config as cfg
from . import windows

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Local transcription and speaker identification for AudioGrabber recordings.",
)
console = Console()

# Commands that need the network; everything else runs offline
_ONLINE_COMMANDS = {"configure", "download-models"}

OK = "[green]✓[/green]"
FAIL = "[red]✗[/red]"
WARN = "[yellow]![/yellow]"


@app.callback()
def _main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand not in _ONLINE_COMMANDS:
        from .models import go_offline

        go_offline()


def _require_config() -> cfg.Config:
    config = cfg.load_config()
    if config is None or not config.recordings_dir:
        console.print(f"{FAIL} agscribe isn't configured yet: run [bold]agscribe configure[/bold]")
        raise typer.Exit(1)
    return config


# --------------------------------------------------------------------------- configure


@app.command()
def configure(
    reconfigure: bool = typer.Option(False, "--reconfigure", help="Ask every question again."),
) -> None:
    """Set the recordings folder, the Hugging Face token and audio playback."""
    config = cfg.load_config() or cfg.Config()
    console.rule("agscribe configuration")

    _configure_recordings(config, reconfigure)
    _configure_transcripts(config, reconfigure)
    cfg.save_config(config)
    token_ok = _configure_token(config, reconfigure)
    _configure_playback(config, reconfigure)
    cfg.save_config(config)

    console.print(f"\nSaved to {cfg.CONFIG_FILE}")
    if not token_ok:
        console.print(f"{FAIL} The Hugging Face token is missing or not working: speaker identification won't work.")
        raise typer.Exit(1)


def _configure_recordings(config: cfg.Config, reconfigure: bool) -> None:
    console.print("\n[bold]1. Recordings folder[/bold] (where AudioGrabber saves the MP3 files)")
    current = Path(config.recordings_dir) if config.recordings_dir else None
    if current and current.is_dir() and not reconfigure:
        console.print(f"{OK} {current}")
        return

    detected, why = windows.detect_recordings_dir()
    if detected and detected.is_dir() and not reconfigure:
        # Same folder AudioGrabber records to: nothing to ask
        error = _ensure_writable(detected / cfg.DATA_DIR_NAME)
        if error is None:
            config.recordings_dir = str(detected)
            console.print(f"{OK} {detected}  [dim]({why})[/dim]")
            return
        console.print(f"   {FAIL} Can't write in {detected}: {error}")
    if detected:
        console.print(f"   Detected: {detected}  [dim]({why})[/dim]")
    else:
        console.print(f"   {WARN} Not detected: {why}")
    path = _ask_folder("Recordings folder", current or detected, cfg.DATA_DIR_NAME)
    config.recordings_dir = str(path)
    console.print(f"{OK} {path}")


def _configure_transcripts(config: cfg.Config, reconfigure: bool) -> None:
    console.print("\n[bold]2. Transcripts folder[/bold] (where the Markdown transcripts are saved, e.g. your notes)")
    if config.transcripts_dir and Path(config.transcripts_dir).is_dir() and not reconfigure:
        console.print(f"{OK} {config.transcripts_dir}")
        return
    console.print("   [dim]Press Enter to keep them next to the recordings.[/dim]")
    path = _ask_folder("Transcripts folder", Path(config.transcripts_dir or config.recordings_dir), None)
    config.transcripts_dir = str(path)
    console.print(f"{OK} {path}")


def _ask_folder(label: str, default: Path | None, subfolder: str | None) -> Path:
    """Ask for a folder (Windows or Linux path), create it if needed, check it's writable."""
    console.print("   [dim]Windows (C:\\...) or Linux (/mnt/c/...) paths are both accepted.[/dim]")
    while True:
        answer = Prompt.ask(f"   {label}", default=str(default) if default else None)
        if not answer:
            continue
        path = windows.user_path(answer)
        if path is None:
            console.print(f"   {FAIL} Not a valid path: {answer}")
            continue
        if not path.is_dir():
            if not Confirm.ask(f"   {path} doesn't exist yet. Create it?", default=True):
                continue
            try:
                path.mkdir(parents=True)
            except OSError as exc:
                console.print(f"   {FAIL} {exc}")
                continue
        error = _ensure_writable(path / subfolder if subfolder else path)
        if error:
            console.print(f"   {FAIL} Can't write in {path}: {error}")
            continue
        return path


def _ensure_writable(folder: Path) -> str | None:
    """Create folder if needed and check it's writable; returns an error message or None."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".agscribe-write-test"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        return str(exc)
    return None


def _configure_token(config: cfg.Config, reconfigure: bool) -> bool:
    from .models import check_token

    console.print("\n[bold]3. Hugging Face token[/bold] (one-time download of the speaker-identification model)")
    token = cfg.load_token()
    if token and not reconfigure:
        ok, message = check_token(token, config.diarization_model)
        if ok:
            console.print(f"{OK} {message}")
            return True
        console.print(f"   {FAIL} Saved token: {message}")

    console.print(
        "   The model is free but its authors ask you to accept their terms first:\n"
        "   1. Create a free account at https://huggingface.co (or log in)\n"
        f"   2. Accept the terms on {cfg.DIARIZATION_TERMS_URL}\n"
        f"   3. Create a token (type 'Read') on {cfg.TOKEN_URL}\n"
        "   The token is only used to download the model; recordings never leave this machine."
    )
    while True:
        answer = Prompt.ask("   Paste the token (empty to skip for now)", password=True, default="")
        if not answer.strip():
            return False
        ok, message = check_token(answer.strip(), config.diarization_model)
        if ok:
            cfg.save_token(answer)
            console.print(f"{OK} {message} Saved to {cfg.TOKEN_FILE}")
            return True
        console.print(f"   {FAIL} {message}")
        if "terms" in message:
            console.print(f"   Accept them on {cfg.DIARIZATION_TERMS_URL}, then paste the token again.")


def _configure_playback(config: cfg.Config, reconfigure: bool) -> None:
    from .models import SAMPLE_RATE
    from .playback import Player, test_tone, wsl_playback_available

    console.print("\n[bold]4. Audio playback[/bold] (to listen to voices when naming speakers)")
    if config.playback_tested and not reconfigure:
        console.print(f"{OK} {'in the terminal (WSL)' if config.playback == 'wsl' else 'Windows player'}")
        return

    tone = test_tone(SAMPLE_RATE)
    if wsl_playback_available():
        console.print("   Playing two beeps in the terminal...")
        player = Player("wsl")
        try:
            player.play(tone, SAMPLE_RATE, wait=True)
        finally:
            player.close()
        if Confirm.ask("   Did you hear two beeps?", default=True):
            config.playback = "wsl"
            config.playback_tested = True
            console.print(f"{OK} Clips will play in the terminal")
            return
    else:
        console.print(f"   {WARN} ffplay not found (package ffmpeg): can't play in the terminal")

    console.print("   Trying the Windows player instead (a player window should open)...")
    player = Player("windows")
    try:
        player.play(tone, SAMPLE_RATE)
    except RuntimeError as exc:
        console.print(f"   {FAIL} {exc}")
    finally:
        player.close()
    config.playback = "windows"
    config.playback_tested = True
    if Confirm.ask("   Did a player open and play two beeps?", default=True):
        console.print(f"{OK} Clips will open in the Windows player")
    else:
        console.print(
            f"   {WARN} No sound either way: check the Windows volume, then run "
            "[bold]agscribe configure --reconfigure[/bold]"
        )


# --------------------------------------------------------------------- download-models


@app.command("download-models")
def download_models() -> None:
    """Download the speech-to-text and speaker models (once, ~2 GB)."""
    from .models import download_models as download

    config = _require_config()
    token = cfg.load_token()
    if token is None:
        console.print(f"{FAIL} No Hugging Face token: run [bold]agscribe configure[/bold]")
        raise typer.Exit(1)
    console.print(f"Downloading {config.whisper_model} and {config.diarization_model} (once)...")
    download(config, token)
    console.print(f"{OK} Models downloaded; agscribe now runs offline.")


# ------------------------------------------------------------------------------ doctor


@app.command()
def doctor() -> None:
    """Check the installation and transcribe a short sample, end to end."""
    import shutil

    from . import models

    failures = 0

    def check(ok: bool, message: str, warn_only: bool = False) -> bool:
        nonlocal failures
        if ok:
            console.print(f"{OK} {message}")
        elif warn_only:
            console.print(f"{WARN} {message}")
        else:
            console.print(f"{FAIL} {message}")
            failures += 1
        return ok

    config = _require_config()
    check(True, f"Configuration: {cfg.CONFIG_FILE}")
    recordings = config.recordings_path
    if check(recordings.is_dir(), f"Recordings folder: {recordings}"):
        mp3_count = len(list(recordings.glob("*.mp3")))
        check(True, f"{mp3_count} recording(s) found")
        error = _ensure_writable(config.data_path)
        check(error is None, f"Data folder writable: {config.data_path}" + (f" ({error})" if error else ""))
    error = _ensure_writable(config.transcripts_path)
    check(error is None, f"Transcripts folder writable: {config.transcripts_path}" + (f" ({error})" if error else ""))
    if config.playback == "wsl":
        check(shutil.which("ffplay") is not None, "ffplay available (clip playback)")
    else:
        check(True, "Playback: Windows player")

    sample = Path(str(resources.files("agscribe") / "data" / "jfk.flac"))
    audio = models.load_audio(sample)

    start = time.perf_counter()
    try:
        whisper = models.load_whisper(config)
    except Exception as exc:  # noqa: BLE001 - report any load failure
        check(False, f"Speech-to-text model: {exc} (run agscribe download-models)")
        raise typer.Exit(1) from exc
    segments, info = whisper.transcribe(audio, beam_size=5)
    text = " ".join(segment.text.strip() for segment in segments)
    elapsed = time.perf_counter() - start
    check(
        "country" in text.lower(),
        f"Speech-to-text ({config.whisper_model}, language: {info.language}, {elapsed:.1f}s): \"{text}\"",
    )

    start = time.perf_counter()
    try:
        pipeline = models.load_diarization(config, cfg.load_token())
    except Exception as exc:  # noqa: BLE001
        check(False, f"Speaker model: {exc} (run agscribe download-models)")
        raise typer.Exit(1) from exc
    annotation = models.diarize(pipeline, audio)
    speakers = annotation.labels()
    elapsed = time.perf_counter() - start
    check(len(speakers) >= 1, f"Speaker detection ({elapsed:.1f}s): {len(speakers)} speaker(s) in the sample")

    if failures:
        console.print(f"\n{FAIL} {failures} problem(s) found")
        raise typer.Exit(1)
    console.print(f"\n{OK} Everything works. Transcribe with: [bold]agscribe transcribe[/bold] (coming next)")
