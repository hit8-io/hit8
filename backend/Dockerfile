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

# Copy project files
COPY pyproject.toml .
COPY . .

# Install dependencies using uv with pyproject.toml (modern Python dependency management)
RUN uv pip install --system --no-cache .

# Cloud Run sets PORT environment variable automatically
# Default to 8080 if not set (for local development)
ENV PORT=8080
EXPOSE 8080
CMD ["/bin/sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
