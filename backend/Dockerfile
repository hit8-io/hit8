FROM python:3.11-slim

# Build argument to control production optimizations
ARG PRODUCTION=false

# Install system dependencies for building cryptography and other packages
# This layer is cached unless the base image changes
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip first (cached unless Python version changes)
# Use production optimizations if PRODUCTION=true
RUN if [ "$PRODUCTION" = "true" ]; then \
      pip install --no-cache-dir --disable-pip-version-check --prefer-binary --upgrade pip setuptools wheel; \
    else \
      pip install --no-cache-dir --upgrade pip setuptools wheel; \
    fi

# Copy requirements and install dependencies
# This layer is cached unless requirements.txt changes
COPY requirements.txt .
# Use production optimizations if PRODUCTION=true
RUN if [ "$PRODUCTION" = "true" ]; then \
      pip install --no-cache-dir --disable-pip-version-check --prefer-binary --timeout=300 --use-deprecated=legacy-resolver -r requirements.txt; \
    else \
      pip install --no-cache-dir --use-deprecated=legacy-resolver -r requirements.txt; \
    fi

# Copy application code last (changes most frequently)
# This layer is rebuilt on every code change
COPY . .

# Set port (Cloud Run uses 8080, dev uses 8000)
# Production uses exec for better signal handling, no reload
# Development command is overridden by docker-compose.yml
ENV PORT=8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
