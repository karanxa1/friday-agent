"""P22: artifacts toolset — run_python, make_pdf, save_file, list_artifacts.

Each tool writes into the artifacts dir (served at /api/files/<name>) and
returns a Markdown link the agent can surface to the user.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def arts(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path))
    from core.config import settings
    from friday_tools import artifacts

    # Absolute links when a public URL is configured (settings is frozen).
    old = settings.public_url
    object.__setattr__(settings, "public_url", "https://otpgod.com")
    yield artifacts
    object.__setattr__(settings, "public_url", old)


def test_run_python_returns_output_and_links_new_files(arts):
    out = arts.run_python("open('data.txt','w').write('hi'); print(6*7)")
    assert "42" in out
    assert "exit code: 0" in out
    assert "[data.txt](https://otpgod.com/api/files/data.txt)" in out


def test_run_python_reports_errors(arts):
    out = arts.run_python("raise ValueError('boom')")
    assert "boom" in out
    assert "exit code:" in out and "exit code: 0" not in out


def test_make_pdf_creates_valid_pdf_with_link(arts):
    from core.config import settings

    res = arts.make_pdf("# Title\n\nHello **world**\n\n- a\n- b", "report.pdf", "Report")
    assert "/api/files/report.pdf" in res
    pdf = settings.artifacts_dir / "report.pdf"
    assert pdf.exists() and pdf.read_bytes().startswith(b"%PDF-")


def _make_chart(arts) -> str:
    """Generate a real PNG artifact via run_python; return its name."""
    arts.run_python(
        "import matplotlib; matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "fig,ax=plt.subplots(); ax.plot([1,2,3],[3,1,2]); fig.savefig('chart.png')"
    )
    return "chart.png"


def test_make_pdf_embeds_local_image(arts):
    from core.config import settings

    _make_chart(arts)
    text_only = arts.make_pdf("# Plain\n\njust text, no image", "plain.pdf")
    assert "/api/files/plain.pdf" in text_only
    # Embed the chart both inline (![](name)) and via the images arg.
    res = arts.make_pdf("# Report\n\n![chart](chart.png)", "report.pdf", "R", images="chart.png")
    assert "/api/files/report.pdf" in res
    with_img = (settings.artifacts_dir / "report.pdf").stat().st_size
    without_img = (settings.artifacts_dir / "plain.pdf").stat().st_size
    # An embedded raster makes the PDF materially larger than a text-only one.
    assert with_img > without_img + 5000


def test_resolve_img_src_maps_artifact_refs(arts):
    from friday_tools.artifacts import _dir, _resolve_img_src

    (_dir() / "pic.png").write_bytes(b"\x89PNG\r\n")
    for ref in ("pic.png", "/api/files/pic.png", "https://otpgod.com/api/files/pic.png", "artifacts/pic.png"):
        assert _resolve_img_src(ref) == str(_dir() / "pic.png")
    # Real external URLs and unknown names are left untouched.
    assert _resolve_img_src("https://example.com/x.png") == "https://example.com/x.png"


def test_make_diagram_registered_and_validates(arts):
    # The dot binary may be absent locally; an empty source must error cleanly
    # without raising, and a bad/renderable source returns a string either way.
    assert arts.make_diagram("").startswith("error:")
    out = arts.make_diagram("digraph { A -> B }", "flow.png")
    assert isinstance(out, str) and ("/api/files/flow.png" in out or out.startswith("error:"))


def test_save_file_and_list(arts):
    arts.save_file("notes.md", "# notes")
    listed = arts.list_artifacts()
    assert "notes.md" in listed and "/api/files/notes.md" in listed


def test_filename_traversal_is_sanitized(arts):
    from core.config import settings

    arts.save_file("../../etc/evil.txt", "x")
    # The file must stay inside the artifacts dir (no path escape).
    assert not (settings.artifacts_dir.parent.parent / "etc" / "evil.txt").exists()
    assert any("evil.txt" in f for f in __import__("os").listdir(settings.artifacts_dir))


def test_relative_link_when_no_public_url(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path))
    from core.config import settings
    from friday_tools import artifacts

    old = settings.public_url
    object.__setattr__(settings, "public_url", "")
    try:
        out = artifacts.save_file("x.txt", "y")
        assert "(/api/files/x.txt)" in out
    finally:
        object.__setattr__(settings, "public_url", old)


def test_artifacts_toolset_registered():
    from control_plane import builder
    from core.registry import registry

    builder.import_tool_modules()
    names = {e.name for e in registry.list()}
    assert {"run_python", "make_pdf", "make_diagram", "save_file", "list_artifacts"} <= names
