"""What a run with an API video model asks for, before it is paid.

A take made by an API model is paid when it is asked for. Two guards use this module: Deploy Shots (the estimate of the whole edit is written in its
report, and a deployment over the budget asks for a confirmation) and Generate Shot (API) (the seconds and dollars of the run are counted and the node
that would go over the budget stops, before it calls the model). The budgets are `max_api_seconds` and `max_api_usd` of Generator Select (0: no limit).

The dollars are the sum of the price badges of the API nodes (core/pricing.py), evaluated on the settings of each take. When a badge cannot be
evaluated (jsonata-python not installed, a node without badge) a generator file may carry `price_per_second` and `price_unit`; without either,
the estimate keeps the seconds only. A budget in dollars with no price it can be checked against is not a budget: the estimate says the run stops
before its first shot, and Generate Shot (API) refuses the take, rather than letting it be paid unchecked."""
import json
import os
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

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
    task: str = "reference"  # edit: a Remix take changes a source video


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
                                images=["i"] * settings.images, videos=["v"] * settings.videos, audios=["a"] * settings.audios, task=settings.task)
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
    price: Price | None  # the sum of the badges; None when unknown. low: `takes_low` takes a shot, high: `takes` takes a shot
    amount_text: str = ""  # an amount from price_per_second of the file, when no badge gave one
    takes: int = 1  # the most takes a shot may be made with (a second take, a retry of a bad one): the budget is checked on them
    unpriced: bool = False  # a budget in dollars was set but no price is known: the run cannot be checked, so it stops

    @property
    def seconds_high(self) -> float:
        return self.seconds * self.takes

    @property
    def over_budget(self) -> bool:
        return self.stops_at is not None

    @property
    def text(self) -> str:
        if not self.paid:
            return f"{self.title}: runs on this computer, nothing to pay."
        head = f"{self.title}: {self.shots} shot(s), {self.seconds:g} s of video asked for from the API"
        if self.takes > 1:
            head += f" (up to {self.seconds_high:g} s with {self.takes} takes a shot)"
        if self.price is not None:
            head += f", about {self.price.text} (the price badges of the API nodes added up" + (f"; the high figure counts {self.takes} takes a shot)" if self.takes > 1 else "; a retry of every shot would cost the same again)")
        elif self.amount_text:
            head += f", about {self.amount_text}"
        else:
            head += "; no price: install jsonata-python (requirements.txt) so that the badges of the API nodes can be added up"
        if self.unpriced:
            return head + f". A budget of ${self.budget_usd:g} is set but no price is known, so it cannot be checked: the run stops before shot 1 (set MAX API USD to 0 to count seconds only)."
        limits = [f"{self.budget_seconds} s" if self.budget_seconds > 0 else "", f"${self.budget_usd:g}" if self.budget_usd > 0 else ""]
        limits = " and ".join(x for x in limits if x)
        if not limits:
            return head + ". No budget set."
        if self.stops_at is None:
            return head + f". Within the budget of {limits}."
        return head + f". Over the budget of {limits}: the run stops before shot {self.stops_at}."


def estimate(generator_id: str, shots: list[int], fps: Fraction | float, budget_seconds: int = DEFAULT_BUDGET_SECONDS, budget_usd: float = 0.0, settings: Settings = Settings(),
             badges: Callable[[str], dict | None] | None = None, takes: int = 1, takes_low: int = 1) -> Estimate:
    """shots: the length in frames of each shot that a model has to generate.
    takes: the most takes a shot may be made with (2 when a second take or a retry of a bad take is on); the budget is checked on that many. The
    low figure of the price counts `takes_low` takes a shot (2 when the second take is always made)."""
    gen = load_generator(generator_id)
    takes = max(1, int(takes))
    takes_low = max(1, min(int(takes_low), takes))
    if gen.source != "api":
        return Estimate(gen.id, gen.title, False, len(shots), 0.0, budget_seconds, budget_usd, None, None, takes=takes)
    seconds = [generation_seconds_for(gen.id, frames, fps) or frames / float(fps) for frames in shots]
    prices = [shot_price(gen.id, s, settings, badges=badges) for s in seconds]
    known = all(p is not None for p in prices)
    total = sum(prices, ZERO) if known and prices else None
    if total is not None:
        total = Price(total.low * takes_low, total.high * takes)
    unpriced = budget_usd > 0 and not known and bool(seconds)
    stops_at, run_s, run_usd = (1 if unpriced else None), 0.0, 0.0
    for n, s in enumerate(seconds, 1):
        run_s += s * takes
        run_usd += prices[n - 1].high * takes if known else 0.0  # the dearest the badge says, for every take the shot may need
        if stops_at is None and ((budget_seconds > 0 and run_s > budget_seconds) or (budget_usd > 0 and known and run_usd > budget_usd)):
            stops_at = n
    amount = ""
    if total is None and gen.price_per_second is not None:
        amount = f"{sum(seconds) * gen.price_per_second:g} {gen.price_unit}".strip()
    return Estimate(gen.id, gen.title, True, len(shots), float(sum(seconds)), budget_seconds, budget_usd, stops_at, total, amount, takes, unpriced)


# The widgets of the nodes in the order the frontend saves them in widgets_values (the order of define_schema; a seed with control_after_generate is
# followed by its control). widgets_values is what the frontend keeps up to date; widgets_values_named is only written by Deploy, so it is the fallback.
SELECT_WIDGETS = ("generator", "max_api_seconds", "max_api_usd", "budget_key")
SHOT_WIDGETS = ("aspect_ratio", "resolution", "generate_audio", "seed", "control_after_generate", "reference_fps", "task")


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _widgets(node: dict, order: tuple[str, ...], checks: dict[str, Callable[[object], bool]]) -> dict:
    """The widgets of a saved node by name: from their place in widgets_values when the value there reads right, else from widgets_values_named."""
    named = node.get("widgets_values_named") if isinstance(node.get("widgets_values_named"), dict) else {}
    values = node.get("widgets_values") if isinstance(node.get("widgets_values"), list) else []
    found = {}
    for position, name in enumerate(order):
        check = checks.get(name, lambda _v: True)
        if position < len(values) and check(values[position]):
            found[name] = values[position]
        elif name in named and check(named[name]):
            found[name] = named[name]
    return found


def selected_generator(workflow: dict) -> Choice | None:
    """The model and the budgets of the Generator Select of a saved workflow (frontend JSON), None when the graph has none."""
    node = next((n for n in workflow.get("nodes", []) if n.get("type") == "MajoorGeneratorSelect"), None)
    if node is None:
        return None
    found = _widgets(node, SELECT_WIDGETS, {"generator": lambda v: isinstance(v, str) and bool(v), "max_api_seconds": _number, "max_api_usd": _number})
    return Choice(str(found.get("generator", "")), int(found.get("max_api_seconds", DEFAULT_BUDGET_SECONDS)), float(found.get("max_api_usd", 0.0)))


def settings_of(workflow: dict) -> Settings:
    """The settings the takes of a saved workflow will be asked with: the widgets of its first Generate Shot and the references wired to it."""
    from .api_request import ASPECTS, RESOLUTIONS
    node = next((n for n in workflow.get("nodes", []) if n.get("type") == "MajoorGenerateShot"), None)
    if node is None:
        return Settings()
    found = _widgets(node, SHOT_WIDGETS, {"aspect_ratio": lambda v: v in ASPECTS, "resolution": lambda v: v in RESOLUTIONS, "generate_audio": lambda v: isinstance(v, bool),
                                          "seed": _number, "control_after_generate": lambda v: isinstance(v, str), "reference_fps": _number,
                                          "task": lambda v: v in ("reference", "edit")})
    wired = {i["name"] for i in node.get("inputs", []) if i.get("link") is not None}
    return Settings(str(found.get("aspect_ratio", "9:16")), str(found.get("resolution", "720p")), bool(found.get("generate_audio", True)),
                    sum(1 for i in range(1, 10) if f"image_{i}" in wired), int("reference_frames" in wired or "source_video" in wired), int("reference_audio" in wired),
                    str(found.get("task", "reference")))


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
    """The seconds and dollars already asked for in a run, kept for the last few runs.

    A run is a prompt of ComfyUI, or every prompt that names the same `budget_key` in Generator Select: HyperKut Studio sends one prompt a shot and
    names the job, so the budget is the one of the whole edit, and a graph queued again with the same key goes on from what it already spent.
    With a `path` the counts are kept on disk, so a restart of ComfyUI does not give a fresh budget; runs older than `MAX_AGE` are dropped, at most
    `KEEP` are kept (the ones used least lately go first), and `reset` forgets one or all (the file goes with the last one)."""

    KEEP = 64
    MAX_AGE = 7 * 24 * 3600  # seconds

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else None
        self.runs: dict[str, tuple[float, float]] = {}
        self.stamps: dict[str, float] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            now = time.time()
            for run, row in sorted((data.get("runs") or {}).items(), key=lambda item: float(item[1].get("at", 0))):
                if now - float(row.get("at", 0)) <= self.MAX_AGE:
                    self.runs[str(run)] = (float(row["seconds"]), float(row["usd"]))
                    self.stamps[str(run)] = float(row["at"])
        except (OSError, ValueError, KeyError, TypeError, AttributeError):  # a damaged file is a fresh ledger, not a crash of every take
            self.runs, self.stamps = {}, {}

    def _save(self) -> None:
        if self.path is None:
            return
        data = {"runs": {run: {"seconds": s, "usd": u, "at": self.stamps.get(run, time.time())} for run, (s, u) in self.runs.items()}}
        tmp = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".ledger-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.path)
            tmp = None
        except OSError:
            pass  # the count of this process still holds
        finally:
            if tmp is not None:
                Path(tmp).unlink(missing_ok=True)

    def spent(self, run: str) -> tuple[float, float]:
        return self.runs.get(run, (0.0, 0.0))

    def charge(self, run: str, seconds: float, budget_seconds: int, usd: float | None = 0.0, budget_usd: float = 0.0) -> tuple[float, float]:
        """Add a take to the run and return its totals (seconds, dollars). Raises ValueError (a message for the user) when a budget would be passed,
        or when a budget in dollars is set and the price of the take is unknown (usd=None); nothing is added then."""
        with self._lock:
            spent_s, spent_usd = self.runs.get(run, (0.0, 0.0))
            if budget_seconds > 0 and spent_s + seconds > budget_seconds:
                raise ValueError(f"API budget reached: {spent_s:g} s of video already asked for in this run, {seconds:g} s more would pass the {budget_seconds} s of MAX API SECONDS (Generator Select). Raise it, or set 0 for no limit.")
            if budget_usd > 0 and usd is None:
                raise ValueError(f"MAX API USD is ${budget_usd:g} but the price of this take cannot be read (jsonata-python is not installed, or the API node has no price badge), "
                                 "so the budget cannot be checked: install jsonata-python (requirements.txt), or set MAX API USD to 0 to count seconds only.")
            usd = usd or 0.0
            if budget_usd > 0 and spent_usd + usd > budget_usd:
                raise ValueError(f"API budget reached: about ${spent_usd:.2f} already asked for in this run, ${usd:.2f} more would pass the ${budget_usd:g} of MAX API USD (Generator Select). Raise it, or set 0 for no limit.")
            self.runs.pop(run, None)  # the run moves to the end: the runs dropped are the ones used least lately
            self.runs[run] = (spent_s + seconds, spent_usd + usd)
            self.stamps[run] = time.time()
            for old in list(self.runs)[: -self.KEEP]:
                del self.runs[old]
                self.stamps.pop(old, None)
            self._save()
            return self.runs[run]

    def reset(self, run: str | None = None) -> None:
        """Forget a run (all of them with None); the file goes when nothing is left."""
        with self._lock:
            if run is None:
                self.runs.clear()
                self.stamps.clear()
            else:
                self.runs.pop(run, None)
                self.stamps.pop(run, None)
            if not self.runs and self.path is not None:
                self.path.unlink(missing_ok=True)
            else:
                self._save()
