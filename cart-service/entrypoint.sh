#!/bin/sh
set -e

echo "Waiting for MySQL..."
python - <<'PY'
import os, time, sys
import pymysql

host = os.getenv("DB_HOST", "localhost")
port = int(os.getenv("DB_PORT", "3306"))
user = os.getenv("DB_USER", "")
password = os.getenv("DB_PASSWORD", "")
db = os.getenv("DB_NAME", "")

for i in range(60):
    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password, database=db, connect_timeout=2)
        conn.close()
        print("MySQL is ready.")
        sys.exit(0)
    except Exception:
        time.sleep(2)
print("MySQL not ready after 120s", file=sys.stderr)
sys.exit(1)
PY

python manage.py makemigrations app --noinput
python manage.py migrate --noinput

exec "$@"
