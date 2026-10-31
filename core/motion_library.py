"""Motion templates: a name and a few parameters that expand into the motion layers the renderer already draws.

The planner picks a template from `TEMPLATES` instead of writing layer JSON; `expand_rows` replaces each row {"template": name, ...params} by its layers,
and every other row passes through, so the result goes to `parse_layers` like any layer list."""
from .errors import MajoorError


def _text(content, start, end, **extra):
    return {"type": "text", "content": content, "start": start, "end": end, **extra}


def end_card(start, end, title, credit=""):
    rows = [_text(title, start, end, position="center", size=.1, font="impact", animation="pop", out="fade")]
    if credit:
        rows.append(_text(credit, start + .2, end, position="bottom", size=.04, font="mono", animation="fade", out="fade"))
    return rows


def rec_hud(start, end, label="REC"):
    return [{"type": "brackets", "start": start, "end": end, "rect": [.06, .06, .88, .88], "color": "white", "opacity": .8},
            _text(f"● {label}", start, end, position="top_left", size=.035, font="mono", color="#ff3b30", animation="none")]


def caption_mono(start, end, content, position="bottom_left"):
    return [_text(content, start, end, position=position, size=.03, font="mono", animation="typewriter", out="fade")]


def punch_word(start, end, word, color="white"):
    return [_text(word.upper(), start, end, position="center", size=.16, font="impact", color=color, animation="pop", out="fade", stroke=.08)]


def kinetic_lyrics(start, end, words, accent_color="#ffd60a", position="bottom"):
    """One layer per word, each shown from its own start to the end of its run; words flagged `accent` are bigger and colored."""
    rows = []
    for i, word in enumerate(words):
        following = words[i + 1]["start"] if i + 1 < len(words) else word.get("end", end) + .3  # a word leaves when the next one comes
        a, b = max(word["start"], start), min(following, end)
        if b <= a:
            continue
        accent = word.get("accent", False)
        rows.append(_text(word["word"], a, b, position=position, size=.11 if accent else .07, font="impact",
                          color=accent_color if accent else "white", animation="pop" if accent else "fade", out="fade"))
    return rows


def flash_hit(start, color="white", amount=.9):
    """A full-frame flash that fades out: the hit of a beat or a cut."""
    return [{"type": "effect", "kind": "flash", "start": start, "end": start + .25, "in_time": .25, "amount": amount, "color": color}]


def whip_wipe(start, color="white", duration=.3):
    """A bar that sweeps across the frame from left to right."""
    return [{"type": "effect", "kind": "wipe", "start": start, "end": start + duration, "in_time": duration, "amount": .9, "color": color}]


def letterbox(start, end, amount=1.0):
    return [{"type": "effect", "kind": "letterbox", "start": start, "end": end, "amount": amount, "color": "black"}]


def polaroid_frame(start, end, color="white"):
    return [{"type": "effect", "kind": "frame", "start": start, "end": end, "amount": 1.0, "color": color}]


def glitch_hit(start, amount=.8):
    return [{"type": "effect", "kind": "glitch", "start": start, "end": start + .2, "amount": amount}]


def zoom_punch(start, end=None, amount=.8):
    """A quick push into the picture; two shots cut on it read as a match cut."""
    return [{"type": "effect", "kind": "zoom_punch", "start": start, "end": start + .4 if end is None else end, "in_time": .2, "amount": amount}]


def split_diagonal(start, end):
    return [{"type": "effect", "kind": "split_diagonal", "start": start, "end": end, "amount": 1.0}]


def split_stack(start, end):
    return [{"type": "effect", "kind": "split_stack", "start": start, "end": end, "amount": 1.0}]


def circle_mask(start, end, color="black"):
    return [{"type": "effect", "kind": "circle_mask", "start": start, "end": end, "amount": 1.0, "color": color}]


def picture_in_picture(start, end):
    return [{"type": "effect", "kind": "pip", "start": start, "end": end, "amount": 1.0}]


def cutout_echo(start, end, amount=1.0, color="white", width=.008):
    """The subject with a rough white outline and delayed copies behind it. Needs the subject mask."""
    return [{"type": "effect", "kind": "echo", "start": start, "end": end, "amount": amount},
            {"type": "outline", "start": start, "end": end, "color": color, "width": width}]


def sticker(start, end, name, rect=None, loop=True):
    """A shipped Lottie animation (web/lottie)."""
    return [{"type": "lottie", "start": start, "end": end, "name": name, "rect": rect or [.3, .3, .4, .4], "loop": loop}]


def tiles_grid(start, end):
    """The picture repeated four times, two by two."""
    return [{"type": "effect", "kind": "tiles", "start": start, "end": end, "amount": 1.0}]


def particles(start, end, color="#ffd60a", count=40, speed=.4, size=.008):
    """Falling dots such as confetti, sparks or snow: positions follow a fixed formula, so a render is repeatable."""
    return [{"type": "effect", "kind": "particles", "start": start, "end": end, "amount": .9, "color": color, "count": count, "speed": speed, "radius": size}]


def title_behind(start, end, title, size=.2, color="white"):
    """A big title that passes behind the subject. Needs the subject mask."""
    return [_text(title.upper(), start, end, position="center", size=size, font="impact", color=color, animation="fade", behind=True, safe=False)]


TEMPLATES = {"end_card": end_card, "rec_hud": rec_hud, "caption_mono": caption_mono, "punch_word": punch_word, "kinetic_lyrics": kinetic_lyrics,
             "flash_hit": flash_hit, "whip_wipe": whip_wipe, "letterbox": letterbox, "polaroid_frame": polaroid_frame,
             "glitch_hit": glitch_hit, "zoom_punch": zoom_punch, "split_diagonal": split_diagonal, "split_stack": split_stack, "circle_mask": circle_mask,
             "picture_in_picture": picture_in_picture, "cutout_echo": cutout_echo, "sticker": sticker,
             "tiles_grid": tiles_grid, "particles": particles, "title_behind": title_behind}
SHARED = ("shot_id", "scene", "event_role", "sfx", "sync")  # keys of a row that belong to every layer of its template


def expand_rows(rows):
    result = []
    for row in rows:
        name = row.get("template") if isinstance(row, dict) else None
        if name is None:
            result.append(row)
            continue
        if name not in TEMPLATES:
            raise MajoorError(f"Unknown motion template '{name}'. Available: {list(TEMPLATES)}")
        params = {k: v for k, v in row.items() if k != "template" and k not in SHARED}
        shared = {k: row[k] for k in SHARED if k in row}
        try:
            result.extend({**layer, **shared} for layer in TEMPLATES[name](**params))
        except TypeError as error:
            raise MajoorError(f"Motion template '{name}': {error}") from None
    return result
