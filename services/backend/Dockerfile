FROM python:3.12.13-slim-bookworm

ENV PATH="/app/services/backend/.venv/bin:${PATH}" \
    PYTHONPATH="/app/services/backend/src" \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app/services/backend

RUN python -m pip install --no-cache-dir uv==0.11.16

COPY services/backend/pyproject.toml services/backend/uv.lock ./

RUN uv sync \
    --locked \
    --no-dev \
    --no-install-project \
    --python /usr/local/bin/python

COPY services/backend/alembic.ini ./
COPY services/backend/migrations migrations
COPY services/backend/src src

RUN useradd --create-home --uid 10001 cockpit

USER cockpit
EXPOSE 8000
