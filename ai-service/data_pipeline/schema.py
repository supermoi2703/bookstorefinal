from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


ACTIONS = ("VIEW", "CLICK", "ADD_TO_CART", "PURCHASE", "RATE", "READ")

_ACTION_ALIASES = {
    "view": "VIEW",
    "viewed": "VIEW",
    "click": "CLICK",
    "clicked": "CLICK",
    "addtocart": "ADD_TO_CART",
    "add_to_cart": "ADD_TO_CART",
    "cart": "ADD_TO_CART",
    "purchase": "PURCHASE",
    "purchased": "PURCHASE",
    "transaction": "PURCHASE",
    "buy": "PURCHASE",
    "bought": "PURCHASE",
    "rate": "RATE",
    "rated": "RATE",
    "rating": "RATE",
    "read": "READ",
    "is_read": "READ",
}


def normalize_action(value: Any, *, rating: float | None = None) -> str:
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in _ACTION_ALIASES:
        return _ACTION_ALIASES[key]
    if rating is not None:
        return "RATE"
    raise ValueError(f"Unsupported action: {value!r}")


def normalize_timestamp(value: Any) -> str:
    if value in (None, ""):
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000
        return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()
    text = str(value).strip()
    if text.isdigit():
        return normalize_timestamp(int(text))
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%a %b %d %H:%M:%S %z %Y"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Unsupported timestamp: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class Interaction:
    source: str
    domain: str
    user_id: str
    item_id: str
    action: str
    timestamp: str
    rating: float | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ProductRecord:
    source: str
    domain: str
    external_id: str
    title: str
    creator_or_brand: str = ""
    description: str = ""
    category: str = ""
    price: float = 0.0
    image_url: str = ""
    stock: int = 100
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        data = asdict(self)
        data["metadata"] = self.metadata
        return data
