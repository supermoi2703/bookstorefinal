import json
from itertools import product
from pathlib import Path


DEFAULT_WEIGHTS = {"lstm": 0.45, "graph": 0.35, "semantic": 0.20}
WEIGHTS_PATH = (
    Path(__file__).resolve().parent.parent
    / "model_behavior"
    / "artifacts"
    / "hybrid_weights.json"
)


def load_weights(domain=None):
    if WEIGHTS_PATH.exists():
        payload = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
        selected = payload.get("domains", {}).get(domain) or payload.get("default")
        if selected:
            return selected
    return DEFAULT_WEIGHTS.copy()


def optimize_weights(validation_cases):
    best = {"weights": DEFAULT_WEIGHTS.copy(), "ndcg@10": -1.0}
    grid = [index / 10 for index in range(0, 11)]
    for lstm, graph in product(grid, repeat=2):
        semantic = round(1.0 - lstm - graph, 10)
        if semantic < 0:
            continue
        total = 0.0
        count = 0
        for case in validation_cases:
            scores = {}
            for component, weight in (
                ("lstm", lstm),
                ("graph", graph),
                ("semantic", semantic),
            ):
                for item, score in case.get(component, {}).items():
                    scores[item] = scores.get(item, 0.0) + weight * float(score)
            ranked = sorted(scores, key=scores.get, reverse=True)[:10]
            if case["target"] in ranked:
                import math

                total += 1 / math.log2(ranked.index(case["target"]) + 2)
            count += 1
        ndcg = total / max(1, count)
        if ndcg > best["ndcg@10"]:
            best = {
                "weights": {
                    "lstm": round(lstm, 2),
                    "graph": round(graph, 2),
                    "semantic": round(semantic, 2),
                },
                "ndcg@10": round(ndcg, 6),
            }
    return best
