"""What a run with an API video model asks for, before it is paid.

A take made by an API model is paid when it is asked for. Two guards use this module: Deploy Shots (the estimate of the whole edit is written in its
report, and a deployment over the budget asks for a confirmation) and Generate Shot (API) (the seconds and dollars of the run are counted and the node
that would go over the budget stops, before it calls the model). The budgets are `max_api_seconds` and `max_api_usd` of Generator Select (0: no limit).

The dollars are the sum of the price badges of the API nodes (core/pricing.py), evaluated on the settings of each take. When a badge cannot be
evaluated (jsonata-python not installed, a node without badge) a generator file may carry `price_per_second` and `price_unit`; without either,
the estimate keeps the seconds only."""
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction

from .api_request import build_request
from .errors import MajoorError
from .generators import generation_seconds_for, load_generator
from .pricing import Price, ZERO, badge_of, evaluate

DEFAULT_BUDGET_SECONDS = 120


@dataclass(frozen=True)
class Settings:
    """What the take is asked with, besides its length: the widgets of Generate Shot and how many references it has."""

    aspect: str = "9:16"
    resolution: str = "720p"
    audio: bool = True
    images: int = 1
    videos: int = 0
    audios: int = 0


@dataclass(frozen=True)
class Choice:
    generator: str
    budget_seconds: int
    budget_usd: float


def shot_price(generator_id: str, seconds: float, settings: Settings = Settings(), seed: int = 0, badges: Callable[[str], dict | None] | None = None) -> Price | None:
    """The price badge of the API node that makes a take of `seconds`, on the settings of the take; None when it cannot be known.
    badges: where the badge of a node class comes from (the object_info of a ComfyUI that is not this process); by default the running ComfyUI."""
    try:
        request = build_request(generator_id, prompt="x", seconds=seconds, aspect=settings.aspect, resolution=settings.resolution, audio=settings.audio, seed=seed,
                                images=["i"] * settings.images, videos=["v"] * settings.videos, audios=["a"] * settings.audios)
    except MajoorError:
        return None
    return evaluate((badges or badge_of)(request.class_type), request.inputs, request.media)


@dataclass(frozen=True)
class Estimate:
    generator: str
    title: str
    paid: bool
    shots: int
    seconds: float  # the video asked for, one take per shot
    budget_seconds: int
    budget_usd: float
    stops_at: int | None  # the shot (1-based) that a budget stops, None when all fit
    price: Price | None  # the sum of the badges; None when unknown
    amount_text: str = ""  # an amount from price_per_second of the file, when no badge gave one

    @property
    def over_budget(self) -> bool:
        return self.stops_at is not None

    @property
    def text(self) -> str:
        if not self.paid:
            return f"{self.title}: runs on this computer, nothing to pay."
        head = f"{self.title}: {self.shots} shot(s), {self.seconds:g} s of video asked for from the API"
        if self.price is not None:
            head += f", about {self.price.text} (the price badges of the API nodes added up; a retry of every shot would cost the same again)"
        elif self.amount_text:
            head += f", about {self.amount_text}"
        else:
            head += "; no price: install jsonata-python (requirements.txt) so that the badges of the API nodes can be added up"
        limits = [f"{self.budget_seconds} s" if self.budget_seconds > 0 else "", f"${self.budget_usd:g}" if self.budget_usd > 0 else ""]
        limits = " and ".join(x for x in limits if x)
        if not limits:
            return head + ". No budget set."
        if self.stops_at is None:
            return head + f". Within the budget of {limits}."
        return head + f". Over the budget of {limits}: the run stops before shot {self.stops_at}."


def estimate(generator_id: str, shots: list[int], fps: Fraction | float, budget_seconds: int = DEFAULT_BUDGET_SECONDS, budget_usd: float = 0.0, settings: Settings = Settings(),
             badges: Callable[[str], dict | None] | None = None) -> Estimate:
    """shots: the length in frames of each shot that a model has to generate."""
    gen = load_generator(generator_id)
    if gen.source != "api":
        return Estimate(gen.id, gen.title, False, len(shots), 0.0, budget_seconds, budget_usd, None, None)
    seconds = [generation_seconds_for(gen.id, frames, fps) or frames / float(fps) for frames in shots]
    prices = [shot_price(gen.id, s, settings, badges=badges) for s in seconds]
    known = all(p is not None for p in prices)
    total = sum(prices, ZERO) if known and prices else None
    stops_at, run_s, run_usd = None, 0.0, 0.0
    for n, s in enumerate(seconds, 1):
        run_s += s
        run_usd += prices[n - 1].high if known else 0.0  # the dearest the badge says
        if stops_at is None and ((budget_seconds > 0 and run_s > budget_seconds) or (budget_usd > 0 and known and run_usd > budget_usd)):
            stops_at = n
    amount = ""
    if total is None and gen.price_per_second is not None:
        amount = f"{sum(seconds) * gen.price_per_second:g} {gen.price_unit}".strip()
    return Estimate(gen.id, gen.title, True, len(shots), float(sum(seconds)), budget_seconds, budget_usd, stops_at, total, amount)


def selected_generator(workflow: dict) -> Choice | None:
    """The model and the budgets of the Generator Select of a saved workflow (frontend JSON), None when the graph has none."""
    node = next((n for n in workflow.get("nodes", []) if n.get("type") == "MajoorGeneratorSelect"), None)
    if node is None:
        return None
    named = node.get("widgets_values_named") or {}
    values = node.get("widgets_values") or []
    return Choice(str(named.get("generator") or (values[0] if values else "")),
                  int(named.get("max_api_seconds", values[1] if len(values) > 1 else DEFAULT_BUDGET_SECONDS)),
                  float(named.get("max_api_usd", values[2] if len(values) > 2 else 0.0)))


def settings_of(workflow: dict) -> Settings:
    """The settings the takes of a saved workflow will be asked with: the widgets of its first Generate Shot and the references wired to it."""
    node = next((n for n in workflow.get("nodes", []) if n.get("type") == "MajoorGenerateShot"), None)
    if node is None:
        return Settings()
    named = node.get("widgets_values_named") or {}
    wired = {i["name"] for i in node.get("inputs", []) if i.get("link") is not None}
    return Settings(str(named.get("aspect_ratio", "9:16")), str(named.get("resolution", "720p")), bool(named.get("generate_audio", True)),
                    sum(1 for i in range(1, 10) if f"image_{i}" in wired), int("reference_frames" in wired), int("reference_audio" in wired))


def deploy_notes(workflow: dict, shots: list[tuple[str, int]], fps: float) -> tuple[list[str], list[str]]:
    """(warnings, questions) for Deploy Shots: the estimate of the edit with the chosen model, and a question when it would go over a budget.
    shots: (id, frames) of each shot a model has to generate."""
    chosen = selected_generator(workflow)
    if chosen is None or not shots or fps <= 0:
        return [], []
    found = estimate(chosen.generator, [frames for _, frames in shots], fps, chosen.budget_seconds, chosen.budget_usd, settings_of(workflow))
    if not found.paid:
        return [], []
    return [found.text], ([found.text + " Deploy anyway?"] if found.over_budget else [])


class Ledger:
    """The seconds and dollars already asked for in a run (a prompt of ComfyUI), kept for the last few runs."""

    KEEP = 16

    def __init__(self) -> None:
        self.runs: dict[str, tuple[float, float]] = {}

    def charge(self, run: str, seconds: float, budget_seconds: int, usd: float = 0.0, budget_usd: float = 0.0) -> tuple[float, float]:
        """Add a take to the run and return its totals (seconds, dollars). Raises ValueError (a message for the user) when a budget would be passed; nothing is added then."""
        spent_s, spent_usd = self.runs.get(run, (0.0, 0.0))
        if budget_seconds > 0 and spent_s + seconds > budget_seconds:
            raise ValueError(f"API budget reached: {spent_s:g} s of video already asked for in this run, {seconds:g} s more would pass the {budget_seconds} s of MAX API SECONDS (Generator Select). Raise it, or set 0 for no limit.")
        if budget_usd > 0 and spent_usd + usd > budget_usd:
            raise ValueError(f"API budget reached: about ${spent_usd:.2f} already asked for in this run, ${usd:.2f} more would pass the ${budget_usd:g} of MAX API USD (Generator Select). Raise it, or set 0 for no limit.")
        self.runs[run] = (spent_s + seconds, spent_usd + usd)
        for old in list(self.runs)[: -self.KEEP]:
            del self.runs[old]
        return self.runs[run]
