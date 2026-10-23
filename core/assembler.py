"""Rebuild a video from the active revision of every shot with a single streaming ffmpeg pass."""
import json
import os
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Callable

from ..adapters.ffmpeg import run_ffmpeg
from .errors import AssemblyError, MediaError, ShotNotFoundError
from .fingerprints import file_fingerprint, json_fingerprint
from .fx import merged, overlay_filters, render_text, segment_chain, source_seconds, split_filters, split_frames, transition_filters
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
    effects: bool = True  # effects of a timeline plan (speed, zoom, look, transitions, text)
    sub_cuts: bool = True  # the cuts inside a shot
    music: Path | None = None  # audio files mixed over the audio of audio_policy, each as long as the edit at most
    sfx: Path | None = None
    music_volume: float = 1.0
    sfx_volume: float = 1.0
    music_fade: float = 0.5  # seconds of fade out at the end of the music
    text: bool = True  # the text of a timeline plan, drawn with the other effects


@dataclass
class Layer:
    """A take read besides the main one, to be blended over the picture (kind overlay) or to fill a cell of a split screen (kind panel)."""
    path: Path
    seek: list[str]
    chain: str
    kind: str
    spec: dict
    input_index: int = 0


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
    overlay: Path | None = None  # transparent PNG drawn over the whole segment (text of a timeline plan)
    input_index: int = 0  # ffmpeg input of the take
    overlay_index: int | None = None  # ffmpeg input of the overlay
    layers: list[Layer] = field(default_factory=list)  # other takes composed with this one
    compose: str | None = None  # "split" when the layers are the cells of a split screen, "overlay" when they are blended over the take
    layout: str = ""
    post: str = ""  # filters applied to the composed picture (the transition into the cut)


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


def _fx_segments(shot: Shot, revision_id: str, path: Path, actual: Fraction, fx: dict, target_frames: int, fps: Fraction, width: int, height: int, store: ProjectStore,
                 use_sub_cuts: bool = True, resolve_take: Callable[[str], tuple[Path, Fraction] | None] | None = None, warnings: list[str] | None = None) -> list[Segment]:
    """One segment per sub-cut (or a single one), all read from the same generated take with their own seek, speed, zoom and look."""
    subs = (fx.get("sub_cuts") if use_sub_cuts else None) or [None]
    frames = split_frames(target_frames, [c["frames"] for c in subs], 1) if subs[0] else [target_frames]
    subs = subs[: len(frames)]
    overlay = render_text(fx["text"], width, height, store.resolve("cache/text")) if fx.get("text") else None
    segments, offset = [], 0.0
    for i, (sub, n) in enumerate(zip(subs, frames)):
        spec = merged(fx, sub)
        overlays, split = spec.pop("overlay", None) or [], spec.pop("split", None)
        composing = bool(overlays or split)
        out_seconds = n / float(fps)
        need = source_seconds(spec, out_seconds)
        start = (sub or {}).get("start")
        if start is None:
            start = offset
        offset = start + need
        start = max(0.0, min(start, float(actual) - need))  # keep the cut inside the take
        transition = (sub or {}).get("transition") if sub and "transition" in sub else (fx.get("transition") if i == 0 else None)
        chain = segment_chain(spec, n, fps, width, height, transition, apply_transition=not composing)
        seek = ["-ss", f"{start:.6f}"] if start > 0 else []

        def layer_of(entry: dict, kind: str) -> Layer:
            source_path, source_length = path, actual
            if entry["source"] != "self":
                found = resolve_take(entry["source"]) if resolve_take else None
                if found is None:  # that shot has no generated take (yet): this shot stands in for it
                    if warnings is not None:
                        warnings.append(f"{shot.shot_id}: {entry['source']} has no generated take for the {kind}, this shot is used instead")
                else:
                    source_path, source_length = found
            at = max(0.0, min(start + entry.get("offset", 0.0), float(source_length) - need))
            layer_spec = {k: spec[k] for k in ("speed", "speed_ramp") if k in spec} | {k: entry[k] for k in ("zoom", "focus", "flip", "look") if k in entry}
            return Layer(source_path, ["-ss", f"{at:.6f}"] if at > 0 else [], segment_chain(layer_spec, n, fps, width, height, None), kind, entry)

        segment = Segment(shot, revision_id, path, seek, False, False, n, Fraction(n) / fps, chain, overlay)
        if split:
            segment.compose, segment.layout = "split", split["layout"]
            segment.layers = [layer_of(panel, "panel") for panel in split["panels"]]
        if overlays:
            segment.compose = segment.compose or "overlay"
            segment.layers += [layer_of(entry, "overlay") for entry in overlays]
        if composing:
            segment.post = ",".join(transition_filters(transition, n, fps, width, height, include_punch=True))
        segments.append(segment)
    return segments


def _plan(shot_list: ShotList, store: ProjectStore, opts: AssemblyOptions, fps: Fraction, warnings: list[str], width: int, height: int) -> list[Segment]:
    source = shot_list.source
    segments = []

    def resolve_take(shot_id: str) -> tuple[Path, Fraction] | None:
        """The generated take of another shot, for a split screen or a surimpression; None while it is still the placeholder."""
        try:
            other = shot_list.get_shot(shot_id)
        except ShotNotFoundError:
            return None
        revision = other.active
        if revision.media_range is not None:
            return None
        found = store.resolve(revision.media_ref)
        return (found, probe(found, with_packets=False).duration) if found.is_file() else None

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
            if source.template:
                if opts.missing_shot_policy != "use_original":
                    ordered = sorted(shot_list.shots, key=lambda s: s.timeline_index)
                    done = [s.shot_id for s in ordered if s.active_revision_id != ORIGINAL]
                    waiting = [s.shot_id for s in ordered if s.active_revision_id == ORIGINAL]
                    raise AssemblyError(
                        f"{shot.shot_id}: still the template placeholder. The shot list that reaches Shot Assemble has a generated take for {len(done)} of {len(ordered)} shots "
                        f"(with a take: {', '.join(done) or 'none'}; without: {', '.join(waiting)}). Every Apply Shot Metadata must take the shot list of the previous one "
                        f"(the first one the list of Create Timeline), the last one must feed Shot Assemble, and each needs the generated video of its own shot. "
                        f"Or set missing_shot_policy=use_original to keep the placeholder cards."
                    )
                warnings.append(f"{shot.shot_id}: template placeholder kept (no generated take)")
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
        fx = (shot.plan or {}).get("fx")
        if fx and not keep and opts.effects:  # effects of a timeline plan: sub-cuts, speed, zoom, transition, text
            segments += _fx_segments(shot, revision.revision_id, path, generated.duration, fx if opts.text else {k: v for k, v in fx.items() if k != "text"}, target_frames, fps, width, height, store, opts.sub_cuts, resolve_take, warnings)
            continue
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


def _filter_graph(segments: list[Segment], width: int, height: int, fps: Fraction, audio_policy: str, source_input: int | None, total: Fraction,
                  tracks: tuple[tuple[int, float, float], ...] = ()) -> tuple[str, bool]:
    lines = []

    def normalized(index: int, chain: str, label: str) -> str:
        return (f"[{index}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease:flags=bicubic,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,setpts=PTS-STARTPTS,{chain},setpts=PTS-STARTPTS[{label}]")

    for i, seg in enumerate(segments):
        if not seg.layers:
            lines.append(normalized(seg.input_index, seg.chain, f"v{i}"))
        else:
            if seg.compose != "split":  # a split screen replaces the picture: nothing reads the main take
                lines.append(normalized(seg.input_index, seg.chain, f"m{i}"))
            for j, layer in enumerate(seg.layers):
                lines.append(normalized(layer.input_index, layer.chain, f"l{i}_{j}"))
            current, k = f"m{i}", 0
            panels = [f"l{i}_{j}" for j, layer in enumerate(seg.layers) if layer.kind == "panel"]
            if panels:
                lines += split_filters(panels, seg.layout, f"s{i}", width, height, f"sp{i}")
                current = f"s{i}"
            for j, layer in enumerate(seg.layers):
                if layer.kind == "overlay":
                    lines += overlay_filters(current, f"l{i}_{j}", f"o{i}_{k}", layer.spec, f"ov{i}_{k}")
                    current, k = f"o{i}_{k}", k + 1
            lines.append(f"[{current}]{seg.post + ',' if seg.post else ''}format=yuv420p,setpts=PTS-STARTPTS[v{i}]")
        if seg.overlay_index is not None:
            lines.append(f"[{seg.overlay_index}:v:0]format=rgba,setpts=PTS-STARTPTS[o{i}]")
            lines.append(f"[v{i}][o{i}]overlay=0:0:eof_action=pass:format=auto,format=yuv420p,setpts=PTS-STARTPTS[v{i}]")
    n = len(segments)
    lines.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,setpts=N/({fps.numerator}/{fps.denominator}*TB),fps={fps.numerator}/{fps.denominator}[v]")

    has_audio = False
    out = "ab" if tracks else "a"  # the tracks are mixed with it
    if audio_policy == "source_master" and source_input is not None:
        lines.append(f"[{source_input}:a:0]aresample={AUDIO_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={float(total):.6f}[{out}]")
        has_audio = True
    elif audio_policy == "shot_audio" and any(s.has_audio for s in segments):
        for i, seg in enumerate(segments):
            d = float(seg.seconds)
            if seg.has_audio:
                lines.append(f"[{seg.input_index}:a:0]aresample={AUDIO_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={d:.6f},asetpts=PTS-STARTPTS[a{i}]")
            else:
                lines.append(f"anullsrc=r={AUDIO_RATE}:cl=stereo,atrim=duration={d:.6f},asetpts=PTS-STARTPTS[a{i}]")
        lines.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[{out}]")
        has_audio = True
    if tracks:
        for k, (index, volume, fade) in enumerate(tracks):
            fading = f",afade=t=out:st={max(float(total) - fade, 0):.6f}:d={fade:.6f}" if fade > 0 else ""
            lines.append(f"[{index}:a:0]aresample={AUDIO_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={float(total):.6f},volume={volume:g}{fading}[t{k}]")
        mixed = ["[ab]"] * has_audio + [f"[t{k}]" for k in range(len(tracks))]
        if len(mixed) > 1:
            lines.append("".join(mixed) + f"amix=inputs={len(mixed)}:duration=longest:normalize=0,alimiter=limit=0.97,atrim=duration={float(total):.6f}[a]")
        else:
            lines.append(f"{mixed[0]}anull[a]")
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

    width, height = source.width - source.width % 2, source.height - source.height % 2
    segments = _plan(shot_list, store, opts, fps, warnings, width, height)
    total = sum((s.seconds for s in segments), Fraction(0))
    shot_ids = list(dict.fromkeys(s.shot.shot_id for s in segments))  # a shot cut in several pieces is still one shot
    timeline: list[tuple[str, str, float]] = []
    for s in segments:
        if timeline and timeline[-1][0] == s.shot.shot_id and timeline[-1][1] == s.revision_id:
            timeline[-1] = (s.shot.shot_id, s.revision_id, timeline[-1][2] + float(s.seconds))
        else:
            timeline.append((s.shot.shot_id, s.revision_id, float(s.seconds)))
    modified = len({s.shot.shot_id for s in segments if not s.is_original})
    next_input = 0
    for seg in segments:
        seg.input_index = next_input
        next_input += 1
        if seg.overlay is not None:
            seg.overlay_index = next_input
            next_input += 1
        for layer in seg.layers:
            layer.input_index = next_input
            next_input += 1

    audio_policy = opts.audio_policy
    source_input = None
    if audio_policy == "source_master":
        if not source.has_audio:
            audio_policy = "mute"
        else:
            source_input = next_input
            if opts.assembly_mode == "manual_order":
                warnings.append("source_master audio follows the original timeline and is not reordered with the shots")
            lengths: dict[str, Fraction] = {}
            for s in segments:
                lengths[s.shot.shot_id] = lengths.get(s.shot.shot_id, Fraction(0)) + s.seconds
            if any(s.frames is None or lengths[s.shot.shot_id] != shot_duration(source, s.shot) for s in segments if not s.is_original):
                warnings.append("Shot durations differ from the source: source audio is cut/padded to the new length and is no longer in sync after that shot")

    tracks, extra_inputs = [], []
    for path, volume, fade in ((opts.music, opts.music_volume, opts.music_fade), (opts.sfx, opts.sfx_volume, 0.0)):
        if path is not None:
            tracks.append((next_input + (source_input is not None) + len(extra_inputs), volume, fade))
            extra_inputs.append(path)
    graph, has_audio = _filter_graph(segments, width, height, fps, audio_policy, source_input, total, tuple(tracks))

    plan_key = json_fingerprint(
        [
            ASSEMBLY_VERSION, source.fingerprint, graph, opts.output_format, opts.video_codec, [file_fingerprint(p) for p in extra_inputs],
            [[s.shot.shot_id, s.revision_id, s.shot.revision(s.revision_id).fingerprint, s.seek, str(s.overlay and s.overlay.name), [[l.path.name, l.seek, l.kind] for l in s.layers]] for s in segments],
        ]
    )
    name = sanitize_name(opts.output_name)
    out = store.resolve(f"exports/{name}_{plan_key[:10]}.{opts.output_format}")
    if out.exists() and _valid(out, total, has_audio):
        return AssemblyResult(out, len(shot_ids), modified, float(total), warnings, True, timeline)

    cmd: list[str] = ["-y"]
    for seg in segments:
        cmd += [*seg.seek, "-i", str(seg.path)]
        if seg.overlay is not None:
            cmd += ["-loop", "1", "-framerate", f"{fps.numerator}/{fps.denominator}", "-t", f"{float(seg.seconds) + 0.5:.6f}", "-i", str(seg.overlay)]
        for layer in seg.layers:
            cmd += [*layer.seek, "-i", str(layer.path)]
    if source_input is not None:
        cmd += ["-i", str(store.resolve(source.uri))]
    for path in extra_inputs:
        cmd += ["-i", str(path)]
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
    return AssemblyResult(out, len(shot_ids), modified, float(total), warnings, False, timeline)


def _valid(path: Path, expected: Fraction, want_audio: bool) -> bool:
    try:
        info = probe(path, with_packets=False)
    except MediaError:
        return False
    tolerance = 2 / info.fps
    return abs(info.duration - expected) <= tolerance and info.has_audio == want_audio
