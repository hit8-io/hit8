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
# When DOPPLER_TOKEN is set (GCP), run under doppler.
# For Scaleway, fetch token from Secret Manager API if DOPPLER_TOKEN_SECRET_ID is set.
CMD /bin/sh -c 'if [ -z "${DOPPLER_TOKEN}" ] && [ -n "${DOPPLER_TOKEN_SECRET_ID}" ] && [ -n "${SCALEWAY_SECRET_KEY}" ]; then \
  SECRET_UUID="${DOPPLER_TOKEN_SECRET_ID##*/}"; \
  REGION="${SCALEWAY_SECRET_REGION:-fr-par}"; \
  API_RESPONSE=$(curl -sS -w "\\n%{http_code}" -H "X-Auth-Token: ${SCALEWAY_SECRET_KEY}" "https://api.scaleway.com/secret-manager/v1beta1/regions/${REGION}/secrets/${SECRET_UUID}/versions/latest/access"); \
  HTTP_CODE=$(echo "$API_RESPONSE" | tail -n1); \
  API_BODY=$(echo "$API_RESPONSE" | sed "$d"); \
  if [ "$HTTP_CODE" = "200" ]; then \
    ENCODED=$(echo "$API_BODY" | jq -r ".opaque_data // .data // empty" 2>/dev/null || echo "$API_BODY"); \
    DOPPLER_TOKEN=$(echo "$ENCODED" | tr -d "\\n\\r " | base64 -d 2>/dev/null || echo "$ENCODED"); \
    export DOPPLER_TOKEN; \
  fi; \
fi; \
if [ -n "${DOPPLER_TOKEN}" ]; then \
  exec doppler run -- uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}; \
else \
  exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}; \
fi'
