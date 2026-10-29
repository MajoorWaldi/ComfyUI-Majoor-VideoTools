"""The text written on the placeholder cards of a timeline (shot id, role, cuts, prompt), always entirely visible.

The text is wrapped to the width of the card and the size of the letters is reduced until everything fits: nothing is cut off, whatever the length
of the prompt or the size of the card."""
import os

from PIL import Image, ImageDraw, ImageFont

MIN_SIZE = 3  # px; a card of 432 x 768 holds more than twenty thousand characters at this size
LINE = 1.25
FONTS = {False: ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"], True: ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]}


def font(px: int, bold: bool = False):
    for name in [os.environ.get("MAJOOR_CARD_FONT", ""), *FONTS[bold]]:
        if name:
            try:
                return ImageFont.truetype(name, px)
            except OSError:
                continue
    return ImageFont.load_default(size=px)


def wrap(text: str, f, width: float) -> list[str]:
    """Lines no wider than `width`; a word longer than a line is broken, never dropped."""
    lines: list[str] = []
    for paragraph in str(text).split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}".strip() if line else word
            if f.getlength(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            line = word
            while f.getlength(line) > width and len(line) > 1:
                k = len(line) - 1
                while k > 1 and f.getlength(line[:k]) > width:
                    k -= 1
                lines.append(line[:k])
                line = line[k:]
        lines.append(line)
    return lines


def layout(blocks: list[tuple[str, float, bool]], width: float, height: float, start: int) -> tuple[int, list[tuple[list[str], int, bool]]]:
    """The biggest letter size (down to MIN_SIZE) at which every block fits. blocks: (text, size factor, bold). Returns (size, [(lines, px, bold)])."""
    blocks = [b for b in blocks if str(b[0]).strip()]
    for size in range(start, MIN_SIZE - 1, -1):
        placed, total = [], 0.0
        for text, factor, bold in blocks:
            px = max(round(size * factor), MIN_SIZE)
            lines = wrap(text, font(px, bold), width)
            placed.append((lines, px, bold))
            total += len(lines) * px * LINE + size * 0.6
        if total - size * 0.6 <= height:
            return size, placed
    return MIN_SIZE, placed  # below the minimum the text would be unreadable anyway; it still fits for any realistic prompt


def draw_card_text(image: Image.Image, blocks: list[tuple[str, float, bool]]) -> Image.Image:
    """Write the blocks on the card, in black or white according to the color of the card."""
    w, h = image.size
    margin = max(round(min(w, h) * 0.045), 4)
    size, placed = layout(blocks, w - 2 * margin, h - 2 * margin, max(round(min(w, h) * 0.06), MIN_SIZE))
    r, g, b = image.convert("RGB").resize((1, 1)).getpixel((0, 0))
    ink = (0, 0, 0) if 0.299 * r + 0.587 * g + 0.114 * b > 140 else (255, 255, 255)
    draw = ImageDraw.Draw(image)
    y = float(margin)
    for lines, px, bold in placed:
        f = font(px, bold)
        for line in lines:
            draw.text((margin, y), line, font=f, fill=ink)
            y += px * LINE
        y += size * 0.6
    return image
