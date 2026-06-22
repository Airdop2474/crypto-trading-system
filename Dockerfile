# Multi-stage Docker build for crypto-trading-system
# Stage 1: Build
# TODO: pin to exact digest via:
#   docker pull python:3.13-slim-bookworm && docker inspect --format='{{index .RepoDigests 0}}' python:3.13-slim-bookworm
FROM python:3.13-slim-bookworm AS build

WORKDIR /app

# Install build dependencies
# meson + ninja-build + pkg-config: pandas 2.x 源码构建所需（有 wheel 时不会用到，作为兜底保障）
# python3-dev: 提供 Python.h，部分包源码编译必需
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    meson \
    ninja-build \
    pkg-config \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Configure pip to use Tsinghua mirror (faster metadata resolution in China)
RUN mkdir -p /root/.pip && \
    printf '[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple/\ntrusted-host = pypi.tuna.tsinghua.edu.cn\n' > /root/.pip/pip.conf

# libpq-dev: psycopg2 源码编译需要 PostgreSQL 客户端头文件
# （pip 优先使用 binary wheel，有 wheel 时此步骤不影响速度）
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

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
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY pyproject.toml .
COPY requirements.txt .

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
