FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update -y && apt-get install -y --no-install-recommends ca-certificates tzdata curl tini && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY bot/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY bot /app/bot
RUN mkdir -p /data && chown -R 1000:1000 /data
ENV STORE_PATH=/data/store.json
ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["python","-m","bot.main"]