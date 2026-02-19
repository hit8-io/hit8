FROM node:20-slim

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies using npm ci for reproducible builds
RUN npm ci && \
    npm cache clean --force

# Copy application code
COPY . .

# Build argument for version (optional, defaults to unknown)
ARG VERSION=unknown
LABEL version=$VERSION

# Create non-root user and set permissions in one layer
RUN useradd -m appuser && \
    chown -R appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 5173

# Run dev server with host flag to allow external connections
CMD ["npm", "run", "dev", "--", "--host"]

