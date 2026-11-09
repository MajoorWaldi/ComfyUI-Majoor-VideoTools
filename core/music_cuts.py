"""Seeded musical cut selection and take-preserving timing application."""
import json
import math
import random
from dataclasses import replace

import numpy as np

from .beats import detect_beats, onset_envelope, strong_accents
from .errors import MajoorError
from .music_structure import find_downbeats, track_sections
from .words import parse_words, phrase_groups
from .template import MIN_SHOT_FRAMES, _find_shots, _json_text, parse_plan
from .timeline_sources import _with_lengths, group_cuts, merge_plans, plan_from_music, plan_text, protected_action

MODES = ("legacy", "adaptive", "random", "regular", "free", "phrases", "hits")
MIN_TAKE_FRAMES = 22  # the shortest take H3 makes (the 17k+5 grid)
PULSE_MIN = 0.3  # pulse of a section (autocorrelation of its attacks at the tempo) under which its beats are a metronome the tracker imposed
SYNCOPATION = 0.15  # share of cuts, at full variation, that land on purpose between two beats in a section cut on the beat
PHRASE_HOLD = 1.6  # a section cut by phrases holds its shots this much longer
CHAPTER_SECONDS = 2.0  # a section shorter than this (a lead-in before the first attack) does not open a chapter
BURST_ACTIVITY = 0.25  # activity from which an adaptive edit may burst: calm intros sit near 0.2, rhythmic verses near 0.3 to 0.45, drops above 0.5
HIT = 0.7  # strength of an attack that a cut can underline (a flash, a punch); weaker ones only carry the cut
# Hit sync: what each cut pace keeps, as (weakest hit kept, shortest shot in seconds)
HIT_PACE = {"low": (.6, .6), "auto": (.28, .25), "medium": (.28, .25), "high": (0.0, 0.0)}  # high: every hit, the shortest shot is MIN_SHOT_FRAMES
BASS_WITH_HIT = .12  # a bass entry this close to a kick, a snare or a word is the same event, which keeps the sharper time
HIT_MERGE = .05  # two hits closer than this are one (a kick and a bass entering together)
VOICE_BURST = .45  # strength given to the start of a burst of voice
WORD_START = .5  # strength given to the start of a word (a transcript says exactly where it is)
VOICE_KINDS = ("voice", "word")  # a cut on the voice only fills what the rhythm of the music leaves: it never takes the place of a kick, a bass entry or a snare


def pulse_confidence(samples, rate, bpm):
    """How regular the attacks of a stretch are at `bpm` (0 to 1), or None when the stretch is too short or silent to tell."""
    if bpm <= 0 or len(samples) < 2 * rate:
        return None
    env, hop = onset_envelope(np.asarray(samples), rate)
    centered = env - env.mean()
    power = float(np.dot(centered, centered))
    lag = max(1, round(60.0 / bpm / hop))
    if float(np.max(env)) <= 1e-4 or power <= 1e-8 or lag >= len(centered):
        return None
    return float(np.clip(np.dot(centered[:-lag], centered[lag:]) / power, 0, 1))


def grid_contrast(beats, accents, start, end, bpm):
    """How much better the beats of a stretch fall on its strong attacks (within 60 ms) than the same grid moved a third of a beat: a real pulse
    puts its attacks on the grid, a metronome laid on free music does not. The grid is first moved, by at most 0.1 s, to where it meets the most
    attacks. None with fewer than four beats or no attack."""
    grid = np.asarray([b for b in beats if start <= b < end])
    if len(grid) < 4 or not len(accents) or bpm <= 0:
        return None
    hit = lambda times: float(np.mean([np.min(np.abs(accents - t)) <= .06 for t in times]))
    shift = max(np.arange(-.1, .101, .01), key=lambda d: hit(grid + d))  # the grid of the whole track drifts: each section finds its own phase
    return max(0.0, hit(grid + shift) - hit(grid + shift + 20.0 / bpm))


def section_pacing(samples, rate, bpm, duration, beats=()):
    """The sections of the music, each cut "beat" (on a pulse the tracker can trust) or "phrase" (on phrases and changes of energy: on calm or free
    music the beat grid is a metronome the tracker invents). The pulse of a section is the stronger of two measures: the regularity of its attacks
    at the tempo (which dense hi-hats and rolls dilute) and how much its beats fall on its strong attacks (which dense music blurs). A section too
    short or too quiet to measure takes the pacing of the next one."""
    samples = np.asarray(samples)[:max(1, math.ceil(duration * rate))]
    sections = [dict(s) for s in track_sections(samples, rate)] or [{"tag": "intro", "start": 0.0, "end": duration}]
    times, strength = strong_accents(samples, rate) if bpm > 0 and len(beats) else (np.zeros(0), np.zeros(0))
    accents = times[strength >= .5]
    for section in sections:
        measures = [pulse_confidence(samples[round(section["start"] * rate):round(section["end"] * rate)], rate, bpm),
                    grid_contrast(beats, accents, section["start"], section["end"], bpm)]
        known = [m for m in measures if m is not None]
        section["pulse"] = round(max(known), 3) if known else None
    measured = [s["pulse"] for s in sections]
    for i, section in enumerate(sections):
        pulse = next((m for m in measured[i:] if m is not None), next((m for m in reversed(measured[:i]) if m is not None), None))
        section["pacing"] = "beat" if bpm > 0 and (pulse is None or pulse >= PULSE_MIN) else "phrase"
    return sections


def vocal_phrases(samples, rate, *, min_pause=.35, min_length=.6):
    """(start, end) seconds of the stretches loud enough to carry a voice, split at pauses of at least `min_pause` seconds."""
    hop = max(1, round(rate * .05))
    levels = np.array([np.sqrt(np.mean(chunk.astype(np.float64) ** 2)) for start in range(0, len(samples), hop)
                       if len(chunk := samples[start:start + hop])])
    if not len(levels) or levels.max() <= 0:
        return []
    active = levels >= .25 * np.percentile(levels, 95)
    phrases, begin, last = [], None, None
    for i, on in enumerate(active):
        if on:
            if begin is None:
                begin = i
            last = i
        elif begin is not None and (i - last) * hop / rate >= min_pause:
            phrases.append((begin * hop / rate, (last + 1) * hop / rate))
            begin = None
    if begin is not None:
        phrases.append((begin * hop / rate, (last + 1) * hop / rate))
    return [(a, b) for a, b in phrases if b - a >= min_length]


def music_cut_plan(samples, rate, *, duration, fps=24.0, mode="adaptive", density="auto",
                   variation=0.5, sync=1.0, seed=42, cut_every="2_beats", mood="", words=None):
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
    if mode == "phrases":
        # Words with times (a transcript) say exactly where a phrase starts and ends; without them, the loud stretches of the voice are used.
        try:
            spoken = [(a, b) for a, b in phrase_groups(parse_words(words)) if b - a >= .3] if words else []
        except ValueError as error:  # json.JSONDecodeError
            raise MajoorError(f"The words are not valid JSON: {error}") from error
        phrases = spoken or vocal_phrases(samples, rate)
        # a cut falls in the middle of each pause between two phrases
        cuts = [round((a_end + b_start) / 2 * fps) for (_, a_end), (b_start, _) in zip(phrases, phrases[1:])]
        cuts = [f for f in cuts if MIN_SHOT_FRAMES <= f <= total - MIN_SHOT_FRAMES]
        bounds = [0]
        for f in cuts:
            if f - bounds[-1] >= MIN_SHOT_FRAMES:
                bounds.append(f)
        bounds.append(total)
        bpm, beats = detect_beats(samples, rate)
        return {"fps": fps, "shots": [{"duration_frames": b - a, "prompt": "", "notes": "vocal phrase"}
                                      for a, b in zip(bounds, bounds[1:])]}, {
            "bpm": float(bpm) if bpm > 0 else None, "beat_times": [float(t) for t in beats] if bpm > 0 else [],
            "warnings": [] if phrases else ["No vocal phrase found; the whole track is one shot"],
            "timing_source": ("word_phrases" if spoken else "vocal_phrases") if phrases else "narrative"}
    if mode == "hits":
        return _hit_plan(samples, rate, total=total, fps=fps, density=density, words=words)
    if mode == "regular":
        return plan_from_music(samples, rate, duration=duration, fps=fps, cut_every=cut_every)
    if mode in ("legacy", "free"):
        raise MajoorError("Free and legacy modes use the narrative plan, not selected musical cuts")
    # Imported here because audio_events also uses timeline_sources for its text.
    from .audio_events import band_hits

    bpm, beats = detect_beats(samples, rate)
    hits = band_hits(samples, rate)
    candidates, kinds = {}, {}

    def candidate(frame, strength, kind):
        if strength > candidates.get(frame, -1):
            candidates[frame], kinds[frame] = strength, kind

    for band in ("kick", "snare"):
        for seconds, strength in hits[band]:
            candidate(round(seconds * fps), strength, "hit" if strength >= HIT else "accent")
    for seconds in beats if bpm > 0 else []:
        candidate(round(float(seconds) * fps), .25, "beat")
    if bpm > 0:
        for seconds in find_downbeats(samples, rate, beats):  # the first beat of a bar weighs more than the others
            candidate(round(float(seconds) * fps), .5, "downbeat")
        for left, right in zip(beats, beats[1:]):
            candidate(round(float(left + right) / 2 * fps), .25, "offbeat")
    sections = section_pacing(samples, rate, bpm, duration, beats if bpm > 0 else ())
    voice = vocal_phrases(samples, rate)
    for (_, end), (start, _) in zip(voice, voice[1:]):  # the pause between two phrases of the voice
        candidate(round((end + start) / 2 * fps), .6, "phrase pause")
    candidates = {f: score for f, score in candidates.items() if MIN_SHOT_FRAMES <= f <= total - MIN_SHOT_FRAMES}
    starts = sorted(round(s["start"] * fps) for before, s in zip(sections, sections[1:])  # a chapter: both sections last long enough to be heard as one
                    if min(before["end"] - before["start"], s["end"] - s["start"]) >= CHAPTER_SECONDS and MIN_SHOT_FRAMES <= round(s["start"] * fps) <= total - MIN_SHOT_FRAMES)
    # Local RMS and its change describe acoustic pacing, not a guessed emotion.
    hop = max(1, round(rate / 4))
    levels = np.array([np.sqrt(np.mean(chunk.astype(np.float64) ** 2))
                       for start in range(0, min(len(samples), math.ceil(duration * rate)), hop)
                       if len(chunk := samples[start:start + hop])])
    peak = float(np.percentile(levels, 95)) if len(levels) else 0  # the loud part of the track, not its single loudest moment
    levels = np.minimum(levels / peak, 1.0) if peak > 0 else levels
    rng = random.Random(seed)
    baseline = {"auto": 2.5, "low": 4.0, "medium": 2.5, "high": 1.25}[density]
    baseline *= {"calm": 1.35, "dreamy": 1.25, "intense": .8}.get(mood, 1)
    cuts, notes, position = [], [], 0
    phrase = []
    while total - position >= 2 * MIN_SHOT_FRAMES:
        section = next((s for s in reversed(sections) if s["start"] * fps <= position), sections[0])
        by_phrase = section["pacing"] == "phrase"
        i = min(len(levels) - 1, max(0, round(position / fps * rate / hop)))
        level = float(np.mean(levels[i:i + 4])) if len(levels) else 0  # the second ahead: one quarter of a second is too noisy to judge a passage
        previous = float(np.mean(levels[max(0, i - 4):i + 1])) if len(levels) else 0
        activity = min(1.0, .7 * level + .3 * abs(level - previous))
        target_seconds = baseline * (1.7 - 1.1 * activity if mode == "adaptive" else 1)
        target_seconds *= math.exp(rng.uniform(-1, 1) * variation * .8)
        if by_phrase:  # no bursts on an invented grid: longer shots, cut where the music or the voice turns
            target_seconds *= PHRASE_HOLD
            phrase = []
        if (not by_phrase and not phrase and bpm > 0 and variation > 0
                and (mode == "random" or activity >= BURST_ACTIVITY)
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
        turn = next((f for f in starts if position + MIN_SHOT_FRAMES <= f <= target + 2 * MIN_SHOT_FRAMES), None)  # never step over a section start, never swallow a cut to reach it
        if turn is not None:  # a new section opens a new chapter: its first frame is a cut
            opened = next(s for s in sections if round(s["start"] * fps) == turn)
            target, kind = turn, "start of the " + opened["tag"]
            if opened["pacing"] == "phrase":  # the rest of a burst carries on into a section cut on the beat, not into one cut by phrases
                phrase = []
        else:
            eligible = [(f, strength) for f, strength in candidates.items()
                        if f >= position + MIN_SHOT_FRAMES and total - f >= MIN_SHOT_FRAMES
                        and abs(f - target) <= radius and (not by_phrase or strength >= .5)]
            offbeats = [item for item in eligible if kinds[item[0]] == "offbeat"]
            kind = "free"
            if offbeats and not by_phrase and not phrased and sync > 0 and rng.random() < SYNCOPATION * variation:
                target = min(offbeats, key=lambda item: abs(item[0] - target))[0]  # a syncopation, on purpose
                kind = "offbeat"
            elif eligible and sync > 0:
                target = max(eligible, key=lambda item: sync * item[1] - abs(item[0] - target) / radius)[0]
                kind = kinds[target]
        cuts.append(target)
        notes.append(_pacing_note(next((s for s in reversed(sections) if s["start"] * fps <= target), sections[0]), kind))
        position = target
    warnings = []
    if not candidates:
        warnings.append("No reliable musical accents; using varied narrative timing without a beat grid")
    bounds = [0, *cuts, total]
    # each shot says where it sits in the music and what its first frame lands on, for the planner: a hit is worth a flash or a punch, a pulse only a cut
    opening = [_pacing_note(sections[0], "free"), *notes]
    return {"fps": fps, "shots": [{"duration_frames": b - a, "prompt": "", "notes": f"{mode} music pacing; {note}"}
                                  for (a, b), note in zip(zip(bounds, bounds[1:]), opening)]}, {
        "bpm": float(bpm) if bpm > 0 else None, "beat_times": [float(t) for t in beats] if bpm > 0 else [], "warnings": warnings,
        "timing_source": "measured_accents" if candidates else "narrative",
        "sections": [{k: s[k] for k in ("tag", "start", "end", "pacing", "pulse")} for s in sections],
    }


def hit_candidates(samples, rate, words=None) -> list[tuple[float, float, str]]:
    """(seconds, strength, kind) of everything a cut can land on: the kicks, the snares, the entries of the bass, the starts of the voice (words with their times when
    there are some, else the bursts of voice), and the start of each section. Hits within HIT_MERGE of each other are one: the strongest names it."""
    from .audio_events import band_hits, bass_hits
    found = [(t, x, band) for band, rows in band_hits(samples, rate).items() if band in ("kick", "snare") for t, x in rows]
    found += [(t, x, "bass") for t, x in bass_hits(samples, rate)]
    spoken = []
    if words:
        try:
            spoken = [(w["start"], WORD_START, "word") for w in parse_words(words)]
        except ValueError as error:
            raise MajoorError(f"The words are not valid JSON: {error}") from error
    found += spoken or [(a, VOICE_BURST, "voice") for a, _ in vocal_phrases(samples, rate, min_pause=.12, min_length=.1)]
    found += [(s["start"], 1.0, "start of the " + s["tag"]) for s in track_sections(np.asarray(samples), rate)[1:]]
    sharp = [(t, x, k) for t, x, k in found if k != "bass"]
    found = sharp + [(t, x, k) for t, x, k in found if k == "bass" and not any(abs(t - other) < BASS_WITH_HIT for other, _, _ in sharp)]  # a bass that comes in with a kick is that kick
    found = [(t, max([x, *[y for u, y, k in found if k == "bass" and abs(t - u) < BASS_WITH_HIT]]) if kind in ("kick", "snare") else x, kind) for t, x, kind in found]
    merged = []
    for time, strength, kind in sorted(found):
        if merged and time - merged[-1][0] < HIT_MERGE:
            if strength > merged[-1][1]:
                merged[-1] = (merged[-1][0], strength, kind)
            continue
        merged.append((time, strength, kind))
    return merged


def _hit_plan(samples, rate, *, total, fps, density, words):
    """A cut on the hits themselves: every kick, bass entry, snare or word the cut pace keeps, strongest first, never two closer than the pace allows."""
    weakest, gap_seconds = HIT_PACE[density]
    gap = max(MIN_SHOT_FRAMES, round(gap_seconds * fps))
    chosen = []
    found = hit_candidates(samples, rate, words)
    for voice in (False, True):  # the music first, then the voice in what is left
        for time, strength, kind in sorted((row for row in found if (row[2] in VOICE_KINDS) == voice), key=lambda row: -row[1]):
            frame = round(time * fps)
            if strength < weakest or not MIN_SHOT_FRAMES <= frame <= total - MIN_SHOT_FRAMES:
                continue
            if all(abs(frame - other) >= gap for other, _ in chosen):
                chosen.append((frame, kind))
    chosen.sort()
    bounds = [0, *[frame for frame, _ in chosen], total]
    kinds = ["", *[kind for _, kind in chosen]]
    bpm, beats = detect_beats(samples, rate)
    return {"fps": fps, "shots": [{"duration_frames": b - a, "prompt": "", "notes": "hit sync" + (f"; starts on {'an' if kind[0] in 'aeiou' else 'a'} {kind}" if kind else "")}
                                  for (a, b), kind in zip(zip(bounds, bounds[1:]), kinds)]}, {
        "bpm": float(bpm) if bpm > 0 else None, "beat_times": [float(t) for t in beats] if bpm > 0 else [],
        "warnings": [] if chosen else ["No hit found; the whole track is one shot"], "timing_source": "hits" if chosen else "narrative"}


def _pacing_note(section, kind):
    """The note of a shot: the section it opens in, how that section is cut, and what its first frame lands on."""
    pacing = "cut by phrases" if section["pacing"] == "phrase" else "cut on the beat"
    if kind == "free":
        return f"{section['tag']}, {pacing}"
    if kind.startswith("start"):
        return f"{section['tag']}, {pacing}; opens the {section['tag']}"
    return f"{section['tag']}, {pacing}; starts on {'an' if kind[0] in 'aeiou' else 'a'} {kind}"


def burst_takes(plan: dict) -> dict:
    """The plan with the cuts too short to be a generation of their own joined into takes of at least `MIN_TAKE_FRAMES`, their cuts kept as sub-cuts: a burst is one generation, cut up."""
    rows, shots, at = plan["shots"], [], 0
    for group in group_cuts([row["duration_frames"] for row in rows], MIN_TAKE_FRAMES):
        row = {**rows[at], "duration_frames": sum(group)}
        if len(group) > 1:
            row["sub_cuts"] = [{"duration_frames": n} for n in group]
        shots.append(row)
        at += len(group)
    return {**plan, "shots": shots}


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
