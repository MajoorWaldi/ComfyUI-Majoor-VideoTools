"""Edit plans for Create Timeline that are not written by hand: cut on the bars/beats of a music, or on the cuts of a video.

Both return the same JSON plan that Timeline accepts from a text (see core/template.py), so every later step is shared."""
import json
import math
from fractions import Fraction
from pathlib import Path

import numpy as np

from .beats import detect_beats
from .errors import MajoorError
from .fx import SUB_MIN_FRAMES,split_frames
from .media_probe import probe
from .scene_detection import merge_short_shots
from .template import MIN_SHOT_FRAMES, _find_shots, _json_text, parse_duration, parse_plan

CUT_EVERY = ("half_beat", "beat", "2_beats", "bar", "2_bars", "4_bars")
VIDEO_MODES = ("adaptive", "content", "threshold_fade")
COMMON_FPS = (23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0)


def _steps(cut_every: str, beats_per_bar: int) -> float:
    steps = {"half_beat": 0.5, "beat": 1, "2_beats": 2, "bar": beats_per_bar, "2_bars": 2 * beats_per_bar, "4_bars": 4 * beats_per_bar}
    if cut_every not in steps:
        raise MajoorError(f"cut_every '{cut_every}' is not supported. Available: {list(CUT_EVERY)}")
    return steps[cut_every]


def _pick(candidates: list[int], count: int) -> list[int]:
    """`count` cut frames spread evenly over the candidates."""
    if count >= len(candidates):
        return candidates
    spots = np.linspace(0, len(candidates) - 1, count).round().astype(int)
    return [candidates[i] for i in dict.fromkeys(spots.tolist())]


def plan_from_music(samples: np.ndarray, rate: int, *, cut_every: str = "bar", duration: float = 0.0, bpm: float = 0.0, beats_per_bar: int = 4,
                    downbeat: int = 0, shots: int = 0, fps: float = 24.0) -> tuple[dict, dict]:
    """Shots whose cuts fall on the music's bars or beats. Returns (plan, info)."""
    step = _steps(cut_every, beats_per_bar)
    if not 0 <= downbeat < beats_per_bar:
        raise MajoorError(f"downbeat must be between 0 and {beats_per_bar - 1}")
    found, beats = detect_beats(samples, rate, bpm)
    length = duration if duration > 0 else len(samples) / rate
    if length <= 0:
        raise MajoorError("The music is empty")
    if found <= 0:
        total = max(round(length * fps), 1)
        count = min(max(shots, 1), total)
        lengths = [total // count + (i < total % count) for i in range(count)]
        return {'fps': fps, 'shots': [{'duration_frames': n, 'prompt': '', 'notes': 'No reliable musical pulse; narrative timing'} for n in lengths]}, {
            'bpm': None, 'beat_times': [], 'beats_per_bar': beats_per_bar, 'length': length, 'timing_source': 'none',
            'warnings': ['No reliable pulse; no measured beat grid was imposed']}
    period = 60.0 / found
    first = float(beats[0]) if len(beats) else 0.0
    first += downbeat * period
    grid = first + np.arange(0, int((length - first) / (period * step)) + 2) * period * step
    total = max(round(length * fps), 1)
    cuts: list[int] = []
    for t in grid:  # a cut needs room on both sides
        f = round(float(t) * fps)
        if MIN_SHOT_FRAMES <= f <= total - MIN_SHOT_FRAMES and (not cuts or f - cuts[-1] >= MIN_SHOT_FRAMES):
            cuts.append(f)
    warnings = []
    if shots > 0 and shots - 1 > len(cuts):
        warnings.append(f"Only {len(cuts) + 1} shots fit on the {cut_every} grid ({shots} asked)")
    bounds = [0, *cuts, total]
    beat_frames = period * fps
    pieces = [(a, b) for a, b in zip(bounds, bounds[1:])]
    if shots > 0:  # fewer takes than grid steps: neighbouring steps become the sub-cuts of one shot, so a cut does not cost a generation
        count = min(shots, len(pieces))
        sizes = [len(pieces) // count + (1 if i < len(pieces) % count else 0) for i in range(count)]
        groups = [pieces[sum(sizes[:i]):sum(sizes[:i + 1])] for i in range(count)]
    else:
        groups = [[p] for p in pieces]
    rows = []
    for group in groups:
        index = round((group[0][0] - first * fps) / beat_frames)  # beats since the first (down)beat
        where = f"bar {index // beats_per_bar + 1} beat {index % beats_per_bar + 1}" if index >= 0 else "before the first beat"
        row = {"duration_frames": group[-1][1] - group[0][0], "prompt": "", "notes": where}
        if len(group) > 1:
            row["sub_cuts"] = [{"duration_frames": b - a} for a, b in group]
        rows.append(row)
    info = {"bpm": round(float(found), 2), "beat_times": [float(t) for t in beats], "beats_per_bar": beats_per_bar, "length": length, "warnings": warnings}
    return {"fps": fps, "shots": rows}, info


def group_cuts(lengths: list[int], min_shot_frames: int) -> list[list[int]]:
    """Group consecutive cut lengths (frames) into shots of at least min_shot_frames: bursts of short cuts become one shot with sub-cuts."""
    groups: list[list[int]] = []
    current: list[int] = []
    for n in lengths:
        current.append(n)
        if sum(current) >= min_shot_frames:
            groups.append(current)
            current = []
    if current:
        if groups:
            groups[-1] += current  # a short tail joins the last shot
        else:
            groups.append(current)
    return groups


def plan_from_video(path: Path, *, detection_mode: str = "adaptive", sensitivity: float = 0.5, min_cut_seconds: float = 0.1,
                    min_shot_seconds: float = 1.0, fps: float = 0.0) -> tuple[dict, dict]:
    """One shot per group of cuts of the video; the original cuts of a group become the shot's sub-cuts. Returns (plan, info)."""
    if detection_mode not in VIDEO_MODES:
        raise MajoorError(f"detection_mode '{detection_mode}' is not supported. Available: {list(VIDEO_MODES)}")
    from ..adapters import pyscenedetect  # optional dependency

    info = probe(path, with_packets=False)
    source_fps = float(info.fps)
    rate = fps if fps > 0 else min(COMMON_FPS, key=lambda c: abs(c - source_fps))
    total = max(round(float(info.duration) * rate), 1)
    times = pyscenedetect.detect_cut_times(path, detection_mode, sensitivity, max(round(min_cut_seconds * source_fps), 1))
    warnings: list[str] = []
    cuts = sorted({round(t * rate) for t in times} - {0})
    cuts = merge_short_shots([c for c in cuts if c < total], total, max(round(min_cut_seconds * rate), SUB_MIN_FRAMES), warnings)
    bounds = [0, *cuts, total]
    lengths = [b - a for a, b in zip(bounds, bounds[1:])]
    groups = group_cuts(lengths, max(round(min_shot_seconds * rate), MIN_SHOT_FRAMES))
    rows, at = [], 0
    for group in groups:
        row = {"duration_frames": sum(group), "prompt": "", "notes": f"reference {at / rate:.2f}-{(at + sum(group)) / rate:.2f}s, {len(group)} cut{'s' if len(group) > 1 else ''}"}
        if len(group) > 1:
            row["sub_cuts"] = [{"duration_frames": n} for n in group]
        rows.append(row)
        at += sum(group)
    w, h = info.display_size
    ratio = w / h
    aspect = "16:9" if ratio > 1.3 else "9:16" if ratio < 0.75 else "1:1"
    detail = {"cuts": len(lengths), "aspect_ratio": aspect, "fps": rate, "warnings": warnings}
    return {"fps": rate, "aspect_ratio": aspect, "shots": rows}, detail


def plan_from_shots(shot_list) -> dict:
    """The shots of a detected video as a rhythm skeleton, at the fps of the video: cuts too short for a shot are grouped into one shot with sub-cuts."""
    src = shot_list.source
    fps = src.fps_num / src.fps_den
    rows, at = [], 0
    for group in group_cuts([s.end_frame_exclusive - s.start_frame for s in shot_list.shots], MIN_SHOT_FRAMES):
        row = {"duration_frames": sum(group), "prompt": "", "notes": f"reference {at / fps:.2f}-{(at + sum(group)) / fps:.2f}s, {len(group)} cut{'s' if len(group) > 1 else ''}"}
        if len(group) > 1:
            row["sub_cuts"] = [{"duration_frames": n} for n in group]
        rows.append(row)
        at += sum(group)
    wide, high = (src.height, src.width) if src.rotation % 180 else (src.width, src.height)
    return {"fps": fps, "aspect_ratio": "16:9" if wide > high * 1.3 else "9:16" if wide * 1.3 < high else "1:1", "shots": rows}


def rhythm_text(plan_text: str, fps: float, extra: str = "") -> str:
    """The rhythm of a plan in words, to hand to the LLM that writes the prompts: shot ids, durations and the cuts inside each shot."""
    plan = parse_plan(plan_text, fps, "16:9", 64)
    rate = float(plan.fps)
    lines = []
    at = 0
    cuts = 0
    for shot in plan.shots:
        subs = shot.fx.get("sub_cuts") or []
        inside = [c["weight"] for c in subs] or [shot.frames]
        cuts += len(inside)
        lines.append(f"{shot.shot_id}  {at / rate:.2f}-{(at + shot.frames) / rate:.2f}s  ({shot.frames / rate:.2f}s)  cuts: " + " / ".join(f"{n / rate:.2f}" for n in inside)
                     + (f"  [{shot.notes}]" if shot.notes else ""))
        at += shot.frames
    seconds = at / rate
    head = f"EDIT RHYTHM: {len(plan.shots)} shots, {cuts} cuts, {seconds:.2f} s ({cuts / seconds:.1f} cuts/s), {rate:g} fps" + (f", {extra}" if extra else "")
    return "\n".join([head, *lines])


def plan_text(plan: dict) -> str:
    return json.dumps(plan, indent=2)


def _aspect_of(plan) -> str:
    return "16:9" if plan.width > plan.height else "9:16" if plan.width < plan.height else "1:1"


def with_size(text: str, width: int, height: int) -> str:
    """The plan with a size in pixels, which replaces its aspect_ratio and resolution. A text that is not JSON is given back: parse_plan reports it."""
    try:
        data = json.loads(_json_text(text))
    except json.JSONDecodeError:
        return text
    if isinstance(data, list):
        data = {"shots": data}
    return json.dumps({**data, "width": width, "height": height}) if isinstance(data, dict) else text


def fit_duration(text: str, seconds: float, fps: float) -> str:
    """The plan with every shot (and its sub-cuts) stretched or shrunk by the same factor so that the shots add up to `seconds`: an LLM seldom adds up to the length that was asked for. A text that is not JSON is given back: parse_plan reports it."""
    try:
        data = _find_shots(json.loads(_json_text(text)))
    except json.JSONDecodeError:
        return text
    rate = Fraction(str(fps)).limit_denominator(1001)
    shots = [s for s in data.get("shots", []) if isinstance(s, dict)] if isinstance(data, dict) else []
    try:
        lengths = [parse_duration(s["duration"], rate) if "duration" in s else sum(parse_duration(c["duration"], rate) for c in s.get("sub_cuts", [])) for s in shots]
    except (KeyError, ValueError, TypeError):
        return text
    if not shots or sum(lengths) <= 0:
        return text
    factor = seconds * float(rate) / sum(lengths)
    target=round(seconds*float(rate))
    if target<len(shots):
        raise MajoorError('The requested duration cannot give every shot at least one frame')
    fitted=split_frames(target,lengths)
    for shot, frames, count in zip(shots, lengths, fitted):
        shot["duration"] = f"{count}f"
        for cut in shot.get("sub_cuts", []):
            if isinstance(cut, dict) and "duration" in cut:
                cut["duration"] = f"{max(round(parse_duration(cut['duration'], rate) * factor), 1)}f"
    return json.dumps(data)


BURST_WORDS = ("detail", "macro", "close", "texture", "cap", "edge", "refraction")


def protected_action(shot):
    if shot.get("dialogue") or (isinstance(shot.get("story"), dict) and shot["story"].get("dialogue")):
        return True
    if shot.get('protect_action') is True or (isinstance(shot.get('story'), dict) and shot['story'].get('protect_action') is True):
        return True
    words = ' '.join(str(shot.get(k, '')) for k in ('prompt', 'notes', 'story')).casefold()
    return any(term in words for term in (
        'continuous', 'uninterrupted', 'unbroken', 'no cuts', 'do not interrupt',
        'remove the cap', 'removes the cap', 'cap removal', 'atomizer', 'spray',
        'action continue', 'sans coupe', 'sans interruption', 'retire le bouchon', 'pulvÃ©r'))


def edit_segment_frames(shots, fps=24):
    """Actual edited segments, including independently generated short inserts."""
    rate=Fraction(str(fps))
    def frames(row):
        return int(row['duration_frames']) if 'duration_frames' in row else parse_duration(row.get('duration'),rate)
    return [frames(cut) for shot in shots for cut in (shot.get('sub_cuts') or [shot])]


def is_dense_edit(shots, fps=24):
    try:
        frames=edit_segment_frames(shots,fps)
    except (KeyError,ValueError,TypeError):
        return False
    return bool(frames) and len(frames)>=max(8,math.ceil(sum(frames)/fps*1.2)) and sum(n<=fps for n in frames)>=len(frames)/2


def ensure_burst(text: str, density: str) -> str:
    """Add bounded editorial accents to eligible takes; preserve existing cuts and protected actions.
    High density considers the whole edit, not merely the presence of one sub-cut.
    It never invents a new generated viewpoint, mirrors a label or adds generations.
    """
    if density not in ("medium", "high"):
        return text
    try:
        data = _find_shots(json.loads(_json_text(text)))
    except json.JSONDecodeError:
        return text
    shots = [s for s in data.get("shots", []) if isinstance(s, dict)] if isinstance(data, dict) else []
    if len(shots) < 3 or (density=='medium' and any(s.get('sub_cuts') for s in shots)) or (density=='high' and is_dense_edit(shots)):
        return text
    seconds = []
    for shot in shots:
        try:
            seconds.append(float(shot['duration_frames'])/24 if 'duration_frames' in shot else float(parse_duration(shot["duration"], Fraction(24))) / 24.0)
        except (KeyError, ValueError, TypeError):
            return text
    inner = [i for i in range(1, len(shots) - 1) if seconds[i] >= 1.2 and not shots[i].get('sub_cuts') and not protected_action(shots[i])]
    if not inner:
        return text
    ranked=sorted(inner,key=lambda i:(any(w in f"{shots[i].get('prompt','')} {shots[i].get('notes','')}".lower() for w in BURST_WORDS),seconds[i]),reverse=True)
    for pick in ranked[:3 if density=='high' else 1]:
        total=seconds[pick]
        if density == "high":
            cuts = [{"duration": 0.17}, {"duration": 0.17, "zoom": 1.7, "focus": [0.5, 0.3]}, {"duration": 0.17, "zoom": 2.4, "focus": [0.6, 0.5]}, {"duration": 0.17, "zoom": 1.5, "focus": [0.5, 0.5]}]
        else:
            cuts = [{"duration": 0.45}, {"duration": 0.45, "zoom": 1.8, "focus": [0.5, 0.35]}]
        rest = round(total - sum(c["duration"] for c in cuts), 3)
        shots[pick]["sub_cuts"] = [*cuts, {"duration": rest, "zoom": 1.3}]
        if 'duration_frames' not in shots[pick]:shots[pick]["duration"] = round(total, 3)
        if density=='medium' or is_dense_edit(shots):break
    return json.dumps(data)


def ensure_text(text: str, allowed: str) -> str:
    """The plan of an LLM with the words that the user asked for: when `allowed` is set and no shot has a text, the last shot gets it, in the middle of the safe area and fading in. A plan that has a text is left as it is."""
    allowed = allowed.strip()
    if not allowed:
        return text
    try:
        data = _find_shots(json.loads(_json_text(text)))
    except json.JSONDecodeError:
        return text
    shots = [s for s in data.get("shots", []) if isinstance(s, dict)] if isinstance(data, dict) else []
    if not shots or any(s.get("text") for s in shots):
        return text
    shots[-1]["text"] = {"content": allowed[:120], "position": "center", "size": 0.1, "animation": "fade"}
    return json.dumps(data)


def plan_to_dict(plan, aspect_ratio: str | None = None) -> dict:
    """A parsed Plan back to the JSON form Timeline reads (frames everywhere, effects as parsed)."""
    shots = []
    for s in plan.shots:
        row: dict = {"id": s.shot_id, "duration_frames": s.frames, "prompt": s.prompt, "image_prompt": s.image_prompt, "notes": s.notes}
        if s.story:
            row["story"] = dict(s.story)
        if s.motion:
            row['motion'] = s.motion
        if s.render_source and s.render_source['kind']!='generated':
            row['render_source']=dict(s.render_source)
        if s.color:
            row["color"] = s.color
        if s.location:
            row["location"] = s.location
        fx = dict(s.fx)
        subs = fx.pop("sub_cuts", None)
        row.update({k: v for k, v in fx.items() if v is not None})
        if subs:
            row["sub_cuts"] = [{"duration_frames": c["weight"], **{k: v for k, v in c.items() if k != "weight" and v is not None}} for c in subs]
        if s.layers:
            row["layers"] = [{"rect": list(layer.rect), "color": layer.color, "opacity": layer.opacity} for layer in s.layers]
        shots.append(row)
    return {"title": plan.title, "fps": float(plan.fps), "aspect_ratio": aspect_ratio or _aspect_of(plan), "resolution": max(plan.width, plan.height), "shots": shots}


def _effects_of(cut: dict) -> dict:
    return {k: v for k, v in cut.items() if k != "weight" and v is not None}


def _with_lengths(text: str) -> str:
    """The plan of a language model that only writes prompts and effects may leave the lengths out: give them a placeholder, the rhythm decides."""
    from .template import _find_shots

    try:
        data = _find_shots(json.loads(_json_text(text)))
    except json.JSONDecodeError:
        return text  # parse_plan reports it
    for shot in data.get("shots", []) if isinstance(data, dict) else []:
        if not isinstance(shot, dict):
            continue
        for cut in shot.get("sub_cuts") if isinstance(shot.get("sub_cuts"), list) else []:
            if isinstance(cut, dict) and not any(k in cut for k in ("duration", "duration_seconds", "seconds", "duration_frames")):
                cut["duration_frames"] = 1
        if not any(k in shot for k in ("duration", "duration_seconds", "seconds", "duration_frames")) and not shot.get("sub_cuts"):
            shot["duration_frames"] = 1
    return json.dumps(data)


def merge_plans(skeleton_text: str, plan_text_: str, fps: float, aspect_ratio: str, resolution: int) -> tuple[dict, list[str]]:
    """The rhythm of a skeleton (ids, durations, the cuts inside each shot) with the prompts and effects of another plan.

    A language model writes the prompts and the effects; the lengths come from a reliable source (a music, a video). A shot takes the
    prompt and effects of the plan's shot with the same id (or at the same position); its sub-cuts take their effects by position."""
    from .template import _find_shots, _json_text  # the plan readers

    skeleton = parse_plan(skeleton_text, fps, aspect_ratio, resolution)
    llm = parse_plan(_with_lengths(plan_text_), fps, aspect_ratio, resolution)
    raw = _find_shots(json.loads(_json_text(skeleton_text)))
    aspect = str(raw.get("aspect_ratio", aspect_ratio)) if isinstance(raw, dict) else aspect_ratio
    warnings: list[str] = []
    by_id = {s.shot_id: s for s in llm.shots}
    rows = []
    for i, base in enumerate(skeleton.shots):
        src = by_id.get(base.shot_id) or (llm.shots[i] if i < len(llm.shots) else None)
        row: dict = {"id": base.shot_id, "duration_frames": base.frames, "prompt": "", "image_prompt": "", "notes": base.notes}
        base_subs = base.fx.get("sub_cuts") or []
        if src is None:
            warnings.append(f"{base.shot_id}: the plan has no shot for it, left without prompt")
            if base_subs:
                row["sub_cuts"] = [{"duration_frames": c["weight"]} for c in base_subs]
            rows.append(row)
            continue
        row["prompt"], row["image_prompt"] = src.prompt, src.image_prompt
        if src.story or base.story:
            row["story"] = dict(src.story or base.story)
        if src.motion or base.motion:
            row['motion'] = src.motion or base.motion
        if src.render_source and src.render_source['kind']!='generated':
            row['render_source']=dict(src.render_source)
        row["notes"] = " | ".join(x for x in (src.notes, base.notes) if x)
        if src.color:
            row["color"] = src.color
        if src.location:
            row["location"] = src.location
        row.update({k: v for k, v in src.fx.items() if k != "sub_cuts" and v is not None})
        src_subs = src.fx.get("sub_cuts") or []
        if base_subs:  # the cuts inside the shot belong to the rhythm
            row["sub_cuts"] = [{"duration_frames": c["weight"], **(_effects_of(src_subs[j]) if j < len(src_subs) else {})} for j, c in enumerate(base_subs)]
            if src_subs and len(src_subs) != len(base_subs):
                warnings.append(f"{base.shot_id}: {len(base_subs)} cuts in the rhythm, {len(src_subs)} in the plan; effects matched by position")
        elif src_subs:  # a rhythm without cuts inside (a music): the plan may add some
            row["sub_cuts"] = [{"duration_frames": c["weight"], **_effects_of(c)} for c in src_subs]
        rows.append(row)
    if len(llm.shots) > len(skeleton.shots):
        warnings.append(f"The plan has {len(llm.shots)} shots, the rhythm {len(skeleton.shots)}: the extra ones were ignored")
    return {"title": llm.title or skeleton.title, "fps": float(skeleton.fps), "aspect_ratio": aspect, "resolution": resolution, "shots": rows}, warnings
