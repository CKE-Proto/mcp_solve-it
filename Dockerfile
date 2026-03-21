## Multi-stage build for mcp-chassis server.
## Stage 1: install dependencies. Stage 2: minimal runtime image.

# ── builder stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Copy only the project definition first for layer caching
COPY pyproject.toml .
COPY src/ src/

# Install the package and its dependencies into the system site-packages
RUN pip install --no-cache-dir .

# ── runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Install basic troubleshooting utilities (not present in slim images)
RUN apt-get update \
    && apt-get install -y --no-install-recommends procps net-tools curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for running the server
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy config (loaded at runtime). The package code is already in site-packages.
COPY config/ config/

# Ensure the server finds the config file in the container
ENV MCP_CHASSIS_CONFIG=/app/config/default.toml

# Drop to non-root user
USER appuser

# MCP servers communicate over stdio — no network ports needed
ENTRYPOINT ["python", "-m", "mcp_chassis"]
