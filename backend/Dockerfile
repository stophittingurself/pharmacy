
# ============================================================
# Multi-stage build with uv
#
# Key trick: venv must live at the same absolute path in both
# builder and runtime stages so shebang lines stay valid after
# the COPY. We use /app/.venv in both.
# ============================================================

# --- Stage 1: Builder ---
FROM python:3.13-slim AS builder

# uv is a single static binary — no extra dependencies needed
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy requirements first so this layer is cached independently from app code
COPY requirements.txt .

# Create venv at /app/.venv and install all dependencies into it
ENV VIRTUAL_ENV=/app/.venv
RUN uv venv $VIRTUAL_ENV && uv pip install -r requirements.txt

# Copy application code after deps (cache-efficient: code changes don't bust dep layer)
COPY app/ ./app/

# --- Stage 2: Runtime ---
FROM python:3.13-slim AS runtime

# Security: never run as root in containers
RUN groupadd -r pharmacy && useradd -r -g pharmacy pharmacy

WORKDIR /app

# Copy pre-built venv (same path /app/.venv — shebangs remain valid)
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app ./app/

# Activate venv via PATH — no uv needed at runtime
ENV PATH="/app/.venv/bin:$PATH"

USER pharmacy

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
