#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
python - <<'PY'
import os
import time
import sys
import psycopg2

host = os.getenv("DB_HOST", "localhost")
port = int(os.getenv("DB_PORT", "5432"))
user = os.getenv("DB_USER", "ai_user")
password = os.getenv("DB_PASSWORD", "ai_pass")
db = os.getenv("DB_NAME", "ai_db")

for _ in range(60):
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=db,
            connect_timeout=2,
        )
        conn.close()
        print("PostgreSQL is ready.")
        sys.exit(0)
    except Exception:
        time.sleep(2)
print("PostgreSQL not ready after timeout.", file=sys.stderr)
sys.exit(1)
PY

echo "Waiting for Neo4j..."
python - <<'PY'
import os
import time
import sys

neo4j_uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
neo4j_user = os.getenv("NEO4J_USER", "neo4j")
neo4j_pass = os.getenv("NEO4J_PASSWORD", "productstore123")

try:
    from neo4j import GraphDatabase
    for attempt in range(30):
        try:
            driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
            driver.verify_connectivity()
            driver.close()
            print("Neo4j is ready.")
            sys.exit(0)
        except Exception:
            time.sleep(2)
    print("Neo4j not ready after timeout.", file=sys.stderr)
except ImportError:
    print("neo4j driver not installed, skipping Neo4j check.")
sys.exit(0)
PY

python scripts/init_db.py

exec "$@"
