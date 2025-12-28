FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package installer)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:/root/.cargo/bin:$PATH"

WORKDIR /app

# Copy dependency files first (for better layer caching)
# Dependencies only need to be reinstalled if pyproject.toml changes
COPY pyproject.toml uv.lock* ./

# Install dependencies (cached unless pyproject.toml or uv.lock changes)
RUN uv pip install --system .

# Copy application code last (changes most frequently)
# This layer will be rebuilt on code changes, but dependencies layer stays cached
COPY . .

# Cloud Run sets PORT environment variable automatically
# Default to 8080 if not set (for local development)
ENV PORT=8080
EXPOSE 8080
CMD ["/bin/sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
