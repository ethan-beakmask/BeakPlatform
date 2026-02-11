FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/BeakPlatform

# Install Python dependencies
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy application code
COPY backend/ backend/
COPY modules/ modules/
COPY scripts/ scripts/
COPY deploy/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Production environment defaults
ENV FLASK_ENV=production \
    GUNICORN_BIND=0.0.0.0:5000 \
    GUNICORN_WORKERS=3 \
    GUNICORN_THREADS=2

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

WORKDIR /opt/BeakPlatform/backend

ENTRYPOINT ["/docker-entrypoint.sh"]
