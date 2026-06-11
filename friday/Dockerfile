# Friday — container image for Cloud Run / any Docker host.
# Multi-stage: install deps with uv, then run the FastAPI control plane.

FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System deps: git (self-dev commits), build basics.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates fonts-dejavu-core \
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

# Initialize a git repo so self-dev git_snapshot works in-container.
RUN git init -q && git config user.email "friday@local" && git config user.name "Friday" \
    && git add -A && git commit -q -m "container baseline" || true

CMD ["sh", "-c", "uvicorn control_plane.app:app --host 0.0.0.0 --port ${PORT}"]
