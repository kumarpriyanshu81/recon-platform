# recon-platform — Dockerfile
#
# Installs ProjectDiscovery subfinder and httpx from pre-built binaries
# alongside the Python framework. No Go toolchain required at runtime.
#
# Build:
#   docker build -t recon-platform .
#
# Run:
#   docker run --rm -v $(pwd)/output:/app/output recon-platform -d example.com
#
# Pass environment overrides:
#   docker run --rm \
#     -e HTTPX_THREADS=100 \
#     -e SUBFINDER_TIMEOUT=180 \
#     -v $(pwd)/output:/app/output \
#     recon-platform -d example.com

FROM python:3.12-slim

LABEL maintainer="recon-platform"
LABEL description="Modular reconnaissance orchestration framework"

# -------------------------------------------------------------------------
# System dependencies
# -------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        unzip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------------------------------
# ProjectDiscovery tools (linux/amd64 pre-built binaries)
# -------------------------------------------------------------------------
ARG SUBFINDER_VERSION=v2.6.6
ARG HTTPX_VERSION=v1.6.10

RUN curl -sSL \
    "https://github.com/projectdiscovery/subfinder/releases/download/${SUBFINDER_VERSION}/subfinder_${SUBFINDER_VERSION#v}_linux_amd64.zip" \
    -o /tmp/subfinder.zip \
    && unzip -q /tmp/subfinder.zip -d /tmp/subfinder \
    && mv /tmp/subfinder/subfinder /usr/local/bin/subfinder \
    && chmod +x /usr/local/bin/subfinder \
    && rm -rf /tmp/subfinder /tmp/subfinder.zip

RUN curl -sSL \
    "https://github.com/projectdiscovery/httpx/releases/download/${HTTPX_VERSION}/httpx_${HTTPX_VERSION#v}_linux_amd64.zip" \
    -o /tmp/httpx.zip \
    && unzip -q /tmp/httpx.zip -d /tmp/httpx \
    && mv /tmp/httpx/httpx /usr/local/bin/httpx \
    && chmod +x /usr/local/bin/httpx \
    && rm -rf /tmp/httpx /tmp/httpx.zip

# Use standard 'httpx' name (not httpx-toolkit) inside the container
ENV HTTPX_BIN=httpx

# -------------------------------------------------------------------------
# Application
# -------------------------------------------------------------------------
WORKDIR /app
COPY . .

# Ensure output directory exists and is writable
RUN mkdir -p /app/output /app/private_modules

ENTRYPOINT ["python", "main.py"]
