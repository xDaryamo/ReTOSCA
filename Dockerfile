# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip git make \
 && rm -rf /var/lib/apt/lists/*

# Install Go for Puccini build
ARG GO_VERSION=1.23.0
RUN curl -fsSL https://golang.org/dl/go${GO_VERSION}.linux-amd64.tar.gz -o /tmp/go.tar.gz \
 && tar -C /usr/local -xzf /tmp/go.tar.gz \
 && rm /tmp/go.tar.gz
ENV PATH="/usr/local/go/bin:$PATH"

# Install Terraform CLI (necessario per tflocal)
ARG TF_VERSION=1.8.5
RUN curl -fsSL https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_linux_amd64.zip -o /tmp/terraform.zip \
 && unzip /tmp/terraform.zip -d /usr/local/bin \
 && rm /tmp/terraform.zip

# Install Puccini TOSCA compiler
RUN git clone https://github.com/xDaryamo/puccini.git /tmp/puccini \
 && cd /tmp/puccini \
 && ./scripts/build \
 && cp /root/go/bin/puccini-* /usr/local/bin/ \
 && rm -rf /tmp/puccini

# Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - --version 1.8.3
ENV PATH="/root/.local/bin:$PATH"

# Configure Poetry to install globally without virtual environment
ENV POETRY_NO_INTERACTION=1
ENV POETRY_CACHE_DIR=/tmp/poetry_cache

# Create separate directory for dependency installation
WORKDIR /deps
COPY pyproject.toml poetry.lock* /deps/

# Install dependencies globally
RUN poetry config virtualenvs.create false \
    && poetry install --no-root --only main \
    && rm -rf /tmp/poetry_cache

# Set final working directory
WORKDIR /app

# Copy the project (includes examples, scripts, src, etc.)
COPY . .

# Make scripts executable
RUN chmod +x scripts/test-tosca.sh

# No default entrypoint - let docker-compose or user specify the command
