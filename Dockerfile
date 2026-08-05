FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SOUNDCHECK_DB_PATH=/app/data/soundcheck.duckdb

WORKDIR /app

RUN addgroup --system soundcheck \
    && adduser --system --ingroup soundcheck soundcheck \
    && pip install --no-cache-dir \
        "duckdb==1.5.5" \
        "fastapi==0.139.2" \
        "pydantic==2.13.4" \
        "uvicorn[standard]==0.51.0"

COPY --chown=soundcheck:soundcheck soundcheck /app/soundcheck
COPY --chown=soundcheck:soundcheck data/soundcheck.duckdb /app/data/soundcheck.duckdb

USER soundcheck

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/api/health', timeout=3)"]

CMD ["sh", "-c", "exec uvicorn soundcheck.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
