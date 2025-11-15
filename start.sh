#!/usr/bin/env bash
set -e

echo "=== BotShop Bootstrap ==="
echo "Python version:"
python -V || true

echo "Installing dependencies (if in local dev)..."
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
fi

echo "Running uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
