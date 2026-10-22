"""Post effects of a timeline plan, applied by Shot Assemble on the generated takes (the generator only makes plain takes).

Per shot, in the JSON plan: speed, speed_ramp, zoom, focus, flip, look, transition, text, and sub_cuts (several cuts out of ONE
generated take, each with its own speed / zoom / focus / flip / look / transition). Parsing gives a plain dict, stored in the
shot's plan; the ffmpeg filters are built here from that dict."""
import hashlib
import json
import os
import re
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

from .errors import MajoorError

LOOKS = ("none", "mono", "contrast", "negative")
# default length in frames of each transition into a shot (at the start of the shot)
TRANSITIONS = {"cut": 0, "flash": 4, "flash_black": 4, "fade_black": 6, "fade_white": 10, "whip": 4, "whip_v": 4, "blur": 4, "punch": 6, "glitch": 6, "shake": 8, "strobe": 6, "invert": 3}
# the names an LLM writes for them
TRANSITION_ALIASES = {"flash_white": "flash", "white_flash": "flash", "black_flash": "flash_black", "dip_to_black": "fade_black", "fade": "fade_black", "fade_in": "fade_black", "dip_to_white": "fade_white",
                      "whip_pan": "whip", "whip_horizontal": "whip", "whip_vertical": "whip_v", "defocus": "blur", "dissolve": "blur", "cross_dissolve": "blur", "crossfade": "blur",
                      "zoom": "punch", "punch_in": "punch", "rgb_split": "glitch", "glitch_rgb": "glitch", "camera_shake": "shake", "negative": "invert", "flicker": "strobe"}
MAX_SUB_CUTS = 24
SUB_MIN_FRAMES = 3
SPEED = (0.1, 8.0)
ZOOM = (1.0, 4.0)
BLENDS = {"normal": "normal", "screen": "screen", "multiply": "multiply", "overlay": "overlay", "add": "addition", "lighten": "lighten", "darken": "darken",
          "difference": "difference", "softlight": "softlight"}
SPLIT_LAYOUTS = {"left_right": 2, "top_bottom": 2, "columns_3": 3, "rows_3": 3, "grid_4": 4}  # layout -> number of panels
MAX_OVERLAYS = 3
COMMON = ("speed", "speed_ramp", "zoom", "focus", "flip", "look", "overlay", "split")
# anchor of the text block (x, y as fractions of the frame, the block is placed inside a 5 % margin)
TEXT_POSITIONS = {
    "center": (0.5, 0.5), "top": (0.5, 0.0), "bottom": (0.5, 1.0), "left": (0.0, 0.5), "right": (1.0, 0.5),
    "top_left": (0.0, 0.0), "top_right": (1.0, 0.0), "bottom_left": (0.0, 1.0), "bottom_right": (1.0, 1.0),
}


def _number(value, name: str, where: str, lo: float, hi: float, strict: bool = False) -> float:
    if isinstance(value, bool):
        raise MajoorError(f"{where}: {name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise MajoorError(f"{where}: {name} must be a number") from None
    if not lo <= number <= hi:
        if strict:
            raise MajoorError(f"{where}: {name} must be between {lo:g} and {hi:g}")
        return min(max(number, lo), hi)  # an LLM writes zoom 0.8 or speed 12: the nearest value that the effect accepts
    return number


def _pair(value, name: str, where: str, lo: float, hi: float) -> list[float]:
    if isinstance(value, (list, tuple)):
        if len(value) != 2:
            raise MajoorError(f"{where}: {name} must be one number or [from, to]")
        return [_number(v, name, where, lo, hi) for v in value]
    number = _number(value, name, where, lo, hi)
    return [number, number]


def _color(value, where: str, fallback: str | None = None) -> str:
    """A CSS color name or hex. A color of text that is not one ('none', 'transparent'...) takes the fallback instead of stopping the plan."""
    try:
        ImageColor.getrgb(str(value))
    except ValueError:
        if fallback is not None:
            return fallback
        raise MajoorError(f"{where}: unknown color '{value}' (use a CSS name such as 'white' or a hex value such as '#ffd400')") from None
    return str(value)


def _transition(value, where: str, fps: Fraction) -> dict | None:
    kind, frames = value, None
    if isinstance(value, dict):
        kind = value.get("type", "cut")
        if "frames" in value:
            frames = int(_number(value["frames"], "transition frames", where, 1, 48))
        elif "duration" in value:
            frames = round(_number(value["duration"], "transition duration", where, 0.02, 2.0) * float(fps))
    kind = str(kind).strip().lower().replace(" ", "_").replace("-", "_")
    kind = TRANSITION_ALIASES.get(kind, kind)
    if kind not in TRANSITIONS or kind == "cut":  # a name that no transition has is a plain cut: the plan still runs
        return None
    return {"type": kind, "frames": max(1, frames or TRANSITIONS[kind])}


_SOURCE = re.compile(r"self|[A-Za-z0-9_-]{1,40}")


def _layer_spec(item, where: str, *, overlay: bool) -> dict:
    """One layer of a surimpression or one panel of a split screen: a take (this shot's or another shot's) with its own crop and look."""
    if isinstance(item, str):
        item = {"source": item}
    if not isinstance(item, dict):
        raise MajoorError(f'{where} must be an object like {{"source": "SHOT_003"}}')
    source = str(item.get("source", "self"))
    if not _SOURCE.fullmatch(source):
        raise MajoorError(f"{where}: invalid source '{source}' (a shot id, or self)")
    out: dict = {"source": source, "offset": _number(item.get("offset", 0.0), "offset", where, 0.0, 600.0)}
    if "zoom" in item:
        out["zoom"] = _pair(item["zoom"], "zoom", where, *ZOOM)
    if "focus" in item:
        out["focus"] = _pair(item["focus"], "focus", where, 0.0, 1.0)
    if "flip" in item:
        out["flip"] = bool(item["flip"])
    if "look" in item:
        look = str(item["look"])
        if look not in LOOKS:
            raise MajoorError(f"{where}: unknown look '{look}'. Available: {list(LOOKS)}")
        out["look"] = look
    if overlay:
        out["opacity"] = _number(item.get("opacity", 0.5), "opacity", where, 0.0, 1.0)
        blend = str(item.get("blend", "screen"))
        if blend not in BLENDS:
            raise MajoorError(f"{where}: unknown blend '{blend}'. Available: {list(BLENDS)}")
        out["blend"] = blend
        out["scale"] = _number(item.get("scale", 1.0), "scale", where, 0.1, 1.0)
        position = str(item.get("position", "center"))
        if position not in TEXT_POSITIONS:
            raise MajoorError(f"{where}: unknown position '{position}'. Available: {list(TEXT_POSITIONS)}")
        out["position"] = position
    return out


def _composite(item: dict, where: str) -> dict:
    """overlay (a surimpression: other takes blended over the picture) and split (the picture replaced by panels)."""
    out: dict = {}
    if item.get("overlay"):
        layers = item["overlay"] if isinstance(item["overlay"], list) else [item["overlay"]]
        if len(layers) > MAX_OVERLAYS:
            raise MajoorError(f"{where}: at most {MAX_OVERLAYS} overlays")
        out["overlay"] = [_layer_spec(layer, f"{where} overlay {n}", overlay=True) for n, layer in enumerate(layers, start=1)]
    if "overlay" in item and not item["overlay"]:
        out["overlay"] = None
    if item.get("split"):
        split = item["split"] if isinstance(item["split"], dict) else {"layout": item["split"]}
        layout = str(split.get("layout", "left_right"))
        if layout not in SPLIT_LAYOUTS:
            raise MajoorError(f"{where}: unknown split layout '{layout}'. Available: {list(SPLIT_LAYOUTS)}")
        panels = split.get("panels") or []
        if not isinstance(panels, list) or len(panels) > SPLIT_LAYOUTS[layout]:
            raise MajoorError(f"{where}: the split '{layout}' has {SPLIT_LAYOUTS[layout]} panels, panels must be a list of at most that many")
        parsed = [_layer_spec(panel, f"{where} split panel {n}", overlay=False) for n, panel in enumerate(panels, start=1)]
        while len(parsed) < SPLIT_LAYOUTS[layout]:  # the panels left out show this shot
            parsed.append({"source": "self", "offset": 0.0})
        out["split"] = {"layout": layout, "panels": parsed}
    if "split" in item and not item["split"]:
        out["split"] = None
    return out


def _common(item: dict, where: str, fps: Fraction) -> dict:
    """The effects that exist both on a shot and on one of its sub-cuts. Only the keys that were given are kept."""
    out: dict = {}
    if "speed" in item:
        out["speed"] = _number(item["speed"], "speed", where, *SPEED)
    if "speed_ramp" in item:
        ramp = item["speed_ramp"]
        if not isinstance(ramp, (list, tuple)) or len(ramp) != 2:
            raise MajoorError(f"{where}: speed_ramp must be [start_speed, end_speed]")
        out["speed_ramp"] = [_number(v, "speed_ramp", where, *SPEED) for v in ramp]
    if "zoom" in item:
        out["zoom"] = _pair(item["zoom"], "zoom", where, *ZOOM)
    if "focus" in item:
        out["focus"] = _pair(item["focus"], "focus", where, 0.0, 1.0)
    if "flip" in item:
        out["flip"] = bool(item["flip"])
    if "look" in item:
        look = str(item["look"])
        if look not in LOOKS:
            raise MajoorError(f"{where}: unknown look '{look}'. Available: {list(LOOKS)}")
        out["look"] = look
    transition = item.get("transition", item.get("transition_in"))
    if transition is not None:
        out["transition"] = _transition(transition, where, fps)
    out.update(_composite(item, where))
    return out


def _text(item, where: str) -> dict:
    if isinstance(item, str):
        item = {"content": item}
    if not isinstance(item, dict) or not str(item.get("content", "")).strip():
        raise MajoorError(f'{where}: text must be a string or {{"content": "..."}}')
    position = str(item.get("position", "center"))
    if position not in TEXT_POSITIONS:
        raise MajoorError(f"{where}: unknown text position '{position}'. Available: {list(TEXT_POSITIONS)}")
    spec = {
        "content": str(item["content"]).strip()[:120],
        "position": position,
        "size": _number(item.get("size", 0.08), "text size", where, 0.02, 0.6),
        "color": _color(item.get("color", "white"), where, "white"),
        "repeat": int(_number(item.get("repeat", 1), "text repeat", where, 1, 12)),
        "rotate": _number(item.get("rotate", 0), "text rotate", where, -45, 45),
    }
    if item.get("background") and _color(item["background"], where, "") != "":
        spec["background"] = str(item["background"])
    return spec


def parse_fx(row: dict, sid: str, fps: Fraction, parse_duration) -> dict:
    """Read the effect fields of a plan shot. Returns {} when the shot has none."""
    fx = _common(row, sid, fps)
    if row.get("refs"):  # the pictures of the character, product... used by this shot (<Picture 1>, <Picture 2>...), for workflows that wire several references
        refs = row["refs"] if isinstance(row["refs"], list) else [row["refs"]]
        fx["refs"] = sorted({int(_number(r, "refs", sid, 1, 9, strict=True)) for r in refs})
    if "text" in row and row["text"]:
        fx["text"] = _text(row["text"], sid)
    cuts = row.get("sub_cuts")
    if cuts is None:
        return fx
    if not isinstance(cuts, list) or not cuts:
        raise MajoorError(f"{sid}: sub_cuts must be a non-empty list")
    if len(cuts) > MAX_SUB_CUTS:
        raise MajoorError(f"{sid}: at most {MAX_SUB_CUTS} sub_cuts per shot")
    subs = []
    for n, cut in enumerate(cuts, start=1):
        where = f"{sid} sub_cut {n}"
        if not isinstance(cut, dict):
            raise MajoorError(f"{where} must be an object")
        raw = next((cut[k] for k in ("duration", "duration_seconds", "seconds") if k in cut), None)
        try:
            weight = int(cut["duration_frames"]) if "duration_frames" in cut else parse_duration(raw, fps)
        except (ValueError, ZeroDivisionError, TypeError):
            raise MajoorError(f"{where}: cannot read the duration (use seconds, '6f' or a timecode)") from None
        if weight < 1:
            raise MajoorError(f"{where}: duration must be at least one frame")
        sub = {"weight": weight, **_common(cut, where, fps)}
        if "start" in cut and cut["start"] is not None:
            sub["start"] = _number(cut["start"], "start", where, 0.0, 600.0)
        subs.append(sub)
    fx["sub_cuts"] = subs
    return fx


def _fmt(value) -> str:
    return f"{value:g}" if isinstance(value, (int, float)) else str(value)


def _effects_words(spec: dict) -> list[str]:
    words = []
    if "speed_ramp" in spec:
        words.append(f"speed {_fmt(spec['speed_ramp'][0])}→{_fmt(spec['speed_ramp'][1])}")
    elif spec.get("speed", 1.0) != 1.0:
        words.append(f"speed {_fmt(spec['speed'])}")
    z = spec.get("zoom")
    if z and (z[0] != 1.0 or z[1] != 1.0):
        words.append(f"zoom {_fmt(z[0])}" if z[0] == z[1] else f"zoom {_fmt(z[0])}→{_fmt(z[1])}")
    if spec.get("flip"):
        words.append("flip")
    if spec.get("look", "none") != "none":
        words.append(f"look {spec['look']}")
    split = spec.get("split")
    if split:
        words.append(f"split {split['layout']} (" + ", ".join(p["source"] for p in split["panels"]) + ")")
    for layer in spec.get("overlay") or []:
        words.append(f"overlay {layer['source']} {layer['blend']} {layer['opacity']:g}" + (f" at {layer['scale']:g} {layer['position']}" if layer["scale"] < 1 else ""))
    return words


def describe_fx(fx: dict | None, fps: float, frames: int) -> tuple[dict, str]:
    """What a shot of a timeline plan asks of the edit: its transition, the cuts inside it and their effects, as data and in words."""
    fx = fx or {}
    seconds = lambda n: round(n / fps, 3)  # noqa: E731
    transition = fx.get("transition")
    info: dict = {"fps": fps, "duration_s": seconds(frames), "transition": ({"type": transition["type"], "frames": transition["frames"], "seconds": seconds(transition["frames"])} if transition else None)}
    for key in ("speed", "speed_ramp", "zoom", "focus", "flip", "look", "overlay", "split", "refs", "text"):
        if key in fx:
            info[key] = fx[key]
    subs = fx.get("sub_cuts") or []
    cuts = []
    for i, c in enumerate(subs, start=1):
        cut = {"index": i, "duration_s": seconds(c["frames"])}
        cut.update({k: v for k, v in c.items() if k in ("start", "speed", "speed_ramp", "zoom", "focus", "flip", "look", "transition", "overlay", "split") and v is not None})
        cuts.append(cut)
    info["cut_count"] = max(len(cuts), 1)
    info["sub_cuts"] = cuts
    lines = [f"transition in: {transition['type']} ({transition['frames']} frames)" if transition else "transition in: cut"]
    if cuts:
        parts = []
        for c in subs:
            extra = _effects_words({k: c[k] for k in ("speed", "speed_ramp", "zoom", "flip", "look", "overlay", "split") if k in c})
            t = c.get("transition")
            if t:
                extra.append(f"transition {t['type']}")
            parts.append(f"{c['frames'] / fps:.2f}s" + (f" ({', '.join(extra)})" if extra else ""))
        lines.append(f"cuts ({len(cuts)}): " + " / ".join(parts))
    else:
        lines.append("cuts: 1 (the whole shot)")
    shot_words = _effects_words(fx)
    if fx.get("text"):
        shot_words.append(f"text '{fx['text']['content']}' ({fx['text']['position']})")
    if fx.get("refs"):
        shot_words.append("pictures " + ", ".join(f"<Picture {r}>" for r in fx["refs"]))
    if shot_words:
        lines.append("shot: " + ", ".join(shot_words))
    return info, "\n".join(lines)


def describe_shot(shot_id: str, start: float, duration: float, frames: int, plan: dict | None, fps: float) -> tuple[dict, str]:
    """A shot as one brief: where it sits, its role (the notes of the plan), its transition, the cuts inside it, its effects. Works for any shot:
    one cut from a video has no plan and just gets its place and length."""
    plan = plan or {}
    info, effects = describe_fx(plan.get("fx"), fps, frames)
    notes = str(plan.get("notes") or "").strip()
    info.update({"shot_id": shot_id, "start_s": round(start, 3), "end_s": round(start + duration, 3), "notes": notes, "frames": frames})
    head = f"{shot_id} · {start:.2f}-{start + duration:.2f}s · {duration:.2f}s · {frames} frames"
    return info, "\n".join([head, *([f"role: {notes}"] if notes else []), effects])


def split_frames(total: int, weights: list[int], min_frames: int = 1) -> list[int]:
    """Share `total` frames in proportion to the weights (largest remainder), each part at least min_frames when that is possible."""
    weights = weights[: max(total, 1)]
    n = len(weights)
    floor = min_frames if total >= n * min_frames else 1
    raw = [total * w / sum(weights) for w in weights]
    parts = [int(r) for r in raw]
    for i in sorted(range(n), key=lambda i: raw[i] - int(raw[i]), reverse=True)[: total - sum(parts)]:
        parts[i] += 1
    for i in range(n):  # lift the short parts, taking the frames from the longest ones
        while parts[i] < floor:
            donor = max(range(n), key=lambda j: parts[j])
            if parts[donor] <= floor:
                break
            parts[donor] -= 1
            parts[i] += 1
    return parts


def merged(fx: dict, sub: dict | None) -> dict:
    """The effects of one cut: the shot's own, overridden by the sub-cut's."""
    spec = {k: fx[k] for k in COMMON if k in fx}
    for k in COMMON:
        if sub and k in sub:
            spec[k] = sub[k]
    if sub and "speed" in sub and "speed_ramp" not in sub:
        spec.pop("speed_ramp", None)
    if sub and "speed_ramp" in sub and "speed" not in sub:
        spec.pop("speed", None)
    return spec


def source_seconds(spec: dict, out_seconds: float) -> float:
    """How much of the take this cut consumes."""
    if "speed_ramp" in spec:
        return out_seconds * sum(spec["speed_ramp"]) / 2
    return out_seconds * spec.get("speed", 1.0)


def transition_filters(transition: dict | None, frames: int, fps: Fraction, width: int, height: int, *, include_punch: bool = False) -> list[str]:
    """The filters of the transition into a cut (flash, fade, whip blur...). A punch is a zoom: in a plain cut it is folded into the zoom of the chain,
    here (include_punch) it is its own zoom, for a picture that was composed of several takes."""
    if transition is None:
        return []
    kind, n = transition["type"], transition["frames"]
    f: list[str] = []
    if kind in ("flash", "flash_black", "fade_black", "fade_white"):
        f.append(f"fade=t=in:st=0:d={n / float(fps):.4f}:color={'white' if kind in ('flash', 'fade_white') else 'black'}")
    elif kind == "strobe":
        f.append(f"eq=brightness='if(lt(n,{n}),0.7*mod(n,2),0)':eval=frame")
    elif kind == "invert":
        f.append(f"negate=enable='lt(n,{n})'")
    elif kind == "glitch":
        f.append(f"chromashift=crh=-14:crv=3:cbh=14:cbv=-3:edge=smear:enable='lt(n,{n})'")
        f.append(f"noise=alls=40:allf=t:enable='lt(n,{n})'")
    elif kind == "shake":
        f.append(f"scale=w='trunc(iw*(1+0.1*lt(n,{n}))/2)*2':h='trunc(ih*(1+0.1*lt(n,{n}))/2)*2':eval=frame:flags=bicubic")
        f.append(f"crop={width}:{height}:x='(iw-{width})/2*(1+if(lt(n,{n}),random(0)*2-1,0))':y='(ih-{height})/2*(1+if(lt(n,{n}),random(1)*2-1,0))',setsar=1")
    elif kind in ("whip", "whip_v", "blur"):
        first, second = max(n // 2, 1), n
        for lo, hi, scale in ((0, first, 0.08), (first, second, 0.03)):
            sigma = max(width if kind != "whip_v" else height, 1) * scale
            axes = {"whip": f"sigma={sigma:.1f}:sigmaV=0.1", "whip_v": f"sigma=0.1:sigmaV={sigma:.1f}", "blur": f"sigma={sigma:.1f}"}[kind]
            f.append(f"gblur={axes}:steps=2:enable='between(n,{lo},{hi - 1})'")
    elif kind == "punch" and include_punch:
        zoom = f"(1+0.35*pow(max(0,1-n/{n}),2))"
        f.append(f"scale=w='trunc(iw*{zoom}/2)*2':h='trunc(ih*{zoom}/2)*2':eval=frame:flags=bicubic")
        f.append(f"crop={width}:{height}:x='(iw-{width})*0.5':y='(ih-{height})*0.5',setsar=1")
    return f


def segment_chain(spec: dict, frames: int, fps: Fraction, width: int, height: int, transition: dict | None, apply_transition: bool = True) -> str:
    """ffmpeg filters of one cut, applied after the frame has been scaled to width x height. apply_transition=False leaves the transition to the caller."""
    if not apply_transition:
        transition = None
    rate = f"{fps.numerator}/{fps.denominator}"
    seconds = frames / float(fps)
    f = []
    if "speed_ramp" in spec:
        a, b = spec["speed_ramp"]
        k = (b - a) / seconds
        if abs(k) < 1e-6:
            f.append(f"setpts=PTS/{a:.6f}")
        else:  # source time u = a*t + k*t^2/2, so the output time of source time u is the root below
            f.append(f"setpts='(sqrt(max(0,{a:.6f}*{a:.6f}+2*{k:.6f}*PTS*TB))-{a:.6f})/{k:.6f}/TB'")
    elif abs(spec.get("speed", 1.0) - 1.0) > 1e-6:
        f.append(f"setpts=PTS/{spec['speed']:.6f}")
    f += [f"fps={rate}", "tpad=stop_mode=clone:stop=-1", f"trim=end_frame={frames}", "setpts=PTS-STARTPTS"]

    if spec.get("flip"):
        f.append("hflip")
    z0, z1 = spec.get("zoom", [1.0, 1.0])
    punch = transition is not None and transition["type"] == "punch"
    if z0 != 1.0 or z1 != 1.0 or punch:
        zoom = f"({z0:.4f}+({z1:.4f}-{z0:.4f})*min(1,n/{max(frames - 1, 1)}))"
        if punch:
            zoom = f"({zoom}*(1+0.35*pow(max(0,1-n/{transition['frames']}),2)))"
        fx_, fy_ = spec.get("focus", [0.5, 0.5])
        f.append(f"scale=w='trunc(iw*{zoom}/2)*2':h='trunc(ih*{zoom}/2)*2':eval=frame:flags=bicubic")
        f.append(f"crop={width}:{height}:x='(iw-{width})*{fx_:.4f}':y='(ih-{height})*{fy_:.4f}',setsar=1")  # the rounded scale changes the SAR
    look = spec.get("look", "none")
    if look == "mono":
        f.append("hue=s=0")
    elif look == "contrast":
        f.append("eq=contrast=1.35:saturation=1.15")
    elif look == "negative":
        f.append("negate")

    f += transition_filters(transition, frames, fps, width, height)
    return ",".join(f)


def _anchor(position: str) -> tuple[str, str]:
    ax, ay = TEXT_POSITIONS[position]
    return (f"(main_w-overlay_w)*{ax:g}+main_w*{0.04 * (1 - 2 * ax):g}", f"(main_h-overlay_h)*{ay:g}+main_h*{0.04 * (1 - 2 * ay):g}")


def overlay_filters(base: str, layer: str, out: str, spec: dict, tag: str) -> list[str]:
    """Blend a layer over the picture (a surimpression), or, with scale < 1, place a smaller transparent copy of it (picture in picture)."""
    mode, opacity, scale = BLENDS[spec["blend"]], spec["opacity"], spec["scale"]
    if scale >= 0.999:
        return [f"[{base}][{layer}]blend=all_mode={mode}:all_opacity={opacity:g},format=yuv420p[{out}]"]
    x, y = _anchor(spec["position"])
    return [f"[{layer}]scale=trunc(iw*{scale:g}/2)*2:trunc(ih*{scale:g}/2)*2,format=yuva420p,colorchannelmixer=aa={opacity:g}[{tag}s]",
            f"[{base}][{tag}s]overlay=x='{x}':y='{y}':format=auto,format=yuv420p[{out}]"]


def split_filters(panels: list[str], layout: str, out: str, width: int, height: int, tag: str) -> list[str]:
    """Panels side by side: each full-frame picture is covered-and-cropped to its cell, the cells are stacked back to the size of the frame."""
    half_w, half_h = (width // 2) // 2 * 2, (height // 2) // 2 * 2
    third_w, third_h = (width // 3) // 2 * 2, (height // 3) // 2 * 2
    cell = {"left_right": (half_w, height), "top_bottom": (width, half_h), "columns_3": (third_w, height), "rows_3": (width, third_h), "grid_4": (half_w, half_h)}[layout]
    lines = [f"[{p}]scale={cell[0]}:{cell[1]}:force_original_aspect_ratio=increase:flags=bicubic,crop={cell[0]}:{cell[1]},setsar=1[{tag}c{k}]" for k, p in enumerate(panels)]
    cells = "".join(f"[{tag}c{k}]" for k in range(len(panels)))
    stack = {"left_right": "hstack=inputs=2", "top_bottom": "vstack=inputs=2", "columns_3": "hstack=inputs=3", "rows_3": "vstack=inputs=3",
             "grid_4": "xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0"}[layout]
    lines.append(f"{cells}{stack},scale={width}:{height}:flags=bicubic,setsar=1,format=yuv420p[{out}]")
    return lines


def _font(px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [os.environ.get("MAJOOR_FONT", ""), "impact.ttf", "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
    for name in candidates:
        if name:
            try:
                return ImageFont.truetype(name, px)
            except OSError:
                continue
    return ImageFont.load_default(size=px)


def render_text(spec: dict, width: int, height: int, store_dir: Path) -> Path:
    """A transparent PNG of the text overlay, cached by content. No text engine of ffmpeg is needed."""
    key = hashlib.sha1(json.dumps([spec, width, height], sort_keys=True).encode()).hexdigest()[:16]
    out = store_dir / f"{key}.png"
    if out.exists():
        return out
    px = max(int(height * spec["size"]), 8)
    font = _font(px)
    text = spec["content"].upper()
    rows = spec["repeat"]
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
    tw, th = right - left, bottom - top
    gap = int(px * 0.12)
    pad = int(px * 0.25) if spec.get("background") else 0
    bw, bh = tw + 2 * pad, rows * th + (rows - 1) * gap + 2 * pad
    block = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(block)
    if spec.get("background"):
        draw.rectangle([0, 0, bw - 1, bh - 1], fill=ImageColor.getrgb(spec["background"])[:3] + (255,))
    for r in range(rows):
        draw.text((pad - left, pad - top + r * (th + gap)), text, font=font, fill=ImageColor.getrgb(spec["color"])[:3] + (255,))
    if spec["rotate"]:
        block = block.rotate(spec["rotate"], expand=True, resample=Image.BICUBIC)
    margin = int(min(width, height) * 0.05)
    ax, ay = TEXT_POSITIONS[spec["position"]]
    x = round(margin + ax * (width - 2 * margin - block.width))
    y = round(margin + ay * (height - 2 * margin - block.height))
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(block, (max(x, 0), max(y, 0))) if block.width <= width and block.height <= height else canvas.alpha_composite(
        block.crop((0, 0, min(block.width, width), min(block.height, height))), (0, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out
