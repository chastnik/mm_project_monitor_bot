FROM python:3.15-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        fontconfig fonts-dejavu-core tzdata \
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

# Планировщик обновляет heartbeat-файл раз в минуту; если файл не обновлялся 5 минут - процесс завис
HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import os, sys, time; from config import config; sys.exit(0 if time.time() - os.path.getmtime(config.HEARTBEAT_FILE) < 300 else 1)" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
