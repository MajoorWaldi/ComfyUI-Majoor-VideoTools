"""Build a shot list from a JSON edit plan instead of a video: the source becomes a generated placeholder video
(one card per shot, optional music as master audio), so every later node works on it like on real footage."""
import colorsys
import dataclasses
import json
import math
import re
import shutil
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor, ImageDraw

from ..adapters.ffmpeg import run_ffmpeg
from .beats import detect_beats, read_wav_mono
from .errors import MajoorError
from .card_text import draw_card_text
from .fx import SUB_MIN_FRAMES, describe_shot, parse_fx, split_frames
from .fingerprints import file_fingerprint, json_fingerprint
from .media_probe import probe
from .models import SCHEMA_VERSION, Detection, ShotList
from .paths import ProjectStore
from .scene_detection import _with_thumbnail, build_shots, build_source, persist_manifest

ASPECTS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1)}
PROFILES = ("none", "minimax_h3")
SNAP_MODES = ("off", "half_beat", "beat", "bar")
H3_MIN_FRAMES = 124
H3_STEP = 17  # valid lengths are 17k + 5
MIN_SHOT_FRAMES = 6
MAX_SHOTS = 150  # the placeholder video is one ffmpeg command with an input per shot: Windows refuses a command line much longer than that
MAX_SECONDS = 3600
TEMPLATE_VERSION = "3"
_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")
# rectangles as fractions of the frame: x, y, width, height
LAYOUTS = {
    "full": (0, 0, 1, 1), "left": (0, 0, 0.5, 1), "right": (0.5, 0, 0.5, 1), "top": (0, 0, 1, 0.5), "bottom": (0, 0.5, 1, 0.5),
    "top_left": (0, 0, 0.5, 0.5), "top_right": (0.5, 0, 0.5, 0.5), "bottom_left": (0, 0.5, 0.5, 0.5), "bottom_right": (0.5, 0.5, 0.5, 0.5),
    "center": (0.2, 0.2, 0.6, 0.6), "pip": (0.62, 0.62, 0.34, 0.34),
}


@dataclass(frozen=True)
class Layer:
    rect: tuple[float, float, float, float]
    color: str
    opacity: float


@dataclass(frozen=True)
class PlanShot:
    shot_id: str
    frames: int
    prompt: str
    image_prompt: str
    notes: str
    color: str = ""
    layers: tuple[Layer, ...] = ()
    fx: dict = field(default_factory=dict)  # post effects applied by Shot Assemble (see core/fx.py)


@dataclass(frozen=True)
class Plan:
    title: str
    fps: Fraction
    width: int
    height: int
    shots: tuple[PlanShot, ...]


def generation_frames(target_frames: int, profile: str) -> int:
    """Frames to ask a generator for so that trimming to target_frames is possible."""
    if profile == "minimax_h3":
        return max(H3_MIN_FRAMES, 5 + H3_STEP * math.ceil(max(target_frames - 5, 0) / H3_STEP))
    return target_frames


def parse_duration(value, fps: Fraction) -> int:
    """12.5 / '2.5' / '2.5s' = seconds; '60f' = frames; 'mm:ss.s' and 'hh:mm:ss.s' = timecodes."""
    if isinstance(value, bool) or value is None:
        raise ValueError("missing duration")
    if isinstance(value, (int, float)):
        seconds = Fraction(str(value))
    else:
        text = str(value).strip().lower().replace(" ", "")
        if text.endswith(("frames", "frame", "f")):
            return int(text.rstrip("framesf"))
        seconds = Fraction(0)
        for part in text.removesuffix("s").split(":"):
            seconds = seconds * 60 + Fraction(part)
    return int(round(seconds * fps))


def _json_text(text: str) -> str:
    """LLMs often wrap JSON in Markdown fences or add a sentence around it."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith(("{", "[")):
        openers = [(text.index(c), c) for c in "{[" if c in text]
        if openers:
            start, opener = min(openers)
            closer = "}" if opener == "{" else "]"
            if closer in text[start:]:
                text = text[start : text.rindex(closer) + 1]
    return text


def _layers(row: dict, sid: str) -> tuple[Layer, ...]:
    items = row.get("layers", [])
    if not isinstance(items, list):
        raise MajoorError(f"{sid}: layers must be a list")
    layers = []
    for n, item in enumerate(items, start=1):
        where = f"{sid} layer {n}"
        if not isinstance(item, dict):
            raise MajoorError(f"{where} must be an object")
        if "rect" in item:
            try:
                x, y, w, h = (float(v) for v in item["rect"])
            except (TypeError, ValueError):
                raise MajoorError(f"{where}: rect must be [x, y, width, height] as fractions of the frame") from None
        else:
            name = str(item.get("layout", "full"))
            if name not in LAYOUTS:
                raise MajoorError(f"{where}: unknown layout '{name}'. Available: {list(LAYOUTS)}")
            x, y, w, h = LAYOUTS[name]
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x + 1e-9 and 0 < h <= 1 - y + 1e-9):
            raise MajoorError(f"{where}: the rectangle must stay inside the frame (fractions between 0 and 1)")
        opacity = float(item.get("opacity", 1.0))
        if not 0 <= opacity <= 1:
            raise MajoorError(f"{where}: opacity must be between 0 and 1")
        color = str(item.get("color", "white"))
        _rgb(color, where)
        layers.append(Layer((x, y, w, h), color, opacity))
    return tuple(layers)


def _find_shots(data):
    """Accept a bare list of shots, or the list under a common alternative key, as LLMs vary."""
    if isinstance(data, list):
        return {"shots": data}
    if isinstance(data, dict) and not isinstance(data.get("shots"), list):
        for key in ("timeline", "scenes", "plan", "edit", "sequence", "clips", "storyboard"):
            value = data.get(key)
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return {**data, "shots": value}
            if isinstance(value, dict) and isinstance(value.get("shots"), list):
                return {**data, **value}
    return data


def parse_plan(text: str, fps: float, aspect_ratio: str, resolution: int) -> Plan:
    received = text.strip()[:200]
    try:
        data = json.loads(_json_text(text))
    except json.JSONDecodeError as e:
        raise MajoorError(f"Plan is not valid JSON: {e}. The node received: {received!r}") from e
    data = _find_shots(data)
    if not isinstance(data, dict) or not isinstance(data.get("shots"), list) or not data["shots"]:
        raise MajoorError(f'Plan must be a JSON object with a non-empty "shots" list. The node received: {received!r}')
    try:
        rate = Fraction(str(data.get("fps", fps))).limit_denominator(1001)
    except (ValueError, ZeroDivisionError):
        raise MajoorError(f"fps '{data.get('fps')}' is not a number") from None
    if not 1 <= rate <= 240:
        raise MajoorError("fps must be between 1 and 240")
    aspect = str(data.get("aspect_ratio", aspect_ratio))
    if aspect not in ASPECTS:  # an LLM writes "2.39:1" or "vertical": the setting of the node is used
        aspect = aspect_ratio
    if aspect not in ASPECTS:
        raise MajoorError(f"aspect_ratio '{aspect}' is not supported. Available: {list(ASPECTS)}")
    aw, ah = ASPECTS[aspect]
    try:
        long_side = int(data.get("resolution", resolution))
    except (ValueError, TypeError):
        raise MajoorError(f"resolution '{data.get('resolution')}' is not a number") from None
    if not 64 <= long_side <= 4096:
        raise MajoorError("resolution (the longest side of the placeholder video) must be between 64 and 4096")
    scale = long_side / max(aw, ah)
    width, height = (max(int(aw * scale) // 2 * 2, 2), max(int(ah * scale) // 2 * 2, 2))

    shots, seen = [], set()
    for i, row in enumerate(data["shots"], start=1):
        if not isinstance(row, dict):
            raise MajoorError(f"shot #{i} must be an object")
        sid = str(row.get("id", row.get("shot_id", f"SHOT_{i:03d}")))
        if not _ID.fullmatch(sid) or sid in seen:
            raise MajoorError(f"shot #{i}: invalid or duplicate id '{sid}' (letters, digits, _ and - only)")
        seen.add(sid)
        raw = next((row[k] for k in ("duration", "duration_seconds", "seconds") if k in row), None)
        fx = parse_fx(row, sid, rate, parse_duration)
        try:
            if "duration_frames" in row:
                frames = int(row["duration_frames"])
            elif raw is None and fx.get("sub_cuts"):  # no duration: the sub-cuts make it
                frames = sum(c["weight"] for c in fx["sub_cuts"])
            else:
                frames = parse_duration(raw, rate)
        except (ValueError, ZeroDivisionError, TypeError):
            raise MajoorError(f"{sid}: cannot read the duration (use seconds, '60f' or a timecode)") from None
        if frames < 1:
            raise MajoorError(f"{sid}: duration must be at least one frame")
        color = str(row.get("color", "")).strip()
        try:
            if color:
                _rgb(color, sid)
        except MajoorError:
            color = ""  # the color only codes the timeline by role: 'none' or 'transparent' from an LLM is no reason to stop
        shots.append(PlanShot(sid, frames, str(row.get("prompt", row.get("video_prompt", ""))).strip(), str(row.get("image_prompt", "")).strip(), str(row.get("notes", "")).strip(), color, _layers(row, sid), fx))
    if len(shots) > MAX_SHOTS:
        raise MajoorError(f"{len(shots)} shots: a timeline holds at most {MAX_SHOTS}. Use fewer, longer shots and put the quick cuts in sub_cuts (or cut the music every bar instead of every beat).")
    if sum(s.frames for s in shots) > MAX_SECONDS * rate:
        raise MajoorError(f"The edit is longer than {MAX_SECONDS // 60} minutes.")
    return Plan(str(data.get("title", "")).strip(), rate, width, height, tuple(shots))


def snap_boundaries(durations: list[int], grid: list[int], warnings: list[str], ids: list[str], label: str = "beat", min_frames: int = MIN_SHOT_FRAMES) -> list[int]:
    """Move each internal cut to the nearest grid frame while keeping every shot at least min_frames long."""
    bounds = np.cumsum(durations).tolist()
    total = bounds[-1]
    snapped = []
    previous = 0
    for i, cut in enumerate(bounds[:-1]):
        target = min(grid, key=lambda g: abs(g - cut), default=cut)
        upper = bounds[i + 1] - min_frames if i + 1 < len(bounds) - 1 else total - min_frames
        if previous + min_frames <= target <= upper:
            if target != cut:
                warnings.append(f"Cut after {ids[i]} moved {target - cut:+d} frames to the {label}")
            cut = target
        else:
            warnings.append(f"Cut after {ids[i]} not moved: the {label} would make a shot shorter than {min_frames} frames")
        snapped.append(cut)
        previous = cut
    edges = [0, *snapped, total]
    return [b - a for a, b in zip(edges, edges[1:])]


def _rgb(color: str, where: str) -> tuple[int, int, int]:
    try:
        return ImageColor.getrgb(color)[:3]
    except ValueError:
        raise MajoorError(f"{where}: unknown color '{color}' (use a CSS name such as 'yellow' or a hex value such as '#ffd400')") from None


def _slate(plan: Plan, shot: PlanShot, tint: tuple[int, int, int], card: str | None = None) -> Image.Image:
    """A card: the shot's color (or an automatic tint), with its layers drawn over it, and, with `card`, the brief of the shot written on it."""
    size = (plan.width, plan.height)
    background = _rgb(shot.color, shot.shot_id) if shot.color else tint
    image = Image.new("RGBA", size, background + (255,))
    for n, layer in enumerate(shot.layers, start=1):
        x, y, w, h = layer.rect
        box = [round(plan.width * x), round(plan.height * y), round(plan.width * (x + w)) - 1, round(plan.height * (y + h)) - 1]
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle(box, fill=_rgb(layer.color, f"{shot.shot_id} layer {n}") + (round(255 * layer.opacity),))
        image = Image.alpha_composite(image, overlay)
    image = image.convert("RGB")
    if card is not None:
        head, _, rest = card.partition("\n")
        draw_card_text(image, [(head, 1.5, True), (rest, 1.0, False), ("PROMPT" if shot.prompt else "", 0.9, True), (shot.prompt, 1.0, False)])
    return image


def _render_source(store: ProjectStore, plan: Plan, durations: list[int], audio: Path | None, out: Path, cards: list[str] | None = None) -> None:
    slates = store.resolve("cache/slates")
    slates.mkdir(parents=True, exist_ok=True)
    fps = f"{plan.fps.numerator}/{plan.fps.denominator}"
    cmd = ["-y"]
    filters = []
    for i, (shot, frames) in enumerate(zip(plan.shots, durations)):
        hue = (i * 0.137) % 1.0
        tint = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.45, 0.32))
        png = slates / f"{shot.shot_id}.png"
        _slate(plan, shot, tint, cards[i] if cards else None).save(png)
        # a looped still limited to frames + 2, then trimmed to exactly `frames`
        cmd += ["-loop", "1", "-framerate", fps, "-t", f"{float((frames + 2) / plan.fps):.6f}", "-i", str(png)]
        filters.append(f"[{i}:v]format=yuv420p,setpts=PTS-STARTPTS,trim=end_frame={frames},setpts=PTS-STARTPTS[v{i}]")
    n = len(plan.shots)
    total = sum(durations)
    filters.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,setpts=N/({fps}*TB),fps={fps}[v]")
    seconds = float(Fraction(total) / plan.fps)
    maps = ["-map", "[v]"]
    if audio is not None:
        cmd += ["-i", str(audio)]
        filters.append(f"[{n}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={seconds:.6f}[a]")
        maps += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    script = store.resolve("logs/template_filter.txt")
    script.write_text(";\n".join(filters), encoding="utf-8")
    tmp = out.with_name(out.stem + ".partial.mp4")
    run_ffmpeg([*cmd, "-filter_complex_script", str(script), *maps, "-fps_mode", "passthrough", "-c:v", "libx264", "-crf", "16", "-preset", "veryfast",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-t", f"{seconds:.6f}", str(tmp)])
    tmp.replace(out)


def _shot_fx(fx: dict, start: int, frames: int, grid: list[int]) -> dict:
    """The effects stored in the manifest: sub-cuts get their final length in frames (the weights fit the shot, then snap to the grid)."""
    subs = fx.get("sub_cuts")
    if not subs:
        return fx
    lengths = split_frames(frames, [c["weight"] for c in subs], SUB_MIN_FRAMES)
    subs = subs[: len(lengths)]
    local = [g - start for g in grid if 0 < g - start < frames]
    if local and len(lengths) > 1:
        lengths = snap_boundaries(lengths, local, [], [f"cut {i}" for i in range(len(lengths))], "half beat", SUB_MIN_FRAMES)
    return {**fx, "sub_cuts": [{k: v for k, v in c.items() if k != "weight"} | {"frames": n} for c, n in zip(subs, lengths)]}


def _check_sources(shots, warnings: list[str]) -> None:
    """A surimpression or a split screen shows the take of a shot: an id the plan does not have is replaced by the shot itself, with a warning."""
    known = {s.shot_id for s in shots}

    def fix(entry: dict, shot_id: str) -> None:
        if entry["source"] != "self" and entry["source"] not in known:
            warnings.append(f"{shot_id}: '{entry['source']}' in an overlay or a split is not a shot of the plan, the shot itself is used")
            entry["source"] = "self"

    for shot in shots:
        for holder in [shot.fx, *(shot.fx.get("sub_cuts") or [])]:
            for layer in holder.get("overlay") or []:
                fix(layer, shot.shot_id)
            for panel in (holder.get("split") or {}).get("panels", []):
                fix(panel, shot.shot_id)


def _card_texts(plan: Plan, durations: list[int], grid: list[int]) -> list[str]:
    """What is written on each card: its place, role, transition and cuts (the same brief Select Shot gives)."""
    rate = float(plan.fps)
    texts, start = [], 0
    for spec, frames in zip(plan.shots, durations):
        fx = _shot_fx(spec.fx, start, frames, grid) if spec.fx else {}
        texts.append(describe_shot(spec.shot_id, start / rate, frames / rate, frames, {"notes": spec.notes, "fx": fx}, rate)[1])
        start += frames
    return texts


def create_template(
    plan_text: str,
    store_root: Path,
    *,
    fps: float,
    aspect_ratio: str,
    resolution: int,
    profile: str = "none",
    audio_wav: Path | None = None,
    cut_snap: str = "off",
    bpm: float = 0.0,
    thumbnails: bool = True,
    card_text: bool = True,
) -> ShotList:
    if profile not in PROFILES:
        raise MajoorError(f"generation_profile '{profile}' is not supported. Available: {list(PROFILES)}")
    if cut_snap not in SNAP_MODES:
        raise MajoorError(f"cut_snap '{cut_snap}' is not supported. Available: {list(SNAP_MODES)}")
    plan = parse_plan(plan_text, fps, aspect_ratio, resolution)
    audio_fp = file_fingerprint(audio_wav) if audio_wav else ""
    options = {"profile": profile, "snap": cut_snap if audio_wav else "off", "bpm": round(bpm, 3), "card_text": card_text}
    key = json_fingerprint([TEMPLATE_VERSION, dataclasses.asdict(plan) | {"fps": str(plan.fps)}, audio_fp, options])
    store = ProjectStore(store_root, "p_" + key[:12])

    durations = [s.frames for s in plan.shots]
    warnings: list[str] = []
    detected_bpm = 0.0
    snapping = audio_wav is not None and cut_snap != "off" and len(durations) > 1
    sub_grid: list[int] = []
    if audio_wav is not None and cut_snap != "off" and len(durations) > 1:
        samples, rate = read_wav_mono(audio_wav)
        detected_bpm, beats = detect_beats(samples, rate, bpm)
        half = np.sort(np.concatenate([beats, (beats[:-1] + beats[1:]) / 2]))  # beats and the offbeats between them
        on_grid = {"bar": beats[::4], "beat": beats, "half_beat": half}[cut_snap]
        grid = [round(float(t) * float(plan.fps)) for t in on_grid]
        sub_grid = [round(float(t) * float(plan.fps)) for t in half]  # sub-cuts always snap to half beats
        durations = snap_boundaries(durations, grid, warnings, [s.shot_id for s in plan.shots], cut_snap)
        warnings.insert(0, f"Tempo {detected_bpm:.1f} BPM ({'given' if bpm > 0 else 'detected'}), cuts snapped to the {cut_snap}")

    _check_sources(plan.shots, warnings)
    with store.lock():
        source_path = store.dir / "sources" / "source.mp4"
        music = None
        if audio_wav is not None:
            music = store.dir / "sources" / "music.wav"
            if not music.exists():
                shutil.copy2(audio_wav, music)
        total = sum(durations)
        reusable = False
        if source_path.exists():
            existing = probe(source_path, with_packets=False)
            reusable = existing.frame_count == total and existing.has_audio == (music is not None)
        if not reusable:
            _render_source(store, plan, durations, music, source_path, _card_texts(plan, durations, sub_grid if snapping else []) if card_text else None)
        info = probe(source_path)
        if info.frame_count != total:
            raise MajoorError(f"Template video has {info.frame_count} frames, expected {total}")

        source = dataclasses.replace(build_source(info, store.rel(source_path), file_fingerprint(source_path)), template=True)
        edges = np.cumsum(durations).tolist()[:-1]
        shots = []
        for shot, spec, frames in zip(build_shots(source, info, edges), plan.shots, durations):
            data = {"prompt": spec.prompt, "image_prompt": spec.image_prompt, "notes": spec.notes, "generation_frames": generation_frames(frames, profile)}
            if spec.fx:
                data["fx"] = _shot_fx(spec.fx, shot.start_frame, frames, sub_grid if snapping else [])
            shots.append(dataclasses.replace(shot, shot_id=spec.shot_id, source_media_ref=source.uri, plan=data))
        if thumbnails:
            shots = [_with_thumbnail(store, source_path, source, info, s, False) for s in shots]
        shot_list = ShotList(
            project_id=store.dir.name,
            source=source,
            detection=Detection("template", 0.0, MIN_SHOT_FRAMES, key[:16], tuple(warnings)),
            shots=tuple(shots),
            schema_version=SCHEMA_VERSION,
        )
        shot_list.validate()
        persist_manifest(store, shot_list, only_if_absent=True)
    return shot_list
