"""Generator registry: what each video model can do, kept as one JSON file per model in the generators/ folder of the pack.

The pipeline asks a generator for a length and hands it references. What a model accepts (frame grid or whole seconds, how many
pictures, videos and audios, whether it makes its own sound) differs from one model to the next, so it is read here, never
hard-coded where a shot is planned. Adding a model is adding a file.

Fields of a file: id, kind (video), title, source (local | api), node (ComfyUI node), model (option of that node), family (h3 | seedance | wan | ltx: which request builder talks to it), cost (free | credits),
duration ({mode: frames_grid, min_frames, step, offset} or {mode: seconds, min, max, step, values?}),
inputs ({images, videos, audios: how many, null when unknown; first_frame, last_frame}), audio (native | none), prompt_skill, notes."""
import json
import math
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from .errors import MajoorError

GENERATORS = Path(__file__).resolve().parents[1] / "generators"
KINDS = ("video",)
SOURCES = ("local", "api")
_ID = re.compile(r"[a-z0-9_]{1,40}")


@dataclass(frozen=True)
class Generator:
    id: str
    kind: str
    title: str
    source: str
    node: str
    model: str
    family: str
    cost: str
    duration: dict
    inputs: dict
    audio: str
    prompt_skill: str
    notes: str

    @property
    def seconds_based(self) -> bool:
        return self.duration["mode"] == "seconds"

    def limit(self, what: str) -> int | None:
        """How many pictures / videos / audios it takes; None when unknown."""
        value = self.inputs.get(what)
        return None if value is None else int(value)


def _parse(path: Path) -> Generator:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise MajoorError(f"Generator '{path.stem}' is not valid JSON: {e}") from e
    try:
        gen = Generator(
            id=str(raw["id"]), kind=str(raw["kind"]), title=str(raw["title"]), source=str(raw["source"]), node=str(raw["node"]),
            model=str(raw.get("model", "")), family=str(raw.get("family", "")), cost=str(raw.get("cost", "free")), duration=dict(raw["duration"]), inputs=dict(raw.get("inputs", {})),
            audio=str(raw.get("audio", "none")), prompt_skill=str(raw.get("prompt_skill", "")), notes=str(raw.get("notes", "")),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise MajoorError(f"Generator '{path.stem}' is incomplete: {e!r}") from e
    if gen.id != path.stem or not _ID.fullmatch(gen.id):
        raise MajoorError(f"Generator file '{path.name}' must hold the id '{path.stem}' (lowercase letters, digits, underscore)")
    if gen.kind not in KINDS or gen.source not in SOURCES:
        raise MajoorError(f"Generator '{gen.id}': kind {gen.kind!r} or source {gen.source!r} unknown")
    mode = gen.duration.get("mode")
    if mode == "frames_grid":
        needed = ("min_frames", "step", "offset")
    elif mode == "seconds":
        needed = ("min", "max", "step")
    else:
        raise MajoorError(f"Generator '{gen.id}': duration mode {mode!r} unknown (frames_grid | seconds)")
    if any(k not in gen.duration for k in needed) or gen.duration["step"] <= 0:
        raise MajoorError(f"Generator '{gen.id}': duration needs {needed} with a step above 0")
    return gen


def list_generators(kind: str | None = None) -> list[str]:
    if not GENERATORS.is_dir():
        return []
    return sorted(p.stem for p in GENERATORS.glob("*.json") if kind is None or load_generator(p.stem).kind == kind)


def load_generator(generator_id: str) -> Generator:
    if not _ID.fullmatch(generator_id or ""):
        raise MajoorError(f"Invalid generator id {generator_id!r}")
    path = GENERATORS / f"{generator_id}.json"
    if not path.is_file():
        raise MajoorError(f"Unknown generator '{generator_id}'. Available: {list_generators()}")
    return _parse(path)


def _seconds_for(gen: Generator, target_frames: int, fps: Fraction | float) -> int:
    """Whole seconds to ask for: the length of the shot rounded up to what the model offers, never above its maximum."""
    need = max(1, math.ceil(target_frames / float(fps) - 1e-9))
    d = gen.duration
    values = d.get("values")
    if values:
        return next((int(v) for v in sorted(values) if v >= need), int(max(values)))
    step = int(d["step"])
    low = int(d["min"])
    return min(int(d["max"]), max(low, low + step * math.ceil((need - low) / step)))


def generation_frames_for(generator_id: str, target_frames: int, fps: Fraction | float | None = None) -> int:
    """Frames to ask the generator for so that trimming to target_frames is possible.
    A model that works in seconds needs the fps of the plan to turn them into frames."""
    gen = load_generator(generator_id)
    d = gen.duration
    if d["mode"] == "frames_grid":
        offset, step = int(d["offset"]), int(d["step"])
        return max(int(d["min_frames"]), offset + step * math.ceil(max(target_frames - offset, 0) / step))
    if not fps or float(fps) <= 0:
        raise MajoorError(f"Generator '{generator_id}' works in seconds: its generation_frames need the fps of the plan")
    return round(_seconds_for(gen, target_frames, fps) * float(fps))


def generation_seconds_for(generator_id: str, target_frames: int, fps: Fraction | float) -> float | None:
    """The exact length in seconds to request from a model that works in seconds; None for a frame-grid model."""
    gen = load_generator(generator_id)
    return float(_seconds_for(gen, target_frames, fps)) if gen.seconds_based else None


def check_shot(generator_id: str, shot_id: str, target_frames: int, fps: Fraction | float, images: int = 0, videos: int = 0, audios: int = 0) -> list[str]:
    """What the model cannot do for this shot: a length above its maximum, more references than it takes."""
    gen = load_generator(generator_id)
    problems = []
    if gen.seconds_based:
        need = target_frames / float(fps)
        top = max(gen.duration.get("values") or [gen.duration["max"]])
        if need > top + 1e-6:
            problems.append(f"{shot_id}: {need:.1f}s is longer than {gen.title} can make ({top}s); split the shot or take the first {top}s")
    for what, n in (("images", images), ("videos", videos), ("audios", audios)):
        cap = gen.limit(what)
        if cap is not None and n > cap:
            problems.append(f"{shot_id}: {n} reference {what} but {gen.title} takes {cap}")
    return problems


def describe(generator_id: str) -> dict:
    """The file as plain data, for the frontend."""
    gen = load_generator(generator_id)
    return {"id": gen.id, "kind": gen.kind, "title": gen.title, "source": gen.source, "node": gen.node, "model": gen.model, "family": gen.family, "cost": gen.cost,
            "duration": gen.duration, "inputs": gen.inputs, "audio": gen.audio, "prompt_skill": gen.prompt_skill, "notes": gen.notes}
