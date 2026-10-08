FROM python:3.13-slim AS builder
WORKDIR /app
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime
WORKDIR /app
COPY --from=builder /app/.venv .venv
COPY alembic/ alembic/
COPY alembic.ini .
COPY app/ app/
COPY scripts/ scripts/
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --log-level ${LOG_LEVEL:-info}"]
