"""The report of a finished edit, without any model: a contact sheet (one frame 0.3 s after each cut), the first frame, black stretches, the cuts against the attacks of the music, the loudness.
The frames of the sheet are what a vision model or a person reads against REVIEW_CHECKLIST."""
import json
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageStat

from ..adapters.ffmpeg import CREATIONFLAGS, find_binary
from .audio_quality import measure_loudness
from .beats import read_wav_mono, strong_accents
from .errors import MediaError
from .media_probe import probe

REVIEW_CHECKLIST = """Look at each frame of the sheet.
Composition: one focal point; nothing collides; nothing important near the edge; the first frame is a real picture, not black.
Text: nothing cut off; readable at the width of a phone; not over the caption area at the bottom; the text is on the screen long enough to be read.
Timing: the cuts fall on the attacks of the music; a readable state holds long enough; an exit is quicker than an entrance.
Consistency: the subject looks the same in every shot; the colours follow one palette; one accent marks the point of the frame.
Report what was checked, what is wrong and in which tile."""


def _run(command: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, creationflags=CREATIONFLAGS, timeout=timeout)
    if result.returncode:
        raise MediaError(result.stderr.decode(errors="replace")[-400:])
    return result


def cut_times(manifest: dict) -> list[float]:
    """The times of the cuts of an edit in seconds: where each shot starts after the first, and the cuts inside a shot."""
    source = manifest.get("source", {})
    fps = float(source.get("fps_num", 24)) / float(source.get("fps_den", 1) or 1)
    times, at = [], 0.0
    for shot in manifest.get("shots", []):
        fx = (shot.get("plan") or {}).get("fx") or {}
        if at > 0:
            times.append(round(at, 3))
        inside = 0.0
        for cut in (fx.get("sub_cuts") or [])[:-1]:
            inside += float(cut.get("frames", 0)) / fps
            times.append(round(at + inside, 3))
        at += float(shot.get("target_duration_seconds", 0))
    return sorted(set(times))


def frame_at(video: Path, seconds: float) -> Image.Image:
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "frame.png"
        _run([find_binary("ffmpeg"), "-y", "-v", "error", "-ss", f"{max(seconds, 0):.3f}", "-i", str(video), "-frames:v", "1", str(out)])
        return Image.open(out).convert("RGB")


def contact_sheet(video: Path, times: list[float], out_dir: Path, columns: int = 4, rows: int = 2, tile_width: int = 270) -> list[Path]:
    """The frames at `times` tiled `columns` x `rows` to a sheet, each tile labelled with its time. Returns the sheets."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tiles = []
    for t in times:
        frame = frame_at(video, t)
        frame = frame.resize((tile_width, round(frame.height * tile_width / frame.width)))
        ImageDraw.Draw(frame).text((6, 4), f"{t:.2f}s", fill=(255, 255, 0), stroke_width=2, stroke_fill=(0, 0, 0), font=ImageFont.load_default(size=16))
        tiles.append(frame)
    per_sheet, sheets = columns * rows, []
    for number, start in enumerate(range(0, len(tiles), per_sheet), 1):
        chunk = tiles[start:start + per_sheet]
        height = max(t.height for t in chunk)
        sheet = Image.new("RGB", (columns * tile_width, ((len(chunk) - 1) // columns + 1) * height), (20, 20, 24))
        for i, tile in enumerate(chunk):
            sheet.paste(tile, ((i % columns) * tile_width, (i // columns) * height))
        path = out_dir / f"sheet-{number}.png"
        sheet.save(path)
        sheets.append(path)
    return sheets


def first_frame(video: Path) -> dict:
    """The first frame is the thumbnail of a social video: it must be a picture, not black."""
    stat = ImageStat.Stat(frame_at(video, 0.0).convert("L"))
    return {"mean": round(stat.mean[0], 1), "contrast": round(stat.stddev[0], 1), "ok": stat.mean[0] >= 12 and stat.stddev[0] >= 5}


def black_stretches(video: Path, minimum: float = 0.1) -> list[dict]:
    result = _run([find_binary("ffmpeg"), "-hide_banner", "-nostdin", "-i", str(video), "-an", "-vf", f"blackdetect=d={minimum}:pix_th=0.06", "-f", "null", "-"])
    text = result.stderr.decode(errors="replace")
    return [{"start": float(a), "end": float(b)} for a, b in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)", text)]


def sync_report(cuts: list[float], accents: np.ndarray, strength: np.ndarray, floor: float = 0.7) -> dict:
    """How far each cut is from the nearest strong attack of the music (ms), and how many are within 50 and 100 ms."""
    strong = accents[strength >= floor]
    if not len(strong) or not cuts:
        return {"cuts": len(cuts), "attacks": int(len(strong)), "distances_ms": [], "within_50ms": None, "within_100ms": None, "median_ms": None}
    distances = [round(1000 * float(np.abs(strong - c).min())) for c in cuts]
    return {"cuts": len(cuts), "attacks": int(len(strong)), "distances_ms": distances, "within_50ms": sum(d <= 50 for d in distances), "within_100ms": sum(d <= 100 for d in distances), "median_ms": int(np.median(distances))}


def edit_report(project_dir: Path, video: Path, out_dir: Path | None = None) -> dict:
    """The report of the edit `video` of a project, written to <project>/exports/edit_report.json with its contact sheets."""
    manifest = json.loads((project_dir / "manifest.json").read_text(encoding="utf-8"))
    out_dir = out_dir or project_dir / "exports"
    cuts = cut_times(manifest)
    report: dict = {"video": video.name, "cuts": cuts, "first_frame": first_frame(video), "black": black_stretches(video), "loudness": measure_loudness(video)}
    music = project_dir / "music" / "retained.wav"
    if music.is_file():
        samples, rate = read_wav_mono(music)
        report["sync"] = sync_report(cuts, *strong_accents(samples, rate))
    else:
        report["sync"] = None
    duration = float(probe(video, with_packets=False).duration)
    boundaries = sorted(set([0.0, *(c for c in cuts if 0 < c < duration), duration]))
    sample_times = [a + min(.3, (b - a) / 2) for a, b in zip(boundaries, boundaries[1:]) if b > a]
    report["sample_times"] = sample_times
    report["provenance"] = {"cuts": "manifest_target_durations", "music": "music/retained.wav" if music.is_file() else None,
                            "limits": "Cut times are reconstructed, not detected in the final video. Still images do not validate motion or perceived synchronization."}
    report["sheets"] = [p.name for p in contact_sheet(video, sample_times, out_dir)]
    report["checklist"] = REVIEW_CHECKLIST
    from .delivery_review import review_delivery
    report['delivery_review'] = review_delivery(video)
    (out_dir / "edit_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
