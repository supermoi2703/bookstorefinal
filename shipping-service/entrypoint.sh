#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
python - <<'PY'
import os, time, sys
import psycopg2

host = os.getenv("DB_HOST", "localhost")
port = int(os.getenv("DB_PORT", "5432"))
user = os.getenv("DB_USER", "")
password = os.getenv("DB_PASSWORD", "")
db = os.getenv("DB_NAME", "")

for i in range(60):
    try:
        conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=db, connect_timeout=2)
        conn.close()
        print("PostgreSQL is ready.")
        sys.exit(0)
    except Exception:
        time.sleep(2)
print("PostgreSQL not ready after 120s", file=sys.stderr)
sys.exit(1)
PY

python manage.py makemigrations app --noinput
python manage.py migrate --noinput

exec "$@"
