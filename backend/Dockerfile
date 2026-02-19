FROM python:3.11-slim

# Install build dependencies and Doppler CLI via apt (recommended method)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    curl \
    apt-transport-https \
    ca-certificates \
    gnupg \
    jq \
    pandoc \
    && curl -sLf --retry 3 --tlsv1.2 --proto "=https" 'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' | gpg --dearmor -o /usr/share/keyrings/doppler-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" | tee /etc/apt/sources.list.d/doppler-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends doppler \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:/root/.cargo/bin:$PATH"

WORKDIR /app

# Copy dependency files first (for better layer caching)
# Dependencies only need to be reinstalled if pyproject.toml changes
COPY pyproject.toml uv.lock* ./

# Install dependencies including dev group
RUN uv pip install --system . && \
    uv pip install --system --group dev .

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

# Cloud Run / Scaleway set PORT automatically; default 8080 for local dev
ENV PORT=8080
EXPOSE 8080
# When DOPPLER_TOKEN is set (GCP/Scaleway), run under doppler.
# Scaleway Secret Manager stores secrets base64-encoded and injects them as-is.
# GCP Secret Manager injects decoded values.
CMD /bin/sh -c 'if [ -n "${DOPPLER_TOKEN}" ]; then \
  TOKEN="${DOPPLER_TOKEN}"; \
  if ! echo "${TOKEN}" | grep -q "^dp\\."; then \
    DECODED=$(echo "${TOKEN}" | tr -d "\\n\\r " | base64 -d 2>/dev/null); \
    if [ $? -eq 0 ] && [ -n "${DECODED}" ] && echo "${DECODED}" | grep -q "^dp\\."; then \
      TOKEN="${DECODED}"; \
    fi; \
  fi; \
  export DOPPLER_TOKEN="${TOKEN}"; \
  exec doppler run -- uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}; \
else \
  exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}; \
fi'
