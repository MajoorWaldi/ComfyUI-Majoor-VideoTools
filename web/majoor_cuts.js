// Majoor VideoTools - Cut Markers editor.
//
// A timeline in the node: the waveform of the music, its beats, the cuts of the video and your markers. Run the node once to load
// the media (the backend sends "majoor_cuts", see nodes/cut_markers.py), then edit:
//   click / drag on the timeline = move the playhead      double-click, M, "+ marker" = add a marker
//   drag a marker = move it (it sticks to the beats)      right-click, Delete = remove it
//   wheel = zoom, shift + wheel = pan                     Space = play / pause      Alt while dragging = no snap
// The markers are written, as seconds, in the `markers` text of the node.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyle, el, growTo, mountWidget } from "./majoor_videotools.js";
import * as L from "./majoor_cuts_logic.js";

const NODE = "MajoorCutMarkers";
const PROP = "majoor_cuts_ui";
const CANVAS_HEIGHT = 170;

const CSS = `
.mjr-cuts { gap: 4px; outline: none; }
.mjr-cuts .mjr-video { flex: 0 0 auto; max-height: 220px; }
.mjr-cutbar { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.mjr-cutbar button, .mjr-cutbar select { height: 22px; padding: 0 6px; background: var(--comfy-input-bg, #222); color: inherit; border: 1px solid var(--border-color, #444); border-radius: 4px; font: inherit; font-size: 11px; cursor: pointer; }
.mjr-cutbar button:hover { filter: brightness(1.3); }
.mjr-cutbar .mjr-time { margin-left: auto; font-variant-numeric: tabular-nums; opacity: .8; }
.mjr-cutcanvas { width: 100%; height: ${CANVAS_HEIGHT}px; flex: 0 0 ${CANVAS_HEIGHT}px; background: #1b1b1b; border: 1px solid var(--border-color, #444); border-radius: 4px; cursor: crosshair; touch-action: none; }
`;

function addCutsStyle() {
  if (document.getElementById("mjr-cuts-style")) return;
  const style = document.createElement("style");
  style.id = "mjr-cuts-style";
  style.textContent = CSS;
  document.head.appendChild(style);
}

const mediaURL = (ref) => api.apiURL(`/view?${new URLSearchParams({ filename: ref.file, subfolder: ref.folder ?? "", type: ref.kind })}`);
const widgetOf = (node, name) => node.widgets?.find((w) => w.name === name);

const SNAPS = [["off", "no snap"], ["frame", "snap: frame"], ["half_beat", "snap: half beat"], ["beat", "snap: beat"], ["bar", "snap: bar"], ["video_cuts", "snap: video cuts"]];
const FILLS = [["", "Fill from…"], ["beats:half", "beats · every half beat"], ["beats:1", "beats · every beat"], ["beats:2", "beats · every 2 beats"], ["beats:bar", "beats · every bar"],
  ["beats:2_bars", "beats · every 2 bars"], ["beats:4_bars", "beats · every 4 bars"], ["video", "video cuts"]];

function setupCuts(node) {
  addStyle();
  addCutsStyle();
  const root = el("div", "mjr-root mjr-cuts");
  root.tabIndex = 0;
  const video = el("video", "mjr-video");
  video.playsInline = true;
  video.preload = "auto";
  video.style.display = "none";
  const audio = el("audio");
  audio.preload = "auto";
  const bar = el("div", "mjr-cutbar");
  const button = (text, title, onClick) => {
    const b = el("button", null, text);
    b.type = "button";
    b.title = title;
    b.addEventListener("click", onClick);
    return b;
  };
  const select = (options, onChange) => {
    const s = el("select");
    for (const [value, label] of options) {
      const o = el("option", null, label);
      o.value = value;
      s.appendChild(o);
    }
    s.addEventListener("change", () => onChange(s.value));
    return s;
  };
  const playBtn = button("▶", "Play / pause (Space)", () => toggle());
  const addBtn = button("+ marker", "Add a marker at the playhead (M)", () => addAtHead());
  const snapSel = select(SNAPS, (v) => { snapMode = v; });
  const fillSel = select(FILLS, (v) => { fill(v); fillSel.value = ""; });
  const undoBtn = button("↶", "Undo (Ctrl+Z)", () => undo());
  const clearBtn = button("Clear", "Remove every marker", () => commit([]));
  const fitBtn = button("Fit", "Show the whole timeline", () => { if (view) { view.fit(); draw(); } });
  const zoomIn = button("+", "Zoom in", () => zoomBy(0.6));
  const zoomOut = button("−", "Zoom out", () => zoomBy(1 / 0.6));
  const timeLabel = el("span", "mjr-time", "00:00.00");
  bar.append(playBtn, addBtn, snapSel, fillSel, undoBtn, clearBtn, fitBtn, zoomOut, zoomIn, timeLabel);
  const canvas = el("canvas", "mjr-cutcanvas");
  const info = el("div", "mjr-info", "Run the node once to load the video and the music, then place the cuts.");
  root.append(video, audio, bar, canvas, info);
  mountWidget(node, "cuts_editor", root, () => (payload?.video ? 230 : 0) + 34 + CANVAS_HEIGHT + 56);

  let payload = null;
  let markers = [];
  let selected = -1;
  let view = null;
  let head = 0;
  let snapMode = "off";
  let drag = null;
  let raf = 0;
  const undoStack = [];

  const fps = () => payload?.fps || 24;
  const duration = () => payload?.duration || 0;
  const markersWidget = () => widgetOf(node, "markers");
  const ctx = () => ({ beats: payload?.beats ?? [], bpb: payload?.beats_per_bar ?? 4, downbeat: payload?.downbeat ?? 0, videoCuts: payload?.video_cuts ?? [], fps: fps() });
  // the video is the clock when there is one (a music can be shorter than the edit); the music follows it while it lasts
  const master = () => (payload?.video ? video : payload?.audio ? audio : null);
  const audioLength = () => (Number.isFinite(audio.duration) ? audio.duration : Infinity);

  // ---- markers <-> the text widget ----------------------------------------------------------------------------------
  const writeWidget = () => {
    const w = markersWidget();
    if (!w) return;
    w.value = L.formatMarkers(markers);
    w.callback?.(w.value);
    app.graph?.setDirtyCanvas(true, true);
  };
  const commit = (next, keep = -1) => {
    if (JSON.stringify(next) === JSON.stringify(markers)) return;
    undoStack.push(markers);
    if (undoStack.length > 60) undoStack.shift();
    markers = next;
    selected = keep;
    writeWidget();
    summary();
    draw();
  };
  const undo = () => {
    if (!undoStack.length) return;
    markers = undoStack.pop();
    selected = -1;
    writeWidget();
    summary();
    draw();
  };
  const readWidget = () => {
    markers = L.parseMarkers(markersWidget()?.value ?? "", fps());
    selected = -1;
    summary();
    draw();
  };
  const minShot = () => Number(widgetOf(node, "min_shot_seconds")?.value) || 1;
  const summary = () => {
    if (!payload) return;
    const plan = L.planPreview(markers, duration(), fps(), minShot());
    const media = [payload.audio && `music ${payload.bpm || "?"} BPM`, payload.video && `video, ${payload.video_cuts.length} cuts detected`].filter(Boolean).join(" · ");
    info.textContent = `${markers.length} markers → ${plan.cuts} cuts → ${plan.shots.length} shots (cuts under ${minShot()} s are grouped)${media ? `\n${media}` : ""}`;
    growTo(node, node.computeSize()[1]);
  };

  // ---- time and playback --------------------------------------------------------------------------------------------
  const seek = (t) => {
    head = Math.min(Math.max(t, 0), duration());
    if (payload?.audio) audio.currentTime = Math.min(head, audioLength());
    if (payload?.video) video.currentTime = head;
    timeLabel.textContent = L.formatTime(head);
    draw();
  };
  const playing = () => !!master() && !master().paused;
  const stopped = () => { if (playBtn.textContent !== "▶") pause(); };
  video.addEventListener("ended", stopped);
  audio.addEventListener("ended", () => { if (master() === audio) stopped(); });
  const tick = () => {
    const m = master();
    if (!m) return;
    head = m.currentTime;
    if (payload.audio && payload.video) {
      if (head < audioLength() - 0.05) {
        if (audio.paused) audio.play().catch(() => {});
        if (Math.abs(audio.currentTime - head) > 0.08) audio.currentTime = head;
      } else if (!audio.paused) audio.pause();
    }
    if (head >= duration() - 0.02) pause();
    if (view) view.reveal(head);
    timeLabel.textContent = L.formatTime(head);
    draw();
    raf = playing() ? requestAnimationFrame(tick) : 0;
  };
  function toggle() {
    playing() ? pause() : play();
  }
  function play() {
    const m = master();
    if (!m) return;
    if (head >= duration() - 0.05) seek(0);
    if (payload.audio && payload.video) {
      video.muted = true;
      video.currentTime = head;
      if (head < audioLength()) {
        audio.currentTime = head;
        audio.play().catch(() => {});
      }
    }
    m.play().catch(() => {});
    playBtn.textContent = "❚❚";
    if (!raf) raf = requestAnimationFrame(tick);
  }
  function pause() {
    audio.pause();
    video.pause();
    playBtn.textContent = "▶";
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
  }
  const addAtHead = () => commit(L.addMarker(markers, head, duration(), fps()));
  const zoomBy = (f) => {
    if (!view) return;
    view.zoomAt(head >= view.start && head <= view.start + view.span ? head : view.start + view.span / 2, f);
    draw();
  };
  const fill = (what) => {
    if (!payload || !what) return;
    if (what === "video") return commit(L.markersFromVideoCuts(payload.video_cuts, duration()));
    const every = what.split(":")[1];
    commit(L.markersFromBeats(payload.beats, every, { bpb: payload.beats_per_bar, downbeat: payload.downbeat, duration: duration() }));
  };

  // ---- drawing ------------------------------------------------------------------------------------------------------
  const resize = () => {
    const width = Math.max(Math.floor(canvas.clientWidth || node.size[0] - 24), 100);
    const ratio = window.devicePixelRatio || 1;
    if (canvas.width !== Math.floor(width * ratio)) {
      canvas.width = Math.floor(width * ratio);
      canvas.height = Math.floor(CANVAS_HEIGHT * ratio);
    }
    if (view) view.width = width;
    return [width, ratio];
  };
  function draw() {
    const g = canvas.getContext?.("2d");
    if (!g) return;
    const [W, ratio] = resize();
    g.setTransform(ratio, 0, 0, ratio, 0, 0);
    g.clearRect(0, 0, W, CANVAS_HEIGHT);
    if (!payload || !view) {
      g.fillStyle = "#888";
      g.font = "12px sans-serif";
      g.fillText("Run the node once to load the media.", 12, 24);
      return;
    }
    const mid = 74;
    const top = 18;
    const t0 = view.start;
    const t1 = view.start + view.span;
    const shots = L.planPreview(markers, duration(), fps(), minShot()).shots;
    // planned shots (strip at the bottom) and their cuts
    shots.forEach((s, i) => {
      if (s.end < t0 || s.start > t1) return;
      const x0 = view.toX(s.start);
      const x1 = view.toX(s.end);
      g.fillStyle = i % 2 ? "rgba(74,144,226,.20)" : "rgba(74,144,226,.12)";
      g.fillRect(x0, 128, x1 - x0, 24);
      g.fillStyle = "#9bc4f4";
      g.font = "10px sans-serif";
      if (x1 - x0 > 22) g.fillText(`#${i + 1}`, x0 + 4, 143);
      let at = s.start;
      for (const c of s.cuts.slice(0, -1)) {
        at += c;
        g.fillStyle = "rgba(255,255,255,.35)";
        g.fillRect(view.toX(at), 128, 1, 24);
      }
    });
    // waveform
    if (payload.peaks?.length) {
      g.fillStyle = "rgba(74,144,226,.75)";
      const n = payload.peaks.length;
      for (let x = 0; x < W; x++) {
        const i = Math.min(Math.floor((view.toT(x) / duration()) * n), n - 1);
        if (i < 0) continue;
        const h = Math.max(payload.peaks[i] * 44, 1);
        g.fillRect(x, mid - h, 1, h * 2);
      }
    }
    // beats and bars
    const beats = payload.beats ?? [];
    const bpb = payload.beats_per_bar || 4;
    const dense = beats.length > 1 && (view.toX(beats[1]) - view.toX(beats[0])) > 5;
    beats.forEach((b, i) => {
      if (b < t0 || b > t1) return;
      const bar = ((i - payload.downbeat) % bpb + bpb) % bpb === 0;
      if (!bar && !dense) return;
      g.fillStyle = bar ? "rgba(255,255,255,.35)" : "rgba(255,255,255,.12)";
      g.fillRect(Math.round(view.toX(b)), top, 1, 106);
    });
    // detected cuts of the video
    g.fillStyle = "#e2a34a";
    for (const c of payload.video_cuts ?? []) {
      if (c < t0 || c > t1) continue;
      const x = Math.round(view.toX(c));
      g.fillRect(x, 0, 1, 14);
      g.fillRect(x - 2, 0, 5, 3);
    }
    // ruler
    const step = L.tickStep(view.span);
    g.fillStyle = "#999";
    g.font = "10px sans-serif";
    for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) {
      const x = Math.round(view.toX(t));
      g.fillRect(x, 154, 1, 6);
      g.fillText(L.formatTime(t).replace(/^00:/, ""), x + 3, 166);
    }
    // markers
    markers.forEach((m, i) => {
      if (m < t0 || m > t1) return;
      const x = Math.round(view.toX(m));
      g.fillStyle = i === selected ? "#ffffff" : "#4ae28a";
      g.fillRect(x, top, 2, 134);
      g.beginPath();
      g.moveTo(x - 6, top);
      g.lineTo(x + 8, top);
      g.lineTo(x + 1, top + 10);
      g.fill();
    });
    // playhead
    const hx = Math.round(view.toX(head));
    if (hx >= 0 && hx <= W) {
      g.fillStyle = "#ff5a4d";
      g.fillRect(hx, 0, 2, CANVAS_HEIGHT - 22);
    }
  }

  // ---- the mouse and the keyboard -----------------------------------------------------------------------------------
  // pixels of the timeline: the graph canvas can be zoomed, which scales the node on the screen but not canvas.clientWidth
  const position = (e) => {
    const r = canvas.getBoundingClientRect();
    const k = r.width && canvas.clientWidth ? canvas.clientWidth / r.width : 1;
    return (e.clientX - r.left) * k;
  };
  const snapped = (t, e) => (e.altKey ? t : L.snapTime(t, snapMode, ctx(), (view.span / view.width) * 10));
  canvas.addEventListener("pointerdown", (e) => {
    if (!view || e.button !== 0) return;
    root.focus();
    canvas.setPointerCapture?.(e.pointerId);
    const x = position(e);
    const hit = L.hitMarker(markers, x, view);
    if (hit >= 0) {
      selected = hit;
      drag = { kind: "marker", index: hit, before: markers };
    } else {
      selected = -1;
      drag = { kind: "scrub" };
      seek(view.toT(x));
    }
    draw();
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!view) return;
    const x = position(e);
    if (!drag) {
      canvas.style.cursor = L.hitMarker(markers, x, view) >= 0 ? "ew-resize" : "crosshair";
      return;
    }
    if (drag.kind === "scrub") return seek(view.toT(x));
    const moved = L.moveMarker(markers, drag.index, snapped(view.toT(x), e), duration());
    markers = moved.markers;
    drag.index = selected = moved.index;
    draw();
  });
  const release = () => {
    if (drag?.kind === "marker") {
      const final = markers;
      markers = drag.before;
      commit(final, selected);
    }
    drag = null;
  };
  canvas.addEventListener("pointerup", release);
  canvas.addEventListener("pointercancel", release);
  canvas.addEventListener("dblclick", (e) => {
    if (!view || L.hitMarker(markers, position(e), view) >= 0) return;
    const t = snapped(view.toT(position(e)), e);
    commit(L.addMarker(markers, t, duration(), fps()));
  });
  canvas.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    if (!view) return;
    const hit = L.hitMarker(markers, position(e), view);
    if (hit >= 0) commit(L.removeMarker(markers, hit));
  });
  // the graph canvas listens to the wheel before the widgets do: take it earlier, at the window, when it is over the timeline
  const onWheel = (e) => {
    if (!view || e.target !== canvas) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.shiftKey) view.pan((e.deltaY / view.width) * view.span);
    else view.zoomAt(view.toT(position(e)), e.deltaY > 0 ? 1.25 : 0.8);
    draw();
  };
  window.addEventListener?.("wheel", onWheel, { capture: true, passive: false });
  root.addEventListener("keydown", (e) => {
    if (e.target?.tagName === "TEXTAREA" || e.target?.tagName === "INPUT") return;
    const key = e.key;
    const step = (e.shiftKey ? 1 : 1 / fps());
    let used = true;
    if (key === " ") toggle();
    else if (key === "m" || key === "M") addAtHead();
    else if ((key === "Delete" || key === "Backspace") && selected >= 0) commit(L.removeMarker(markers, selected));
    else if (key === "ArrowLeft") seek(head - step);
    else if (key === "ArrowRight") seek(head + step);
    else if ((e.ctrlKey || e.metaKey) && (key === "z" || key === "Z")) undo();
    else used = false;
    if (used) {
      e.preventDefault();
      e.stopPropagation();
    }
  });
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(() => draw()).observe(root);

  // ---- loading what the backend sent --------------------------------------------------------------------------------
  node._mjrCuts = (p) => {
    pause();
    payload = p;
    const total = p.duration;
    view = new L.View(total, canvas.clientWidth || node.size[0] - 24);
    video.style.display = p.video ? "" : "none";
    video.muted = !!p.audio;
    const loadInto = (element, ref) => {
      const url = ref ? mediaURL(ref) : "";
      if (url && element.dataset.src !== url) {
        element.dataset.src = url;
        element.src = url;
      } else if (!url) {
        element.removeAttribute("src");
      }
    };
    loadInto(video, p.video);
    loadInto(audio, p.audio);
    if (snapMode === "off") {
      snapMode = (p.beats?.length ? "beat" : "frame");
      snapSel.value = snapMode;
    }
    readWidget();
    seek(Math.min(head, total));
    growTo(node, node.computeSize()[1]);
  };
  const widget = markersWidget();
  if (widget) {
    const previous = widget.callback;
    widget.callback = function (value) {
      const r = previous?.apply(this, arguments);
      if (payload && L.formatMarkers(markers) !== L.formatMarkers(L.parseMarkers(value, fps()))) readWidget();
      return r;
    };
  }
  node.onRemoved = ((prev) => function () {
    pause();
    window.removeEventListener?.("wheel", onWheel, { capture: true });
    video.removeAttribute("src");
    audio.removeAttribute("src");
    return prev?.apply(this, arguments);
  })(node.onRemoved);
}

app.registerExtension({
  name: "Majoor.CutMarkers",
  nodeCreated(node) {
    if (node.comfyClass === NODE) setupCuts(node);
  },
  loadedGraphNode(node) {
    if (node.comfyClass === NODE && node.properties?.[PROP]) node._mjrCuts?.(node.properties[PROP]);
  },
  setup() {
    api.addEventListener("executed", ({ detail }) => {
      const payload = detail?.output?.majoor_cuts?.[0];
      if (!payload) return;
      const node = app.graph?.getNodeById(detail.display_node ?? detail.node);
      if (node?.comfyClass !== NODE) return;
      node.properties = node.properties || {};
      node.properties[PROP] = payload;
      node._mjrCuts?.(payload);
    });
  },
});
