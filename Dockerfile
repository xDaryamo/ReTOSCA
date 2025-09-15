############################
# STAGE 1: build Puccini
############################
FROM golang:1.23-bookworm AS puccini-builder

# Build dependencies + bash (the script often uses it)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git bash ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ARG PUCCINI_REF=main
WORKDIR /tmp
RUN git clone --depth 1 --branch "${PUCCINI_REF}" https://github.com/xDaryamo/puccini.git
WORKDIR /tmp/puccini

# Build with the official script
RUN chmod +x scripts/build && ./scripts/build

# Collect the binaries produced in /out (robust to path changes)
RUN set -eux; \
    mkdir -p /out; \
    found="$( (find . "$GOPATH/bin" -type f -name 'puccini-*' 2>/dev/null || true) | head -n 5 )"; \
    if [ -z "$found" ]; then echo "Puccini binaries not found!" >&2; exit 1; fi; \
    echo "$found" | xargs -I{} cp "{}" /out/; \
    chmod +x /out/puccini-*; \
    ls -l /out

############################
# STAGE 2: runtime
############################
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# --- Terraform CLI (pin + checksum recommended) ---
ARG TF_VERSION=1.13.2
RUN curl -fsSL https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_linux_amd64.zip -o /tmp/terraform.zip \
 && unzip /tmp/terraform.zip -d /usr/local/bin \
 && rm /tmp/terraform.zip

# --- Puccini binaries from builder stage ---
COPY --from=puccini-builder /out/puccini-* /usr/local/bin/
RUN chmod +x /usr/local/bin/puccini-*

# --- Poetry (pinned version) ---
RUN curl -sSL https://install.python-poetry.org | python3 - --version 1.8.3
ENV PATH="/root/.local/bin:$PATH" \
    POETRY_NO_INTERACTION=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Install dependencies in a separate layer for cache
WORKDIR /deps
COPY pyproject.toml poetry.lock* /deps/
RUN poetry config virtualenvs.create false \
 && poetry install --no-root --only main \
 && rm -rf /tmp/poetry_cache

    # App
WORKDIR /app
COPY . .

# (optional) hardening: non-root user
RUN useradd -m -u 10001 app && chown -R app:app /app
USER app

# (if you really need it)
RUN chmod +x scripts/test-tosca.sh || true

# No entrypoint: you decide or use docker-compose
# Examples:
# CMD ["poetry", "run", "python", "-m", "src.main", "--help"]
