import argparse
import time

from app.database import init_db, session_scope
from graph.service import ensure_schema, sync_pending_events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    init_db()
    ensure_schema()
    while True:
        with session_scope() as db:
            result = sync_pending_events(db, args.batch_size)
        if result.get("processed"):
            print(result, flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
