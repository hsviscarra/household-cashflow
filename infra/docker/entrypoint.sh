#!/bin/sh
# Prepare the database, apply migrations, then start the API.
set -e

python -m app.db.ensure_database   # no-op outside APP_ENV=local
alembic upgrade head
python -m app.db.reader         # the read-only login for /mcp (F18); no-op without it
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
