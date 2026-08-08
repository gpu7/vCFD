# vCFD MCP server image (OpenFOAM may be separate container or native on host).
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
COPY cases/templates ./cases/templates
COPY prompts ./prompts

RUN pip install --no-cache-dir .

ENV VCFD_CASES_ROOT=/data/cases \
    VCFD_TEMPLATES_ROOT=/app/cases/templates \
    VCFD_JOBS_ROOT=/data/jobs \
    VCFD_OPENFOAM_MODE=docker \
    VCFD_TRANSPORT=http \
    VCFD_HOST=0.0.0.0 \
    VCFD_PORT=8000

RUN mkdir -p /data/cases /data/jobs

EXPOSE 8000

CMD ["vcfd", "serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
