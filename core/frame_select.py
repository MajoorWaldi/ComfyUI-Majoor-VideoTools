"""Frame selection text: '0-10, 24, 30-90:5, -1, ~8' -> list of frame indices."""
from .errors import MajoorError


def _index(token: str, count: int) -> int:
    try:
        n = int(token)
    except ValueError:
        raise MajoorError(f"Cannot read the frame '{token}'. Use numbers, ranges like 10-20 or 10-20:2.") from None
    if n < 0:
        n += count
    if not 0 <= n < count:
        raise MajoorError(f"Frame {token} is outside the video ({count} frames, 0 to {count - 1}).")
    return n


def _spread(token: str, count: int) -> list[int]:
    """~n: n frames spread evenly from the first to the last (a single one: the middle)."""
    if not token.strip().isdigit() or int(token) < 1:
        raise MajoorError(f"Cannot read '~{token}': give the number of frames to keep, for example ~8.")
    n = min(int(token), count)
    return [count // 2] if n == 1 else [round(i * (count - 1) / (n - 1)) for i in range(n)]


def parse_frames(text: str, count: int) -> list[int]:
    """Indices in the order written (a frame can repeat). A range a-b is inclusive and takes an optional step: a-b:step; ~n keeps n frames spread evenly."""
    out: list[int] = []
    for part in text.replace("\n", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("~"):
            out.extend(_spread(part[1:], count))
            continue
        span, _, step = part.partition(":")
        start, dash, end = span.strip().lstrip("-").partition("-")
        if not dash:
            if step:
                raise MajoorError(f"A step needs a range: '{part}'.")
            out.append(_index(span.strip(), count))
            continue
        first = _index(("-" if span.strip().startswith("-") else "") + start.strip(), count)
        last = _index(end.strip(), count)
        stride = int(step) if step.strip().isdigit() and int(step) > 0 else None
        if step and stride is None:
            raise MajoorError(f"The step of '{part}' must be a positive number.")
        out.extend(range(first, last + 1, stride or 1) if first <= last else range(first, last - 1, -(stride or 1)))
    return out


def every_n_frames(count: int, every: int, max_frames: int = 0, to_end: bool = True) -> list[int]:
    """Frame 0, every, 2*every... With to_end the last frame is always kept and, when more than max_frames come out, they are thinned evenly from the first to the last."""
    if count < 1:
        raise MajoorError("There is no frame to select from.")
    indices = list(range(0, count, max(every, 1)))
    if not to_end:
        return indices[:max_frames] if max_frames > 0 else indices
    if indices[-1] != count - 1:
        indices.append(count - 1)
    if 0 < max_frames < len(indices):
        indices = [indices[len(indices) // 2]] if max_frames == 1 else [indices[round(i * (len(indices) - 1) / (max_frames - 1))] for i in range(max_frames)]
    return indices
