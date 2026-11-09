"""What a run with an API video model asks for, before it is paid.

A take made by an API model is paid when it is asked for, in seconds of video. Two guards use this module: Deploy Shots (the estimate of the whole edit
is written in its report, and a deployment over the budget asks for a confirmation) and Generate Shot (API) (the seconds of the run are counted and the
node that would go over the budget stops, before it calls the model). The budget is `max_api_seconds` of Generator Select (0: no limit).

The shipped generator files do not carry a price: the amounts of the partner nodes change and are shown by their own badge. A file may hold
`price_per_second` and `price_unit` to get an amount in the estimate."""
from dataclasses import dataclass
from fractions import Fraction

from .generators import generation_seconds_for, load_generator

DEFAULT_BUDGET_SECONDS = 120


@dataclass(frozen=True)
class Estimate:
    generator: str
    title: str
    paid: bool
    shots: int
    seconds: float  # the video asked for, one take per shot
    retry_seconds: float  # more, if every shot is retried once
    budget: int
    stops_at: int | None  # the shot (1-based) that the budget stops, None when all fit
    amount: float | None
    unit: str

    @property
    def over_budget(self) -> bool:
        return self.budget > 0 and self.stops_at is not None

    @property
    def text(self) -> str:
        if not self.paid:
            return f"{self.title}: runs on this computer, nothing to pay."
        head = f"{self.title}: {self.shots} shot(s), {self.seconds:g} s of video asked for from the API (up to {self.seconds + self.retry_seconds:g} s if every take is retried)"
        if self.amount is not None:
            head += f", about {self.amount:g} {self.unit}"
        else:
            head += "; the price is on the badge of the API node"
        if self.budget <= 0:
            return head + ". No budget set."
        if self.stops_at is None:
            return head + f". Within the budget of {self.budget} s."
        return head + f". Over the budget of {self.budget} s: the run stops before shot {self.stops_at}."


def estimate(generator_id: str, shots: list[int], fps: Fraction | float, budget: int = DEFAULT_BUDGET_SECONDS) -> Estimate:
    """shots: the length in frames of each shot that a model has to generate."""
    gen = load_generator(generator_id)
    if gen.source != "api":
        return Estimate(gen.id, gen.title, False, len(shots), 0.0, 0.0, budget, None, None, "")
    seconds = [generation_seconds_for(gen.id, frames, fps) or frames / float(fps) for frames in shots]
    total, stops_at, running = float(sum(seconds)), None, 0.0
    for n, s in enumerate(seconds, 1):
        running += s
        if budget > 0 and running > budget and stops_at is None:
            stops_at = n
    price = gen.price_per_second
    return Estimate(gen.id, gen.title, True, len(shots), total, total, budget, stops_at, None if price is None else total * price, gen.price_unit)


def selected_generator(workflow: dict) -> tuple[str, int] | None:
    """The model and the budget of the Generator Select of a saved workflow (frontend JSON), None when the graph has none."""
    node = next((n for n in workflow.get("nodes", []) if n.get("type") == "MajoorGeneratorSelect"), None)
    if node is None:
        return None
    named = node.get("widgets_values_named") or {}
    values = node.get("widgets_values") or []
    generator = named.get("generator") or (values[0] if values else "")
    budget = named.get("max_api_seconds", values[1] if len(values) > 1 else DEFAULT_BUDGET_SECONDS)
    return str(generator), int(budget)


def deploy_notes(workflow: dict, shots: list[tuple[str, int]], fps: float) -> tuple[list[str], list[str]]:
    """(warnings, questions) for Deploy Shots: the estimate of the edit with the chosen model, and a question when it would go over the budget.
    shots: (id, frames) of each shot a model has to generate."""
    chosen = selected_generator(workflow)
    if chosen is None or not shots or fps <= 0:
        return [], []
    found = estimate(chosen[0], [frames for _, frames in shots], fps, chosen[1])
    if not found.paid:
        return [], []
    notes = [found.text]
    return notes, ([found.text + " Deploy anyway?"] if found.over_budget else [])


class Ledger:
    """The seconds already asked for in a run (a prompt of ComfyUI), kept for the last few runs."""

    KEEP = 16

    def __init__(self) -> None:
        self.runs: dict[str, float] = {}

    def charge(self, run: str, seconds: float, budget: int) -> float:
        """Add the seconds of a take to the run and return the total; raises ValueError (a message for the user) when the budget would be passed. Nothing is added then."""
        spent = self.runs.get(run, 0.0)
        if budget > 0 and spent + seconds > budget:
            raise ValueError(f"API budget reached: {spent:g} s of video already asked for in this run, {seconds:g} s more would pass the {budget} s of MAX API SECONDS (Generator Select). Raise it, or set 0 for no limit.")
        self.runs[run] = spent + seconds
        for old in list(self.runs)[: -self.KEEP]:
            del self.runs[old]
        return self.runs[run]
