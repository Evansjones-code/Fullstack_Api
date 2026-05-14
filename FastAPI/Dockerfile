# BUILD STAGE
FROM python:3.12-slim-bookworm AS builder

# Copy UV binary from official image
COPY --from=ghcr.io/astral-sh/uv:0.4.15 /uv /uvx /bin/

WORKDIR /app

# UV Docker optimizations
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=0

# Install dependencies first (cached if unchanged)
COPY pyproject.toml uv.lock ./
# FIX: Removed --locked to bypass lockfile synchronization errors
RUN uv sync --no-install-project --no-dev

# Copy app code and install project
COPY . ./
# FIX: Removed --locked here as well
RUN uv sync --no-dev

# PRODUCTION STAGE
FROM python:3.12-slim-bookworm

WORKDIR /app

# Run as non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Copy app and virtual environment from builder stage
COPY --from=builder --chown=appuser:appuser /app /app

# Set path to use the uv-created virtualenv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Expose container application port
EXPOSE 8000

# Change from 0.0.0.0:8000 to use the dynamic cloud PORT variable
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
