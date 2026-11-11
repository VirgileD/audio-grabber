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
    console.print(f"\n{OK} Everything works. Transcribe with: [bold]agscribe transcribe[/bold]")


# -------------------------------------------------------------------------- transcribe


@app.command()
def transcribe(
    names: list[str] = typer.Argument(None, help="Recordings to transcribe (default: every new one)."),
    force: bool = typer.Option(False, "--force", help="Transcribe again recordings already done."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Start without asking for confirmation."),
) -> None:
    """Transcribe new recordings (or the ones given) and match known voices."""
    import sys
    import traceback
    from datetime import datetime

    from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table

    from . import recordings as rec
    from .pipeline import Models, audio_duration, seconds_per_audio_second, transcribe_recording
    from .render import pending, short_duration
    from .voices import VoiceStore

    from .models import missing_models

    config = _require_config()
    # An install problem must not mark recordings as failed: check first
    missing = missing_models(config)
    if missing:
        console.print(f"{FAIL} Model(s) not downloaded: {', '.join(missing)}")
        console.print("   Run [bold]agscribe download-models[/bold] (needs the Hugging Face token: agscribe configure)")
        raise typer.Exit(1)
    everything = rec.discover(config)

    if names:
        try:
            requested = rec.find(config, names)
        except LookupError as exc:
            console.print(f"{FAIL} {exc}")
            raise typer.Exit(1) from exc
        selected = []
        for recording in requested:
            status = recording.status()
            if not recording.has_audio:
                console.print(f"{WARN} {recording.name}: its audio was deleted, it can't be transcribed again")
            elif status == rec.IN_PROGRESS:
                console.print(f"{WARN} {recording.name} is still being recorded: skipped")
            elif status == rec.DONE and not force:
                console.print(f"{WARN} {recording.name} is already transcribed (use --force to redo it)")
            else:
                selected.append(recording)
    else:
        if force:
            console.print(f"{FAIL} --force needs the recording(s) to redo, e.g. agscribe transcribe --force Recording_...")
            raise typer.Exit(1)
        selected = [r for r in everything if r.status() in (rec.NEW, rec.FAILED)]
        recording_now = [r for r in everything if r.status() == rec.IN_PROGRESS]
        for recording in recording_now:
            console.print(f"{WARN} {recording.name} is still being recorded: skipped")

    if not selected:
        console.print(f"{OK} Nothing new to transcribe ({len(everything)} recording(s) in {config.recordings_path})")
        return

    # What will be done, and how long it should take
    speed = seconds_per_audio_second(config)
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Recording")
    table.add_column("Length", justify="right")
    table.add_column("Estimate", justify="right")
    total = 0.0
    for recording in selected:
        duration = audio_duration(recording)
        estimate = duration * speed if duration else None
        total += estimate or 0
        status = " (retry)" if recording.status() == rec.FAILED else ""
        table.add_row(
            recording.name + status,
            short_duration(duration) if duration else "?",
            f"~{_human_minutes(estimate)}" if estimate else "?",
        )
    console.print(table)
    console.print(f"Estimated total: ~{_human_minutes(total + 30)}  [dim](CPU only; the estimate improves after each run)[/dim]")

    if not yes:
        if not sys.stdin.isatty():
            console.print(f"{FAIL} Not running in a terminal: add --yes to start without confirmation")
            raise typer.Exit(1)
        if not Confirm.ask(f"Transcribe {len(selected)} recording(s)?", default=True):
            raise typer.Exit(0)

    loaded = Models(config, cfg.load_token())
    store = VoiceStore(config.data_path)
    done, failed = [], []
    columns = [TextColumn("{task.description}"), BarColumn(), TaskProgressColumn(), TimeElapsedColumn()]
    with Progress(*columns, console=console, transient=True) as progress_bar:
        for recording in selected:
            task = progress_bar.add_task(recording.name, total=None)

            def report(phase: str, fraction: float | None, task=task, name=recording.name) -> None:
                progress_bar.update(
                    task,
                    description=f"{name}: {phase}",
                    total=100 if fraction is not None else None,
                    completed=(fraction or 0) * 100,
                )

            try:
                state = transcribe_recording(recording, everything, config, loaded, store, report)
            except KeyboardInterrupt:
                progress_bar.stop()
                console.print(f"\n{WARN} Interrupted: {recording.name} will be transcribed again next time")
                raise typer.Exit(130) from None
            except Exception as exc:  # noqa: BLE001 - report and continue with the next one
                recording.data_dir.mkdir(parents=True, exist_ok=True)
                (recording.data_dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
                rec.write_json(recording.state_file, {
                    "status": rec.FAILED,
                    "error": f"{type(exc).__name__}: {exc}",
                    "updated": datetime.now().isoformat(timespec="seconds"),
                })
                progress_bar.console.print(f"{FAIL} {recording.name}: {type(exc).__name__}: {exc}")
                progress_bar.console.print(f"   [dim]details: {recording.data_dir / 'error.log'}[/dim]")
                failed.append(recording)
                continue
            finally:
                progress_bar.remove_task(task)

            speakers = rec.read_json(recording.data_dir / "speakers.json") or {}
            to_identify, to_confirm = pending(speakers)
            todo = []
            if to_identify:
                todo.append(f"{to_identify} to identify")
            if to_confirm:
                todo.append(f"{to_confirm} to confirm")
            progress_bar.console.print(
                f"{OK} {recording.name} -> {state['transcript_file']}  "
                f"[dim]({len(speakers)} speaker(s){': ' + ', '.join(todo) if todo else ''}; "
                f"took {_human_minutes(state['processing_seconds'])})[/dim]"
            )
            done.append((recording, to_identify + to_confirm))

    console.print(f"\nTranscripts: {config.transcripts_path}")
    if any(count for _, count in done):
        console.print("Some speakers need a name: run [bold]agscribe name[/bold]")
    if failed:
        console.print(f"{FAIL} {len(failed)} recording(s) failed; they'll be retried next time")
        raise typer.Exit(1)


def _human_minutes(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    if seconds < 90:
        return f"{max(1, round(seconds))} s"
    minutes = round(seconds / 60)
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60:02d} min"


# ------------------------------------------------------------------------------ status


@app.command()
def status() -> None:
    """List recordings: new, being recorded, transcribed, speakers to name, failed."""
    from rich.table import Table

    from . import recordings as rec
    from .pipeline import audio_duration
    from .render import pending, short_duration

    config = _require_config()
    everything = rec.discover(config)
    if not everything:
        console.print(f"No recordings in {config.recordings_path}")
        return

    table = Table(header_style="bold", box=None, padding=(0, 2))
    for column in ("Recording", "Length", "Status", "Transcript"):
        table.add_column(column)
    for recording in everything:
        state = recording.state() or {}
        status_ = recording.status()
        duration = state.get("duration") or audio_duration(recording)
        if status_ == rec.DONE:
            speakers = rec.read_json(recording.data_dir / "speakers.json") or {}
            to_identify, to_confirm = pending(speakers)
            if to_identify or to_confirm:
                label = f"[yellow]to name ({to_identify + to_confirm})[/yellow]"
            else:
                label = "[green]done[/green]"
            if not recording.has_audio:
                label += " [dim](audio deleted)[/dim]"
        elif status_ == rec.FAILED:
            error_type = (state.get("error") or "").split(":")[0]
            label = f"[red]failed[/red] [dim]{error_type}[/dim]"
        elif status_ == rec.IN_PROGRESS:
            label = "[blue]recording...[/blue]"
        else:
            label = "new"
        table.add_row(
            recording.name,
            short_duration(duration) if duration else "?",
            label,
            state.get("transcript_file", ""),
        )
    console.print(table)
    if any(r.status() == rec.FAILED for r in everything):
        console.print("[dim]Failed recordings are retried by agscribe transcribe; details in "
                      "transcripts-data/recordings/<name>/error.log[/dim]")
    console.print(f"[dim]Recordings: {config.recordings_path}\nTranscripts: {config.transcripts_path}[/dim]")


# ------------------------------------------------------------------------------ render


@app.command()
def render(
    names: list[str] = typer.Argument(None, help="Recordings to render (default: all transcribed)."),
) -> None:
    """Regenerate the Markdown transcripts from saved data (no new transcription)."""
    from . import recordings as rec
    from .pipeline import render_recording
    from .voices import VoiceStore

    config = _require_config()
    try:
        targets = rec.find(config, names) if names else rec.discover(config)
    except LookupError as exc:
        console.print(f"{FAIL} {exc}")
        raise typer.Exit(1) from exc
    store = VoiceStore(config.data_path)
    count = 0
    for recording in targets:
        filename = render_recording(recording, config, store)
        if filename:
            count += 1
            console.print(f"{OK} {filename}")
        elif names:
            console.print(f"{WARN} {recording.name} isn't transcribed yet")
    console.print(f"{count} transcript(s) written to {config.transcripts_path}")


# -------------------------------------------------------------------------------- name


class _TerminalUI:
    """Terminal input/output for the naming session."""

    def say(self, text: str) -> None:
        console.print(text, highlight=False)

    def ask(self, prompt: str, completions: dict[str, str] | None = None) -> str:
        from prompt_toolkit import prompt as read_line
        from prompt_toolkit.completion import WordCompleter

        completer = None
        if completions:
            completer = WordCompleter(
                list(completions), meta_dict=completions, ignore_case=True, sentence=True
            )
        return read_line(f"{prompt}: ", completer=completer)


@app.command()
def name(
    names: list[str] = typer.Argument(None, help="Recordings to work on (default: all with speakers to name)."),
) -> None:
    """Name the speakers agscribe doesn't know yet (listening to their voice)."""
    import sys

    from . import recordings as rec
    from .naming import NamingSession, RecordingData
    from .playback import Player, load_clip
    from .voices import VoiceStore

    config = _require_config()
    if not sys.stdin.isatty():
        console.print(f"{FAIL} agscribe name is interactive: run it in a terminal")
        raise typer.Exit(1)
    everything = rec.discover(config)
    try:
        candidates = rec.find(config, names) if names else list(reversed(everything))  # newest first
    except LookupError as exc:
        console.print(f"{FAIL} {exc}")
        raise typer.Exit(1) from exc
    targets = []
    for recording in candidates:
        data = RecordingData.load(recording)
        if data is not None and data.pending_labels():
            targets.append(recording)
    if not targets:
        console.print(f"{OK} No speaker left to name")
        return

    store = VoiceStore(config.data_path)
    player = Player(config.playback)
    session = NamingSession(config, store, everything, _TerminalUI(), player, clip_loader=load_clip)
    try:
        session.run(targets)
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n{WARN} Stopped (everything named so far is saved)")
    finally:
        player.close()

    remaining = sum(
        len(data.pending_labels())
        for data in (RecordingData.load(r) for r in everything)
        if data is not None
    )
    console.print(f"\n{OK} {session.named} speaker(s) named"
                  + (f"; {remaining} still to name (run agscribe name again)" if remaining else ""))


# ----------------------------------------------------------------------------- cleanup


@app.command()
def cleanup(
    older_than: int = typer.Option(30, "--older-than", help="Only recordings older than this many days (0 = any age)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Delete without asking for confirmation."),
) -> None:
    """Delete the audio of recordings that are transcribed and fully named.

    Transcripts, speaker data and learned voices are kept. Recordings with
    speakers still to name are never touched (naming needs the audio)."""
    import sys
    from datetime import datetime

    from rich.table import Table

    from . import recordings as rec
    from .pipeline import render_recording
    from .render import pending
    from .voices import VoiceStore

    config = _require_config()
    now = datetime.now()
    candidates, waiting = [], 0
    for recording in rec.discover(config):
        if not recording.has_audio or recording.status() != rec.DONE:
            continue
        speakers = rec.read_json(recording.data_dir / "speakers.json") or {}
        if any(pending(speakers)):
            waiting += 1
            continue
        if older_than <= 0 or (now - recording.started).days >= older_than:
            candidates.append(recording)

    if waiting:
        console.print(f"[dim]{waiting} transcribed recording(s) kept: speakers still to name (agscribe name)[/dim]")
    if not candidates:
        age = f" older than {older_than} days" if older_than else ""
        console.print(f"{OK} No fully named recording{age} with audio to delete")
        return

    table = Table(header_style="bold", box=None, padding=(0, 2))
    table.add_column("Recording")
    table.add_column("Date")
    table.add_column("Size", justify="right")
    total = 0
    for recording in candidates:
        size = recording.mp3.stat().st_size + (recording.log.stat().st_size if recording.log.exists() else 0)
        total += size
        table.add_row(recording.name, f"{recording.started:%Y-%m-%d}", f"{size / 1e6:.0f} MB")
    console.print(table)
    console.print(f"Deletes the MP3 (and .log) of {len(candidates)} recording(s): {total / 1e6:.0f} MB freed.")
    console.print("[dim]Transcripts, speaker data and learned voices are kept.[/dim]")

    if not yes:
        if not sys.stdin.isatty():
            console.print(f"{FAIL} Not running in a terminal: add --yes to delete without confirmation")
            raise typer.Exit(1)
        if not Confirm.ask("Delete this audio?", default=False):
            raise typer.Exit(0)

    store = VoiceStore(config.data_path)
    for recording in candidates:
        try:
            recording.mp3.unlink()
            if recording.log.exists():
                recording.log.unlink()
        except OSError as exc:
            console.print(f"{FAIL} {recording.name}: {exc}")
            continue
        state = recording.state() or {}
        state["audio_deleted"] = now.isoformat(timespec="seconds")
        rec.write_json(recording.state_file, state)
        render_recording(recording, config, store)  # header now says "audio deleted"
        console.print(f"{OK} {recording.name}")
