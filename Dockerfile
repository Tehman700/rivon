FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY rivon ./rivon

RUN useradd --system --no-create-home rivon
USER rivon

EXPOSE 8000
CMD ["uvicorn", "rivon.main:app", "--host", "0.0.0.0", "--port", "8000"]
