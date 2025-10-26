#!/bin/sh
set -e
echo "[start.sh] installing requirements..."
pip install --no-cache-dir -r /app/bot/requirements.txt
echo "[start.sh] starting bot..."
python -m bot.main