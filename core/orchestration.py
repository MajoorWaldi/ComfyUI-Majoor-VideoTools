"""Running an edit from one prompt as a chain of named stages, and the retake loop for a take that fails its check.

This module only sequences work: each stage is a function you give it (a planner call, a ComfyUI graph, an assembly), so it
needs no GPU and runs the same in tests. A stage may need earlier stages; if one of them failed, the stages that need it are
skipped, never run on missing input. A stage can be retried; an optional stage may fail without stopping the run."""
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .errors import MajoorError
from .lipsync import needs_retake, next_seed

STAGE_ORDER = ("plan", "casting", "character_sheets", "shots", "lipsync", "assemble")
STAGE_NEEDS = {"plan": (), "casting": ("plan",), "character_sheets": ("casting",), "shots": ("plan",),
               "lipsync": ("shots",), "assemble": ("shots",)}
OPTIONAL = {"casting", "character_sheets", "lipsync"}


class Cancelled(MajoorError):
    pass


class StageFailed(MajoorError):
    """A required stage failed. `report` holds every stage as far as the run went; the stage's own error is the cause."""

    def __init__(self, name: str, message: str, report):
        super().__init__(f"Stage '{name}' failed: {message}")
        self.stage, self.report = name, report


@dataclass(frozen=True)
class Stage:
    name: str
    run: Callable[[dict], object]
    needs: tuple[str, ...] = ()
    retries: int = 0
    optional: bool = False


@dataclass
class StageResult:
    name: str
    status: str = "pending"   # done | failed | skipped
    attempts: int = 0
    seconds: float = 0.0
    error: str = ""


@dataclass
class Report:
    stages: list[StageResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.status in ("done", "skipped") for s in self.stages) and not any(s.status == "failed" for s in self.stages)

    def get(self, name: str) -> StageResult:
        return next(s for s in self.stages if s.name == name)


def build_stages(handlers: dict[str, Callable[[dict], object]], retries: dict[str, int] | None = None) -> list[Stage]:
    """The stages of an edit made from a prompt, in order, for the handlers given. `plan` and `shots` are required;
    a stage left out (no casting, no lip sync) is simply absent and nothing waits for it."""
    unknown = set(handlers) - set(STAGE_ORDER)
    if unknown:
        raise MajoorError(f"Unknown stages: {sorted(unknown)}. Known: {list(STAGE_ORDER)}")
    for required in ("plan", "shots"):
        if required not in handlers:
            raise MajoorError(f"The '{required}' stage is required")
    stages = []
    for name in STAGE_ORDER:
        if name in handlers:
            needs = tuple(n for n in STAGE_NEEDS[name] if n in handlers)
            stages.append(Stage(name, handlers[name], needs, (retries or {}).get(name, 0), name in OPTIONAL))
    return stages


def _validate(stages: list[Stage]) -> None:
    seen: set[str] = set()
    for stage in stages:
        if stage.name in seen:
            raise MajoorError(f"Stage '{stage.name}' appears twice")
        missing = [n for n in stage.needs if n not in seen]
        if missing:
            raise MajoorError(f"Stage '{stage.name}' needs {missing}, which must come before it")
        seen.add(stage.name)


def run_pipeline(stages: list[Stage], context: dict | None = None, *, cancelled: Callable[[], bool] | None = None,
                 on_event: Callable[[str, StageResult], None] | None = None) -> tuple[dict, Report]:
    """Run the stages in order. Each result is stored in the context under the stage name, for the stages after it.

    A failed required stage ends the run with `StageFailed` (the later stages are marked skipped in its `report`, the stage's
    own error is its `__cause__`); a failed optional stage is reported and the stages that need it are skipped. `cancelled()` is asked before each stage."""
    _validate(stages)
    context = {} if context is None else context
    report = Report([StageResult(s.name) for s in stages])
    emit = on_event or (lambda event, result: None)
    for stage, result in zip(stages, report.stages):
        if cancelled and cancelled():
            raise Cancelled("The run was cancelled")
        blocked = [n for n in stage.needs if report.get(n).status != "done"]
        if blocked:
            result.status, result.error = "skipped", f"needs {blocked}, which did not finish"
            emit("skipped", result)
            continue
        emit("start", result)
        started = time.monotonic()
        error = None
        for attempt in range(1, stage.retries + 2):
            result.attempts = attempt
            try:
                context[stage.name] = stage.run(context)
                error = None
                break
            except Cancelled:
                raise
            except Exception as caught:  # a stage is any callable: whatever it raises is that stage's failure
                error = caught
                if cancelled and cancelled():
                    raise Cancelled("The run was cancelled") from caught
        result.seconds = round(time.monotonic() - started, 3)
        if error is None:
            result.status = "done"
            emit("done", result)
            continue
        result.status, result.error = "failed", str(error) or type(error).__name__
        emit("failed", result)
        if not stage.optional:
            for later in report.stages[report.stages.index(result) + 1:]:
                later.status, later.error = "skipped", f"'{stage.name}' failed"
            raise StageFailed(stage.name, result.error, report) from error
    return context, report


def retake_loop(generate: Callable[[int], object], check: Callable[[object], dict], seed: int, *, max_attempts: int = 3):
    """Make a take, check it, and make it again with another seed while it fails and tries remain.

    Returns (take, report, history). When every try fails, the take with the best score is kept, not simply the last one.
    A take that could not be measured is kept at once. `history` is [{attempt, seed, report}]."""
    if max_attempts < 1:
        raise MajoorError("max_attempts must be at least 1")
    history, best = [], None
    for attempt in range(1, max_attempts + 1):
        take = generate(seed)
        report = check(take)
        history.append({"attempt": attempt, "seed": seed, "report": report})
        score = report.get("score")
        if best is None or (score if score is not None else -1) > (best[1].get("score") if best[1].get("score") is not None else -1):
            best = (take, report)
        if not needs_retake(report, attempt, max_attempts):
            if report.get("status") != "fail":
                return take, report, history
            break
        seed = next_seed(seed, attempt)
    return best[0], best[1], history
