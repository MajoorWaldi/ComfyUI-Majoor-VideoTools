"""Motion graphics drawn over a video, from a JSON list of layers: animated texts, boxes and corner brackets, emojis, effects of the whole frame (chromatic aberration, glitch, grid,
dots, scanlines), an outline around the subject and points that follow something (a dot, a label, an emoji that track a point or the subject).

A generated take has no text: the titles, counters and frames of the source video are redrawn here, after the assembly, from a list that a person or an LLM writes
(the skill `overlay_reader` reads them from the frames of the source). The layer contract and mask/tracking preparation are shared with HyperFrames, which performs production composition.
Low-level raster helpers remain for compatibility; the former video renderer delegates to HyperFrames. Its local runtime is required; the subject mask (outline, effects on the subject or the background, anchors on the subject) comes from any segmentation node.

    {"layers": [
      {"type": "text", "content": "WHICH ONE?", "position": "top_left", "size": 0.07, "color": "#111", "start": "0%", "end": "40%", "animation": "typewriter", "out": "fade"},
      {"type": "outline", "color": "#ffffff", "width": 0.006, "style": "neon", "glow": 0.6},
      {"type": "effect", "kind": "chromatic", "amount": 0.5, "start": 1.2, "end": 1.6},
      {"type": "track", "anchor": "subject_top", "label": "LOOK 06", "emoji": "🔥", "shape": "ring", "line": true}]}

start and end are seconds or a percentage of the length of the video ("40%"); no end = until the last frame."""
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

from ..adapters.ffmpeg import CREATIONFLAGS, find_binary
from .errors import MajoorError
from .fx import TEXT_POSITIONS, _font
from .media_probe import probe
from .template import _json_text

TYPES = ("text", "box", "brackets", "emoji", "outline", "effect", "track", "vector")
ANIMATIONS = ("none", "fade", "pop", "slide_up", "slide_down", "slide_left", "slide_right", "typewriter", "glitch", "shake", "draw", "float", "words")
EFFECTS = ("chromatic", "glitch", "grid", "dots", "scanlines", "grain", "vignette", "light_leak", "pan", "roll", "handheld")
TARGETS = ("frame", "subject", "background")
OUTLINES = ("solid", "double", "dashed", "neon")
ANCHORS = ("subject_top", "subject_center", "subject_bottom", "subject_left", "subject_right")
SHAPES = ("none", "dot", "ring", "cross")
MAX_LAYERS = 120


def _number(value, name: str, where: str, lo: float, hi: float) -> float:
    """A value out of range is brought to the nearest accepted one: an LLM that writes size 0.9 should not stop the whole workflow."""
    try:
        return min(max(float(value), lo), hi)
    except (TypeError, ValueError):
        raise MajoorError(f"{where}: {name} must be a number, not {value!r}") from None


def _color(value, where: str, default: str) -> str:
    try:
        ImageColor.getrgb(str(value))
        return str(value)
    except ValueError:
        return default


def _time(value, name: str, where: str, length: float, default: float | None) -> float | None:
    """Seconds, or a percentage of the video ("40%")."""
    if value is None or value == "":
        return default
    if isinstance(value, str) and value.strip().endswith("%"):
        return _number(value.strip()[:-1], name, where, 0, 100) / 100 * length
    return _number(value, name, where, 0, max(length, 0.0))


def _choice(value, options: tuple, default: str) -> str:
    return str(value) if str(value) in options else default


def _point(value, where: str, default: list[float]) -> list[float]:
    if isinstance(value, list) and len(value) == 2:
        return [_number(value[0], "x", where, -1, 2), _number(value[1], "y", where, -1, 2)]
    return default


def parse_layers(text: str, length: float) -> list[dict]:
    """The layers of the JSON, checked and completed (times in seconds). `length` is the length of the video in seconds."""
    try:
        data = json.loads(_json_text(text))
    except json.JSONDecodeError as e:
        raise MajoorError(f"The layers are not valid JSON: {e}. The node received: {text.strip()[:200]!r}") from e
    if isinstance(data, dict):
        data = data.get("layers", [])
    if not isinstance(data, list):
        raise MajoorError('The layers must be a list, or {"layers": [...]}')
    if len(data) > MAX_LAYERS:
        raise MajoorError(f"{len(data)} layers: at most {MAX_LAYERS}")
    layers = []
    for i, row in enumerate(data, start=1):
        where = f"layer #{i}"
        if not isinstance(row, dict):
            raise MajoorError(f"{where} must be an object")
        kind = str(row.get("type", "text"))
        if kind in ('line', 'dot', 'ring'):
            if row.get('shape', kind) != kind:
                raise MajoorError(f'{where}: conflicting vector type and shape')
            row = {**row, 'type': 'vector', 'shape': kind}
            kind = 'vector'
        if kind not in TYPES:
            raise MajoorError(f"{where}: unknown type '{kind}'. Available: {list(TYPES)}")
        start = _time(row.get("start"), "start", where, length, 0.0)
        end = _time(row.get("end"), "end", where, length, None)
        if end is not None and end <= start:
            end = start + 0.2
        animation = _choice(row.get("animation", "none"), ANIMATIONS, "none")  # an LLM invents names: a layer without animation beats a stopped workflow
        layer = {"type": kind, "start": start, "end": end, "animation": animation, "out": "fade" if str(row.get("out", "none")) == "fade" else "none",
                 "in_time": _number(row.get("in_time", 0.25), "in_time", where, 0.05, 3.0), "opacity": _number(row.get("opacity", 1), "opacity", where, 0, 1),
                 "color": _color(row.get("color", "white"), where, "white"), "needs_mask": False}
        from .motion_scenes import transform
        if 'motion_from' in row or 'motion_to' in row:
            layer.update(motion_from=transform(row.get('motion_from', {})), motion_to=transform(row.get('motion_to', {})))
        layer['ease'] = _choice(row.get('ease','out'), ('out','smooth','linear','back'), 'out')
        if row.get('scene'): layer['scene']=str(row['scene'])[:80]
        if kind in ("text", "emoji"):
            content = str(row.get("content", "")).strip()[:120 if kind == "text" else 8]
            if not content:
                raise MajoorError(f'{where}: a {kind} layer needs "content"')
            position = str(row.get("position", "center"))
            if position not in TEXT_POSITIONS and "x" not in row:
                position = "center"
            layer.update(content=content, size=_number(row.get("size", 0.08), "size", where, 0.02, 0.6), position=position, rotate=_number(row.get("rotate", 0), "rotate", where, -45, 45),
                         stroke=_number(row.get("stroke", 0.05), "stroke", where, 0, 0.2))
            layer["font"] = str(row.get("font", "impact")) if row.get("font", "impact") in ("impact", "clean", "serif", "mono") else "impact"
            layer["safe"] = bool(row.get("safe", True))
            layer['accent_last'] = bool(row.get('accent_last', True))
            layer["repeat"] = max(1, min(int(row.get("repeat", 1)), 12))
            if row.get("background") and _color(row["background"], where, "") != "":
                layer["background"] = str(row["background"])
            if "x" in row:
                layer["x"], layer["y"] = _number(row.get("x"), "x", where, -1, 1), _number(row.get("y", 0), "y", where, -1, 1)
        elif kind in ("box", "brackets"):
            rect = row.get("rect", [0.25, 0.25, 0.5, 0.5])
            if not (isinstance(rect, list) and len(rect) == 4):
                raise MajoorError(f"{where}: rect must be [x, y, width, height] as fractions of the frame")
            layer["rect"] = [_number(rect[0], "rect x", where, -1, 1), _number(rect[1], "rect y", where, -1, 1), _number(rect[2], "rect width", where, 0.001, 2), _number(rect[3], "rect height", where, 0.001, 2)]
            layer["thickness"] = _number(row.get("thickness", 0.004), "thickness", where, 0.001, 0.05)
            layer["arm"] = _number(row.get("arm", 0.2), "arm", where, 0.05, 0.5)
        elif kind == 'vector':
            layer.update(shape=_choice(row.get('shape','line'),('line','dot','ring'),'line'),
                         at=_point(row.get('at'),where,[.2,.7]),to=_point(row.get('to'),where,[.8,.7]),
                         radius=_number(row.get('radius',.009),'radius',where,.001,.2),
                         thickness=_number(row.get('thickness',.003),'thickness',where,.001,.05))
        elif kind == "outline":
            layer.update(width=_number(row.get("width", 0.006), "width", where, 0.001, 0.05), style=_choice(row.get("style", "solid"), OUTLINES, "solid"), glow=_number(row.get("glow", 0), "glow", where, 0, 1),
                         needs_mask=True)
        elif kind == "effect":
            effect = str(row.get("kind", "chromatic"))
            if effect not in EFFECTS:
                raise MajoorError(f"{where}: unknown effect '{effect}'. Available: {list(EFFECTS)}")
            target = _choice(row.get("target", "frame"), TARGETS, "frame")
            layer.update(kind=effect, amount=_number(row.get("amount", 0.5), "amount", where, 0, 1), target=target, spacing=_number(row.get("spacing", 0.06), "spacing", where, 0.01, 0.4),
                         thickness=_number(row.get("thickness", 0.0015), "thickness", where, 0.0005, 0.02), radius=_number(row.get("radius", 0.008), "radius", where, 0.001, 0.05),
                         flicker=_number(row.get("flicker", 0), "flicker", where, 0, 30), speed=_number(row.get("speed", 0), "speed", where, -2, 2), needs_mask=target != "frame")
        else:  # track
            anchor = str(row.get("anchor", "")) if str(row.get("anchor", "")) in ANCHORS else ""
            layer.update(anchor=anchor, at=_point(row.get("at"), where, [0.5, 0.5]), shape=_choice(row.get("shape", "ring"), SHAPES, "ring"), label=str(row.get("label", "")).strip()[:60],
                         emoji=str(row.get("emoji", "")).strip()[:4], offset=_point(row.get("offset"), where, [0.08, -0.08]), line=bool(row.get("line", True)),
                         size=_number(row.get("size", 0.035), "size", where, 0.015, 0.2), radius=_number(row.get("radius", 0.014), "radius", where, 0.004, 0.08), needs_mask=bool(anchor))
        layers.append(layer)
    return layers


def needs_mask(layers: list[dict]) -> bool:
    return any(layer["needs_mask"] for layer in layers)


def _ease(p: float) -> float:
    return 1 - (1 - p) ** 3


def _back(p: float) -> float:
    c = 1.70158
    return 1 + (c + 1) * (p - 1) ** 3 + c * (p - 1) ** 2


def _state(layer: dict, t: float, length: float, seed: int) -> dict | None:
    """What the layer looks like at the time t: None when it is not there, else opacity, offset in fractions of the frame, scale, share of the text or of the brackets drawn."""
    start, end = layer["start"], layer["end"] if layer["end"] is not None else length + 1
    if not start <= t < end:
        return None
    p = min((t - start) / layer["in_time"], 1.0)
    state = {"alpha": layer["opacity"], "dx": 0.0, "dy": 0.0, "scale": 1.0, "reveal": 1.0}
    animation = layer["animation"]
    if animation == "fade":
        state["alpha"] *= p
    elif animation == "pop":
        state["scale"], state["alpha"] = 0.6 + 0.4 * _back(p), state["alpha"] * min(p * 3, 1)
    elif animation in ("slide_up", "slide_down"):
        state["dy"], state["alpha"] = (1 - _ease(p)) * 0.08 * (1 if animation == "slide_up" else -1), state["alpha"] * _ease(p)
    elif animation in ("slide_left", "slide_right"):
        state["dx"], state["alpha"] = (1 - _ease(p)) * 0.1 * (1 if animation == "slide_left" else -1), state["alpha"] * _ease(p)
    elif animation in ("typewriter", "draw"):
        state["reveal"] = p
    elif animation == "glitch" and p < 1:
        rng = np.random.default_rng(seed)
        state["dx"], state["dy"] = float(rng.uniform(-0.03, 0.03)), float(rng.uniform(-0.01, 0.01))
    elif animation == "shake":
        state["dx"], state["dy"] = 0.004 * math.sin(t * 90), 0.004 * math.cos(t * 70)
    elif animation == "float":
        state["dy"], state["alpha"] = 0.012 * math.sin((t - start) * 4), state["alpha"] * min(p * 2, 1)
    if layer["out"] == "fade" and layer["end"] is not None:
        state["alpha"] *= min(max((end - t) / 0.2, 0.0), 1.0)
    return state


EMOJI_FONTS = ("seguiemj.ttf", "C:/Windows/Fonts/seguiemj.ttf", "NotoColorEmoji.ttf", "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", "/System/Library/Fonts/Apple Color Emoji.ttc")


def _emoji_font(px: int) -> tuple[ImageFont.FreeTypeFont, float]:
    """A color emoji font (Segoe UI Emoji, Noto Color Emoji, Apple Color Emoji; MAJOOR_EMOJI_FONT names another one) and the factor to scale its picture by:
    the bitmap fonts only exist at one size (109)."""
    for name in (os.environ.get("MAJOOR_EMOJI_FONT", ""), *EMOJI_FONTS):
        if not name:
            continue
        try:
            return ImageFont.truetype(name, px), 1.0
        except OSError:
            try:
                return ImageFont.truetype(name, 109), px / 109
            except OSError:
                continue
    raise MajoorError("No color emoji font was found (Segoe UI Emoji, Noto Color Emoji or Apple Color Emoji): set MAJOOR_EMOJI_FONT to the path of one, or write the layer without an emoji.")


def _emoji_sprite(char: str, px: int) -> Image.Image:
    font, factor = _emoji_font(px)
    big = Image.new("RGBA", (int(px * 2.2 * len(char)) + 16, int(px * 2.2) + 16), (0, 0, 0, 0))
    ImageDraw.Draw(big).text((8, 8), char, font=font, embedded_color=True, fill=(255, 255, 255, 255))
    box = big.getbbox()
    if box is None:
        raise MajoorError(f"The font of the emojis has no picture for {char!r}")
    sprite = big.crop(box)
    if factor != 1.0:
        sprite = sprite.resize((max(int(sprite.width * factor), 1), max(int(sprite.height * factor), 1)), Image.LANCZOS)
    return sprite


class _Sprites:
    """The picture of each layer (text with its box, rotated), kept by size so that a layer is drawn once, not at every frame."""

    def __init__(self, width: int, height: int):
        self.width, self.height, self.cache = width, height, {}

    def text(self, layer: dict, chars: int, scale: float) -> Image.Image:
        key = (id(layer), chars, round(scale, 2))
        if key not in self.cache:
            px = max(int(self.height * layer["size"] * scale), 6)
            if layer["type"] == "emoji":
                sprite = _emoji_sprite(layer["content"], px)
                if layer["rotate"]:
                    sprite = sprite.rotate(layer["rotate"], expand=True, resample=Image.BICUBIC)
                self.cache[key] = sprite
                return sprite
            font = _font(px)
            text = layer["content"][:chars]
            stroke = int(px * layer["stroke"])
            probe_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
            full = probe_draw.textbbox((0, 0), layer["content"], font=font, stroke_width=stroke)
            left, top, right, bottom = full
            pad = int(px * 0.25) if layer.get("background") else 0
            sprite = Image.new("RGBA", (right - left + 2 * pad, bottom - top + 2 * pad), (0, 0, 0, 0))
            draw = ImageDraw.Draw(sprite)
            if layer.get("background"):
                draw.rectangle([0, 0, sprite.width - 1, sprite.height - 1], fill=ImageColor.getrgb(layer["background"])[:3] + (255,))
            draw.text((pad - left, pad - top), text, font=font, fill=ImageColor.getrgb(layer["color"])[:3] + (255,), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
            if layer["rotate"]:
                sprite = sprite.rotate(layer["rotate"], expand=True, resample=Image.BICUBIC)
            self.cache[key] = sprite
        return self.cache[key]

    def shape(self, layer: dict, share: float, scale: float) -> tuple[Image.Image, tuple[int, int]]:
        x, y, w, h = layer["rect"]
        bw, bh = max(int(w * self.width * scale), 2), max(int(h * self.height * scale), 2)
        ox, oy = int(x * self.width + (w * self.width - bw) / 2), int(y * self.height + (h * self.height - bh) / 2)
        sprite = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        color = ImageColor.getrgb(layer["color"])[:3] + (255,)
        draw = ImageDraw.Draw(sprite)
        if layer["type"] == "box":
            draw.rectangle([0, 0, bw - 1, bh - 1], fill=color)
        else:
            thick = max(int(min(self.width, self.height) * layer["thickness"]), 1)
            arm = max(int(min(bw, bh) * layer["arm"] * share), 1)
            for cx, cy, sx, sy in ((0, 0, 1, 1), (bw - 1, 0, -1, 1), (0, bh - 1, 1, -1), (bw - 1, bh - 1, -1, -1)):
                draw.rectangle([min(cx, cx + sx * arm), min(cy, cy + thick * sy - sy), max(cx, cx + sx * arm), max(cy, cy + thick * sy - sy)], fill=color)
                draw.rectangle([min(cx, cx + thick * sx - sx), min(cy, cy + sy * arm), max(cx, cx + thick * sx - sx), max(cy, cy + sy * arm)], fill=color)
        return sprite, (ox, oy)


def _paste(frame: np.ndarray, sprite: Image.Image, x: int, y: int, alpha: float) -> None:
    """Alpha-blend a sprite on the frame (a uint8 array, changed in place), clipped to the frame."""
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + sprite.width, w), min(y + sprite.height, h)
    if x0 >= x1 or y0 >= y1 or alpha <= 0:
        return
    part = np.asarray(sprite.crop((x0 - x, y0 - y, x1 - x, y1 - y)))
    a = part[..., 3:4].astype(np.float32) / 255 * alpha
    region = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (region * (1 - a) + part[..., :3].astype(np.float32) * a).astype(np.uint8)


def _tint(frame: np.ndarray, weight: np.ndarray, color: tuple, alpha: float) -> None:
    """Paint a color over the frame where `weight` (H x W, 0 to 1) is."""
    a = (weight * alpha)[..., None]
    frame[:] = (frame.astype(np.float32) * (1 - a) + np.array(color, np.float32) * a).astype(np.uint8)


# ---- effects of the whole frame ------------------------------------------------------------------------------------------

def _chromatic(frame: np.ndarray, layer: dict, amount: float) -> np.ndarray:
    shift = max(int(frame.shape[1] * 0.02 * amount), 1)
    out = frame.copy()
    out[..., 0] = np.roll(frame[..., 0], shift, axis=1)
    out[..., 2] = np.roll(frame[..., 2], -shift, axis=1)
    out[..., 0] = np.roll(out[..., 0], shift // 2, axis=0)
    out[..., 2] = np.roll(out[..., 2], -(shift // 2), axis=0)
    return out


def _glitch(frame: np.ndarray, layer: dict, amount: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    height, width = frame.shape[:2]
    out = frame.copy()
    for _ in range(2 + int(amount * 9)):
        band = max(int(height * rng.uniform(0.01, 0.1)), 1)
        y0 = int(rng.uniform(0, height - band))
        dx = int(rng.uniform(-0.15, 0.15) * width * amount)
        out[y0:y0 + band] = np.roll(out[y0:y0 + band], dx, axis=1)
        channel = int(rng.integers(0, 3))
        out[y0:y0 + band, :, channel] = np.roll(out[y0:y0 + band, :, channel], int(dx * 0.4), axis=1)
    return out


def _pattern(layer: dict, width: int, height: int, t: float) -> np.ndarray:
    """A grid of lines, a grid of dots or scanlines, as a 0 to 1 weight."""
    side = min(width, height)
    step = max(int(side * layer["spacing"]), 3)
    yy, xx = np.mgrid[0:height, 0:width]
    moving = int(t * layer["speed"] * side)
    if layer["kind"] == "grid":
        thick = max(int(side * layer["thickness"]), 1)
        return (((xx + moving) % step < thick) | ((yy + moving) % step < thick)).astype(np.float32)
    if layer["kind"] == "scanlines":
        return ((yy + moving) % step < max(step // 3, 1)).astype(np.float32)
    radius = max(side * layer["radius"], 1.0)
    dx, dy = (xx + moving) % step - step / 2, (yy % step) - step / 2
    return ((dx * dx + dy * dy) < radius * radius).astype(np.float32)


def _effect(frame: np.ndarray, layer: dict, state: dict, t: float, index: int, subject: np.ndarray | None) -> None:
    if layer["flicker"] and int(t * layer["flicker"] * 2) % 2:
        return
    amount = layer["amount"] * state["alpha"]
    if amount <= 0:
        return
    if layer['kind'] in ('grain','vignette','light_leak','pan','roll','handheld'):
        height,width=frame.shape[:2]
        yy,xx=np.mgrid[-1:1:complex(height),-1:1:complex(width)]
        original=frame.astype(np.float32)
        kind=layer['kind']
        if kind=='grain':
            noise=np.random.default_rng(index+7919).normal(0,12*amount,(height,width,1))
            changed=original+noise
        elif kind=='vignette':
            changed=original*(1-.55*amount*np.clip((xx*xx+yy*yy)/2,0,1))[...,None]
        elif kind=='light_leak':
            glow=np.exp(-((xx-(.75+.25*math.sin(t)))**2+(yy+.3)**2)/.45)
            changed=original+glow[...,None]*np.array([85,35,12])*amount
        else:
            phase=t-layer['start']
            angle=2.5*amount*math.sin(phase*.8) if kind=='roll' else .45*amount*math.sin(phase*7) if kind=='handheld' else 0
            matrix=cv2.getRotationMatrix2D((width/2,height/2),angle,1+.1*amount)
            matrix[0,2]+=width*.025*amount*math.sin(phase*(4.1 if kind=='handheld' else .65))
            matrix[1,2]+=height*.015*amount*math.sin(phase*5.3) if kind=='handheld' else 0
            changed=cv2.warpAffine(frame,matrix,(width,height),borderMode=cv2.BORDER_REFLECT_101).astype(np.float32)
        weight=np.ones((height,width),np.float32) if layer['target']=='frame' else subject if layer['target']=='subject' else 1-subject
        frame[:]=np.clip(original*(1-weight[...,None])+changed*weight[...,None],0,255).astype(np.uint8)
        return
    if layer["kind"] in ("chromatic", "glitch"):
        changed = _chromatic(frame, layer, amount) if layer["kind"] == "chromatic" else _glitch(frame, layer, amount, index * 17 + 3)
        weight = np.ones(frame.shape[:2], np.float32) if layer["target"] == "frame" else (subject if layer["target"] == "subject" else 1 - subject)
        frame[:] = (frame.astype(np.float32) * (1 - weight[..., None]) + changed.astype(np.float32) * weight[..., None]).astype(np.uint8)
        return
    weight = _pattern(layer, frame.shape[1], frame.shape[0], t - layer["start"])
    if layer["target"] != "frame":
        weight = weight * (subject if layer["target"] == "subject" else 1 - subject)
    _tint(frame, weight, ImageColor.getrgb(layer["color"])[:3], state["alpha"] * 0.6)


def _outline(frame: np.ndarray, layer: dict, state: dict, subject: np.ndarray, t: float) -> None:
    side = min(frame.shape[:2])
    width = max(int(side * layer["width"]), 1)
    solid = (subject > 0.5).astype(np.uint8)
    if not solid.any():
        return
    ring = cv2.dilate(solid, np.ones((2 * width + 1, 2 * width + 1), np.uint8)) - solid
    if layer["style"] == "double":
        inner = cv2.dilate(solid, np.ones((2 * width * 3 + 1, 2 * width * 3 + 1), np.uint8))
        ring = ring | (inner - cv2.dilate(solid, np.ones((2 * width * 2 + 1, 2 * width * 2 + 1), np.uint8)))
    elif layer["style"] == "dashed":
        yy, xx = np.mgrid[0:frame.shape[0], 0:frame.shape[1]]
        ring = ring * (((xx + yy + int(t * side * 0.4)) // max(width * 4, 4)) % 2 == 0)
    weight = ring.astype(np.float32)
    color = ImageColor.getrgb(layer["color"])[:3]
    glow = layer["glow"] if layer["style"] != "neon" else max(layer["glow"], 0.7)
    if glow:
        halo = cv2.GaussianBlur(weight, (0, 0), max(width * 3, 2)) * 2.5 * glow
        _tint(frame, np.clip(halo, 0, 1), color, state["alpha"])
    _tint(frame, weight, color, state["alpha"])


# ---- points that follow something ------------------------------------------------------------------------------------------

def _anchor(subject: np.ndarray, which: str) -> tuple[float, float] | None:
    ys, xs = np.nonzero(subject > 0.5)
    if not len(xs):
        return None
    return {"subject_top": (float(xs[ys <= ys.min() + 2].mean()), float(ys.min())), "subject_bottom": (float(xs[ys >= ys.max() - 2].mean()), float(ys.max())),
            "subject_left": (float(xs.min()), float(ys[xs <= xs.min() + 2].mean())), "subject_right": (float(xs.max()), float(ys[xs >= xs.max() - 2].mean())),
            "subject_center": (float(xs.mean()), float(ys.mean()))}[which]


class _Tracker:
    """The position of each track layer: the point of the layer is followed from frame to frame by Lucas-Kanade optical flow, or taken from the mask of the subject."""

    def __init__(self):
        self.points: dict[int, np.ndarray] = {}
        self.previous: np.ndarray | None = None

    def update(self, layers: list[dict], gray: np.ndarray, t: float, subject: np.ndarray | None) -> None:
        height, width = gray.shape
        for layer in layers:
            if layer["type"] != "track" or t < layer["start"]:
                continue
            key = id(layer)
            if layer["anchor"]:
                found = _anchor(subject, layer["anchor"]) if subject is not None else None
                if found is not None:
                    old = self.points.get(key)
                    new = np.array(found, np.float32)
                    self.points[key] = new if old is None else old * 0.5 + new * 0.5  # a little smoothing: the edge of a mask jitters
            elif key not in self.points:
                self.points[key] = np.array([layer["at"][0] * width, layer["at"][1] * height], np.float32)
            elif self.previous is not None:
                moved, found, _ = cv2.calcOpticalFlowPyrLK(self.previous, gray, self.points[key].reshape(1, 1, 2), None, winSize=(31, 31), maxLevel=3)
                if found[0][0]:
                    self.points[key] = moved.reshape(2)
        self.previous = gray


def _track(frame: np.ndarray, layer: dict, state: dict, point: np.ndarray, sprites: _Sprites) -> None:
    height, width = frame.shape[:2]
    side = min(width, height)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    color = ImageColor.getrgb(layer["color"])[:3] + (255,)
    px, py = float(point[0]), float(point[1])
    r = side * layer["radius"] * state["scale"]
    thick = max(int(side * 0.004), 1)
    if layer["shape"] == "dot":
        draw.ellipse([px - r / 2, py - r / 2, px + r / 2, py + r / 2], fill=color)
    elif layer["shape"] == "ring":
        draw.ellipse([px - r, py - r, px + r, py + r], outline=color, width=thick)
        draw.ellipse([px - r / 4, py - r / 4, px + r / 4, py + r / 4], fill=color)
    elif layer["shape"] == "cross":
        draw.line([px - r, py, px + r, py], fill=color, width=thick)
        draw.line([px, py - r, px, py + r], fill=color, width=thick)
    tx, ty = px + layer["offset"][0] * width + state["dx"] * width, py + layer["offset"][1] * height + state["dy"] * height
    if layer["line"] and (layer["label"] or layer["emoji"]):
        draw.line([px, py, tx, ty], fill=color, width=thick)
    _paste(frame, canvas, 0, 0, state["alpha"])
    if layer["label"]:
        text = {"type": "text", "content": layer["label"], "size": layer["size"], "color": layer["color"], "rotate": 0, "stroke": 0.08, "position": "center"}
        chars = max(math.ceil(len(layer["label"]) * state["reveal"]), 1) if layer["animation"] == "typewriter" else len(layer["label"])
        sprite = sprites.text(text, chars, state["scale"])
        _paste(frame, sprite, int(tx - (0 if layer["offset"][0] >= 0 else sprite.width)), int(ty - sprite.height / 2), state["alpha"])
    if layer["emoji"]:
        sprite = sprites.text({"type": "emoji", "content": layer["emoji"], "size": layer["size"] * 1.6, "rotate": 0}, 0, state["scale"])
        _paste(frame, sprite, int(tx - sprite.width / 2), int(ty - sprite.height / 2 - (side * layer["size"] * 1.3 if layer["label"] else 0)), state["alpha"])


class Masks:
    """The mask of the subject for every frame: the masks read from the video are spread over its length, the frames between two of them blend the two (the contour glides instead of jumping),
    and a light blur takes the jitter out of the edge. One mask per frame, fewer or more, it is the same."""

    def __init__(self, array: np.ndarray | None):
        self.array = array
        self.resized: dict[int, np.ndarray] = {}

    def _mask(self, n: int, width: int, height: int) -> np.ndarray:
        if n not in self.resized:
            if len(self.resized) > 4:
                self.resized.clear()
            m = self.array[n].astype(np.float32)
            self.resized[n] = cv2.resize(m, (width, height), interpolation=cv2.INTER_LINEAR) if m.shape != (height, width) else m
        return self.resized[n]

    def at(self, index: int, total: int, width: int, height: int) -> np.ndarray | None:
        if self.array is None:
            return None
        position = index * (len(self.array) - 1) / max(total - 1, 1)  # the first and the last mask are the first and the last frame
        n = min(int(position), len(self.array) - 1)
        after = min(n + 1, len(self.array) - 1)
        weight = position - n
        mask = self._mask(n, width, height) if after == n or weight == 0 else (1.0 - weight) * self._mask(n, width, height) + weight * self._mask(after, width, height)
        sigma = max(min(width, height) * 0.004, 1.0)
        return cv2.GaussianBlur(mask, (0, 0), sigma)


def draw_layers(frame: np.ndarray, layers: list[dict], t: float, length: float, index: int, sprites: _Sprites, subject: np.ndarray | None = None, tracker: _Tracker | None = None) -> None:
    height, width = frame.shape[:2]
    margin = int(min(width, height) * 0.05)
    if tracker is not None:
        tracker.update(layers, cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), t, subject)
    for n, layer in enumerate(layers):
        state = _state(layer, t, length, index * 31 + n)
        if state is None:
            continue
        kind = layer["type"]
        if kind == "effect":
            _effect(frame, layer, state, t, index, subject)
        elif kind == "outline":
            _outline(frame, layer, state, subject, t)
        elif kind == "track":
            if tracker is not None and id(layer) in tracker.points:
                _track(frame, layer, state, tracker.points[id(layer)], sprites)
        elif kind in ("text", "emoji"):
            chars = max(math.ceil(len(layer["content"]) * state["reveal"]), 1) if layer["animation"] == "typewriter" and kind == "text" else len(layer["content"])
            full = sprites.text(layer, len(layer["content"]), 1.0)  # the box of the whole text keeps its place while the letters appear
            sprite = sprites.text(layer, chars, state["scale"])
            if "x" in layer:
                x, y = int(layer["x"] * width), int(layer["y"] * height)
            else:
                ax, ay = TEXT_POSITIONS[layer["position"]]
                x, y = round(margin + ax * (width - 2 * margin - full.width)), round(margin + ay * (height - 2 * margin - full.height))
            grown = state["scale"] != 1.0  # a text that pops grows around its center
            x, y = x + int(state["dx"] * width) + ((full.width - sprite.width) // 2 if grown else 0), y + int(state["dy"] * height) + ((full.height - sprite.height) // 2 if grown else 0)
            _paste(frame, sprite, x, y, state["alpha"])
        else:
            sprite, (x, y) = sprites.shape(layer, state["reveal"], state["scale"])
            _paste(frame, sprite, x + int(state["dx"] * width), y + int(state["dy"] * height), state["alpha"])


def render_motion(source: Path, layers: list[dict], out: Path, on_progress=None, is_cancelled=None, masks=None) -> None:
    """Compatibility entry point; all production composition now uses HyperFrames."""
    from .hyperframes import render_hyperframes
    import shutil
    if needs_mask(layers) and masks is None:
        raise MajoorError("These layers need the mask of the subject")
    result, _ = render_hyperframes(source, out.parent / '_hyperframes',
        '{"preset":"minimal","reactive":false,"intensity":0}',
        layers_text=json.dumps(layers), masks=masks, progress=on_progress, cancelled=is_cancelled)
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix('.partial.mp4')
    try:
        shutil.copy2(result, temporary)
        temporary.replace(out)
    finally:
        temporary.unlink(missing_ok=True)
