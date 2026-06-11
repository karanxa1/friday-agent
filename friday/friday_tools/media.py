"""Media toolset: image generation via the CallMissed Images API + self-check.

Reference (docs.callmissed.com/docs/image-generation):
  Endpoint : POST {CALLMISSED_BASE_URL}/v1/images/generations   (OpenAI-compatible)
  Auth     : Authorization: Bearer <CALLMISSED_API_KEY>
  Request  : {"model", "prompt", "n", "size", "negative_prompt", "seed", "steps"}
  Response : {"created": ..., "data": [{"b64_json": "<base64 PNG>"}]}

Policy: only two models are allowed — ``flux-2-klein-9b`` (default; docs rank it
highest quality, "final output, print, marketing") and ``nano-banana-2``
(fast multimodal). Friendly aliases map onto them. Every generated image is
immediately re-read by the vision model (analyze_image) so the agent verifies
its own output before using it anywhere.
"""

from __future__ import annotations

import base64
import time

from core import audit
from core.config import settings
from core.registry import tool

# Allowed models + aliases (user policy: nano-banana-2 and flux only, default flux).
_MODEL_ALIASES = {
    "flux": "flux-2-klein-9b",
    "flux-2-pro": "flux-2-klein-9b",
    "flux-2-klein-9b": "flux-2-klein-9b",
    "nano-banana-2": "nano-banana-2",
    "nano-banana": "nano-banana-2",
    "nano banana 2": "nano-banana-2",
}
_DEFAULT_MODEL = "flux-2-klein-9b"
_SIZES = {"512x512", "768x768", "1024x1024", "1024x1536", "1536x1024"}

_CHECK_QUESTION = (
    "You generated this image from the prompt: {prompt!r}. Check it carefully: "
    "1) Does it match the prompt? 2) Any artifacts, distorted anatomy, or garbled "
    "text? 3) Is it usable for a social media post? Answer with VERDICT: PASS or "
    "VERDICT: FAIL on the first line, then 2-3 sentences of reasoning."
)


def _images_dir():
    # Save into the artifacts dir so the image is served at /api/files/<name>
    # (the same place run_python / make_diagram write). Saving under
    # workspace/images/ — which is NOT served — left the agent handing out a
    # filesystem path that 404'd when the user opened it.
    d = settings.artifacts_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _public_link(name: str) -> str:
    base = settings.public_url.rstrip("/")
    return f"{base}/api/files/{name}" if base else f"/api/files/{name}"


@tool(
    "media",
    description="Generate an image (flux default / nano-banana-2) and self-check it with vision.",
)
def generate_image(
    prompt: str,
    model: str = "flux",
    size: str = "1024x1024",
    negative_prompt: str = "",
) -> str:
    """Generate an image via the CallMissed Images API, save it, and verify it.

    The generated file is ALWAYS analyzed by the vision model afterwards; the
    verdict is included in the result. If the verdict is FAIL, refine the
    prompt and regenerate before using the image.

    Args:
        prompt: text description of the image (1-4000 chars).
        model: 'flux' (default, highest quality) or 'nano-banana-2' (fast).
        size: one of 512x512, 768x768, 1024x1024, 1024x1536, 1536x1024.
        negative_prompt: concepts to avoid (e.g. 'lowres, blurry, watermark').
    """
    import httpx

    if not settings.callmissed_api_key:
        return "error: CALLMISSED_API_KEY not set — cannot generate images"
    prompt = (prompt or "").strip()
    if not prompt:
        return "error: prompt is required"
    resolved = _MODEL_ALIASES.get(model.strip().lower())
    if resolved is None:
        return (
            f"error: model {model!r} not allowed. Use 'flux' (default) or 'nano-banana-2'."
        )
    if size not in _SIZES:
        return f"error: size must be one of {sorted(_SIZES)}"

    body: dict = {"model": resolved, "prompt": prompt, "n": 1, "size": size}
    if negative_prompt.strip():
        body["negative_prompt"] = negative_prompt.strip()

    try:
        resp = httpx.post(
            f"{settings.callmissed_base_url.rstrip('/')}/v1/images/generations",
            headers={"Authorization": f"Bearer {settings.callmissed_api_key}"},
            json=body,
            timeout=120.0,
        )
    except httpx.HTTPError as exc:
        return f"error: image request failed: {exc}"
    if resp.status_code != 200:
        return f"error: images API returned HTTP {resp.status_code}: {resp.text[:300]}"
    try:
        b64 = resp.json()["data"][0]["b64_json"]
    except (ValueError, KeyError, IndexError) as exc:
        return f"error: malformed images API response: {exc}"

    path = _images_dir() / f"img_{int(time.time())}_{resolved.split('-')[0]}.png"
    path.write_bytes(base64.b64decode(b64))
    audit.log("media.generate_image", model=resolved, size=size, file=path.name)

    # Mandatory self-check: the agent looks at its own output before using it.
    from mcp_tools.vision import analyze_image

    verdict = analyze_image(str(path), _CHECK_QUESTION.format(prompt=prompt))
    audit.log("media.image_check", file=path.name, verdict=verdict[:120])

    link = _public_link(path.name)
    return (
        f"image generated — open/download it here: {link}\n"
        f"(embed it in a reply or PDF with ![{prompt[:40]}]({link}))\n"
        f"model: {resolved} | size: {size}\n"
        f"--- vision self-check ---\n{verdict}\n"
        f"(If VERDICT: FAIL, refine the prompt and regenerate before using this image.)"
    )
