# Use Python 3.12 (Stable)
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

# Install Node.js 20 (LTS)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs npm

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set environment variables for uv
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/workspace/.venv
