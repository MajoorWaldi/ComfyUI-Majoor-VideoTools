import dataclasses
import os
import re
import shutil
from fractions import Fraction
from pathlib import Path

from . import energy as energy_tools
from .errors import MajoorError
from .fx import parse_fx
from .fingerprints import file_fingerprint, json_fingerprint
from .frames import write_thumbnail
from .media_probe import MediaInfo, probe
from .models import ORIGINAL, SCHEMA_VERSION, Detection, Revision, Shot, ShotList, Source
from .paths import ProjectStore
from .timeline import frame_time, nearest_frame_index

MODES = ("adaptive", "content", "threshold_fade", "manual")
ENERGY = ("off", "events", "events_and_camera")  # what a shot did that a generated take will not do again: flashes, shakes, punch-ins (and the push of the camera)
DETECTION_VERSION = "2"


def parse_cut_points(text: str, info: MediaInfo) -> list[int]:
    """Frame numbers (plain integers) or times (hh:mm:ss.fff, mm:ss, 12.5, 12.5s) -> sorted frame indices."""
    cuts: set[int] = set()
    rel_pts = [p - info.first_pts for p in info.pts]
    for token in re.split(r"[,;\s]+", text.strip()):
        if not token:
            continue
        if token.isdigit():
            idx = int(token)
        else:
            seconds = _parse_seconds(token)
            idx = nearest_frame_index(rel_pts, seconds / info.time_base)
        if not 0 < idx < info.frame_count:
            raise MajoorError(f"cut point '{token}' is outside the video (valid frames: 1..{info.frame_count - 1})")
        cuts.add(idx)
    return sorted(cuts)


def _parse_seconds(token: str) -> Fraction:
    t = token.lower().removesuffix("s")
    try:
        parts = [Fraction(p) for p in t.split(":")]
    except (ValueError, ZeroDivisionError):
        raise MajoorError(f"cut point '{token}' is not a frame number or timecode") from None
    if len(parts) > 3:
        raise MajoorError(f"cut point '{token}' is not a frame number or timecode")
    seconds = Fraction(0)
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def merge_short_shots(cuts: list[int], frame_count: int, min_frames: int, warnings: list[str]) -> list[int]:
    """Drop cuts that would create shots shorter than min_frames; every dropped cut is reported."""
    bounds = [0, *cuts, frame_count]
    while len(bounds) > 2:
        lengths = [b - a for a, b in zip(bounds, bounds[1:])]
        i = next((k for k, n in enumerate(lengths) if n < min_frames), None)
        if i is None:
            break
        removed = bounds.pop(i + 1 if i == 0 else i)
        warnings.append(f"Cut at frame {removed} removed: shot shorter than min_shot_frames={min_frames}")
    return bounds[1:-1]


def project_id_for(source_fingerprint: str, mode: str, sensitivity: float, min_frames: int, cut_points: str, energy: str = "off") -> str:
    params = {"mode": mode, "s": round(sensitivity, 4), "min": min_frames, "cuts": cut_points.strip() if mode == "manual" else "", **({"energy": energy} if energy != "off" else {})}
    return "p_" + json_fingerprint([source_fingerprint, params])[:12]


def import_source(video_path: Path, store: ProjectStore) -> Path:
    """Make the source part of the project without copying bytes when a hard link is possible."""
    dest = store.dir / "sources" / ("source" + video_path.suffix.lower())
    if dest.exists():
        return dest
    tmp = dest.with_name(dest.name + ".partial")
    tmp.unlink(missing_ok=True)
    try:
        os.link(video_path, tmp)
    except OSError:
        shutil.copy2(video_path, tmp)
    os.replace(tmp, dest)
    return dest


def build_source(info: MediaInfo, uri: str, fingerprint: str) -> Source:
    width, height = info.display_size
    return Source(
        uri=uri,
        fingerprint=fingerprint,
        width=width,
        height=height,
        fps_num=info.fps.numerator,
        fps_den=info.fps.denominator,
        timing_mode=info.timing_mode,
        frame_count=info.frame_count,
        duration_seconds=float(info.duration),
        has_audio=info.has_audio,
        audio_stream_index=info.audio_stream_index,
        time_base_num=info.time_base.numerator,
        time_base_den=info.time_base.denominator,
        rotation=info.rotation,
        first_pts=info.first_pts,
        codec=info.codec,
    )


def build_shots(source: Source, info: MediaInfo, cuts: list[int]) -> tuple[Shot, ...]:
    bounds = [0, *cuts, info.frame_count]
    end_pts_last = info.first_pts + round(info.duration / info.time_base)
    shots = []
    for i, (a, b) in enumerate(zip(bounds, bounds[1:]), start=1):
        start_pts = info.pts[a]
        end_pts = info.pts[b] if b < info.frame_count else end_pts_last
        duration = (end_pts - start_pts) * info.time_base
        shots.append(
            Shot(
                shot_id=f"SHOT_{i:03d}",
                timeline_index=i,
                start_frame=a,
                end_frame_exclusive=b,
                start_pts=start_pts,
                end_pts_exclusive=end_pts,
                target_duration_seconds=float(duration),
                source_media_ref=source.uri,
                active_revision_id=ORIGINAL,
                revisions=(
                    Revision(
                        revision_id=ORIGINAL,
                        media_ref=source.uri,
                        media_range={"start_frame": a, "end_frame_exclusive": b},
                        actual_duration_seconds=float(duration),
                        status="original",
                        fingerprint=source.fingerprint,
                        has_audio=source.has_audio,
                    ),
                ),
            )
        )
    return tuple(shots)


def detect_scenes(
    video_path: Path,
    store_root: Path,
    mode: str,
    sensitivity: float,
    min_shot_frames: int,
    cut_points: str = "",
    thumbnails: bool = True,
    force_refresh: bool = False,
    energy: str = "off",
) -> ShotList:
    if mode not in MODES:
        raise MajoorError(f"Unknown detection_mode '{mode}'. Available: {list(MODES)}")
    if energy not in ENERGY:
        raise MajoorError(f"Unknown energy '{energy}'. Available: {list(ENERGY)}")
    fingerprint = file_fingerprint(video_path)
    project_id = project_id_for(fingerprint, mode, sensitivity, min_shot_frames, cut_points, energy)
    store = ProjectStore(store_root, project_id)

    with store.lock():
        source_path = import_source(video_path, store)
        info = probe(source_path)
        source = build_source(info, store.rel(source_path), fingerprint)

        if mode != "manual":
            from ..adapters import pyscenedetect  # optional dependency, not needed for manual cuts
        cache_key = json_fingerprint([project_id, DETECTION_VERSION, "" if mode == "manual" else pyscenedetect.VERSION])[:16]
        cache_rel = f"cache/scene_metrics/{cache_key}.json"
        cached = None if force_refresh else store.read_json(cache_rel)
        if cached is None:
            warnings: list[str] = []
            if mode == "manual":
                cuts = parse_cut_points(cut_points, info)
            else:
                rel_pts = [p - info.first_pts for p in info.pts]
                times = pyscenedetect.detect_cut_times(source_path, mode, sensitivity, min_shot_frames)
                cuts = sorted({nearest_frame_index(rel_pts, Fraction(t) / info.time_base) for t in times} - {0})
            events: list[energy_tools.Event] = []
            if energy != "off":
                gray = energy_tools.read_gray(source_path, info.fps)
                events = energy_tools.detect_events(energy_tools.measure(gray))
                if mode != "manual":  # a flash is not a cut: the cuts that a detector puts on its frames go
                    cuts = energy_tools.clean_cuts(cuts, events, gray, warnings)
            cuts = merge_short_shots(cuts, info.frame_count, min_shot_frames, warnings)
            if info.timing_mode == "VFR":
                warnings.append("Variable frame rate source: shot bounds use PTS, frame indices are informative")
            cached = {"cuts": cuts, "warnings": warnings, "events": [[e.kind, e.frame, e.frames, e.strength] for e in events]}
            store.write_json(cache_rel, cached)

        shots = build_shots(source, info, cached["cuts"])
        if energy != "off":  # what each shot did, as the effects that Shot Assemble puts on a generated take of it
            events = [energy_tools.Event(k, f, n, s) for k, f, n, s in cached.get("events", [])]
            shots = tuple(_with_energy(s, events, info.fps, energy == "events_and_camera") for s in shots)
        if thumbnails:
            shots = tuple(_with_thumbnail(store, source_path, source, info, s, force_refresh) for s in shots)
        shot_list = ShotList(
            project_id=project_id,
            source=source,
            detection=Detection(mode, sensitivity, min_shot_frames, cache_key, tuple(cached["warnings"]),
                                energy=energy_tools.summarize_energy(events,cached['cuts'],source.duration_seconds) if energy!='off' else None),
            shots=shots,
            schema_version=SCHEMA_VERSION,
        )
        shot_list.validate()
        persist_manifest(store, shot_list, only_if_absent=True)
    return shot_list


def _with_energy(shot: Shot, events: list[energy_tools.Event], fps: Fraction, camera: bool) -> Shot:
    from .template import _shot_fx  # template imports this module

    row = energy_tools.shot_fx(events, shot.start_frame, shot.end_frame_exclusive, camera)
    fx = _shot_fx(parse_fx(row, shot.shot_id, fps, lambda value, rate: 0), shot.start_frame, shot.frame_count, []) if row else {}  # sub-cut weights become frames, as in a template
    return dataclasses.replace(shot, plan={"fx": fx}) if fx else shot


def _with_thumbnail(store: ProjectStore, source_path: Path, source: Source, info: MediaInfo, shot: Shot, force: bool) -> Shot:
    rel =f"cache/thumbnails/{shot.shot_id}.jpg"
    out = store.resolve(rel)
    if force or not out.exists():
        write_thumbnail(source_path, frame_time(source, shot, shot.frame_count // 2), 1 / info.fps, out)
    return dataclasses.replace(shot, thumbnail_ref=rel)


def persist_manifest(store: ProjectStore, shot_list: ShotList, only_if_absent: bool = False) -> None:
    """manifest.json is the latest collection; manifests/<hash>.json keeps every collection version."""
    data = shot_list.to_dict()
    store.write_json(f"manifests/{json_fingerprint(data)[:12]}.json", data)
    if only_if_absent and store.resolve("manifest.json").exists():
        return
    store.write_json("manifest.json", data)
