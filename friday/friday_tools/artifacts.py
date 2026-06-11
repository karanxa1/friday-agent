"""Artifacts toolset: run Python, make PDFs, and save files — each returned as a
clickable link the user can open in the browser.

Everything lands in ``settings.artifacts_dir`` (``~/.friday/artifacts``), which
the control plane serves read-only at ``/api/files/<name>``. Tools return a
Markdown link (absolute when ``FRIDAY_PUBLIC_URL`` is set, e.g.
``https://otpgod.com/api/files/report.pdf``) so the agent's reply renders a
real, openable link.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

from core import audit
from core.config import settings
from core.registry import tool

_MAX_OUTPUT = 30_000


def _dir() -> Path:
    d = settings.artifacts_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _public_url(name: str) -> str:
    base = settings.public_url.rstrip("/")
    return f"{base}/api/files/{name}" if base else f"/api/files/{name}"


def _link(name: str) -> str:
    return f"[{name}]({_public_url(name)})"


def _clip(text: str) -> str:
    if len(text) > _MAX_OUTPUT:
        return text[:_MAX_OUTPUT] + f"\n… (truncated, {len(text)} chars total)"
    return text


def _safe_name(name: str, default_ext: str) -> str:
    base = os.path.basename((name or "").strip())
    if not base:
        base = f"artifact-{uuid.uuid4().hex[:8]}{default_ext}"
    return base.replace("/", "_").replace("\\", "_")


@tool(
    "artifacts",
    description=(
        "Run Python code and return its stdout/stderr. Any files the code writes "
        "to the current directory are saved and returned as openable links "
        "(great for generating reports, charts, data files)."
    ),
)
def run_python(code: str, timeout: int = 120) -> str:
    """Execute Python in the artifacts dir; link any files it produces."""
    if not (code or "").strip():
        return "error: empty code"
    d = _dir()
    before = set(os.listdir(d))
    script = d / f".run-{uuid.uuid4().hex[:8]}.py"
    script.write_text(code, encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, script.name],
            cwd=str(d), capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"error: python timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"
    finally:
        script.unlink(missing_ok=True)
    new_files = sorted(
        f for f in (set(os.listdir(d)) - before) if not f.startswith(".run-")
    )
    body = (proc.stdout or "")
    if proc.stderr:
        body += "\n[stderr]\n" + proc.stderr
    out = f"exit code: {proc.returncode}\n" + _clip(body)
    if new_files:
        out += "\n\nCreated files:\n" + "\n".join(f"- {_link(f)}" for f in new_files)
    audit.log("artifacts.run_python", returncode=proc.returncode, files=len(new_files))
    return out


@tool(
    "artifacts",
    description=(
        "Create a PDF from Markdown (headings, lists, tables, code all supported) "
        "or plain text, and return an openable link to it."
    ),
)
def make_pdf(content: str, filename: str = "document.pdf", title: str = "") -> str:
    """Render Markdown/text to a PDF in the artifacts dir; return its link."""
    if not (content or "").strip():
        return "error: empty content"
    name = _safe_name(filename, ".pdf")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    try:
        import markdown as _md
        from fpdf import FPDF
    except Exception as exc:  # noqa: BLE001
        return f"error: PDF libraries not installed ({exc})"
    html_body = _md.markdown(content, extensions=["tables", "fenced_code", "sane_lists"])

    # Prefer a full Unicode font family (regular+bold+italic) so write_html's
    # <b>/<i> work AND non-Latin glyphs render. DejaVu ships in the container /
    # CI runner. Without it, use the built-in Latin-1 helvetica and sanitize.
    fontdir = next(
        (d for d in ("/usr/share/fonts/truetype/dejavu",)
         if os.path.exists(os.path.join(d, "DejaVuSans.ttf"))),
        None,
    )

    def _build(use_unicode: bool) -> "FPDF":
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        if use_unicode:
            pdf.add_font("uni", "", os.path.join(fontdir, "DejaVuSans.ttf"))
            for style, fn in (("B", "DejaVuSans-Bold.ttf"),
                              ("I", "DejaVuSans-Oblique.ttf"),
                              ("BI", "DejaVuSans-BoldOblique.ttf")):
                fp = os.path.join(fontdir, fn)
                if os.path.exists(fp):
                    pdf.add_font("uni", style, fp)
            base, body = "uni", html_body
        else:
            base = "helvetica"
            body = html_body.encode("latin-1", "replace").decode("latin-1")
        if title:
            pdf.set_font(base, "B", 18)
            pdf.multi_cell(0, 10, title if use_unicode
                           else title.encode("latin-1", "replace").decode("latin-1"))
            pdf.ln(2)
        pdf.set_font(base, "", 11)
        pdf.write_html(body)
        return pdf

    out_path = _dir() / name
    try:
        pdf = _build(bool(fontdir))
    except Exception:  # noqa: BLE001 — last resort: plain text
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("helvetica", size=11)
        pdf.multi_cell(0, 6, content.encode("latin-1", "replace").decode("latin-1"))
    pdf.output(str(out_path))
    audit.log("artifacts.make_pdf", filename=name, bytes=out_path.stat().st_size)
    return f"PDF created — open it here: {_link(name)}"


@tool(
    "artifacts",
    description="Save text/markdown/code/csv/json to a file and return an openable link.",
)
def save_file(filename: str, content: str) -> str:
    """Write content to a file in the artifacts dir; return its link."""
    name = _safe_name(filename, ".txt")
    (_dir() / name).write_text(content or "", encoding="utf-8")
    audit.log("artifacts.save_file", filename=name)
    return f"Saved — open it here: {_link(name)}"


@tool("artifacts", description="List the artifact files created so far, with links.")
def list_artifacts() -> str:
    """Return a Markdown list of all current artifacts with links."""
    files = sorted(f for f in os.listdir(_dir()) if not f.startswith(".run-"))
    if not files:
        return "No artifacts yet."
    return "\n".join(f"- {_link(f)}" for f in files)
