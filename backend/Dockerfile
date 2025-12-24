FROM python:3.11-slim

# Install system dependencies for building cryptography and other packages
# Install in one layer to reduce image size
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip and install wheel for faster installs
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy requirements and install dependencies
# This layer will be cached if requirements.txt doesn't change
# Use --prefer-binary to use pre-built wheels when available (much faster)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --use-deprecated=legacy-resolver -r requirements.txt

# Copy application code (this changes frequently, so it's last)
COPY . .

# Expose port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

