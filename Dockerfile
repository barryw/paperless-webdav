FROM python:3.12-slim

# OCI image labels (static)
LABEL org.opencontainers.image.title="paperless-webdav"
LABEL org.opencontainers.image.source="https://github.com/barryw/paperless-webdav"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.vendor="barryw"
# Dynamic labels (version, description, created) are added at build time by CI

WORKDIR /app

# Install system dependencies for python-ldap
RUN apt-get update && apt-get install -y \
    gcc \
    libldap2-dev \
    libsasl2-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Install dependencies
RUN uv sync --frozen --no-dev

# Expose ports
EXPOSE 8080 8081

# Run the application
CMD ["uv", "run", "python", "-m", "paperless_webdav.main"]
