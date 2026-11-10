"""The price of a take, from the price badge of the API node that makes it.

Every partner node of ComfyUI carries a `price_badge`: a JSONata expression that the frontend evaluates on the widgets of the node and the number of
connected references (seconds, resolution, ratio, model...) and that gives a price in dollars, one amount or a range. Generate Shot (API) creates
its node when the graph runs, so the badge is evaluated here on the same values, which makes the price of an edit the sum of the badges of its takes.

The evaluator is the `jsonata-python` package (requirements.txt). Without it, or outside ComfyUI, or for a node that has no badge, a price is None:
the estimate then keeps the seconds only."""
from dataclasses import dataclass
from functools import lru_cache

try:
    from jsonata import Jsonata
except ImportError:  # the estimate keeps working in seconds
    Jsonata = None


@dataclass(frozen=True)
class Price:
    low: float  # dollars
    high: float

    def __add__(self, other: "Price") -> "Price":
        return Price(self.low + other.low, self.high + other.high)

    @property
    def text(self) -> str:
        if abs(self.high - self.low) < 0.005:
            return f"${self.high:.2f}"
        return f"${self.low:.2f} to ${self.high:.2f}"


ZERO = Price(0.0, 0.0)


def available() -> bool:
    return Jsonata is not None


@lru_cache(maxsize=32)
def _compiled(expr: str):
    return Jsonata(expr)


def badge_of(class_type: str) -> dict | None:
    """The price badge of a node class of the running ComfyUI (the same dict the frontend receives); None outside ComfyUI."""
    try:
        import nodes
        info = nodes.NODE_CLASS_MAPPINGS[class_type].GET_NODE_INFO_V1()
    except Exception:  # not in ComfyUI, unknown class, a node of another kind
        return None
    return info.get("price_badge") or None


def _context(badge: dict, widgets: dict, media: list[str]) -> dict:
    values = {k: (v.lower() if isinstance(v, str) else v) for k, v in widgets.items()}  # the frontend lower-cases the strings it gives to a badge: its tables are spelled in lower case
    depends = badge.get("depends_on") or {}
    return {
        "widgets": values,
        "inputs": {i["name"]: {"connected": i["name"] in media} for i in depends.get("inputs", [])},
        "inputGroups": {g: sum(1 for m in media if m.startswith(g + ".")) for g in depends.get("input_groups", [])},
    }


def _price(result) -> Price | None:
    if not isinstance(result, dict):
        return None
    if result.get("type") == "usd":
        return Price(float(result["usd"]), float(result["usd"]))
    if result.get("type") == "range_usd" and "min_usd" in result and "max_usd" in result:
        return Price(float(result["min_usd"]), float(result["max_usd"]))
    return None  # a badge that could not read its widgets gives a type and nothing else


def evaluate(badge: dict | None, inputs: dict, media: list[str]) -> Price | None:
    """The price a badge gives for the inputs of a node (widget values by name, `media` = the names of the connected references)."""
    if Jsonata is None or not badge or badge.get("engine") != "jsonata" or not badge.get("expr"):
        return None
    widgets = {k: v for k, v in inputs.items() if k not in media}
    try:
        return _price(_compiled(badge["expr"]).evaluate(_context(badge, widgets, media)))
    except Exception:  # an expression the evaluator cannot run is no price
        return None
