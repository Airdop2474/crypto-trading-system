# Multi-stage Docker build for crypto-trading-system
# Stage 1: Build
# TODO: pin to exact digest via:
#   docker pull python:3.13-slim-bookworm && docker inspect --format='{{index .RepoDigests 0}}' python:3.13-slim-bookworm
FROM python:3.13-slim-bookworm AS build

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies with hash verification
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
# TODO: pin to exact digest via:
#   docker pull python:3.13-slim-bookworm && docker inspect --format='{{index .RepoDigests 0}}' python:3.13-slim-bookworm
FROM python:3.13-slim-bookworm

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from build stage
COPY --from=build /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY data/ ./data/
COPY pyproject.toml .

# Create non-root user
RUN useradd --create-home --shell /bin/bash trader && \
    chown -R trader:trader /app
USER trader

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command: Start API server
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
