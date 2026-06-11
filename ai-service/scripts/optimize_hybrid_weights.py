import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from recommendation.weights import DEFAULT_WEIGHTS, WEIGHTS_PATH, optimize_weights


def main():
    parser = argparse.ArgumentParser(
        description="Optimize hybrid weights from validation candidate-score cases."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="JSON mapping domain to cases with target/lstm/graph/semantic fields.",
    )
    parser.add_argument("--output", default=str(WEIGHTS_PATH))
    args = parser.parse_args()
    cases = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = {
        "default": DEFAULT_WEIGHTS,
        "domains": {},
        "validation_ndcg@10": {},
    }
    for domain, domain_cases in cases.items():
        optimized = optimize_weights(domain_cases)
        result["domains"][domain] = optimized["weights"]
        result["validation_ndcg@10"][domain] = optimized["ndcg@10"]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
