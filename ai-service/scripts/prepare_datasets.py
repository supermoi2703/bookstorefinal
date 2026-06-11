import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data_pipeline.pipeline import prepare_all


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default=str(BASE_DIR / "data" / "datasets.json")
    )
    parser.add_argument(
        "--output", default=str(BASE_DIR / "data" / "processed")
    )
    args = parser.parse_args()
    result = prepare_all(args.config, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
