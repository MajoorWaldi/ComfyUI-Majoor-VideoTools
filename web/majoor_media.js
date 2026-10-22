// Majoor VideoTools - Compare Video widget.
//
// ComfyUI keeps the last executed output of every node in app.nodeOutputs, and Load Video previews its file
// straight from its widget. This widget reads the same places, so it updates as soon as a video or an image
// batch is connected (or the upstream node changes) without running the graph. When nothing can be read
// from upstream it shows the result of the last run, which the backend sends as "majoor_compare".

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyle, el, fmt, growTo, mountWidget } from "./majoor_videotools.js";

const COMPARE = "MajoorCompareVideo";
const VIDEO_FILE = /\.(mp4|webm|mov|mkv|m4v|avi)$/i;
const POLL_MS = 800;

const watchers = new Set();

export const fileURL = (e) => api.apiURL(`/view?${new URLSearchParams({ filename: e.filename, subfolder: e.subfolder ?? "", type: e.type ?? "output" })}`);
const refURL = (r) => fileURL({ filename: r.file, subfolder: r.folder, type: r.kind });

// "clips/a.mp4 [input]" -> { filename, subfolder, type }
export function parseAnnotated(value) {
  const m = /^(.*?)(?: \[(input|output|temp)\])?$/.exec(String(value ?? ""));
  const cut = m[1].lastIndexOf("/");
  return { filename: m[1].slice(cut + 1), subfolder: cut >= 0 ? m[1].slice(0, cut) : "", type: m[2] ?? "input" };
}

function upstreamOf(node, name) {
  const slot = node.inputs?.findIndex((i) => i.name === name) ?? -1;
  if (slot < 0 || node.inputs[slot].link == null) return null;
  const up = node.getInputNode(slot);
  return up ? { node: up, slot: node.graph?._links?.get(node.inputs[slot].link)?.origin_slot ?? 0 } : null;
}

const connected = (node, name) => upstreamOf(node, name) !== null;
const widgetValue = (node, name) => node.widgets?.find((w) => w.name === name)?.value;

// The video URL the node connected to `name` would show, read without executing anything.
function resolveVideo(node, name) {
  const src = upstreamOf(node, name);
  if (!src) return "";
  const up = src.node;
  if (up.comfyClass === "LoadVideo") return fileURL(parseAnnotated(widgetValue(up, "file")));
  const shots = up.properties?.majoor_ui;
  if (up.comfyClass === "MajoorSelectShot" && src.slot === 0 && shots?.clip) {
    const parts = shots.clip.split("/");
    return fileURL({ filename: parts.pop(), subfolder: [shots.base, ...parts].join("/"), type: "output" });
  }
  const out = app.nodeOutputs?.[String(up.id)];
  const first = out?.images?.[0];
  return out?.animated?.some(Boolean) && first && VIDEO_FILE.test(first.filename) ? fileURL(first) : "";
}

function makeVideo() {
  const v = el("video", "mjr-video");
  v.muted = true;
  v.preload = "auto";
  v.playsInline = true;
  return v;
}

function setSource(video, url) {
  if (url && video.dataset.src !== url) {
    video.dataset.src = url;
    video.src = url;
  } else if (!url && video.dataset.src) {
    video.dataset.src = "";
    video.removeAttribute("src");
    video.load();
  }
}

function controlsRow() {
  const play = el("button", null, "▶");
  play.type = "button";
  const scrub = el("input");
  scrub.type = "range";
  scrub.min = "0";
  scrub.max = "1000";
  scrub.value = "0";
  const clock = el("span", null, "00:00.0");
  const row = el("div", "mjr-controls");
  row.append(play, scrub, clock);
  return { row, play, scrub, clock };
}

function track(node, refresh) {
  node._mjrRefresh = refresh;
  watchers.add(node);
  node.onConnectionsChange = ((prev) => function () {
    const r = prev?.apply(this, arguments);
    setTimeout(refresh, 0);
    return r;
  })(node.onConnectionsChange);
  setTimeout(refresh, 0);
}

function untrack(node, release) {
  node.onRemoved = ((prev) => function () {
    watchers.delete(node);
    release();
    return prev?.apply(this, arguments);
  })(node.onRemoved);
}

// ---- Compare Video --------------------------------------------------------------------------------------------

function setupCompare(node) {
  const root = el("div", "mjr-root");
  const stage = el("div", "mjr-stage");
  const a = makeVideo();
  const b = makeVideo();
  const divider = el("div", "mjr-divider");
  const tagA = el("div", "mjr-label");
  const tagB = el("div", "mjr-label");
  stage.append(a, b, divider, tagA, tagB);
  const { row, play, scrub, clock } = controlsRow();
  const info = el("div", "mjr-info", "Connect two videos. The comparison updates by itself.");
  root.append(stage, row, info);

  let split = 0.5;
  const sideBySide = () => widgetValue(node, "mode") === "side_by_side";

  const height = () => {
    const w = node.size[0] - 20;
    const ratio = a.videoWidth ? a.videoHeight / a.videoWidth : 9 / 16;
    const stageH = Math.min(Math.max((sideBySide() ? w / 2 : w) * ratio, 90), 420);
    return Math.round(stageH + 24 + info.textContent.split("\n").length * 16 + 18);
  };
  mountWidget(node, "compare_view", root, height);

  const layout = () => {
    const side = sideBySide();
    stage.classList.toggle("mjr-side", side);
    stage.classList.toggle("mjr-wipe", !side);
    divider.style.display = side ? "none" : "";
    b.style.clipPath = side ? "" : `inset(0 0 0 ${split * 100}%)`;
    divider.style.left = `${split * 100}%`;
    tagA.textContent = widgetValue(node, "label_a") ?? "A";
    tagB.textContent = widgetValue(node, "label_b") ?? "B";
    tagA.style.left = "4px";
    tagB.style.left = side ? "calc(50% + 6px)" : "";
    tagB.style.right = side ? "" : "4px";
    app.graph?.setDirtyCanvas(true, true);
  };
  for (const name of ["mode", "label_a", "label_b"]) {
    const w = node.widgets?.find((x) => x.name === name);
    if (!w) continue;
    const prev = w.callback;
    w.callback = function () {
      const r = prev?.apply(this, arguments);
      layout();
      growTo(node, node.computeSize()[1]);
      return r;
    };
  }

  const duration = () => a.duration || 0;
  const paint = () => {
    if (duration()) scrub.value = String(Math.round((a.currentTime / duration()) * 1000));
    clock.textContent = fmt(a.currentTime);
  };
  const seek = (t) => {
    a.currentTime = t;
    b.currentTime = t;
    paint();
  };
  play.addEventListener("click", () => {
    if (a.paused) {
      if (a.ended) seek(0);
      a.play();
      b.play();
    } else {
      a.pause();
      b.pause();
    }
  });
  a.addEventListener("play", () => { play.textContent = "⏸"; });
  a.addEventListener("pause", () => { play.textContent = "▶"; });
  a.addEventListener("timeupdate", () => {
    if (Math.abs(b.currentTime - a.currentTime) > 0.15) b.currentTime = a.currentTime;
    paint();
  });
  a.addEventListener("ended", () => b.pause());
  scrub.addEventListener("input", () => seek((Number(scrub.value) / 1000) * duration()));

  let dragging = false;
  const move = (e) => {
    const rect = stage.getBoundingClientRect();
    split = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1);
    layout();
  };
  stage.addEventListener("pointerdown", (e) => {
    if (sideBySide()) return;
    dragging = true;
    stage.setPointerCapture?.(e.pointerId);
    move(e);
  });
  stage.addEventListener("pointermove", (e) => { if (dragging) move(e); });
  stage.addEventListener("pointerup", () => { dragging = false; });

  const describe = () => {
    if (!a.videoWidth && !b.videoWidth) return;
    const line = (name, v) => (v.videoWidth ? `${name}: ${v.videoWidth}x${v.videoHeight} · ${fmt(v.duration)}` : `${name}: loading`);
    const lines = [line("A", a), line("B", b)];
    if (a.videoWidth && b.videoWidth) {
      if (a.videoWidth !== b.videoWidth || a.videoHeight !== b.videoHeight) lines.push("⚠ different sizes");
      if (Math.abs(a.duration - b.duration) > 0.05) lines.push("⚠ different durations");
    }
    info.textContent = lines.join("\n");
    growTo(node, node.computeSize()[1]);
  };
  a.addEventListener("loadedmetadata", describe);
  b.addEventListener("loadedmetadata", describe);

  const pick = (name, side) => {
    const live = resolveVideo(node, name);
    if (live) return live;
    const ref = node.properties?.majoor_compare?.[side];
    return ref ? refURL(ref) : "";
  };
  const refresh = () => {
    setSource(a, pick("video_a", "a"));
    setSource(b, pick("video_b", "b"));
    if (!a.dataset.src && !b.dataset.src) info.textContent = "Connect two videos. The comparison updates by itself.";
    layout();
  };

  node._mjrRender = (data) => {
    node.properties = node.properties || {};
    node.properties.majoor_compare = data;
    refresh();
  };
  track(node, refresh);
  untrack(node, () => {
    for (const v of [a, b]) {
      v.pause();
      setSource(v, "");
    }
  });
  layout();
}

app.registerExtension({
  name: "Majoor.VideoTools.Media",

  nodeCreated(node) {
    if (node.comfyClass === COMPARE) {
      addStyle();
      setupCompare(node);
    }
  },

  afterConfigureGraph() {
    setTimeout(() => watchers.forEach((n) => n._mjrRefresh?.()), 0);
  },

  setup() {
    api.addEventListener("executed", ({ detail }) => {
      const node = app.graph?.getNodeById(detail.display_node ?? detail.node);
      const compare = detail?.output?.majoor_compare?.[0];
      if (compare && node?.comfyClass === COMPARE) node._mjrRender(compare);
      // an upstream node just produced a new output: re-read it once the frontend has stored it
      setTimeout(() => watchers.forEach((n) => n._mjrRefresh?.()), 0);
    });
    // No event tells us that an upstream widget (Load Video's file, for one) changed, so one light timer re-reads the inputs.
    setInterval(() => {
      if (document.hidden) return;
      for (const n of watchers) {
        if (!n.graph) watchers.delete(n);
        else n._mjrRefresh?.();
      }
    }, POLL_MS);
  },
});
