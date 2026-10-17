"""Rebuild a video from the active revision of every shot with a single streaming ffmpeg pass."""
import json
import os
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from ..adapters.ffmpeg import run_ffmpeg
from .errors import AssemblyError, MediaError
from .fingerprints import json_fingerprint
from .media_probe import probe
from .models import ORIGINAL, Shot, ShotList
from .paths import ProjectStore, sanitize_name
from .timeline import shot_duration, shot_start

ASSEMBLY_VERSION = "1"
ORDER_MODES = ("original_order", "manual_order")
MISSING_POLICIES = ("error", "use_original")
DURATION_POLICIES = ("trim_or_pad_last_frame", "trim_or_error", "retime_to_target", "use_generated_duration")
FPS_POLICIES = ("source", "fixed")
AUDIO_POLICIES = ("source_master", "mute", "shot_audio")
FORMATS = ("mp4", "mov")
CODECS = ("h264",)
AUDIO_RATE = 48000


@dataclass
class AssemblyOptions:
    assembly_mode: str = "original_order"
    manual_order: str = ""
    missing_shot_policy: str = "error"
    duration_policy: str = "trim_or_pad_last_frame"
    fps_policy: str = "source"
    output_fps: float = 24.0
    audio_policy: str = "source_master"
    output_format: str = "mp4"
    video_codec: str = "h264"
    output_name: str = "majoor_edit"


@dataclass
class Segment:
    shot: Shot
    revision_id: str
    path: Path
    seek: list[str]
    has_audio: bool
    is_original: bool
    frames: int | None  # None: keep every generated frame
    seconds: Fraction  # expected duration of the segment in the output
    chain: str  # video filters applied after normalisation


@dataclass
class AssemblyResult:
    path: Path
    shot_count: int
    modified_count: int
    duration_seconds: float
    warnings: list[str]
    reused: bool
    timeline: list[tuple[str, str, float]]  # (shot_id, take, seconds) in output order


def parse_manual_order(text: str, shot_list: ShotList) -> list[str]:
    text = text.strip()
    if not text:
        raise AssemblyError("assembly_mode='manual_order' requires manual_order (comma separated shot ids or a JSON array)")
    if text.startswith("["):
        try:
            order = json.loads(text)
        except json.JSONDecodeError as e:
            raise AssemblyError(f"manual_order is not valid JSON: {e}") from e
        if not all(isinstance(i, str) for i in order):
            raise AssemblyError("manual_order JSON must be an array of shot id strings")
    else:
        order = [t for t in (p.strip() for p in text.replace("\n", ",").split(",")) if t]
    known = {s.shot_id for s in shot_list.shots}
    unknown = [i for i in order if i not in known]
    if unknown:
        raise AssemblyError(f"manual_order contains unknown shot ids {unknown}. Available: {sorted(known)}")
    duplicates = sorted({i for i in order if order.count(i) > 1})
    if duplicates:
        raise AssemblyError(f"manual_order lists shots more than once: {duplicates}")
    missing = sorted(known - set(order))
    if missing:
        raise AssemblyError(f"manual_order must contain every shot exactly once; missing: {missing}")
    return order


def ordered_shots(shot_list: ShotList, opts: AssemblyOptions) -> list[Shot]:
    if opts.assembly_mode == "manual_order":
        return [shot_list.get_shot(i) for i in parse_manual_order(opts.manual_order, shot_list)]
    return sorted(shot_list.shots, key=lambda s: s.timeline_index)


def _plan(shot_list: ShotList, store: ProjectStore, opts: AssemblyOptions, fps: Fraction, warnings: list[str]) -> list[Segment]:
    source = shot_list.source
    segments = []
    for shot in ordered_shots(shot_list, opts):
        revision = shot.active
        path = store.resolve(revision.media_ref)
        if revision.media_range is None and not path.is_file():
            if opts.missing_shot_policy != "use_original":
                raise MediaError(
                    f"{shot.shot_id}: media of {revision.revision_id} is missing ({revision.media_ref}). Set missing_shot_policy=use_original to fall back to the original shot."
                )
            warnings.append(f"{shot.shot_id}: {revision.revision_id} media missing, original shot used instead")
            revision = shot.revision(ORIGINAL)
            path = store.resolve(revision.media_ref)
        target = shot_duration(source, shot)
        target_frames = max(1, round(target * fps))

        if revision.media_range is not None:  # untouched original: exact frame range of the source
            if not path.is_file():
                raise MediaError(f"{shot.shot_id}: project source is missing ({revision.media_ref})")
            fd = 1 / source.fps
            start = shot_start(source, shot)
            ss = max(start - fd / 2, Fraction(0))
            seek = ["-ss", f"{float(ss):.6f}", "-t", f"{float(target + start - ss):.6f}"]
            # at the end of the file ffmpeg can flush one frame short; pad then trim keeps the count exact
            chain = f"fps={fps.numerator}/{fps.denominator},tpad=stop_mode=clone:stop=2,trim=end_frame={target_frames}"
            segments.append(Segment(shot, revision.revision_id, path, seek, source.has_audio, True, target_frames, Fraction(target_frames) / fps, chain))
            continue

        generated = probe(path, with_packets=False)
        actual = generated.duration
        keep = opts.duration_policy == "use_generated_duration" or revision.duration_policy == "keep_generated"
        fps_filter = f"fps={fps.numerator}/{fps.denominator}"
        short_by = target - actual
        if keep:
            frames, chain = None, fps_filter
            seconds = actual
            if actual != target:
                warnings.append(f"{shot.shot_id}: generated duration {float(actual):.3f}s kept (target {float(target):.3f}s)")
        elif opts.duration_policy == "retime_to_target":
            frames = target_frames
            chain = f"setpts=PTS*{float(target / actual):.9f},{fps_filter},tpad=stop_mode=clone:stop=-1,trim=end_frame={frames}"
            if abs(float(target / actual) - 1) > 0.25:
                warnings.append(f"{shot.shot_id}: retime by x{float(actual / target):.2f} to fit {float(target):.3f}s")
            seconds = Fraction(frames) / fps
        else:
            if opts.duration_policy == "trim_or_error" and short_by > 1 / fps:
                raise AssemblyError(
                    f"{shot.shot_id}: generated media is {float(actual):.3f}s, shorter than the {float(target):.3f}s target (duration_policy=trim_or_error)"
                )
            frames = target_frames
            chain = f"{fps_filter},tpad=stop_mode=clone:stop=-1,trim=end_frame={frames}"
            if abs(float(short_by)) > float(1 / fps):
                action = "padded with its last frame" if short_by > 0 else "trimmed"
                warnings.append(f"{shot.shot_id}: generated media {float(actual):.3f}s {action} to the {float(target):.3f}s target")
            seconds = Fraction(frames) / fps
        segments.append(Segment(shot, revision.revision_id, path, [], generated.has_audio, False, frames, seconds, chain))
    return segments


def _filter_graph(segments: list[Segment], width: int, height: int, fps: Fraction, audio_policy: str, source_input: int | None, total: Fraction) -> tuple[str, bool]:
    lines = []
    for i, seg in enumerate(segments):
        lines.append(
            f"[{i}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease:flags=bicubic,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,setpts=PTS-STARTPTS,{seg.chain},setpts=PTS-STARTPTS[v{i}]"
        )
    n = len(segments)
    lines.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,setpts=N/({fps.numerator}/{fps.denominator}*TB),fps={fps.numerator}/{fps.denominator}[v]")

    has_audio = False
    if audio_policy == "source_master" and source_input is not None:
        lines.append(f"[{source_input}:a:0]aresample={AUDIO_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={float(total):.6f}[a]")
        has_audio = True
    elif audio_policy == "shot_audio" and any(s.has_audio for s in segments):
        for i, seg in enumerate(segments):
            d = float(seg.seconds)
            if seg.has_audio:
                lines.append(f"[{i}:a:0]aresample={AUDIO_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={d:.6f},asetpts=PTS-STARTPTS[a{i}]")
            else:
                lines.append(f"anullsrc=r={AUDIO_RATE}:cl=stereo,atrim=duration={d:.6f},asetpts=PTS-STARTPTS[a{i}]")
        lines.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]")
        has_audio = True
    return ";\n".join(lines), has_audio


def assemble_shots(
    shot_list: ShotList,
    store_root: Path,
    opts: AssemblyOptions,
    on_progress: Callable[[float], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> AssemblyResult:
    for value, allowed, name in (
        (opts.assembly_mode, ORDER_MODES, "assembly_mode"),
        (opts.missing_shot_policy, MISSING_POLICIES, "missing_shot_policy"),
        (opts.duration_policy, DURATION_POLICIES, "duration_policy"),
        (opts.fps_policy, FPS_POLICIES, "fps_policy"),
        (opts.audio_policy, AUDIO_POLICIES, "audio_policy"),
        (opts.output_format, FORMATS, "output_format"),
        (opts.video_codec, CODECS, "video_codec"),
    ):
        if value not in allowed:
            raise AssemblyError(f"{name}='{value}' is not supported. Available: {list(allowed)}")

    source = shot_list.source
    store = ProjectStore(store_root, shot_list.project_id)
    warnings: list[str] = []
    fps = source.fps if opts.fps_policy == "source" else Fraction(opts.output_fps).limit_denominator(1001)
    if fps <= 0:
        raise AssemblyError("output_fps must be positive")
    if opts.fps_policy == "source" and source.timing_mode == "VFR":
        warnings.append(f"Variable frame rate source: output resampled at {float(fps):.3f} fps")

    segments = _plan(shot_list, store, opts, fps, warnings)
    total = sum((s.seconds for s in segments), Fraction(0))
    timeline = [(s.shot.shot_id, s.revision_id, float(s.seconds)) for s in segments]
    width, height = source.width - source.width % 2, source.height - source.height % 2
    modified = sum(1 for s in segments if not s.is_original)

    audio_policy = opts.audio_policy
    source_input = None
    if audio_policy == "source_master":
        if not source.has_audio:
            audio_policy = "mute"
        else:
            source_input = len(segments)
            if opts.assembly_mode == "manual_order":
                warnings.append("source_master audio follows the original timeline and is not reordered with the shots")
            if any(s.frames is None or s.seconds != shot_duration(source, s.shot) for s in segments if not s.is_original):
                warnings.append("Shot durations differ from the source: source audio is cut/padded to the new length and is no longer in sync after that shot")

    graph, has_audio = _filter_graph(segments, width, height, fps, audio_policy, source_input, total)

    plan_key = json_fingerprint(
        [
            ASSEMBLY_VERSION, source.fingerprint, graph, opts.output_format, opts.video_codec,
            [[s.shot.shot_id, s.revision_id, s.shot.revision(s.revision_id).fingerprint, s.seek] for s in segments],
        ]
    )
    name = sanitize_name(opts.output_name)
    out = store.resolve(f"exports/{name}_{plan_key[:10]}.{opts.output_format}")
    if out.exists() and _valid(out, total, has_audio):
        return AssemblyResult(out, len(segments), modified, float(total), warnings, True, timeline)

    cmd: list[str] = ["-y"]
    for seg in segments:
        cmd += [*seg.seek, "-i", str(seg.path)]
    if source_input is not None:
        cmd += ["-i", str(store.resolve(source.uri))]
    script = store.resolve(f"logs/filter_{plan_key[:10]}.txt")
    script.write_text(graph, encoding="utf-8")
    cmd += ["-filter_complex_script", str(script), "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    cmd += [
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-fps_mode", "passthrough",
        "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", "-map_metadata", "-1",
        "-movflags", "+faststart", "-t", f"{float(total):.6f}",
    ]
    tmp = out.with_name(out.stem + ".partial" + out.suffix)
    tmp.unlink(missing_ok=True)
    cmd.append(str(tmp))
    try:
        run_ffmpeg(cmd, float(total), on_progress, is_cancelled)
        if not _valid(tmp, total, has_audio):
            raise AssemblyError(f"Export validation failed for {out.name}: duration or streams do not match the plan")
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return AssemblyResult(out, len(segments), modified, float(total), warnings, False, timeline)


def _valid(path: Path, expected: Fraction, want_audio: bool) -> bool:
    try:
        info = probe(path, with_packets=False)
    except MediaError:
        return False
    tolerance = 2 / info.fps
    return abs(info.duration - expected) <= tolerance and info.has_audio == want_audio
