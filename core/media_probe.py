import json
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from ..adapters.ffmpeg import run_capture
from .errors import MediaError


@dataclass
class MediaInfo:
    width: int
    height: int
    rotation: int
    fps: Fraction
    timing_mode: str
    time_base: Fraction
    first_pts: int
    frame_count: int
    duration: Fraction
    has_audio: bool
    audio_stream_index: int | None
    codec: str
    pts: list[int] = field(default_factory=list)

    @property
    def display_size(self) -> tuple[int, int]:
        return (self.height, self.width) if self.rotation % 180 else (self.width, self.height)


def _fraction(text: str | None) -> Fraction:
    if not text or text in ("0/0", "N/A"):
        return Fraction(0)
    return Fraction(text)


def probe(path: Path, with_packets: bool = True) -> MediaInfo:
    """Read stream properties. with_packets also lists every video PTS (cheap, no decoding)."""
    path = Path(path)
    if not path.is_file():
        raise MediaError(f"Media file not found: {path}")
    try:
        info = json.loads(run_capture(["-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)], "ffprobe"))
    except Exception as e:
        raise MediaError(f"Cannot read media '{path.name}': {e}") from e
    video = next((s for s in info.get("streams", []) if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    if video is None:
        raise MediaError(f"'{path.name}' has no video stream")
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)

    rotation = 0
    for side in video.get("side_data_list", []):
        if "rotation" in side:
            rotation = int(round(float(side["rotation"]))) % 360
    time_base = _fraction(video["time_base"])
    avg = _fraction(video.get("avg_frame_rate"))
    rfr = _fraction(video.get("r_frame_rate"))

    pts: list[int] = []
    if with_packets:
        out = run_capture(
            ["-v", "error", "-select_streams", str(video['index']), "-show_entries", "packet=pts", "-of", "csv=p=0", str(path)],
            "ffprobe",
        ).decode()
        for line in out.splitlines():
            token = line.strip().split(",")[0]
            if token.lstrip("-").isdigit():
                pts.append(int(token))
        pts.sort()
        if not pts:
            raise MediaError(f"'{path.name}' contains no decodable video packets")
        diffs = [b - a for a, b in zip(pts, pts[1:])]
        if diffs:
            frame_ticks = Counter(diffs).most_common(1)[0][0]
            cfr = sum(abs(d - frame_ticks) > 1 for d in diffs) <= max(1, len(diffs) // 100)  # tolerate a stray timestamp
        else:
            frame_ticks, cfr = 0, True
        timing_mode = "CFR" if cfr else "VFR"
        fps = rfr if cfr and rfr else avg
        if not fps:
            fps = 1 / (time_base * frame_ticks) if frame_ticks else Fraction(25)
        last_ticks = frame_ticks or int(1 / (fps * time_base))
        duration = Fraction(len(pts)) / fps if cfr else (pts[-1] - pts[0] + last_ticks) * time_base
        frame_count = len(pts)
        first_pts = pts[0]
    else:
        fps = avg or rfr or Fraction(25)
        timing_mode = "CFR" if avg == rfr else "VFR"
        dur_text = video.get("duration") or info.get("format", {}).get("duration")
        duration = Fraction(dur_text).limit_denominator(1_000_000) if dur_text else Fraction(0)
        nb = video.get("nb_frames")
        frame_count = int(nb) if nb and nb.isdigit() else round(duration * fps)
        first_pts = 0

    return MediaInfo(
        width=int(video["width"]),
        height=int(video["height"]),
        rotation=rotation,
        fps=fps,
        timing_mode=timing_mode,
        time_base=time_base,
        first_pts=first_pts,
        frame_count=frame_count,
        duration=duration,
        has_audio=audio is not None,
        audio_stream_index=None if audio is None else int(audio["index"]),
        codec=video.get("codec_name", ""),
        pts=pts,
    )
