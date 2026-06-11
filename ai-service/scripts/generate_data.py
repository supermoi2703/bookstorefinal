"""
Câu 1: Sinh tập dữ liệu data_user500.csv
- 500 user, mỗi user có nhiều behaviors
- Columns: user_id, product_id, action, timestamp
- Actions: view, click, add_to_cart
- Product IDs: 1-15 (tương ứng products trong hệ thống)
"""

import csv
import os
import random
from datetime import datetime, timedelta

# ============================================================
# Configuration
# ============================================================
NUM_USERS = 500
PRODUCT_IDS = list(range(1, 16))  # 15 products
ACTIONS = ["view", "click", "add_to_cart"]
ACTION_WEIGHTS = [0.60, 0.25, 0.15]  # view chiếm 60%, click 25%, add_to_cart 15%
MIN_EVENTS_PER_USER = 4
MAX_EVENTS_PER_USER = 16
DAYS_RANGE = 90  # 90 ngay gan day
SEED = 42

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "data_user500.csv")


def generate_data():
    random.seed(SEED)
    now = datetime(2026, 4, 20, 12, 0, 0)
    start_date = now - timedelta(days=DAYS_RANGE)

    rows = []
    for user_id in range(1, NUM_USERS + 1):
        # Moi user co so luong events ngau nhien
        num_events = random.randint(MIN_EVENTS_PER_USER, MAX_EVENTS_PER_USER)

        # User co xu huong thich 2-4 san pham nhat dinh (realistic)
        num_fav = random.randint(2, 4)
        fav_products = random.sample(PRODUCT_IDS, num_fav)

        for _ in range(num_events):
            # 70% xac suat chon san pham yeu thich, 30% random
            if random.random() < 0.7:
                product_id = random.choice(fav_products)
            else:
                product_id = random.choice(PRODUCT_IDS)

            action = random.choices(ACTIONS, weights=ACTION_WEIGHTS, k=1)[0]

            # Timestamp ngau nhien trong 90 ngay
            offset_seconds = random.randint(0, DAYS_RANGE * 24 * 3600)
            ts = start_date + timedelta(seconds=offset_seconds)
            timestamp = ts.strftime("%Y-%m-%d %H:%M:%S")

            rows.append({
                "user_id": user_id,
                "product_id": product_id,
                "action": action,
                "timestamp": timestamp,
            })

    # Sap xep theo timestamp
    rows.sort(key=lambda r: (r["user_id"], r["timestamp"]))

    # Ghi CSV
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["user_id", "product_id", "action", "timestamp"])
        writer.writeheader()
        writer.writerows(rows)

    # Thong ke
    unique_users = len(set(r["user_id"] for r in rows))
    action_counts = {}
    for r in rows:
        action_counts[r["action"]] = action_counts.get(r["action"], 0) + 1

    print("=" * 60)
    print("DATA GENERATION COMPLETE")
    print("=" * 60)
    print(f"Output file  : {OUTPUT_FILE}")
    print(f"Total rows   : {len(rows)}")
    print(f"Unique users : {unique_users}")
    print(f"Products     : {len(PRODUCT_IDS)}")
    print(f"Action dist  :")
    for act, cnt in sorted(action_counts.items()):
        pct = cnt / len(rows) * 100
        print(f"  {act:15s}: {cnt:5d} ({pct:.1f}%)")
    print("=" * 60)

    # In 20 dong dau
    print("\n--- 20 dòng đầu tiên ---")
    for r in rows[:20]:
        print(f"  user_id={r['user_id']:3d}  product_id={r['product_id']:2d}  "
              f"action={r['action']:12s}  timestamp={r['timestamp']}")

    return rows


if __name__ == "__main__":
    generate_data()
