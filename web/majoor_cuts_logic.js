// Majoor VideoTools - Cut Markers: the logic of the timeline editor, without any DOM (tested by tests/web/cuts.mjs).
// Times are seconds. The text format of the markers is the one core/cut_markers.py reads.

const MIN_GAP = 1e-3;

// ---- the text of the markers ------------------------------------------------------------------------------------------

function toSeconds(token, fps) {
  let t = token.trim().toLowerCase();
  if (/^[0-9.]+f$/.test(t)) return parseFloat(t) / fps; // 36f
  if (t.endsWith("s")) t = t.slice(0, -1);
  const parts = t.split(":");
  if (parts.length > 3) return NaN;
  return parts.reduce((total, p) => total * 60 + Number(p), 0);
}

export function parseMarkers(text, fps = 24) {
  const found = new Set();
  for (const token of String(text ?? "").trim().split(/[\s,;]+/)) {
    if (!token) continue;
    const s = toSeconds(token, fps);
    if (Number.isFinite(s) && s > 0) found.add(Math.round(s * 1e4) / 1e4);
  }
  return [...found].sort((a, b) => a - b);
}

export function formatMarkers(times) {
  return [...times].sort((a, b) => a - b).map((t) => (Math.round(t * 1000) / 1000).toString()).join(" ");
}

// ---- the visible part of the timeline ---------------------------------------------------------------------------------

export class View {
  constructor(duration, width) {
    this.duration = Math.max(duration, 0.1);
    this.width = Math.max(width, 1);
    this.start = 0;
    this.span = this.duration;
  }

  fit() {
    this.start = 0;
    this.span = this.duration;
  }

  toX(t) {
    return ((t - this.start) / this.span) * this.width;
  }

  toT(x) {
    return this.start + (x / this.width) * this.span;
  }

  clamp() {
    this.span = Math.min(Math.max(this.span, 0.25), this.duration);
    this.start = Math.min(Math.max(this.start, 0), this.duration - this.span);
  }

  zoomAt(t, factor) {
    const ratio = (t - this.start) / this.span;
    this.span *= factor;
    this.span = Math.min(Math.max(this.span, 0.25), this.duration);
    this.start = t - ratio * this.span;
    this.clamp();
  }

  pan(dt) {
    this.start += dt;
    this.clamp();
  }

  reveal(t) {
    if (t < this.start || t > this.start + this.span) {
      this.start = t - this.span * 0.1;
      this.clamp();
    }
  }
}

// ---- snapping ---------------------------------------------------------------------------------------------------------

// The times a marker can stick to for one snap mode.
export function snapPoints(mode, { beats = [], bpb = 4, downbeat = 0, videoCuts = [] } = {}) {
  if (mode === "beat") return beats;
  if (mode === "half_beat") return beats.flatMap((b, i) => (i + 1 < beats.length ? [b, (b + beats[i + 1]) / 2] : [b]));
  if (mode === "bar") return beats.filter((_, i) => ((i - downbeat) % bpb + bpb) % bpb === 0);
  if (mode === "video_cuts") return videoCuts;
  return [];
}

export function snapTime(t, mode, ctx = {}, thresholdSeconds = 0.15) {
  if (mode === "off") return t;
  if (mode === "frame") return Math.round(t * (ctx.fps || 24)) / (ctx.fps || 24);
  let best = t;
  let gap = thresholdSeconds;
  for (const p of snapPoints(mode, ctx)) {
    const d = Math.abs(p - t);
    if (d < gap) {
      best = p;
      gap = d;
    }
  }
  return best;
}

// ---- editing the markers ----------------------------------------------------------------------------------------------

const clean = (list) => [...new Set(list.map((t) => Math.round(t * 1e4) / 1e4))].sort((a, b) => a - b);

export function addMarker(markers, t, duration, fps = 24) {
  if (!(t > 0) || t >= duration) return markers;
  if (markers.some((m) => Math.abs(m - t) < Math.max(MIN_GAP, 0.5 / fps))) return markers;
  return clean([...markers, t]);
}

export function moveMarker(markers, index, t, duration) {
  const others = markers.filter((_, i) => i !== index);
  const lo = 0.5 / 24;
  const clamped = Math.min(Math.max(t, lo), duration - lo);
  if (others.some((m) => Math.abs(m - clamped) < MIN_GAP)) return { markers, index };
  const next = clean([...others, clamped]);
  return { markers: next, index: next.indexOf(Math.round(clamped * 1e4) / 1e4) };
}

export function removeMarker(markers, index) {
  return markers.filter((_, i) => i !== index);
}

// The index of the marker under x (pixels), nearest first, or -1.
export function hitMarker(markers, x, view, tolerance = 6) {
  let best = -1;
  let gap = tolerance;
  markers.forEach((m, i) => {
    const d = Math.abs(view.toX(m) - x);
    if (d <= gap) {
      best = i;
      gap = d;
    }
  });
  return best;
}

// ---- filling the markers from the music or the video ----------------------------------------------------------------

// Cuts every `every` beats ('half' = every half beat, 'bar' = every bar), from the first bar of the music.
export function markersFromBeats(beats, every, { bpb = 4, downbeat = 0, duration = Infinity } = {}) {
  const start = Math.min(Math.max(downbeat, 0), Math.max(beats.length - 1, 0));
  const grid = beats.slice(start);
  let picked;
  if (every === "half") picked = snapPoints("half_beat", { beats: grid });
  else {
    const step = every === "bar" ? bpb : every === "2_bars" ? 2 * bpb : every === "4_bars" ? 4 * bpb : Number(every) || 1;
    picked = grid.filter((_, i) => i % step === 0);
  }
  return clean(picked.filter((t) => t > MIN_GAP && t < duration - MIN_GAP));
}

export function markersFromVideoCuts(cuts, duration = Infinity) {
  return clean(cuts.filter((t) => t > MIN_GAP && t < duration - MIN_GAP));
}

// ---- what the markers will make (same rules as core/cut_markers.py + core/timeline_sources.py) -------------------------

const SUB_MIN_FRAMES = 3;
const MIN_SHOT_FRAMES = 6;

export function planPreview(markers, duration, fps = 24, minShotSeconds = 1) {
  const total = Math.max(Math.round(duration * fps), 1);
  const cuts = [...new Set(markers.map((t) => Math.round(t * fps)).filter((f) => f > 0 && f < total))].sort((a, b) => a - b);
  const bounds = [0, ...cuts, total];
  for (;;) { // merge_short_shots: drop a cut that would make a shot shorter than 3 frames
    if (bounds.length <= 2) break;
    const lengths = bounds.slice(1).map((b, i) => b - bounds[i]);
    const i = lengths.findIndex((n) => n < SUB_MIN_FRAMES);
    if (i < 0) break;
    bounds.splice(i === 0 ? i + 1 : i, 1);
  }
  const lengths = bounds.slice(1).map((b, i) => b - bounds[i]);
  const minShot = Math.max(Math.round(minShotSeconds * fps), MIN_SHOT_FRAMES);
  const groups = [];
  let current = [];
  for (const n of lengths) { // group_cuts: short cuts in a row become one shot
    current.push(n);
    if (current.reduce((a, b) => a + b, 0) >= minShot) {
      groups.push(current);
      current = [];
    }
  }
  if (current.length) {
    if (groups.length) groups[groups.length - 1].push(...current);
    else groups.push(current);
  }
  let at = 0;
  const shots = groups.map((g) => {
    const frames = g.reduce((a, b) => a + b, 0);
    const shot = { start: at / fps, end: (at + frames) / fps, cuts: g.map((n) => n / fps) };
    at += frames;
    return shot;
  });
  return { shots, cuts: lengths.length };
}

// ---- time labels ------------------------------------------------------------------------------------------------------

export function formatTime(t, fps = 24) {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${String(m).padStart(2, "0")}:${s.toFixed(2).padStart(5, "0")}`;
}

// A round step (1, 2, 5, 10... seconds) giving about `target` ticks over `span`.
export function tickStep(span, target = 8) {
  const raw = span / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 5, 10]) if (m * mag >= raw) return m * mag;
  return 10 * mag;
}
