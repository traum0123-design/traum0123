FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    UVICORN_WORKERS=2

WORKDIR /app

# Install Python dependencies first for better layer caching
COPY requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

# Copy application source
COPY . .

# Create unprivileged user and fix permissions
RUN adduser --disabled-password --gecos "" --home /nonexistent --no-create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

# Use non-root user
USER appuser

# Expose default port (many PaaS override via $PORT)
EXPOSE 8000

# Container healthcheck (uses local HTTP health endpoint)
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD python -c "import sys,urllib.request,os,json;u=f'http://127.0.0.1:{os.getenv(''PORT'',''8000'')}/api/healthz';
import urllib.error
try:
 r=urllib.request.urlopen(u,timeout=2);
 ok=(r.getcode()==200 and json.loads(r.read().decode(''utf-8'')).get(''ok''));
 sys.exit(0 if ok else 1)
except Exception:
 sys.exit(1)"

# Start the FastAPI app with uvicorn
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${UVICORN_WORKERS:-2} --log-level ${UVICORN_LOG_LEVEL:-info}"]
