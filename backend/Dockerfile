# syntax=docker/dockerfile:1.7

# ============================================================================
# Stage 1 — Builder : install deps avec uv
# ============================================================================
FROM python:3.12-slim-bookworm AS builder

# Variables d'environnement pour uv : reproductibilité + perf
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Installer uv depuis l'image officielle (multi-arch, supporte ARM64)
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

# Dépendances système nécessaires à la compilation de certains wheels
# (psycopg, cryptography, argon2-cffi en build natif si pas de wheel ARM dispo)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copie d'abord uniquement les fichiers de lock — meilleure mise en cache Docker
COPY pyproject.toml uv.lock ./

# Sync les deps prod uniquement (--no-dev), reproductible (--frozen)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copie ensuite le code applicatif et install le projet lui-même
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# ============================================================================
# Stage 2 — Runtime : image minimale finale
# ============================================================================
FROM python:3.12-slim-bookworm AS runtime

# Variables d'env pour Python en prod
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv

# Dépendances runtime uniquement (libpq pour psycopg, curl pour healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 appgroup \
    && useradd --system --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copie le venv et le code depuis le builder
COPY --from=builder --chown=appuser:appgroup /app /app

USER appuser

EXPOSE 8000

# Healthcheck : ping /health toutes les 30s, 3 retries avant unhealthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/healthz || exit 1

# Commande par défaut : API FastAPI via uvicorn
# Les workers Celery overrideront cette commande dans docker-compose.prod.yml
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
