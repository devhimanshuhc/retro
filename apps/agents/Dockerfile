# Retro backend: the API and every agent. One image; the compose `command` picks which one runs.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_SYNC=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app

# dependencies first (cached); the Claude CLI ships inside claude-agent-sdk as a native binary for this platform
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Chromium for the browser fallback (pages that block plain fetches). WITH_BROWSER=0 skips it: ~400 MB smaller.
ARG WITH_BROWSER=1
RUN if [ "$WITH_BROWSER" = "1" ]; then uv run playwright install --with-deps chromium; fi

COPY config.py ./
COPY app ./app
COPY scripts ./scripts
COPY evals ./evals

RUN useradd --create-home retro && chown -R retro /app
USER retro
EXPOSE 8000
CMD ["uv", "run", "python", "scripts/prod_server.py"]
