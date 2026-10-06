FROM python:3.12-slim AS base

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml README.md LICENSE ./
COPY memlite/ memlite/
RUN pip install --no-cache-dir -e ".[dev]" && \
    pip install --no-cache-dir fastapi uvicorn[standard]

# Data volume
RUN mkdir -p /data
ENV MEMLITE_DATA_DIR=/data

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run API server
CMD ["uvicorn", "memlite.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
