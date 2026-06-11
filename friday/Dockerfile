# Friday — container image for Cloud Run / any Docker host.
# Multi-stage: install deps with uv, then run the FastAPI control plane.

FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System deps: git (self-dev commits), build basics.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates fonts-dejavu-core xvfb x11-utils graphviz \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache).
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install -e .

# Browser toolset: Chromium + system deps so Playwright can drive a real
# (headless) browser inside the container.
RUN playwright install --with-deps chromium

# Copy the application.
COPY . .

# Friday's runtime home inside the container.
ENV FRIDAY_HOME=/data/.friday
RUN mkdir -p /data/.friday

# Cloud Run provides $PORT; default to 8080 locally.
ENV PORT=8080
EXPOSE 8080

# Virtual display so the computer-use toolset (screenshots, mouse, keyboard via
# pyautogui) and GUI apps work in this headless container — the agent's "screen".
ENV DISPLAY=:99

# Initialize a git repo so self-dev git_snapshot works in-container.
RUN git init -q && git config user.email "friday@local" && git config user.name "Friday" \
    && git add -A && git commit -q -m "container baseline" || true

# Start a virtual framebuffer on :99, then the API. (-ac allows local clients.)
CMD ["sh", "-c", "Xvfb :99 -screen 0 1440x900x24 -ac >/tmp/xvfb.log 2>&1 & exec uvicorn control_plane.app:app --host 0.0.0.0 --port ${PORT}"]
