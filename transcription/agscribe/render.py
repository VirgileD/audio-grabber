"""Markdown transcript, generated from transcript.json + speakers.json + people.json."""

from __future__ import annotations

from typing import Any

from .voices import KNOWN, SUGGESTED, VoiceStore

# Start a new paragraph within one person's speech after this long, at a sentence end
PARAGRAPH_SECONDS = 60.0

LANGUAGES = {
    "fr": "French", "en": "English", "de": "German", "es": "Spanish", "it": "Italian",
    "nl": "Dutch", "pt": "Portuguese", "pl": "Polish", "ru": "Russian", "zh": "Chinese",
    "ja": "Japanese", "ar": "Arabic",
}


def clock(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def short_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def resolve(label: str, speakers: dict[str, Any]) -> str:
    """Follow 'merged_into' links (a voice split in two by diarization, then merged)."""
    seen = set()
    while speakers.get(label, {}).get("merged_into") and label not in seen:
        seen.add(label)
        label = speakers[label]["merged_into"]
    return label


def speaker_name(label: str, speakers: dict[str, Any], store: VoiceStore) -> str:
    info = speakers.get(label, {})
    if info.get("status") == KNOWN and info.get("email"):
        return store.display_name(info["email"])
    if info.get("status") == SUGGESTED and info.get("email"):
        return f"{store.display_name(info['email'])}?"
    return f"Speaker {info.get('number', '?')}"


def participant(label: str, speakers: dict[str, Any], store: VoiceStore) -> str:
    info = speakers.get(label, {})
    email = info.get("email")
    if info.get("status") == KNOWN and email:
        name = store.display_name(email)
        return f"{name} <{email}>" if name != email else email
    if info.get("status") == SUGGESTED and email:
        return f"{store.display_name(email)} <{email}> (to confirm)"
    return f"Speaker {info.get('number', '?')} (unidentified)"


def turns(words: list[list], speakers: dict[str, Any]) -> list[tuple[str, float, str]]:
    """Group words into (speaker label, start time, text) paragraphs."""
    result: list[tuple[str, float, str]] = []
    current_label, current_start, parts = None, 0.0, []
    for start, _end, text, label in words:
        label = resolve(label, speakers)
        sentence_end = bool(parts) and parts[-1].rstrip().endswith((".", "?", "!"))
        too_long = start - current_start > PARAGRAPH_SECONDS
        if label != current_label or (too_long and sentence_end):
            if parts:
                result.append((current_label, current_start, "".join(parts).strip()))
            current_label, current_start, parts = label, start, []
        parts.append(text)
    if parts:
        result.append((current_label, current_start, "".join(parts).strip()))
    return result


def pending(speakers: dict[str, Any]) -> tuple[int, int]:
    """(speakers to identify, speakers to confirm), merged ones excluded."""
    active = [s for s in speakers.values() if not s.get("merged_into")]
    to_confirm = sum(1 for s in active if s.get("status") == SUGGESTED)
    to_identify = sum(1 for s in active if s.get("status") not in (KNOWN, SUGGESTED))
    return to_identify, to_confirm


def render_markdown(
    transcript: dict[str, Any], speakers: dict[str, Any], store: VoiceStore, mp3_windows_path: str
) -> str:
    words = transcript.get("words", [])
    paragraphs = turns(words, speakers)

    # Participants in order of first appearance
    order: list[str] = []
    for label, _, _ in paragraphs:
        if label not in order:
            order.append(label)

    language = transcript.get("language") or "?"
    lines = [
        f"# Recording {transcript.get('started', '')[:16].replace('T', ' ')}",
        "",
        f"- Recording: {mp3_windows_path}",
        f"- Duration: {short_duration(transcript.get('duration', 0))} · "
        f"Language: {LANGUAGES.get(language, language)}",
        f"- Participants: {', '.join(participant(l, speakers, store) for l in order) or 'none'}",
        "",
    ]

    to_identify, to_confirm = pending({label: speakers.get(label, {}) for label in order})
    todo = []
    if to_identify:
        todo.append(f"{to_identify} speaker{'s' if to_identify > 1 else ''} to identify")
    if to_confirm:
        todo.append(f"{to_confirm} to confirm")
    if todo:
        lines += [f"> {', '.join(todo)}: run `agscribe name`", ""]

    if not paragraphs:
        lines += ["*(no speech detected)*", ""]
    for label, start, text in paragraphs:
        lines += [f"**[{clock(start)}] {speaker_name(label, speakers, store)}:** {text}", ""]

    return "\n".join(lines)
