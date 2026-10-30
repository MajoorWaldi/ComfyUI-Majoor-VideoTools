"""Seeded musical cut selection and take-preserving timing application."""
import json
import math
import random
from dataclasses import replace

import numpy as np

from .beats import detect_beats
from .errors import MajoorError
from .template import MIN_SHOT_FRAMES, _find_shots, _json_text, parse_plan
from .timeline_sources import _with_lengths, merge_plans, plan_from_music, plan_text, protected_action

MODES = ("legacy", "adaptive", "random", "regular", "free")


def music_cut_plan(samples, rate, *, duration, fps=24.0, mode="adaptive", density="auto",
                   variation=0.5, sync=1.0, seed=42, cut_every="2_beats", mood=""):
    if mode not in MODES or density not in ("auto", "low", "medium", "high"):
        raise MajoorError("Unsupported music editing mode or cut density")
    if not 0 <= variation <= 1 or not 0 <= sync <= 1:
        raise MajoorError("Music variation and synchronization must be between 0 and 1")
    if rate <= 0 or fps <= 0 or duration <= 0 or not math.isfinite(duration):
        raise MajoorError("Music cut planning requires positive duration, fps and sample rate")
    samples = np.asarray(samples)
    if samples.ndim != 1 or not len(samples) or not np.isfinite(samples).all():
        raise MajoorError("Music cut planning requires nonempty finite mono audio")
    total = max(1, round(duration * fps))
    if mode == "regular":
        return plan_from_music(samples, rate, duration=duration, fps=fps, cut_every=cut_every)
    if mode in ("legacy", "free"):
        raise MajoorError("Free and legacy modes use the narrative plan, not selected musical cuts")
    # Imported here because audio_events also uses timeline_sources for its text.
    from .audio_events import band_hits

    bpm, beats = detect_beats(samples, rate)
    hits = band_hits(samples, rate)
    candidates = {}
    for band in ("kick", "snare"):
        for seconds, strength in hits[band]:
            frame = round(seconds * fps)
            candidates[frame] = max(candidates.get(frame, 0), strength)
    for seconds in beats if bpm > 0 else []:
        frame = round(float(seconds) * fps)
        candidates[frame] = max(candidates.get(frame, 0), .25)
    if bpm > 0:
        for left, right in zip(beats, beats[1:]):
            frame = round(float(left + right) / 2 * fps)
            candidates[frame] = max(candidates.get(frame, 0), .25)
    candidates = {f: score for f, score in candidates.items() if MIN_SHOT_FRAMES <= f <= total - MIN_SHOT_FRAMES}
    # Local RMS and its change describe acoustic pacing, not a guessed emotion.
    hop = max(1, round(rate / 4))
    levels = np.array([np.sqrt(np.mean(chunk.astype(np.float64) ** 2))
                       for start in range(0, min(len(samples), math.ceil(duration * rate)), hop)
                       if len(chunk := samples[start:start + hop])])
    peak = float(np.max(levels)) if len(levels) else 0
    levels = levels / peak if peak > 0 else levels
    rng = random.Random(seed)
    baseline = {"auto": 2.5, "low": 4.0, "medium": 2.5, "high": 1.25}[density]
    baseline *= {"calm": 1.35, "dreamy": 1.25, "intense": .8}.get(mood, 1)
    cuts, position = [], 0
    phrase = []
    while total - position >= 2 * MIN_SHOT_FRAMES:
        i = min(len(levels) - 1, max(0, round(position / fps * rate / hop)))
        level = float(levels[i]) if len(levels) else 0
        previous = float(levels[max(0, i - 4)]) if len(levels) else 0
        activity = min(1.0, .7 * level + .3 * abs(level - previous))
        target_seconds = baseline * (1.7 - 1.1 * activity if mode == "adaptive" else 1)
        target_seconds *= math.exp(rng.uniform(-1, 1) * variation * .8)
        if (not phrase and bpm > 0 and variation > 0
                and (mode == "random" or activity >= .3)
                and rng.random() < min(1, variation * 2)):
            period = 60.0 / bpm
            hold = max(2, 2 ** round(math.log2(max(1, target_seconds / period * 1.5))))
            phrase = list(rng.choice(((hold, 2, 1, .5, .5),
                                      (hold, 1, 2, .5, .5, 2),
                                      (hold, 2, .5, .5, 1, 2))))
        phrased = bool(phrase)
        if phrased:
            target_seconds = phrase.pop(0) * 60.0 / bpm
        gap = max(MIN_SHOT_FRAMES, round(target_seconds * fps))
        target = position + gap
        if target >= total - MIN_SHOT_FRAMES:
            break
        radius = max(MIN_SHOT_FRAMES, round(gap * (.15 + .35 * sync)))
        if phrased:
            # Keep accent snapping from turning a half-beat burst into a hold.
            radius = max(1, round(60.0 / bpm * fps * .2))
        eligible = [(f, strength) for f, strength in candidates.items()
                    if f >= position + MIN_SHOT_FRAMES and total - f >= MIN_SHOT_FRAMES
                    and abs(f - target) <= radius]
        if eligible and sync > 0:
            target = max(eligible, key=lambda item: sync * item[1] - abs(item[0] - target) / radius)[0]
        cuts.append(target)
        position = target
    warnings = []
    if not candidates:
        warnings.append("No reliable musical accents; using varied narrative timing without a beat grid")
    bounds = [0, *cuts, total]
    return {"fps": fps, "shots": [{"duration_frames": b - a, "prompt": "",
                                  "notes": f"{mode} music pacing"} for a, b in zip(bounds, bounds[1:])]}, {
        "bpm": float(bpm) if bpm > 0 else None, "beat_times": [float(t) for t in beats] if bpm > 0 else [], "warnings": warnings,
        "timing_source": "measured_accents" if candidates else "narrative",
    }


def apply_music_timing(text, timing, fps, aspect_ratio, resolution):
    """Keep every planned take; distribute selected edit intervals as sub-cuts."""
    plan = parse_plan(_with_lengths(text), fps, aspect_ratio, resolution)
    raw = _find_shots(json.loads(_json_text(text)))
    raw_shots = raw["shots"] if isinstance(raw, dict) else []
    lengths = [row["duration_frames"] for row in timing["shots"]]
    warnings = []
    if len(plan.shots) > len(lengths):
        warnings.append("Planned take count exceeds selected musical intervals; extra take boundaries are required")
    while len(lengths) < len(plan.shots):
        index = max(range(len(lengths)), key=lengths.__getitem__)
        size = lengths[index]
        if size < 2 * MIN_SHOT_FRAMES:
            raise MajoorError("Too many generated takes for the selected music duration")
        lengths[index:index + 1] = [size // 2, size - size // 2]
    count = len(plan.shots)
    groups, offset, planned_at = [], 0, 0
    ends = np.cumsum(lengths).tolist()
    total, planned_total = sum(lengths), sum(s.frames for s in plan.shots)
    for i, shot in enumerate(plan.shots):
        planned_at += shot.frames
        if i == count - 1:
            end = len(lengths)
        else:
            target = planned_at / planned_total * total
            end = min(range(offset + 1, len(lengths) - (count - i - 1) + 1),
                      key=lambda j: abs(ends[j - 1] - target))
        pieces = lengths[offset:end]
        offset = end
        row = {"id": shot.shot_id, "duration_frames": sum(pieces), "prompt": ""}
        protected = protected_action(raw_shots[i] if i < len(raw_shots) else {"prompt": shot.prompt, "notes": shot.notes, "story": shot.story})
        if len(pieces) > 1 and not protected:
            row["sub_cuts"] = [{"duration_frames": n} for n in pieces]
        elif len(pieces) > 1:
            warnings.append(f"{shot.shot_id}: continuous action preserved; internal musical cuts omitted")
        groups.append(row)
    merged, notes = merge_plans(plan_text({"fps": fps, "shots": groups}), text, fps, aspect_ratio, resolution)
    for row, base in zip(merged["shots"], groups):
        if "sub_cuts" not in base:
            row.pop("sub_cuts", None)
        else:
            # Plain adjacent excerpts would be an invisible cut. Reuse distinct
            # source windows when the planner supplied no visual change.
            elapsed = 0
            for index, cut in enumerate(row["sub_cuts"]):
                n = base["sub_cuts"][index]["duration_frames"]
                if index and not any(k in cut for k in ("start", "zoom", "focus", "flip", "look", "speed", "speed_ramp")):
                    available = max(0, row["duration_frames"] - n)
                    cut["start"] = (0 if elapsed >= available / 2 else available) / fps
                elapsed = round(cut.get("start", elapsed / fps) * fps) + n
    return merged, [*warnings, *notes]


def musical_take_cuts(shot_list, samples, rate, **options):
    """Preview/export-only Remix cuts; preserve reference boundaries and takes."""
    if options.get("mode", "legacy") in ("legacy", "free"):
        return shot_list
    fps = float(shot_list.source.fps)
    total = sum(shot.frame_count for shot in shot_list.shots)
    timing, info = music_cut_plan(samples, rate, duration=total / fps, fps=fps, **options)
    boundaries = np.cumsum([row["duration_frames"] for row in timing["shots"]]).tolist()[:-1]
    shots, warnings = [], list(info["warnings"])
    for shot in shot_list.shots:
        plan = shot.plan or {}
        if shot.active.media_range is not None or protected_action(plan):
            shots.append(shot)
            warnings.append(f"{shot.shot_id}: reference/continuous take retained without internal musical cuts")
            continue
        cuts = [0]
        for boundary in boundaries:
            local = boundary - shot.start_frame
            if local - cuts[-1] >= MIN_SHOT_FRAMES and shot.frame_count - local >= MIN_SHOT_FRAMES:
                cuts.append(local)
        cuts.append(shot.frame_count)
        fx = dict(plan.get("fx") or {})
        existing = fx.pop("sub_cuts", [])
        if len(cuts) > 2:
            subs, elapsed = [], 0
            for index, (a, b) in enumerate(zip(cuts, cuts[1:])):
                spec = {k: v for k, v in (existing[index] if index < len(existing) else {}).items() if k != "frames"}
                n = b - a
                if index and not any(k in spec for k in ("start", "zoom", "focus", "flip", "look", "speed", "speed_ramp")):
                    available = shot.frame_count - n
                    spec["start"] = (0 if elapsed >= available / 2 else available) / fps
                subs.append({"frames": n, **spec})
                elapsed = round(spec.get("start", elapsed / fps) * fps) + n
            fx["sub_cuts"] = subs
        shots.append(replace(shot, plan={**plan, "fx": fx}))
    warnings.append("Musical Remix: reference shot boundaries retained; generated takes receive musical excerpt cuts")
    return replace(shot_list, shots=tuple(shots),
                   detection=replace(shot_list.detection, warnings=tuple([*shot_list.detection.warnings, *warnings])))
