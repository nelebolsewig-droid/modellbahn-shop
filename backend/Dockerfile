# One image for all backend processes; docker-compose.yml only changes the command:
#   api      uvicorn modellbahn.main:app (default)
#   worker   python -m modellbahn.worker
#   migrate  alembic upgrade head

ARG PYTHON_IMAGE=python:3.13-slim

FROM ${PYTHON_IMAGE} AS builder

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# uv comes from PyPI rather than the official uv image, because ghcr.io is not reachable
# everywhere.
#
# Optional build secret "build_ca": an extra CA certificate for TLS-inspecting proxies (see
# README). It is trusted from here on in this stage only and never reaches the final image.
# It is added in the same step as the first download because BuildKit caches steps without
# regard to secrets: a separate step built once without the secret would be reused unchanged
# after the secret is added.
RUN --mount=type=secret,id=build_ca,required=false \
    if [ -s /run/secrets/build_ca ]; then \
        cat /run/secrets/build_ca >> /etc/ssl/certs/ca-certificates.crt; \
    fi \
    && pip install "uv==0.11.*"

WORKDIR /app

# Dependencies first, so that a code change does not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# The project itself is installed as a regular (non-editable) package into the venv.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH

RUN groupadd --system --gid 10001 modellbahn \
    && useradd --system --uid 10001 --gid modellbahn --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin modellbahn

WORKDIR /app

# Owned by root and therefore read-only for the application user. Besides the venv this
# carries the Alembic configuration and migrations that `alembic upgrade head` reads from /app.
COPY --from=builder /app /app

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

# Open SSE streams would otherwise delay a shutdown until Docker kills the container.
CMD ["uvicorn", "modellbahn.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "5"]
