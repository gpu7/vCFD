# vCFD MCP server image (OpenFOAM runs via host Docker socket or separate containers).
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI only (talks to mounted docker.sock for OpenFOAM jobs on the host)
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
      > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
COPY cases/templates ./cases/templates
COPY prompts ./prompts

RUN pip install --no-cache-dir .

ENV VCFD_CASES_ROOT=/data/vcfd/cases \
    VCFD_TEMPLATES_ROOT=/app/cases/templates \
    VCFD_JOBS_ROOT=/data/vcfd/jobs \
    VCFD_OPENFOAM_MODE=docker \
    VCFD_TRANSPORT=http \
    VCFD_HOST=0.0.0.0 \
    VCFD_PORT=8000

RUN mkdir -p /data/vcfd/cases /data/vcfd/jobs

EXPOSE 8000

CMD ["vcfd", "serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
