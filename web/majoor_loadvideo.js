// Majoor VideoTools - Load Video Advanced widget.
//
// Shows the loaded file with a crop box (drag the box or its corners) and a trim bar (drag the two ends). Both write
// into the node's own widgets (start_time, duration, crop_*), so the node works the same without this file.
// "Add frame" appends the frame under the playhead to the `frames` text; a frame number counts from the trim start.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyle, el, fmt, growTo, mountWidget } from "./majoor_videotools.js";
import { fileURL, parseAnnotated } from "./majoor_media.js";

const LOAD = "MajoorLoadVideoAdvanced";
const MIN_CROP = 8;
// the start is cut to the millisecond downwards: rounded up it could fall after the frame it names and skip it
const floorMs = (seconds) => Math.floor(seconds * 1000 + 1e-6) / 1000;

const STYLE = `
.mjr-crop { position: absolute; box-sizing: border-box; border: 1px solid #fff; box-shadow: 0 0 0 9999px rgba(0, 0, 0, .55); cursor: move; touch-action: none; }
.mjr-crop i { position: absolute; width: 12px; height: 12px; background: #4a90e2; border: 1px solid #fff; box-sizing: border-box; }
.mjr-crop i[data-h=nw] { left: -6px; top: -6px; cursor: nwse-resize; }
.mjr-crop i[data-h=ne] { right: -6px; top: -6px; cursor: nesw-resize; }
.mjr-crop i[data-h=sw] { left: -6px; bottom: -6px; cursor: nesw-resize; }
.mjr-crop i[data-h=se] { right: -6px; bottom: -6px; cursor: nwse-resize; }
.mjr-range { position: absolute; top: 0; bottom: 0; background: rgba(74, 144, 226, .35); border-left: 4px solid #4a90e2; border-right: 4px solid #4a90e2; box-sizing: border-box; pointer-events: none; }
.mjr-grip { position: absolute; top: 0; bottom: 0; width: 12px; margin-left: -6px; cursor: ew-resize; touch-action: none; }
.mjr-bar { touch-action: none; cursor: pointer; }
.mjr-buttons { display: flex; gap: 6px; }
.mjr-buttons button { flex: 1 1 auto; height: 22px; padding: 0 6px; background: var(--comfy-input-bg, #222); color: inherit; border: 1px solid var(--border-color, #444); border-radius: 4px; cursor: pointer; font: inherit; }
`;

function setupLoad(node) {
  addStyle();
  if (!document.getElementById("mjr-load-style")) {
    const style = el("style");
    style.id = "mjr-load-style";
    style.textContent = STYLE;
    document.head.appendChild(style);
  }

  const root = el("div", "mjr-root");
  const stage = el("div", "mjr-stage");
  const video = el("video", "mjr-video");
  video.muted = true;
  video.preload = "auto";
  video.playsInline = true;
  const box = el("div", "mjr-crop");
  for (const h of ["nw", "ne", "sw", "se"]) {
    const grip = el("i");
    grip.dataset.h = h;
    box.append(grip);
  }
  stage.append(video, box);

  const bar = el("div", "mjr-bar");
  const range = el("div", "mjr-range");
  const head = el("div", "mjr-head");
  const gripA = el("div", "mjr-grip");
  const gripB = el("div", "mjr-grip");
  bar.append(range, head, gripA, gripB);

  const controls = el("div", "mjr-controls");
  const play = el("button", null, "▶");
  const back = el("button", null, "◀");
  const next = el("button", null, "▶|");
  for (const b of [play, back, next]) b.type = "button";
  const clock = el("span", null, "");
  controls.append(play, back, next, clock);

  const buttons = el("div", "mjr-buttons");
  const addFrame = el("button", null, "Add frame");
  const resetCrop = el("button", null, "Reset crop");
  const resetTrim = el("button", null, "Reset trim");
  for (const b of [addFrame, resetCrop, resetTrim]) b.type = "button";
  buttons.append(addFrame, resetCrop, resetTrim);

  const text = el("div", "mjr-info", "Pick a video file.");
  root.append(stage, bar, controls, buttons, text);

  let info = null; // { width, height, fps, duration, frames } from /majoor/video_info
  const widget = (name) => node.widgets?.find((x) => x.name === name);
  const get = (name) => Number(widget(name)?.value) || 0;
  const put = (name, value) => {
    const x = widget(name);
    if (x) x.value = value;
  };

  const fps = () => info?.fps || 24;
  const total = () => info?.duration || video.duration || 0;
  const size = () => ({ w: info?.width || video.videoWidth, h: info?.height || video.videoHeight });

  const trim = () => {
    const t = total();
    let s = get("start_time");
    if (s < 0) s = Math.max(t + s, 0);
    s = Math.min(s, t);
    const d = get("duration");
    return { s, e: d > 0 ? Math.min(s + d, t) : t };
  };

  const crop = () => {
    const { w, h } = size();
    const cw = get("crop_width");
    const ch = get("crop_height");
    if (cw <= 0 || ch <= 0) return { x: 0, y: 0, w, h };
    const x = Math.min(get("crop_x"), Math.max(w - 1, 0));
    const y = Math.min(get("crop_y"), Math.max(h - 1, 0));
    return { x, y, w: Math.min(cw, w - x), h: Math.min(ch, h - y) };
  };

  const fit = () => {
    const { w, h } = size();
    if (!w || !stage.clientWidth) return null;
    const k = Math.min(stage.clientWidth / w, stage.clientHeight / h);
    return { k, ox: (stage.clientWidth - w * k) / 2, oy: (stage.clientHeight - h * k) / 2 };
  };

  const frameAt = () => Math.max(Math.round((video.currentTime - trim().s) * fps()), 0);

  const paint = () => {
    const t = total();
    const f = fit();
    if (f) {
      const c = crop();
      box.style.display = "";
      box.style.left = `${f.ox + c.x * f.k}px`;
      box.style.top = `${f.oy + c.y * f.k}px`;
      box.style.width = `${c.w * f.k}px`;
      box.style.height = `${c.h * f.k}px`;
    } else {
      box.style.display = "none";
    }
    if (!t) return;
    const { s, e } = trim();
    range.style.left = `${(s / t) * 100}%`;
    range.style.width = `${((e - s) / t) * 100}%`;
    gripA.style.left = `${(s / t) * 100}%`;
    gripB.style.left = `${(e / t) * 100}%`;
    head.style.left = `${(video.currentTime / t) * 100}%`;
    const c = crop();
    const kept = Math.max(Math.round((e - s) * fps()), 0);
    clock.textContent = `${fmt(video.currentTime)} · frame ${frameAt()}`;
    text.textContent = `${size().w}x${size().h} · ${Number(fps().toFixed(3))} fps · trim ${fmt(s)} - ${fmt(e)} (${kept} frames) · crop ${c.w}x${c.h}`;
  };

  const height = () => {
    const w = node.size[0] - 20;
    const { w: vw, h: vh } = size();
    const stageH = Math.round(Math.min(Math.max(vw ? (w * vh) / vw : (w * 9) / 16, 120), 340));
    stage.style.height = `${stageH}px`;
    return stageH + 30 + 24 + 22 + 34 + 24;
  };
  mountWidget(node, "load_view", root, height);

  const changed = () => {
    paint();
    app.graph?.setDirtyCanvas(true, true);
  };

  // ---- source -----------------------------------------------------------------------------------------------
  const load = async () => {
    const value = widget("file")?.value;
    if (!value) return;
    const url = fileURL(parseAnnotated(value));
    if (video.dataset.src !== url) {
      video.dataset.src = url;
      video.src = url;
    }
    try {
      const r = await api.fetchApi(`/majoor/video_info?file=${encodeURIComponent(value)}`);
      const body = await r.json();
      info = r.ok ? body : null;
      if (!r.ok) text.textContent = `⚠ ${body.error}`;
    } catch {
      info = null;
    }
    if (info) {
      // another file than the one the settings were made for: a crop outside the frame or a start after the end would be wrong
      const outside = get("crop_width") > 0 && get("crop_height") > 0 && (get("crop_x") + get("crop_width") > info.width || get("crop_y") + get("crop_height") > info.height);
      if (outside) for (const n of ["crop_x", "crop_y", "crop_width", "crop_height"]) put(n, 0);
      if (Math.abs(get("start_time")) > info.duration) {
        put("start_time", 0);
        put("duration", 0);
      }
    }
    growTo(node, node.computeSize()[1]);
    changed();
  };
  video.addEventListener("loadedmetadata", () => {
    video.currentTime = trim().s;
    changed();
  });
  video.addEventListener("seeked", paint);

  for (const name of ["file", "start_time", "duration", "crop_x", "crop_y", "crop_width", "crop_height"]) {
    const w = widget(name);
    if (!w) continue;
    const prev = w.callback;
    w.callback = function () {
      const r = prev?.apply(this, arguments);
      if (name === "file") load();
      else changed();
      return r;
    };
  }
  node.onConfigure = ((prev) => function () {
    const r = prev?.apply(this, arguments);
    setTimeout(load, 0);
    return r;
  })(node.onConfigure);
  node.onResize = ((prev) => function () {
    const r = prev?.apply(this, arguments);
    paint();
    return r;
  })(node.onResize);
  node.onRemoved = ((prev) => function () {
    video.pause();
    video.removeAttribute("src");
    return prev?.apply(this, arguments);
  })(node.onRemoved);

  // ---- playback (inside the trim range) ------------------------------------------------------------------------
  let raf = 0;
  const tick = () => {
    const { s, e } = trim();
    if (video.currentTime >= e - 0.5 / fps()) video.currentTime = s;
    paint();
    raf = requestAnimationFrame(tick);
  };
  video.addEventListener("play", () => {
    play.textContent = "⏸";
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(tick);
  });
  video.addEventListener("pause", () => {
    play.textContent = "▶";
    cancelAnimationFrame(raf);
    paint();
  });
  play.addEventListener("click", () => {
    if (video.paused) video.play();
    else video.pause();
  });
  const step = (n) => {
    video.pause();
    const { s, e } = trim();
    video.currentTime = Math.min(Math.max(video.currentTime + n / fps(), s), Math.max(e - 1 / fps(), s));
  };
  back.addEventListener("click", () => step(-1));
  next.addEventListener("click", () => step(1));

  addFrame.addEventListener("click", () => {
    const w = widget("frames");
    if (!w) return;
    const value = String(w.value ?? "").trim().replace(/,$/, "");
    w.value = value ? `${value}, ${frameAt()}` : String(frameAt());
    w.callback?.(w.value);
    app.graph?.setDirtyCanvas(true, true);
  });
  resetCrop.addEventListener("click", () => {
    for (const n of ["crop_x", "crop_y", "crop_width", "crop_height"]) put(n, 0);
    changed();
  });
  resetTrim.addEventListener("click", () => {
    put("start_time", 0);
    put("duration", 0);
    changed();
  });

  // ---- trim bar -------------------------------------------------------------------------------------------------
  const timeAt = (ev) => {
    const rect = bar.getBoundingClientRect();
    const t = Math.min(Math.max((ev.clientX - rect.left) / rect.width, 0), 1) * total();
    return Math.round(t * fps()) / fps();
  };
  const dragGrip = (grip, isStart) => {
    grip.addEventListener("pointerdown", (ev) => {
      ev.stopPropagation();
      grip.setPointerCapture(ev.pointerId);
      const frame = 1 / fps();
      const move = (e) => {
        const t = total();
        const { s, e: end } = trim();
        const at = timeAt(e);
        if (isStart) {
          const ns = Math.max(Math.min(at, end - frame), 0);
          put("start_time", floorMs(ns));
          put("duration", end >= t - 1e-3 ? 0 : Number((end - floorMs(ns)).toFixed(3)));
          video.currentTime = ns;
        } else {
          const ne = Math.max(at, s + frame);
          put("duration", ne >= t - 1e-3 ? 0 : Number((ne - s).toFixed(3)));
          video.currentTime = Math.max(ne - frame, s);
        }
        changed();
      };
      const up = () => {
        grip.removeEventListener("pointermove", move);
        grip.removeEventListener("pointerup", up);
      };
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", up);
    });
  };
  dragGrip(gripA, true);
  dragGrip(gripB, false);
  bar.addEventListener("pointerdown", (ev) => {
    if (!total()) return;
    video.pause();
    const { s, e } = trim();
    video.currentTime = Math.min(Math.max(timeAt(ev), s), e);
  });

  // ---- crop box ---------------------------------------------------------------------------------------------------
  box.addEventListener("pointerdown", (ev) => {
    const f = fit();
    if (!f) return;
    ev.preventDefault();
    box.setPointerCapture(ev.pointerId);
    const mode = ev.target.dataset?.h ?? "move";
    const { w: vw, h: vh } = size();
    const start = crop();
    const zoom = stage.getBoundingClientRect().width / stage.clientWidth;
    const origin = { x: ev.clientX, y: ev.clientY };
    const move = (e) => {
      const dx = Math.round((e.clientX - origin.x) / zoom / f.k);
      const dy = Math.round((e.clientY - origin.y) / zoom / f.k);
      let { x, y, w, h } = start;
      if (mode === "move") {
        x = Math.min(Math.max(start.x + dx, 0), vw - w);
        y = Math.min(Math.max(start.y + dy, 0), vh - h);
      } else {
        if (mode.includes("w")) {
          x = Math.min(Math.max(start.x + dx, 0), start.x + start.w - MIN_CROP);
          w = start.x + start.w - x;
        } else {
          w = Math.min(Math.max(start.w + dx, MIN_CROP), vw - start.x);
        }
        if (mode.includes("n")) {
          y = Math.min(Math.max(start.y + dy, 0), start.y + start.h - MIN_CROP);
          h = start.y + start.h - y;
        } else {
          h = Math.min(Math.max(start.h + dy, MIN_CROP), vh - start.y);
        }
      }
      const full = x === 0 && y === 0 && w === vw && h === vh;
      put("crop_x", full ? 0 : x);
      put("crop_y", full ? 0 : y);
      put("crop_width", full ? 0 : w);
      put("crop_height", full ? 0 : h);
      changed();
    };
    const up = () => {
      box.removeEventListener("pointermove", move);
      box.removeEventListener("pointerup", up);
    };
    box.addEventListener("pointermove", move);
    box.addEventListener("pointerup", up);
  });

  setTimeout(load, 0);
}

app.registerExtension({
  name: "Majoor.VideoTools.LoadVideoAdvanced",
  nodeCreated(node) {
    if (node.comfyClass === LOAD) setupLoad(node);
  },
});
