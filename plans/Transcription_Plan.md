# Transcription Plan (WSL)

Local, on-demand transcription of AudioGrabber recordings, with speaker
identification that learns voices over time.

## Decisions

| Topic | Decision |
|---|---|
| Where it runs | WSL (Ubuntu), CPU only (Ryzen 9 8945HS, no CUDA GPU) |
| Speech-to-text | faster-whisper, model `large-v3-turbo`, int8 on CPU (~15-25 min per hour of audio) |
| Language | Auto-detected per recording |
| Who-spoke-when | pyannote 4 `speaker-diarization-community-1` (free Hugging Face token, terms accepted once on one page; runs offline afterwards) |
| Voice recognition | Speaker embeddings (the model inside pyannote) compared with known voices |
| Transcript format | Markdown, next to the MP3 |
| Data location | With the recordings (Windows side), so it survives a WSL reinstall |
| People | Email = unique ID, plus an optional display name shown in transcripts |
| Matching | Automatic if sure, asked if unsure, "Speaker N" if unknown |
| Backfill | Naming a voice proposes matching unnamed speakers in other transcripts |
| Naming UX | Clips played in the terminal (WSLg audio), fallback to the Windows player |
| Trigger | On demand, by the user |
| Code | This repo, `transcription/` folder |

## Layout

```
AudioGrabber/                      (repo)
└── transcription/
    ├── setup.sh                   one-shot installer (idempotent: safe to re-run)
    ├── pyproject.toml / uv.lock   pinned Python dependencies
    ├── agscribe/                  Python package (CLI + pipeline)
    └── tests/

<recordings folder>/               (Windows side, e.g. next to AudioGrabber.exe)
├── Recording_2026-11-12_100000.mp3      written by AudioGrabber
├── Recording_2026-11-12_100000.log      written by AudioGrabber
├── Recording_2026-11-12_100000.md       transcript (generated - don't edit by hand)
└── transcripts-data/
    ├── people.json                      known people: email -> display name (editable)
    ├── voices/<email>/<recording>.npy   voice samples per person (several = more robust)
    └── recordings/Recording_.../
        ├── transcript.json              words, timestamps, speaker turns
        └── speakers.json                per speaker: voice sample, status, assigned email
```

`people.json` is the human-editable "participants" file:

```json
{
  "alice.martin@corp.com": { "name": "Alice Martin" },
  "me@example.com":        { "name": "Virgile" }
}
```

## Commands

A single command, `agscribe`, installed by setup in `~/.local/bin`:

| Command | What it does |
|---|---|
| `agscribe transcribe` | Transcribes every new recording (or the ones given) |
| `agscribe name` | Interactive naming of unidentified / uncertain speakers, newest recording first |
| `agscribe status` | Lists recordings: not transcribed / to name / done |
| `agscribe people` | Lists known people; rename a display name; merge or forget a person |
| `agscribe render` | Regenerates the Markdown files (e.g. after editing people.json) |

## Step 1 - Transcribe (`agscribe transcribe`)

For each MP3 in the recordings folder that has no transcript yet:

1. **Skip recordings in progress**: only process an MP3 whose `.log` says the
   session completed (or, without a log, unchanged for 2 minutes).
2. Decode to 16 kHz mono with ffmpeg.
3. **Speech-to-text** with faster-whisper (voice-activity filter, word timestamps,
   language auto-detected).
4. **Diarization** with pyannote (`community-1`): who spoke when (anonymous speakers A, B, C...).
5. Assign each word to the speaker talking at that moment; group into turns.
6. **Voice sample** per speaker: an embedding averaged over their clearest
   segments.
7. **Match** against known voices (cosine similarity, best of each person's samples):
   - above the "sure" threshold: named automatically;
   - between "unsure" and "sure": kept as a *suggestion*, confirmed in step 2;
   - below: `Speaker 1`, `Speaker 2`, ...
8. Write `transcript.json`, `speakers.json` and the Markdown.

Transcript example:

```markdown
# Recording 2026-11-12 10:00

- Duration: 47:12 - Language: French
- Participants: Virgile <me@example.com>, Alice Martin <alice.martin@corp.com>, Speaker 1 (unidentified)

> 1 speaker to identify: run `agscribe name`

**[00:00:04] Virgile:** Bonjour à tous, on commence...

**[00:00:11] Alice Martin:** Oui, alors pour le premier point...

**[00:01:32] Speaker 1:** ...
```

## Step 2 - Name the speakers (`agscribe name`)

Goes through the recordings that have unidentified or uncertain speakers. For each:

```
Recording_2026-11-12_100000 - Speaker 1 (6 min 20 s, 14 turns)
  [00:01:32] "...je pense qu'on peut livrer la semaine prochaine..."
  ▶ playing clip 1/3

  Email (Tab completes known people), or:
  [r] replay  [n] next clip  [m] same person as another speaker here
  [s] skip  [q] quit
> bob@corp.com
  New person - display name [Bob]: Bob Durand
```

- **Uncertain match**: `Is this Alice Martin? [Y/n]` with a clip.
- **Same person** (`m`): diarization sometimes splits one voice in two; merge them.
- After a name is set:
  1. the voice sample is added to `voices/<email>/` (each person keeps several
     samples from different recordings: phone, headset, room...);
  2. the Markdown is regenerated;
  3. **backfill**: unidentified speakers in other transcripts that sound like
     this person are proposed (`Recording_... Speaker 2 sounds like Bob Durand
     (clip) - same person? [Y/n]`).
- Email format is validated; names can be fixed later with `agscribe people`.

## Setup (`transcription/setup.sh`)

Goal: in a brand-new Ubuntu WSL, `git clone` + `./transcription/setup.sh` and it
is ready for the next recording. Safe to re-run (it only does what's missing).

1. Check: WSL + Ubuntu, disk space (~10 GB for models and libraries), internet.
2. System packages (asks for the sudo password once): `ffmpeg` (decoding and
   `ffplay` for clips), `pulseaudio-utils` (audio check), build basics.
3. `uv` (Python package manager) in `~/.local/bin`, then a project-local
   **Python 3.12** (the system Python is too new for the AI libraries).
4. Python dependencies from the lock file: CPU-only PyTorch, faster-whisper,
   pyannote.audio, ...
5. **Recordings folder**: auto-detected from AudioGrabber's Windows settings
   (`%APPDATA%\AudioGrabber\settings.json`; `./` resolved via the exe location
   from the startup registry entry), confirmed or typed by the user.
6. **Hugging Face token**: explains the page where to accept the model terms
   (with links), asks for the token, checks access, stores it in
   `~/.config/agscribe/` (permissions 600).
7. **Downloads all models** once (~2 GB). At run time everything is offline
   (`HF_HUB_OFFLINE=1`): audio never leaves the machine.
8. **Audio check**: plays a short tone through WSL; if not heard, configures the
   Windows-player fallback.
9. **Smoke test**: transcribes a short bundled sample to prove the whole chain works.
10. Installs the `agscribe` command and prints a short how-to.

Config file: `~/.config/agscribe/config.toml` (recordings folder, model,
thresholds, playback mode).

## Implementation order

1. `pyproject.toml` + `setup.sh` (install, config, token, model download, audio check).
2. Pipeline: decode → transcribe → diarize → merge → voice samples → Markdown.
3. Voice store + matching (people.json, voices/).
4. `agscribe name` (playback, prompts, merge, suggestions, backfill).
5. `status`, `people`, `render`.
6. Tests: unit tests on merge/matching/rendering; end-to-end on a public
   multi-speaker sample; then a real AudioGrabber recording.
7. Calibrate the "sure"/"unsure" thresholds on real recordings (defaults to start;
   configurable).

## Known limits

- One mixed track: voices are separated by sound only; overlapping speech is
  attributed to the dominant speaker.
- Mic and system audio are ~120 ms apart in the recording (AudioGrabber jitter
  buffer): negligible for transcripts.
- CPU only: a 1-hour meeting takes roughly 20-30 min in total.
- A person heard only briefly (a few seconds) gives a weak voice sample: they may
  need confirming again in later recordings until enough samples exist.
