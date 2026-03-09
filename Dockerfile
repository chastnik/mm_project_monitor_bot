FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        fontconfig fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN useradd --system --no-create-home --shell /bin/false botuser \
    && mkdir -p /app/data \
    && chown -R botuser:botuser /app

USER botuser

HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
    CMD python -c "import os, signal; os.kill(1, 0)" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
