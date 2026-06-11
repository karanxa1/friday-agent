"""Vision tool: let the agent *see* images via the local Claude vision endpoint.

The local model speaks the Anthropic Messages API and supports image input
(verified: it correctly identified a test image). This registers
``analyze_image`` as a native tool so any agent can inspect screenshots,
rendered pages, charts, or competitor creatives.

Reference: local endpoint POST {base}/v1/messages with an image content block.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import httpx

from core import audit
from core.config import settings
from core.registry import tool

_VISION_MODEL = "claude-opus-4-8"  # hard tier reads images well


def _resolve_image(image_path: str) -> Path | None:
    """Find an image file from a path the agent might phrase several ways.

    The agent refers to files inconsistently — absolute (from generate_image /
    browser_screenshot), relative to its home (``workspace/images/x.png``),
    relative to the file_root, or a bare name. Try each base so a valid file is
    found regardless of phrasing; return the first that exists.
    """
    raw = (image_path or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    candidates: list[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        home = settings.home
        candidates += [
            Path.cwd() / p,        # CWD-relative (legacy behavior)
            home / p,              # e.g. "workspace/images/x.png" under ~/.friday
            settings.file_root / p,  # relative to the file root
            home / "workspace" / p,  # bare "images/x.png" or "downloads/x.png"
        ]
    for c in candidates:
        try:
            if c.is_file():
                return c.resolve()
        except OSError:
            continue
    return None


def _encode(path: Path) -> tuple[str, str] | None:
    if not path.is_file():
        return None
    media, _ = mimetypes.guess_type(str(path))
    if media is None or not media.startswith("image/"):
        media = "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return media, data


@tool("vision", description="Analyze an image file and answer a question about it.")
def analyze_image(image_path: str, question: str = "Describe this image in detail.") -> str:
    """Look at an image and answer a question about its visual content.

    Args:
        image_path: path to a local image file (png/jpg/webp/gif). Absolute or
            relative to the agent home / workspace / file root.
        question: what to ask about the image.

    Returns:
        The model's textual answer about the image.
    """
    p = _resolve_image(image_path)
    if p is None:
        return (
            f"error: {image_path!r} is not a readable image file (looked under the "
            f"workspace, file root, and home). Check the path — list it with "
            f"list_files first if unsure."
        )
    enc = _encode(p)
    if enc is None:
        return f"error: {image_path!r} is not a readable image file"
    media, data = enc

    # Route through litellm using the active provider (gemini / vertex /
    # anthropic) so vision works wherever the model lives — Gemini and Claude
    # are both multimodal. Image is passed as a base64 data URL.
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:{media};base64,{data}"}},
            ],
        }
    ]
    provider = settings.llm_provider
    model_id = settings.model_easy
    kwargs: dict = {"max_tokens": 1024}
    if provider == "gemini":
        kwargs["model"] = model_id if "/" in model_id else f"gemini/{model_id}"
        kwargs["api_key"] = settings.gemini_api_key
    elif provider == "vertex":
        kwargs["model"] = model_id if "/" in model_id else f"vertex_ai/{model_id}"
        kwargs["vertex_location"] = settings.vertex_location or "global"
        if settings.vertex_project:
            kwargs["vertex_project"] = settings.vertex_project
    else:  # anthropic-protocol endpoint
        kwargs["model"] = model_id if "/" in model_id else f"anthropic/{model_id}"
        kwargs["api_base"] = settings.llm_base_url
        kwargs["api_key"] = settings.llm_api_key

    try:
        import litellm

        resp = litellm.completion(messages=messages, **kwargs)
        text = resp.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001
        return f"error: vision request failed: {exc}"
    audit.log("tool.analyze_image", path=str(p), chars=len(text))
    return text or "(no text returned)"
