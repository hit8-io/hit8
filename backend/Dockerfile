FROM python:3.11-slim

# Install build dependencies, install packages, then remove build dependencies in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    curl \
    pandoc \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:/root/.cargo/bin:$PATH"

WORKDIR /app

# Copy dependency files first (for better layer caching)
# Dependencies only need to be reinstalled if pyproject.toml changes
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv pip install --system . && \
    uv pip install --system debugpy>=1.8.0

# Remove build tools after package installation to reduce image size
RUN apt-get purge -y build-essential gcc libffi-dev libssl-dev && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy application code last (changes most frequently)
# This layer will be rebuilt on code changes, but dependencies layer stays cached
COPY . .

# Create certificates directory (certificates should be provided via secrets or mounted volumes)
RUN mkdir -p /app/certs

# Build argument for version (optional, defaults to unknown)
ARG VERSION=unknown
LABEL version=$VERSION

# Create non-root user
RUN useradd -m appuser && \
    chown -R appuser /app

# Switch to non-root user
USER appuser

# Cloud Run sets PORT environment variable automatically
# Default to 8080 if not set (for local development)
ENV PORT=8080
EXPOSE 8080
CMD ["/bin/sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
