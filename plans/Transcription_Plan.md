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
| Transcript format | Plain Markdown, in a chosen folder (e.g. the notes folder), named `2026-11-12 10h00 transcript.md` |
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
├── setup.sh                       one-shot installer for the app + transcription (safe to re-run)
└── transcription/
    ├── pyproject.toml / uv.lock   pinned Python dependencies
    ├── agscribe/                  Python package (CLI + pipeline)
    └── tests/

<recordings folder>/               (Windows side, e.g. next to AudioGrabber.exe)
├── Recording_2026-11-12_100000.mp3      written by AudioGrabber
├── Recording_2026-11-12_100000.log      written by AudioGrabber
└── transcripts-data/
    ├── people.json                      known people: email -> display name (editable)
    ├── voices/<email>/<recording>.npy   voice samples per person (several = more robust)
    └── recordings/Recording_.../
        ├── transcript.json              words, timestamps, speaker turns
        └── speakers.json                per speaker: voice sample, status, assigned email

<transcripts folder>/              (asked at setup, e.g. your notes; default: recordings folder)
└── 2026-11-12 10h00 transcript.md       transcript (generated - don't edit by hand)
```

Transcript names come from the recording's start time (`Recording_2026-11-12_100000`
-> `2026-11-12 10h00 transcript.md`); two recordings in the same minute get
` (2)`. The voice data stays with the recordings, so the notes folder only gets
the transcripts.

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

### Which recordings

Each recording's state lives in `transcripts-data/recordings/<name>/state.json`,
not in the Markdown (renaming, moving or deleting a transcript never triggers a
new transcription):

| State | `agscribe transcribe` |
|---|---|
| no state file | new: transcribed |
| still being recorded (`.log` without "Session completed"; without a log: MP3 changed in the last 2 min) | skipped |
| `done` | skipped (`--force <recording>` redoes it; `render` regenerates the Markdown) |
| `failed` (error + `error.log`) | retried |
| interrupted (Ctrl+C, crash, sleep) | retried: `state.json` is written last |

Before starting, it lists the recordings with an estimated time (learned from
previous runs) and asks for confirmation (`--yes` to skip). Missing models are
reported up front, without marking recordings as failed.

### Steps

For each selected recording:

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
8. Write `transcript.json`, `speakers.json`, and the Markdown into the transcripts folder.

Transcript example:

```markdown
# Recording 2026-11-12 10:00

- Recording: C:\Users\me\AudioGrabber\Recording_2026-11-12_100000.mp3
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

## Deleting recordings (`agscribe cleanup`)

MP3s can be deleted to save space; what's kept per recording in
`transcripts-data/` (words, speakers, voice embeddings: ~1 MB per hour) is enough
for `status`, `render` and voice learning. Recordings without audio stay listed
("audio deleted"), and naming falls back to quotes. `agscribe cleanup` deletes
the MP3 + `.log` of recordings that are done and fully named, older than 30 days
by default (`--older-than N`), after showing the space freed and asking.

## Setup (`setup.sh` at the repo root)

Goal: in a brand-new Ubuntu WSL, `git clone` + `./setup.sh` and it
is ready for the next recording. Safe to re-run (it only does what's missing).

1. Check: WSL + Ubuntu, Windows interop, disk space (~10 GB), internet.
   Then the **AudioGrabber app**: .NET 8 SDK (user-local), self-contained
   single-file build, installed to `%USERPROFILE%\AudioGrabber`, started
   (crash report from the Windows event log if it doesn't start).
2. System packages (asks for the sudo password once): `ffmpeg` (decoding and
   `ffplay` for clips), `pulseaudio-utils` (audio check), build basics.
3. `uv` (Python package manager) in `~/.local/bin`, then a project-local
   **Python 3.12** (the system Python is too new for the AI libraries).
4. Python dependencies from the lock file: CPU-only PyTorch, faster-whisper,
   pyannote.audio, ...
5. **Folders** (asked on the first run, remembered; `--reconfigure` asks again):
   - where to install `AudioGrabber.exe` (default `%USERPROFILE%\AudioGrabber`);
   - where recordings go (default `./`: next to the exe), written to
     AudioGrabber's `settings.json`;
   - where transcripts go (e.g. the notes folder; default: recordings folder).
   agscribe then detects the recordings folder from AudioGrabber's settings
   (`./` resolved via the exe's startup registry entry).
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
