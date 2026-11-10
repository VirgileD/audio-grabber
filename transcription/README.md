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
- finds the recordings folder from AudioGrabber's Windows settings (you confirm it);
- checks and stores the Hugging Face token (`~/.config/agscribe/hf_token`, private);
- plays two beeps to check that you can hear clips;
- downloads the models (~2 GB, once: everything runs offline afterwards);
- transcribes a short sample to prove it all works (`agscribe doctor`).

Re-running `./setup.sh` is safe: it only does what's missing.
`./setup.sh --reconfigure` asks the configuration questions again.

## Commands

| Command | |
|---|---|
| `agscribe configure` | Recordings folder, token, audio playback (`--reconfigure` to change them) |
| `agscribe download-models` | Download the models (done by setup) |
| `agscribe doctor` | Check everything and transcribe a sample |

Coming next: `transcribe`, `name`, `status`, `people`, `render`.

## Files

- `~/.config/agscribe/config.toml`: settings (recordings folder, models, matching thresholds, playback)
- `~/.config/agscribe/hf_token`: Hugging Face token (only used to download models)
- `~/.cache/huggingface/`: downloaded models
- `<recordings folder>/transcripts-data/`: known people, voices, working data
