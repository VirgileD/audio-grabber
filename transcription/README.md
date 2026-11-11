# agscribe: transcription for AudioGrabber (WSL)

Transcribes AudioGrabber recordings locally (nothing leaves the machine) and learns
who is speaking. Runs in WSL on the CPU. The full design is in
[`plans/Transcription_Plan.md`](../plans/Transcription_Plan.md).

## Install (new WSL)

Run the repository's `setup.sh` (in an Ubuntu WSL, from a normal terminal: it asks
questions). It installs the AudioGrabber app first, then transcription:

```bash
git clone git@github.com:VirgileD/audio-grabber.git AudioGrabber
cd AudioGrabber
./setup.sh              # app + transcription
./setup.sh --skip-app   # transcription only
```

Before (or while) running it, have a Hugging Face account ready:

1. Create a free account on https://huggingface.co
2. Accept the terms of https://huggingface.co/pyannote/speaker-diarization-community-1
3. Create a *Read* token on https://huggingface.co/settings/tokens

For transcription, the setup:

- installs `ffmpeg` and `pulseaudio-utils` (asks for your sudo password once);
- installs `uv` and a private Python 3.12 with CPU-only libraries (`.venv/`, ~1.6 GB);
- finds the recordings folder from AudioGrabber's Windows settings;
- asks where transcripts go (e.g. your notes folder), named like `2026-11-12 10h00 transcript.md`;
- checks and stores the Hugging Face token (`~/.config/agscribe/hf_token`, private);
- plays two beeps to check that you can hear clips;
- downloads the models (~2 GB, once: everything runs offline afterwards);
- transcribes a short sample to prove it all works (`agscribe doctor`).

Re-running `./setup.sh` is safe: it only does what's missing.
`./setup.sh --reconfigure` asks the configuration questions again.

## Commands

| Command | |
|---|---|
| `agscribe configure` | Recordings and transcripts folders, token, audio playback (`--reconfigure` to change them) |
| `agscribe download-models` | Download the models (done by setup) |
| `agscribe doctor` | Check everything and transcribe a sample |
| `agscribe transcribe` | Transcribe new recordings: lists them with an estimated time, asks, then runs (`--yes` to skip the question) |
| `agscribe transcribe <recording>` | Transcribe specific recordings (`--force` to redo one already done) |
| `agscribe status` | Every recording: new, recording..., done, to name, failed |
| `agscribe render` | Regenerate the Markdown from saved data (e.g. after editing `people.json`) |
| `agscribe name` | Name unknown speakers: hear clips, type an email (Tab completes known people) |
| `agscribe cleanup` | Delete the audio of fully named recordings older than 30 days (`--older-than N`), after confirmation |

Coming next: `people` (rename / merge / forget known people).

### Naming speakers

`agscribe name` goes through recordings with unidentified or uncertain speakers,
newest first. For each speaker it shows what they said and plays clips of their
voice; you type their email (or a known person's name). Keys: `r` replay, `c`
another clip, `m` same person as another speaker of the recording (a voice split
in two), `s` skip, `q` quit. For a suggestion, Enter confirms and `n` rejects it.

After naming someone, their voice is learned (future recordings recognize them)
and unnamed speakers in other recordings that sound like them are proposed.

### Deleting recordings

You can delete MP3s to save space: transcripts, speaker data and learned voices
stay (about 1 MB per hour of meeting vs ~58 MB for the MP3). Deleted recordings
still show in `status` and `render` keeps working. But naming needs the audio
(without it, `name` shows quotes only), so delete a recording once it's **done**,
not **to name**. `agscribe cleanup` does exactly that, safely.

A recording is transcribed once: its state is kept in
`transcripts-data/recordings/<name>/state.json`, so renaming, moving or deleting
the Markdown never causes a new transcription. Recordings still being recorded
are skipped; failed or interrupted ones are retried on the next run.

## Files

- `~/.config/agscribe/config.toml`: settings (recordings and transcripts folders, models, matching thresholds, playback)
- `~/.config/agscribe/hf_token`: Hugging Face token (only used to download models)
- `~/.cache/huggingface/`: downloaded models
- `<recordings folder>/transcripts-data/`: known people, voices, working data
