"""P18: image generation policy + inline media rendering from saved paths."""

from __future__ import annotations

import base64

from friday_tools.media import _MODEL_ALIASES, generate_image

# 1x1 transparent PNG
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_model_policy_only_flux_and_nano_banana():
    assert set(_MODEL_ALIASES.values()) == {"flux-2-klein-9b", "nano-banana-2"}
    assert _MODEL_ALIASES["flux"] == "flux-2-klein-9b"  # default maps to top flux
    assert _MODEL_ALIASES["flux-2-pro"] == "flux-2-klein-9b"
    out = generate_image("a cat", model="dall-e-3")
    assert out.startswith("error:") and "not allowed" in out


def test_generate_image_validates_inputs():
    assert generate_image("").startswith("error:")
    assert "size" in generate_image("a cat", size="999x999")


def test_media_from_paths_inlines_home_images(monkeypatch, tmp_path):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path))
    img = tmp_path / "workspace" / "images" / "img_1_flux.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(_PNG)

    from control_plane.streaming import _media_from_paths

    media = _media_from_paths(f"image saved: {img}\nmodel: flux-2-klein-9b")
    assert media is not None and len(media["images"]) == 1
    assert media["images"][0]["mime"] == "image/png"
    assert base64.b64decode(media["images"][0]["data"]) == _PNG


def test_media_from_paths_inlines_api_files_link(monkeypatch, tmp_path):
    """A generated image returned as an /api/files/<name> link (what run_python /
    make_diagram emit) resolves to the artifacts dir and renders inline."""
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path))
    from core.config import settings
    from control_plane.streaming import _media_from_paths

    (settings.artifacts_dir).mkdir(parents=True, exist_ok=True)
    (settings.artifacts_dir / "chart.png").write_bytes(_PNG)

    media = _media_from_paths(
        "Created files:\n- [chart.png](https://otpgod.com/api/files/chart.png)"
    )
    assert media is not None and len(media["images"]) == 1
    assert base64.b64decode(media["images"][0]["data"]) == _PNG


def test_media_from_paths_refuses_outside_home(monkeypatch, tmp_path):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(_PNG)

    from control_plane.streaming import _media_from_paths

    assert _media_from_paths(f"image saved: {outside}") is None
