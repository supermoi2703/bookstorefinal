import json
import logging
from pathlib import Path

from .next_item import ModelConfig, build_model

logger = logging.getLogger(__name__)
ARTIFACT_ROOT = Path(__file__).resolve().parent / "artifacts"
REGISTRY_PATH = ARTIFACT_ROOT / "registry.json"

_registry = None
_models = {}


def registry_status():
    registry = load_registry()
    return {
        "available": bool(registry.get("domains")),
        "version": registry.get("version"),
        "domains": sorted(registry.get("domains", {}).keys()),
    }


def load_registry(force=False):
    global _registry
    if _registry is not None and not force:
        return _registry
    if not REGISTRY_PATH.exists():
        _registry = {"version": None, "domains": {}}
    else:
        _registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return _registry


def _load_domain_model(domain):
    if domain in _models:
        return _models[domain]
    entry = load_registry().get("domains", {}).get(domain)
    if not entry:
        return None
    try:
        import torch

        checkpoint = torch.load(
            ARTIFACT_ROOT / entry["artifact"], map_location="cpu", weights_only=False
        )
        config = ModelConfig(**checkpoint["config"])
        model = build_model(checkpoint["architecture"], config)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()
        loaded = {
            "model": model,
            "config": config,
            "item_to_index": checkpoint["item_to_index"],
            "index_to_item": {
                int(index): item for index, item in checkpoint["index_to_item"].items()
            },
            "action_to_index": checkpoint["action_to_index"],
            "source": checkpoint["source"],
            "version": entry["version"],
        }
        _models[domain] = loaded
        return loaded
    except Exception as exc:
        logger.warning("Cannot load next-item model for %s: %s", domain, exc)
        return None


def recommend(domain, item_ids, actions, time_deltas=None, limit=50):
    loaded = _load_domain_model(domain)
    if not loaded or len(item_ids) < 2:
        return []
    import torch

    config = loaded["config"]
    pairs = [
        (
            loaded["item_to_index"].get(str(item), 0),
            loaded["action_to_index"].get(str(action).upper(), 0),
        )
        for item, action in zip(item_ids, actions)
    ][-config.sequence_length :]
    if len(pairs) < config.sequence_length:
        padding = [(0, 0)] * (config.sequence_length - len(pairs))
        pairs = padding + pairs
    items = torch.LongTensor([[pair[0] for pair in pairs]])
    action_tensor = torch.LongTensor([[pair[1] for pair in pairs]])
    deltas = list(time_deltas or [])[-config.sequence_length :]
    deltas = [0.0] * (config.sequence_length - len(deltas)) + deltas
    delta_tensor = torch.FloatTensor([deltas])
    with torch.no_grad():
        logits, _ = loaded["model"](items, action_tensor, delta_tensor)
        probabilities = torch.softmax(logits, dim=1)[0]
        count = min(limit, probabilities.shape[0])
        values, indices = torch.topk(probabilities, count)
    results = []
    for score, zero_index in zip(values.tolist(), indices.tolist()):
        item = loaded["index_to_item"].get(zero_index + 1)
        if item:
            results.append(
                {
                    "external_id": item,
                    "source": loaded["source"],
                    "score": round(float(score), 6),
                    "model_version": loaded["version"],
                }
            )
    return results
