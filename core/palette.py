"""The colors of a film, measured on its pictures: an accent for graphics and texts, a light and a dark one for text on top of it. Numpy only, no model.

A graphic in a color taken from the picture belongs to it; a fixed default color looks pasted on."""
import colorsys

import numpy as np

CLUSTERS = 6
ACCENT_SATURATION = 0.3  # under this a color is a grey and cannot carry an accent
ACCENT_VALUE = 0.35      # under this a color is too dark to read as one


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(round(c)):02x}" for c in np.clip(rgb, 0, 255))


def palette(pixels: np.ndarray) -> dict:
    """{"colors": [hex, ...] from the most to the least present, "accent": hex or None, "light": hex, "dark": hex} of RGB pixels (N, 3).
    The colors are the centers of a few clusters (k-means started on the quantiles of brightness, so the same pictures give the same palette)."""
    pixels = np.asarray(pixels, dtype=np.float64).reshape(-1, 3)
    if not len(pixels):
        return {"colors": [], "accent": None, "light": "#ffffff", "dark": "#000000"}
    if len(pixels) > 20000:
        pixels = pixels[np.linspace(0, len(pixels) - 1, 20000).astype(int)]
    brightness = pixels @ [.299, .587, .114]
    order = np.argsort(brightness)
    k = min(CLUSTERS, len(pixels))
    centers = pixels[order[np.linspace(0, len(order) - 1, k).astype(int)]].copy()
    for _ in range(12):
        labels = np.argmin(((pixels[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
        for c in range(k):
            if np.any(labels == c):
                centers[c] = pixels[labels == c].mean(0)
    weights = np.bincount(labels, minlength=k) / len(pixels)
    ranked = sorted(range(k), key=lambda c: -weights[c])
    accent = _accent(pixels)
    luminance = {c: float(centers[c] @ [.299, .587, .114]) for c in range(k)}
    light, dark = max(range(k), key=luminance.get), min(range(k), key=luminance.get)
    return {"colors": [_hex(centers[c]) for c in ranked], "accent": accent,
            "light": _hex(centers[light]) if luminance[light] >= 200 else "#ffffff", "dark": _hex(centers[dark]) if luminance[dark] <= 50 else "#000000"}


def _accent(pixels: np.ndarray) -> str | None:
    """The accent: among the vivid pixels only (a neon sign, a jacket, a sky), even when they cover little of the frame, the most present vivid color."""
    rgb = pixels / 255
    high, low = rgb.max(1), rgb.min(1)
    saturation = np.where(high > 0, (high - low) / np.maximum(high, 1e-9), 0)
    vivid = pixels[(saturation >= ACCENT_SATURATION) & (high >= ACCENT_VALUE)]
    if len(vivid) < max(30, .005 * len(pixels)):
        return None
    hue = np.array([colorsys.rgb_to_hsv(*(p / 255))[0] for p in vivid[np.linspace(0, len(vivid) - 1, min(len(vivid), 4000)).astype(int)]])
    bins = np.bincount(np.floor(hue * 12).astype(int) % 12, minlength=12)  # twelve hue families: the most present one wins
    family = int(np.argmax(bins))
    sample = vivid[np.linspace(0, len(vivid) - 1, len(hue)).astype(int)][np.floor(hue * 12).astype(int) % 12 == family]
    h, s, v = colorsys.rgb_to_hsv(*(np.median(sample, 0) / 255))
    return _hex(np.array(colorsys.hsv_to_rgb(h, max(s, .55), max(v, .8))) * 255)  # lifted a little, so it reads over the picture


def video_palette(path, samples: int = 6) -> dict:
    """The palette of a few frames spread over a video."""
    from fractions import Fraction

    from . import energy
    from .media_probe import probe

    info = probe(path, with_packets=False)
    duration = float(info.duration)
    frames = [energy.read_gray(path, Fraction(info.fps), limit=1, start=duration * (i + .5) / samples, color=True)[0] for i in range(samples)]
    return palette(np.concatenate([f[..., ::-1].reshape(-1, 3) for f in frames]))  # read_gray gives BGR


def palette_text(found: dict) -> str:
    """The palette as a line for the planner."""
    if not found["colors"]:
        return ""
    accent = f"accent {found['accent']}, " if found["accent"] else ""
    return (f"PALETTE OF THE FILM (measured on the pictures): {accent}light {found['light']}, dark {found['dark']}, present colors {', '.join(found['colors'][:5])}. "
            "Unless the brief names colors, take the colors of texts, shapes and effects from it: the accent for what must be seen, light or dark text on top of it.")
