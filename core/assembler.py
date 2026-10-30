"""Rebuild a video from the active revision of every shot with a single streaming ffmpeg pass."""
import json
import math
import os
import wave
import uuid
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path
from typing import Callable

import numpy as np

from ..adapters.ffmpeg import run_ffmpeg
from .audio_quality import normalize_loudness
from .cache_policy import cache_session
from .delivery_profiles import get_profile, output_options, qualify_inputs, validate_delivery
from .editorial_graph import compile_project
from .export_transaction import export_lock, durable_audio
from .beats import read_wav_mono, strong_accents, write_wav
from .errors import AssemblyError, MediaError, ShotNotFoundError
from .fingerprints import file_fingerprint, json_fingerprint
from .fx import validate_stored_fx, merged, overlay_filters, render_text, segment_chain, source_seconds, split_filters, split_frames, text_overlay_filters, transition_filters
from .media_probe import probe
from .models import ORIGINAL, Shot, ShotList
from .paths import ProjectStore, sanitize_name
from .sfx import CUES, RATE as SFX_RATE, plan_cues, render_track
from .sfx_library import load_library
from .timeline import shot_duration
from .timeline_edit import EDIT_KEY, MUSIC_GAIN_KEY, take_bounds

ASSEMBLY_VERSION = "5"
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
    shot_volume: float = 1.0  # the sound that comes with each take (its sound design, its voice) when audio_policy is shot_audio
    duck: float = 0.0  # 0 to 1: how much the music gives way to the sound of the takes (shot_audio with a music)
    auto_sfx: bool = False  # whoosh, impact, hit, glitch and shutter under the cuts of the plan
    sfx_library: str = ""
    motion_layers: str = ""  # explicit finishing score; empty keeps standalone plan cues
    loudness_target: float = 0.0  # LUFS of the finished edit (for example -14); 0 leaves the mix as it is
    dialogue: Path | None = None
    preserve_dialogue: bool = False
    delivery_profile: str = "social"
    color_policy: str = "require_bt709"


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
    overlay_spec: dict | None = None  # the text of the overlay: when it appears and how
    overlay_offset: float = 0.0  # where this cut starts in its shot (seconds)
    shot_seconds: float = 0.0
    layers: list[Layer] = field(default_factory=list)  # other takes composed with this one
    compose: str | None = None  # "split" when the layers are the cells of a split screen, "overlay" when they are blended over the take
    layout: str = ""
    post: str = ""  # filters applied to the composed picture (the transition into the cut)
    cue: str = ""  # the sound effect under the start of this segment (see core.sfx.CUES)
    audio_speed: float = 1.0  # constant speed of the cut: the sound of the take is stretched with the picture
    audio_ramp: bool = False  # a speed ramp has no matching sound stretch: the take is silent for this cut


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
                 use_sub_cuts: bool = True, resolve_take: Callable[[str], tuple[Path, Fraction] | tuple[Path, Fraction, float] | None] | None = None, warnings: list[str] | None = None,
                 has_audio: bool = False, source_offset: float = 0.0, allow_padding: bool = False) -> list[Segment]:
    """One segment per sub-cut (or a single one), all read from the same generated take with their own seek, speed, zoom and look."""
    subs = (fx.get("sub_cuts") if use_sub_cuts else None) or [None]
    frames = split_frames(target_frames, [c["frames"] for c in subs], 1) if subs[0] else [target_frames]
    subs = subs[: len(frames)]
    overlay = render_text(fx["text"], width, height, store.resolve("cache/text")) if fx.get("text") else None
    available = float(actual - Fraction(str(source_offset)))
    if not math.isfinite(available) or available <= 0:
        raise AssemblyError(f"{shot.shot_id}: no media remains after source offset")

    def bounded_start(requested, needed, length, context):
        if not math.isfinite(float(requested)) or not math.isfinite(needed) or needed <= 0:
            raise AssemblyError(f"{shot.shot_id}: {context} has invalid source timing")
        if not math.isfinite(length) or length <= 0:
            raise AssemblyError(f"{shot.shot_id}: {context} has no available source media")
        if needed > length + 1e-7:
            if not allow_padding:
                raise AssemblyError(f"{shot.shot_id}: {context} needs {needed:.6f}s but only {length:.6f}s remains after source offset")
            if warnings is not None:
                message = f"{shot.shot_id}: {context} padded with its last frame (needs {needed:.6f}s, available {length:.6f}s)"
                if message not in warnings:
                    warnings.append(message)
        bounded = max(0.0, min(float(requested), max(0.0, length - needed)))
        if abs(bounded - float(requested)) > 1e-7 and warnings is not None:
            message = f"{shot.shot_id}: {context} start clamped inside available source window"
            if message not in warnings:
                warnings.append(message)
        return bounded

    segments, offset, elapsed = [], 0.0, Fraction(0)
    for i, (sub, n) in enumerate(zip(subs, frames)):
        spec = merged(fx, sub)
        overlays, split = spec.pop("overlay", None) or [], spec.pop("split", None)
        composing = bool(overlays or split)
        out_seconds = float(Fraction(n) / fps)
        need = source_seconds(spec, out_seconds)
        start = (sub or {}).get("start")
        if start is None:
            start = offset
        start = bounded_start(start, need, available, "sub-cut")
        offset = start + need
        transition = (sub or {}).get("transition") if sub and "transition" in sub else (fx.get("transition") if i == 0 else None)
        chain = segment_chain(spec, n, fps, width, height, transition, apply_transition=not composing)
        seek = ["-ss", f"{start + source_offset:.6f}"] if start + source_offset > 0 else []

        def layer_of(entry: dict, kind: str) -> Layer:
            source_path, source_length = path, Fraction(str(available))
            layer_offset = source_offset
            if entry["source"] != "self":
                found = resolve_take(entry["source"]) if resolve_take else None
                if found is None:  # that shot has no generated take (yet): this shot stands in for it
                    if warnings is not None:
                        warnings.append(f"{shot.shot_id}: {entry['source']} has no generated take for the {kind}, this shot is used instead")
                else:
                    source_path, source_length = found[:2]
                    layer_offset = found[2] if len(found) > 2 else 0.0
            at = bounded_start(start + entry.get("offset", 0.0), need, float(source_length), kind)
            layer_spec = {k: spec[k] for k in ("speed", "speed_ramp") if k in spec} | {k: entry[k] for k in ("zoom", "focus", "flip", "look") if k in entry}
            return Layer(source_path, ["-ss", f"{at + layer_offset:.6f}"] if at + layer_offset > 0 else [], segment_chain(layer_spec, n, fps, width, height, None), kind, entry)

        segment = Segment(shot, revision_id, path, seek, has_audio, False, n, Fraction(n) / fps, chain, overlay, overlay_spec=fx.get("text"), overlay_offset=float(elapsed), shot_seconds=target_frames / float(fps), cue=CUES.get(transition["type"], "") if transition else ("hit" if i == 0 else ""),
                          audio_speed=float(spec.get("speed", 1.0)), audio_ramp="speed_ramp" in spec)
        if split:
            segment.compose, segment.layout = "split", split["layout"]
            segment.layers = [layer_of(panel, "panel") for panel in split["panels"]]
        if overlays:
            segment.compose = segment.compose or "overlay"
            segment.layers += [layer_of(entry, "overlay") for entry in overlays]
        if composing:
            segment.post = ",".join(transition_filters(transition, n, fps, width, height, include_punch=True))
        segments.append(segment)
        elapsed += Fraction(n) / fps
    return segments


def _source_offset(revision, actual):
    value = float(revision.source_start_seconds)
    if not math.isfinite(value) or value < 0 or value >= float(actual):
        raise AssemblyError('Take source start must be finite and inside its media')
    return value


def _plan(shot_list: ShotList, store: ProjectStore, opts: AssemblyOptions, fps: Fraction, warnings: list[str], width: int, height: int) -> list[Segment]:
    source = shot_list.source
    segments = []
    edit_cursor = Fraction(0)

    def resolve_take(shot_id: str) -> tuple[Path, Fraction, float] | None:
        """The generated take of another shot, for a split screen or a surimpression; None while it is still the placeholder."""
        try:
            other = shot_list.get_shot(shot_id)
        except ShotNotFoundError:
            return None
        revision = other.active
        if revision.media_range is not None:
            return None
        found = store.resolve(revision.media_ref)
        if not found.is_file():
            return None
        length = probe(found, with_packets=False).duration
        offset = _source_offset(revision, length)
        return found, length - Fraction(str(offset)), offset

    composition = compile_project(shot_list, order=[shot.shot_id for shot in ordered_shots(shot_list, opts)])
    for occurrence in composition.clips:
        shot = shot_list.get_shot(occurrence.shot_id)
        revision = shot.active
        path = store.resolve(revision.media_ref)
        edit = (shot.plan or {}).get(EDIT_KEY)
        if edit is not None:
            if not path.is_file():
                raise MediaError(f"{shot.shot_id}: edited take is missing ({revision.media_ref})")
            if edit.get("version") != 1 or revision.revision_id != edit.get("revision_id"):
                raise AssemblyError(f"{shot.shot_id}: invalid editorial take; select the take in Timeline Edit")
            generated = probe(path, with_packets=False)
            offset = _source_offset(revision, generated.duration)
            target = occurrence.duration
            if abs(offset - edit["source_start_seconds"]) > 1e-8:
                raise AssemblyError(f"{shot.shot_id}: editorial source offset changed outside Timeline Edit")
            if Fraction(str(offset)) + target > generated.duration + Fraction(1, 100000):
                raise AssemblyError(f"{shot.shot_id}: edited range exceeds the take; trim or choose another take")
            frames = round((edit_cursor + target) * fps) - round(edit_cursor * fps)
            edit_cursor += target
            if frames < 1:
                raise AssemblyError(f"{shot.shot_id}: clip is shorter than one output frame; increase output_fps or use source fps")
            chain = f"fps={fps.numerator}/{fps.denominator},tpad=stop_mode=clone:stop=1,trim=end_frame={frames}"
            seek = ["-ss", f"{offset:.9f}"] if offset else []
            segments.append(Segment(shot, revision.revision_id, path, seek, generated.has_audio,
                                    False, frames, Fraction(frames) / fps, chain, cue="hit"))
            continue
        if revision.media_range is None and not path.is_file():
            if opts.missing_shot_policy != "use_original":
                raise MediaError(
                    f"{shot.shot_id}: media of {revision.revision_id} is missing ({revision.media_ref}). Set missing_shot_policy=use_original to fall back to the original shot."
                )
            warnings.append(f"{shot.shot_id}: {revision.revision_id} media missing, original shot used instead")
            revision = shot.revision(ORIGINAL)
            path = store.resolve(revision.media_ref)
        target = occurrence.duration
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
            start = occurrence.source_start
            ss = max(start - fd / 2, Fraction(0))
            seek = ["-ss", f"{float(ss):.6f}", "-t", f"{float(target + start - ss):.6f}"]
            # at the end of the file ffmpeg can flush one frame short; pad then trim keeps the count exact
            chain = f"fps={fps.numerator}/{fps.denominator},tpad=stop_mode=clone:stop=2,trim=end_frame={target_frames}"
            segments.append(Segment(shot, revision.revision_id, path, seek, source.has_audio, True, target_frames, Fraction(target_frames) / fps, chain))
            continue

        generated = probe(path, with_packets=False)
        source_offset = _source_offset(revision, generated.duration)
        actual = generated.duration - Fraction(str(source_offset))
        keep = opts.duration_policy == "use_generated_duration" or revision.duration_policy == "keep_generated"
        fx = (shot.plan or {}).get("fx")
        if fx and opts.effects:
            validate_stored_fx(fx, shot.shot_id, fps)
        if fx and opts.effects:
            transitions=[fx.get('transition'),*(c.get('transition') for c in fx.get('sub_cuts',[]))]
            warnings.extend(f'{shot.shot_id}: {t["approximation"]}' for t in transitions if t and t.get('approximation'))
        if fx and not keep and opts.effects:  # effects of a timeline plan: sub-cuts, speed, zoom, transition, text
            segments += _fx_segments(shot, revision.revision_id, path, generated.duration, fx if opts.text else {k: v for k, v in fx.items() if k != "text"}, target_frames, fps, width, height, store, opts.sub_cuts, resolve_take, warnings,
                                     generated.has_audio, source_offset, opts.duration_policy == "trim_or_pad_last_frame")
            continue
        fps_filter = f"fps={fps.numerator}/{fps.denominator}"
        short_by = target - actual
        if keep:
            frames, chain = None, fps_filter
            seconds = actual
            if opts.preserve_dialogue or opts.dialogue is not None:
                frames = max(1, round(actual * fps))
                seconds = Fraction(frames) / fps
                chain = f"{fps_filter},tpad=stop_mode=clone:stop=1,trim=end_frame={frames}"
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
        seek = ["-ss", f"{source_offset:.6f}"] if source_offset > 0 else []
        segments.append(Segment(shot, revision.revision_id, path, seek, generated.has_audio, False, frames, seconds, chain, cue="hit"))
    return segments


def _filter_graph(segments: list[Segment], width: int, height: int, fps: Fraction, audio_policy: str, source_input: int | None, total: Fraction,
                  tracks: tuple[tuple[int, float, float], ...] = (), shot_volume: float = 1.0, duck: float = 0.0, dialogue_input: int | None = None,
                  pixel_format: str = "yuv420p") -> tuple[str, bool]:
    lines = []

    def normalized(index: int, chain: str, label: str) -> str:
        color = "" if pixel_format == "yuv420p" else ":in_color_matrix=bt709:out_color_matrix=bt709:out_range=tv"
        padding = ":color=black@0" if pixel_format.startswith("yuva") else ""
        return (f"[{index}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease:flags=bicubic{color},"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2{padding},setsar=1,format={pixel_format},"
                f"setpts=PTS-STARTPTS,{chain},setpts=PTS-STARTPTS[{label}]")

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
                lines += split_filters(panels, seg.layout, f"s{i}", width, height, f"sp{i}", pixel_format)
                current = f"s{i}"
            for j, layer in enumerate(seg.layers):
                if layer.kind == "overlay":
                    lines += overlay_filters(current, f"l{i}_{j}", f"o{i}_{k}", layer.spec, f"ov{i}_{k}", pixel_format)
                    current, k = f"o{i}_{k}", k + 1
            lines.append(f"[{current}]{seg.post + ',' if seg.post else ''}format={pixel_format},setpts=PTS-STARTPTS[v{i}]")
        if seg.overlay_index is not None:
            animate, placing = text_overlay_filters(seg.overlay_spec, seg.overlay_offset, seg.shot_seconds, height) if seg.overlay_spec else ("", "x=0:y=0")
            text_format = "rgba" if pixel_format == "yuv420p" else "yuva444p10le"
            lines.append(f"[{seg.overlay_index}:v:0]format={text_format},setpts=PTS-STARTPTS{animate}[o{i}]")
            lines.append(f"[v{i}][o{i}]overlay={placing}:eof_action=pass:format=auto,format={pixel_format},setpts=PTS-STARTPTS[v{i}]")
    n = len(segments)
    lines.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,setpts=N/({fps.numerator}/{fps.denominator}*TB),fps={fps.numerator}/{fps.denominator}[v]")

    has_audio = False
    out = "ab" if tracks else "a"  # the tracks are mixed with it
    if dialogue_input is not None:
        lines.append(f"[{dialogue_input}:a:0]aresample={AUDIO_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={float(total):.6f}[{out}]")
        has_audio = True
    elif audio_policy == "source_master" and source_input is not None:
        lines.append(f"[{source_input}:a:0]aresample={AUDIO_RATE}:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={float(total):.6f}[{out}]")
        has_audio = True
    elif audio_policy == "shot_audio" and any(s.has_audio for s in segments):
        for i, seg in enumerate(segments):
            d = float(seg.seconds)
            if seg.has_audio and not seg.audio_ramp:
                lines.append(f"[{seg.input_index}:a:0]aresample={AUDIO_RATE}:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo{atempo_filters(seg.audio_speed)},apad,atrim=duration={d:.6f},asetpts=PTS-STARTPTS[a{i}]")
            else:
                lines.append(f"anullsrc=r={AUDIO_RATE}:cl=stereo,atrim=duration={d:.6f},asetpts=PTS-STARTPTS[a{i}]")
        lines.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1,volume={shot_volume:g}[{out}]")
        has_audio = True
    if tracks:
        for k, (index, volume, fade) in enumerate(tracks):
            fading = f",afade=t=out:st={max(float(total) - fade, 0):.6f}:d={fade:.6f}" if fade > 0 else ""
            lines.append(f"[{index}:a:0]aresample={AUDIO_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={float(total):.6f},volume={volume:g}{fading}[t{k}]")
        if duck > 0 and has_audio:  # the first track is the music: it gives way to the sound of the takes
            lines.append("[ab]asplit=2[abm][abk]")
            lines.append(f"[t0][abk]sidechaincompress=threshold=0.03:ratio={1 + 9 * duck:.1f}:attack=15:release=350:makeup=1[t0d]")
        names = ["t0d" if k == 0 and duck > 0 and has_audio else f"t{k}" for k in range(len(tracks))]
        mixed = ["[abm]" if duck > 0 else "[ab]"] * has_audio + [f"[{name}]" for name in names]
        if len(mixed) > 1:
            lines.append("".join(mixed) + f"amix=inputs={len(mixed)}:duration=longest:normalize=0,alimiter=limit=0.97,atrim=duration={float(total):.6f}[a]")
        else:
            lines.append(f"{mixed[0]}anull[a]")
        has_audio = True
    return ";\n".join(lines), has_audio


def atempo_filters(speed: float) -> str:
    """The audio filters that play a sound `speed` times faster without changing its pitch (atempo takes 0.5 to 2, a larger change is a chain)."""
    out = []
    while speed > 2.0:
        out.append("atempo=2.0")
        speed /= 2.0
    while 0 < speed < 0.5:
        out.append("atempo=0.5")
        speed /= 0.5
    if abs(speed - 1.0) > 1e-6:
        out.append(f"atempo={speed:.6f}")
    return "".join("," + f for f in out)


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

    for name, low, high in (("output_fps", 1, 240), ("music_volume", 0, 4), ("sfx_volume", 0, 4),
                            ("shot_volume", 0, 4), ("music_fade", 0, 10), ("duck", 0, 1),
                            ("loudness_target", -60, 0)):
        value = getattr(opts, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AssemblyError(f"{name} must be a finite number")
        try:
            valid = math.isfinite(value) and low <= value <= high
        except OverflowError:
            valid = False
        if not valid:
            raise AssemblyError(f"{name} must be finite and between {low} and {high}")
    if opts.loudness_target and opts.loudness_target > -5:
        raise AssemblyError("loudness_target must be zero (disabled) or between -60 and -5 LUFS")
    get_profile(opts.delivery_profile, opts.output_format, opts.color_policy)
    shot_list.validate()
    store = ProjectStore(store_root, shot_list.project_id)
    with cache_session(store) as cache_warnings:
        return _assemble_validated(shot_list, store, opts, on_progress, is_cancelled, cache_warnings)


def _assemble_validated(shot_list, store, opts, on_progress, is_cancelled, cache_warnings):
    source = shot_list.source
    profile = get_profile(opts.delivery_profile, opts.output_format, opts.color_policy)
    warnings: list[str] = list(cache_warnings)
    fps = source.fps if opts.fps_policy == "source" else Fraction(opts.output_fps).limit_denominator(1001)
    if fps <= 0:
        raise AssemblyError("output_fps must be positive")
    if opts.fps_policy == "source" and source.timing_mode == "VFR":
        warnings.append(f"Variable frame rate source: output resampled at {float(fps):.3f} fps")

    width, height = source.width - source.width % 2, source.height - source.height % 2
    if opts.preserve_dialogue:
        if opts.duration_policy == "retime_to_target":
            raise AssemblyError("Dialogue preservation cannot retime speaking takes. Choose a trim/pad or generated-duration policy.")
        protected = []
        for shot in shot_list.shots:
            plan = dict(shot.plan or {})
            plan["fx"] = {key: value for key, value in plan.get("fx", {}).items() if key not in ("speed", "speed_ramp", "sub_cuts")}
            plan["protect_action"] = True
            protected.append(replace(shot, plan=plan))
        shot_list = replace(shot_list, shots=tuple(protected))
        opts = replace(opts, sub_cuts=False)
        warnings.append("Dialogue protected: take audio stays continuous; internal cuts and speed effects omitted on speaking takes. The raw generation manifest is unchanged.")
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

    from .dialogue_track import KEY as DIALOGUE_KEY, audio_duration, render_dialogue
    dialogue = opts.dialogue
    if opts.preserve_dialogue and dialogue is None:
        entries, cursor, seen = [], Fraction(0), set()
        for segment in segments:
            sid = segment.shot.shot_id
            if sid not in seen:
                seen.add(sid)
                revision = segment.shot.revision(segment.revision_id)
                offset, frames = take_bounds(shot_list, segment.shot, revision)
                if segment.has_audio:
                    entries.append({"file": store.rel(segment.path), "start": float(offset),
                                    "duration": frames / float(source.fps), "at": float(cursor), "gain": opts.shot_volume})
            cursor += segment.seconds
        dialogue = render_dialogue(store, entries, float(total))
    if any(DIALOGUE_KEY in (s.plan or {}) for s in shot_list.shots):
        if dialogue is not None:
            raise AssemblyError("Use either the Timeline Edit dialogue track or the dialogue audio input, not both")
        entries = [entry for s in shot_list.shots for entry in (s.plan or {}).get(DIALOGUE_KEY, [])]
        dialogue = render_dialogue(store, entries, float(total))
    if dialogue is not None and audio_duration(dialogue) > float(total) + 1 / float(fps):
        raise AssemblyError("Dialogue extends beyond the video; extend the montage instead of truncating the sentence")
    audio_policy = "mute" if dialogue is not None else opts.audio_policy
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
    music_volume = (shot_list.shots[0].plan or {}).get(MUSIC_GAIN_KEY, opts.music_volume)
    music_fade = 0. if any(DIALOGUE_KEY in (s.plan or {}) for s in shot_list.shots) else opts.music_fade
    for path, volume, fade in ((opts.music, music_volume, music_fade), (opts.sfx, opts.sfx_volume, 0.0)):
        if path is not None:
            tracks.append((next_input + (source_input is not None) + len(extra_inputs), volume, fade))
            extra_inputs.append(path)
    accents, level = None, 1.0
    music_measurement, sound_balance = None, []
    motion_rows, motion_timeline, cursor = [], [], 0.
    for seg in segments:
        sid=seg.shot.shot_id
        if motion_timeline and motion_timeline[-1]['id']==sid:
            motion_timeline[-1]['duration']+=float(seg.seconds)
        elif not any(row['id']==sid for row in motion_timeline):
            motion_timeline.append({'id':sid,'start':cursor,'duration':float(seg.seconds)})
            motion_rows.extend({**layer,'shot_id':sid} for layer in (seg.shot.plan or {}).get('motion',[]))
        cursor+=float(seg.seconds)
    has_scene_sound=any(row.get('sfx') for row in motion_rows)
    if opts.motion_layers:
        configured=json.loads(opts.motion_layers)
        motion_rows=configured.get('layers',[]) if isinstance(configured,dict) else configured
        has_scene_sound=any(row.get('sfx') for row in motion_rows)
    if (opts.auto_sfx or motion_rows) and opts.music is not None:
        try:
            samples, music_rate = read_wav_mono(opts.music)
            music_measurement = (samples * opts.music_volume, music_rate)
            accents = strong_accents(samples, music_rate, 0.45)[0]
            level = float(np.clip(float(np.sqrt(np.mean(samples ** 2))) / 0.10, 0.6, 1.4))  # the effects follow how loud the music is
        except (OSError, ValueError, EOFError, wave.Error):
            pass  # not a 16-bit wav: the cues go where the cuts are
    from .motion_score import build_score, write_score
    resolved_score = build_score(motion_rows, motion_timeline, float(total), float(fps), accents if accents is not None else ()) if motion_rows else None
    shared_score = resolved_score if accents is not None else None
    if opts.auto_sfx:
        events, start = [], Fraction(0)
        for seg in segments:
            if seg.cue and start > 0:
                events.append((round(float(start), 3), seg.cue))
            start += seg.seconds
        events = plan_cues(events, accents)
        explicit=[]
        if has_scene_sound:
            from .sfx import GAINS
            for row in resolved_score['layers']:
                if row.get('sfx'):
                    if row['sfx'] not in GAINS:raise ValueError('Unknown scene sound effect')
                    explicit.append((row['start'],row['sfx'],row.get('event_role','decoration')))
            # Explicit scene cues are already timed with their graphics, not re-snapped.
            events=sorted(set(events+[(t,k) for t,k,_ in explicit]))
        if events:
            from .tone_sfx import tone_library_status, design_cues, tone_anchors
            tone_bank,tone_key,tone_warning=tone_library_status()
            if tone_warning:
                warnings.append(tone_warning)
            library,library_key=load_library(opts.sfx_library)
            preparations = {}
            anchors = tone_anchors() if tone_bank else {}
            if tone_bank:
                palettes = {row['sound_palette'] for row in motion_rows if row.get('sound_palette')}
                palette = next(iter(palettes)) if len(palettes) == 1 else None
                events=design_cues(events,float(total),set(library)|{k for _,k,_ in explicit},tone_bank, preparations=preparations,
                                   palette=palette, seed=int(json_fingerprint(motion_rows)[:8],16))
            from .editorial_cues import arbitrate_cues
            explicit_keys={(t,k) for t,k,_ in explicit}
            protected=[(row['start'],row['start']+row['duration']) for row in motion_timeline
                       if (shot_list.get_shot(row['id']).plan or {}).get('story',{}).get('protect_action') is True]
            # Slow held edits with sparse measured attacks receive more breathing room.
            quiet=bool(accents is not None and len(accents)/max(float(total),1)<.5
                       and motion_timeline and all(row['duration']>=3 for row in motion_timeline))
            events,cue_report=arbitrate_cues([(t,k) for t,k in events if (t,k) not in explicit_keys],
                                           explicit,float(total),protected=protected,quiet=quiet,preparations=preparations)
            if resolved_score is not None:
                resolved_score['sound_cues']=cue_report
            # User cue files override matching Tone types without doubling tracks.
            generated_kinds=set(tone_bank)-set(library)
            library={**tone_bank,**library}
            library_key=json_fingerprint([library_key,tone_key,anchors,'tone-score-v3'])
            sfx_path = store.resolve(f"cache/sfx_{json_fingerprint([events, library_key, level, str(total), SFX_RATE, file_fingerprint(Path(__file__).with_name('sfx.py')), file_fingerprint(Path(__file__).with_name('tone_sfx.py'))])[:24]}.wav")
            with export_lock(store, 'sfx:' + os.path.normcase(str(sfx_path.resolve())), is_cancelled):
                if not sfx_path.is_file():
                    sfx_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary_sfx = sfx_path.with_name(sfx_path.stem + '.' + uuid.uuid4().hex + '.tmp.wav')
                    try:
                        write_wav(temporary_sfx, render_track(events, float(total),library, level, generated_kinds, anchors=anchors), SFX_RATE)
                        os.replace(temporary_sfx, sfx_path)
                    finally:
                        temporary_sfx.unlink(missing_ok=True)
            if music_measurement is not None:
                from .beats import read_wav
                from .sfx import cue_balance
                bus, bus_rate=read_wav(sfx_path)
                sound_balance=cue_balance(events,bus*opts.sfx_volume,music_measurement[0],bus_rate,music_measurement[1])
            tracks.append((next_input + (source_input is not None) + len(extra_inputs), opts.sfx_volume, 0.0))
            extra_inputs.append(sfx_path)
    dialogue_input = None
    if dialogue is not None:
        dialogue_input = next_input + (source_input is not None) + len(extra_inputs)
        extra_inputs.append(dialogue)
    ducking = opts.duck if opts.music is not None and (audio_policy == "shot_audio" or dialogue_input is not None) else 0.0
    graph, has_audio = _filter_graph(segments, width, height, fps, audio_policy, source_input, total, tuple(tracks),
                                     opts.shot_volume, ducking, dialogue_input, profile.working_format)

    media_inputs = {seg.path for seg in segments}
    media_inputs.update(layer.path for seg in segments for layer in seg.layers)
    media_inputs.update(seg.overlay for seg in segments if seg.overlay is not None)
    warnings.extend(qualify_inputs(profile, media_inputs, segments, opts.color_policy, width, height))
    if source_input is not None:
        media_inputs.add(store.resolve(source.uri))
    input_fingerprints = sorted((store.rel(path), file_fingerprint(path)) for path in media_inputs)
    renderer_build = {name: file_fingerprint(Path(__file__).with_name(name))
                      for name in ("assembler.py", "fx.py", "audio_quality.py", "delivery_profiles.py", "editorial_graph.py", "motion_score.py", "motion_timing.py", "motion_scenes.py")}
    plan_key = json_fingerprint(
        [
            ASSEMBLY_VERSION, renderer_build, input_fingerprints, shared_score, source.fingerprint, graph, opts.output_format, opts.video_codec,
            opts.delivery_profile, opts.color_policy, opts.loudness_target, [file_fingerprint(p) for p in extra_inputs],
            [[s.shot.shot_id, s.revision_id, s.shot.revision(s.revision_id).fingerprint, s.seek, str(s.overlay and s.overlay.name), [[l.path.name, l.seek, l.kind] for l in s.layers]] for s in segments],
        ]
    )
    name = sanitize_name(opts.output_name)
    out = store.resolve(f"exports/{name}_{plan_key[:10]}.{opts.output_format}")
    from .delivery_review import save_timeline
    cursor, delivery_boundaries = 0, []
    delivery_time = Fraction(0)
    for seg in segments:
        if cursor:
            delivery_boundaries.append({'frame': cursor, 'transition': seg.cue if seg.cue not in ('', 'hit') else 'cut'})
        delivery_time += seg.seconds
        cursor = round(delivery_time * fps)
    audio_asset = durable_audio(store, opts.music)
    delivery_timeline = {'version': 2, 'fps': float(fps), 'fps_num': fps.numerator, 'fps_den': fps.denominator, 'frames': cursor, 'boundaries': delivery_boundaries,
                         'audio_source': audio_asset['media_ref'] if audio_asset else None, 'audio_asset': audio_asset, 'sound_balance':sound_balance,
                         'audio_policy': audio_policy, 'plan_fingerprint': plan_key, 'renderer_build': renderer_build,
                         'delivery_profile': profile.name, 'working_pixel_format': profile.working_format,
                         'editorial_intent': compile_project(shot_list, order=[shot.shot_id for shot in ordered_shots(shot_list, opts)]).to_dict(),
                         'signal_range': 'limited' if profile.name != 'social' else 'legacy',
                         'range_signaling': 'ProRes legal-range convention; MOV nclc has no range flag' if profile.codec == 'prores' else 'stream'}
    with export_lock(store, os.path.normcase(str(out.resolve())), is_cancelled):
        if out.exists() and _valid(out, total, has_audio):
            validate_delivery(out, profile)
            write_score(store, out, shared_score)
            save_timeline(out, delivery_timeline)
            store.write_json('exports/optional-audio.json', {'version': 2, 'export': store.rel(out), 'plan_fingerprint': plan_key,
                             'warnings': [w for w in warnings if w.startswith('optional:')]})
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
        token = uuid.uuid4().hex
        script = store.resolve(f"logs/filter_{plan_key[:10]}_{token}.txt")
        script.write_text(graph, encoding="utf-8")
        cmd += ["-filter_complex_script", str(script), "-map", "[v]"]
        if has_audio:
            cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"] if profile.name == "social" else ["-map", "[a]", "-c:a", "pcm_s24le"]
        cmd += [
            *output_options(profile), "-fps_mode", "passthrough",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", "-map_metadata", "-1",
            "-movflags", "+faststart", "-t", f"{float(total):.6f}",
        ]
        tmp = out.with_name(out.stem + "." + token + ".partial" + out.suffix)
        cmd.append(str(tmp))
        try:
            run_ffmpeg(cmd, float(total), on_progress, is_cancelled)
            if not _valid(tmp, total, has_audio):
                raise AssemblyError(f"Export validation failed for {out.name}: duration or streams do not match the plan")
            validate_delivery(tmp, profile)
            if opts.loudness_target and has_audio:
                leveled = out.with_name(out.stem + "." + token + ".leveled" + out.suffix)
                try:
                    report = normalize_loudness(tmp, leveled, opts.loudness_target, is_cancelled=is_cancelled,
                                                audio_codec="aac" if profile.name == "social" else "pcm_s24le")
                    if not _valid(leveled, total, has_audio):
                        raise AssemblyError(f"Loudness normalization of {out.name} changed its duration or streams")
                    validate_delivery(leveled, profile)
                    os.replace(leveled, tmp)
                finally:
                    leveled.unlink(missing_ok=True)
                if report["applied"]:
                    warnings.append(f"Loudness {report['before']['integrated_lufs']:.1f} -> {report['after']['integrated_lufs']:.1f} LUFS ({report['gain_db']:+.1f} dB), true peak {report['after']['true_peak_dbtp']:.1f} dBTP")
                if report.get('assessment', {}).get('status') == 'warning':
                    warnings.append('Audio target not reached within 1 LU; decoded true-peak headroom takes priority over additional compression.')
            if is_cancelled and is_cancelled():
                raise AssemblyError("Cancelled before publishing export")
            os.replace(tmp, out)
            write_score(store, out, shared_score)
            save_timeline(out, delivery_timeline)
            store.write_json('exports/optional-audio.json', {'version': 2, 'export': store.rel(out), 'plan_fingerprint': plan_key,
                             'warnings': [w for w in warnings if w.startswith('optional:')]})
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
