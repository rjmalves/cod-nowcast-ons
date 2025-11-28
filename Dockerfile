# Multi-stage Dockerfile for cod-nowcast-ons
# Production-ready image with minimal size

# Build stage
FROM python:3.12-slim AS builder

# Install system dependencies required for compilation
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    gfortran \
    libgeos-dev \
    libproj-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency installation
# Download the latest installer
ADD https://astral.sh/uv/install.sh /uv-installer.sh

# Run the installer then remove it
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure the installed binary is on the `PATH`
ENV PATH="/root/.local/bin/:$PATH"

# Set working directory
WORKDIR /build

# Copy project files
COPY pyproject.toml README.md ./
COPY app/ ./app/
COPY main.py ./

# Create virtual environment and install dependencies
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install --no-cache .

# Runtime stage
FROM python:3.12-slim

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    libgeos-c1v5 \
    libproj25 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser main.py ./
COPY --chown=appuser:appuser README.md ./

# Create directories for data and output
RUN mkdir -p /app/data/input /app/data/output /app/data/shapes && \
    chown -R appuser:appuser /app/data

# Set environment
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import app; print('OK')" || exit 1

# Default command
ENTRYPOINT ["cod-nowcast-ons"]
CMD ["--help"]
