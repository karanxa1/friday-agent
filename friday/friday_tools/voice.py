"""Voice toolset (parity with the reference tts_tool + transcription_tools).

Backed by the CallMissed audio APIs (existing key, no new credentials):
  TTS : POST /v1/audio/speech          model=bulbul:v3  (mp3/wav/opus/...)
  STT : POST /v1/audio/transcriptions  model=saaras:v3  (22 languages + English)
Reference: docs.callmissed.com/docs/text-to-speech, /docs/speech-to-text.
"""

from __future__ import annotations

import time
from pathlib import Path

from core import audit
from core.config import settings
from core.registry import tool

_TTS_FORMATS = {"mp3", "wav", "opus", "aac", "flac", "pcm"}
_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".opus", ".m4a", ".aac", ".flac", ".webm"}


def _audio_dir() -> Path:
    d = settings.home / "workspace" / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


@tool("voice", description="Convert text to speech (saved as an audio file in the workspace).")
def text_to_speech(text: str, voice: str = "shubh", fmt: str = "mp3", speed: float = 1.0) -> str:
    """Synthesize speech from text via the CallMissed audio API.

    Args:
        text: the text to speak.
        voice: voice id (default 'shubh'; 39 voices available).
        fmt: output format — mp3, wav, opus, aac, flac, or pcm.
        speed: speech speed 0.5-2.0 (default 1.0).
    """
    import httpx

    if not settings.callmissed_api_key:
        return "error: CALLMISSED_API_KEY not set — cannot synthesize speech"
    text = (text or "").strip()
    if not text:
        return "error: text is required"
    if fmt not in _TTS_FORMATS:
        return f"error: fmt must be one of {sorted(_TTS_FORMATS)}"
    try:
        resp = httpx.post(
            f"{settings.callmissed_base_url.rstrip('/')}/v1/audio/speech",
            headers={"Authorization": f"Bearer {settings.callmissed_api_key}"},
            json={
                "model": "bulbul:v3",
                "input": text[:4000],
                "voice": voice,
                "speed": max(0.5, min(float(speed), 2.0)),
                "response_format": fmt,
            },
            timeout=120.0,
        )
    except httpx.HTTPError as exc:
        return f"error: TTS request failed: {exc}"
    if resp.status_code != 200:
        return f"error: TTS API returned HTTP {resp.status_code}: {resp.text[:200]}"
    path = _audio_dir() / f"speech_{int(time.time())}.{fmt}"
    path.write_bytes(resp.content)
    audit.log("voice.tts", voice=voice, fmt=fmt, bytes=len(resp.content), file=path.name)
    return f"audio saved: {path} ({len(resp.content)} bytes, voice={voice})"


@tool("voice", description="Transcribe an audio file to text (auto language detection).")
def transcribe_audio(audio_path: str, mode: str = "transcribe", language: str = "") -> str:
    """Speech-to-text via the CallMissed audio API.

    Args:
        audio_path: path to a local audio file (wav/mp3/ogg/…).
        mode: 'transcribe' (default), 'translate' (to English), 'verbatim',
            'translit', or 'codemix'.
        language: optional language code; auto-detected if omitted.
    """
    import httpx

    if not settings.callmissed_api_key:
        return "error: CALLMISSED_API_KEY not set — cannot transcribe"
    p = Path(audio_path).expanduser()
    if not p.is_file():
        return f"error: {audio_path!r} not found"
    if p.suffix.lower() not in _AUDIO_EXTS:
        return f"error: unsupported audio type {p.suffix!r}"
    data = {"model": "saaras:v3", "mode": mode}
    if language.strip():
        data["language"] = language.strip()
    try:
        resp = httpx.post(
            f"{settings.callmissed_base_url.rstrip('/')}/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.callmissed_api_key}"},
            data=data,
            files={"file": (p.name, p.read_bytes())},
            timeout=180.0,
        )
    except httpx.HTTPError as exc:
        return f"error: transcription failed: {exc}"
    if resp.status_code != 200:
        return f"error: STT API returned HTTP {resp.status_code}: {resp.text[:200]}"
    try:
        text = resp.json().get("text", "")
    except ValueError:
        text = resp.text
    audit.log("voice.stt", file=p.name, mode=mode, chars=len(text))
    return text or "(no speech detected)"
