// Majoor VideoTools - preview widgets.
//
// Scene Detect & Split : source video with the detected cuts drawn on a clickable timeline.
// Select Shot          : filmstrip of the shots of the connected list; click one to fill shot_id.
//
// The backend sends a "majoor_shots" entry with each execution (see nodes/preview.py). Everything here is
// optional: the nodes work unchanged through the API without this file.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const DETECT = "MajoorSceneDetectSplit";
const SELECT = "MajoorSelectShot";
const ASSEMBLE = "MajoorShotAssemble";
const WITH_PAYLOAD = new Set([DETECT, SELECT, "MajoorApplyShotMetadata"]);
const PROP = "majoor_ui";

const STYLE = `
.mjr-root { box-sizing: border-box; width: 100%; display: flex; flex-direction: column; gap: 6px; color: var(--input-text, #ddd); font: 12px sans-serif; }
.mjr-video { width: 100%; min-height: 0; flex: 1 1 auto; background: #000; border-radius: 4px; object-fit: contain; }
.mjr-info { opacity: .75; white-space: pre-wrap; line-height: 1.3; }
.mjr-bar { position: relative; height: 30px; flex: 0 0 30px; background: var(--comfy-input-bg, #222); border: 1px solid var(--border-color, #444); border-radius: 4px; overflow: hidden; }
.mjr-seg { position: absolute; top: 0; bottom: 0; box-sizing: border-box; border: 0; border-right: 1px solid var(--border-color, #444); padding: 0 3px; color: inherit; font: inherit; font-size: 10px; text-align: left; overflow: hidden; white-space: nowrap; cursor: pointer; background: var(--comfy-input-bg, #222); }
.mjr-seg:nth-child(even) { background: var(--comfy-menu-bg, #353535); }
.mjr-seg:hover { filter: brightness(1.4); }
.mjr-seg.mjr-on { outline: 2px solid #4a90e2; outline-offset: -2px; }
.mjr-seg.mjr-mod { background: #7a5a22; }
.mjr-head { position: absolute; top: 0; bottom: 0; width: 2px; background: #ff5a4d; pointer-events: none; }
.mjr-strip { display: flex; flex-wrap: wrap; gap: 4px; max-height: 190px; overflow-y: auto; }
.mjr-card { box-sizing: border-box; width: 92px; padding: 3px; display: flex; flex-direction: column; gap: 2px; background: var(--comfy-input-bg, #222); color: inherit; border: 2px solid transparent; border-radius: 4px; font: inherit; font-size: 10px; cursor: pointer; text-align: left; }
.mjr-card:hover { border-color: var(--border-color, #666); }
.mjr-card.mjr-on { border-color: #4a90e2; }
.mjr-card img { width: 100%; aspect-ratio: 16 / 9; object-fit: cover; background: #111; border-radius: 2px; }
.mjr-take { opacity: .7; }
.mjr-take.mjr-mod { color: #e2a34a; opacity: 1; }
`;

function addStyle() {
  if (document.getElementById("mjr-style")) return;
  const style = document.createElement("style");
  style.id = "mjr-style";
  style.textContent = STYLE;
  document.head.appendChild(style);
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function viewURL(payload, rel) {
  const cut = rel.lastIndexOf("/");
  const sub = [payload.base, cut >= 0 ? rel.slice(0, cut) : ""].filter(Boolean).join("/");
  const params = new URLSearchParams({ filename: rel.slice(cut + 1), subfolder: sub, type: "output" });
  return api.apiURL(`/view?${params}`);
}

function fmt(seconds) {
  const m = Math.floor(seconds / 60);
  return `${String(m).padStart(2, "0")}:${(seconds - m * 60).toFixed(1).padStart(4, "0")}`;
}

function saved(node) {
  return node.properties?.[PROP] ?? null;
}

function store(node, payload) {
  node.properties = node.properties || {};
  node.properties[PROP] = payload;
}

// The list a Select Shot node works on comes from the nearest upstream node that reported one.
function upstreamPayload(node) {
  let cur = node;
  for (let hops = 0; cur && hops < 32; hops++) {
    const slot = cur.inputs?.findIndex((i) => i.name === "shot_list") ?? -1;
    cur = slot >= 0 && cur.inputs[slot].link != null ? cur.getInputNode(slot) : null;
    if (cur && saved(cur)) return saved(cur);
  }
  return saved(node);
}

function growTo(node, minHeight) {
  node.setSize([Math.max(node.size[0], 340), Math.max(node.size[1], minHeight)]);
  app.graph?.setDirtyCanvas(true, true);
}

function mountWidget(node, name, root, height) {
  const wd = node.addDOMWidget(name, "majoorWidget", root, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: height,
    getHeight: height,
  });
  // options.serialize is not what litegraph reads; without this the element lands in widgets_values.
  if (wd) wd.serialize = false;
  return wd;
}

// ---- Scene Detect & Split: video + cut timeline -------------------------------------------------------------

function setupDetect(node) {
  const root = el("div", "mjr-root");
  const video = el("video", "mjr-video");
  video.controls = true;
  video.muted = true;
  video.preload = "metadata";
  video.playsInline = true;
  const bar = el("div", "mjr-bar");
  const head = el("div", "mjr-head");
  const info = el("div", "mjr-info", "Run the graph to see the detected cuts.");
  root.append(video, bar, info);

  let payload = null;
  let segs = [];
  let raf = 0;

  const height = () => {
    if (!payload) return 44;
    const { width, height: h } = payload.source;
    const ratio = width && h ? h / width : 9 / 16;
    return Math.round(Math.min(Math.max((node.size[0] - 20) * ratio, 90), 420) + 30 + 40 + 12);
  };
  mountWidget(node, "shots_preview", root, height);

  const sync = () => {
    if (!payload) return;
    const t = video.currentTime;
    head.style.left = `${Math.min(t / payload.source.duration, 1) * 100}%`;
    const idx = payload.shots.findIndex((s) => t >= s.start - 1e-3 && t < s.start + s.duration - 1e-3);
    segs.forEach((seg, i) => seg.classList.toggle("mjr-on", i === idx));
  };
  const loop = () => {
    sync();
    raf = video.paused ? 0 : requestAnimationFrame(loop);
  };
  video.addEventListener("play", () => { if (!raf) raf = requestAnimationFrame(loop); });
  video.addEventListener("timeupdate", sync);
  video.addEventListener("seeked", sync);

  node._mjrRender = (p) => {
    payload = p;
    const total = p.source.duration;
    const url = viewURL(p, p.source.file);
    if (video.dataset.src !== url) {
      video.dataset.src = url;
      video.src = url;
    }
    bar.replaceChildren();
    segs = p.shots.map((s) => {
      const seg = el("button", "mjr-seg", s.id.replace("SHOT_", ""));
      seg.type = "button";
      seg.style.left = `${(s.start / total) * 100}%`;
      seg.style.width = `${(s.duration / total) * 100}%`;
      seg.title = `${s.id} · ${fmt(s.start)}–${fmt(s.start + s.duration)} · ${s.duration.toFixed(2)}s · ${s.frames} frames`;
      seg.addEventListener("click", () => { video.currentTime = s.start + 0.001; sync(); });
      bar.appendChild(seg);
      return seg;
    });
    bar.appendChild(head);
    const src = p.source;
    info.textContent = `${p.shots.length} shots · ${fmt(total)} · ${src.fps.toFixed(3)} fps · ${src.width}x${src.height}`;
    sync();
    growTo(node, node.computeSize()[1]);
  };

  node.onRemoved = ((prev) => function () {
    if (raf) cancelAnimationFrame(raf);
    video.removeAttribute("src");
    video.load();
    return prev?.apply(this, arguments);
  })(node.onRemoved);
}

// ---- Select Shot: filmstrip + shot preview ------------------------------------------------------------------

function setupSelect(node) {
  const root = el("div", "mjr-root");
  const strip = el("div", "mjr-strip");
  const video = el("video", "mjr-video");
  video.controls = true;
  video.muted = true;
  video.preload = "metadata";
  video.playsInline = true;
  const info = el("div", "mjr-info", "Connect a shot list and run the graph to list its shots.");
  root.append(strip, video, info);

  let payload = null;
  let own = null;
  let bounds = null; // when previewing a slice of the source, [start, end]

  const idWidget = () => node.widgets?.find((w) => w.name === "shot_id");
  const height = () => {
    if (!payload) return 44;
    const rows = Math.min(Math.ceil(payload.shots.length / Math.max(Math.floor((node.size[0] - 20) / 96), 1)), 2);
    return rows * 98 + 120 + 40 + 12;
  };
  mountWidget(node, "shots_picker", root, height);

  const preview = (shot) => {
    const fresh = own && own.clip && own.selected === shot.id;
    const url = fresh ? viewURL(own, own.clip) : viewURL(payload, payload.source.file);
    bounds = fresh ? null : [shot.start, shot.start + shot.duration];
    if (video.dataset.src !== url) {
      video.dataset.src = url;
      video.src = url;
    }
    if (bounds) video.currentTime = bounds[0] + 0.001;
  };
  video.addEventListener("loadedmetadata", () => { if (bounds) video.currentTime = bounds[0] + 0.001; });
  video.addEventListener("timeupdate", () => {
    if (bounds && video.currentTime >= bounds[1] - 0.02) {
      video.pause();
      video.currentTime = bounds[0] + 0.001;
    }
  });

  const highlight = () => {
    const wanted = (idWidget()?.value ?? "").trim();
    const shot = payload?.shots.find((s) => s.id === wanted);
    [...strip.children].forEach((card) => card.classList.toggle("mjr-on", card.dataset.id === wanted));
    video.style.display = shot ? "" : "none";
    if (shot) {
      preview(shot);
      info.textContent = `${shot.id} · ${fmt(shot.start)}–${fmt(shot.start + shot.duration)} · ${shot.duration.toFixed(2)}s · ${shot.frames} frames · active: ${shot.active}`;
    } else if (payload) {
      info.textContent = wanted ? `Unknown shot '${wanted}'. Pick one above.` : "Pick a shot above.";
    }
  };

  node._mjrRefresh = () => {
    own = saved(node);
    payload = upstreamPayload(node);
    strip.replaceChildren();
    if (!payload) {
      video.style.display = "none";
      info.textContent = "Connect a shot list and run the graph to list its shots.";
      return;
    }
    for (const s of payload.shots) {
      const card = el("button", "mjr-card");
      card.type = "button";
      card.dataset.id = s.id;
      card.title = `${s.id} · ${s.duration.toFixed(2)}s · takes: ${s.takes.join(", ")}`;
      if (s.thumb) {
        const img = el("img");
        img.loading = "lazy";
        img.src = viewURL(payload, s.thumb);
        card.appendChild(img);
      }
      card.append(el("span", null, `${s.id.replace("SHOT_", "#")} · ${s.duration.toFixed(1)}s`));
      card.append(el("span", s.active === "original" ? "mjr-take" : "mjr-take mjr-mod", s.active === "original" ? "original" : s.active));
      card.addEventListener("click", () => {
        const w = idWidget();
        if (!w) return;
        w.value = s.id;
        w.callback?.(s.id);
        app.graph?.setDirtyCanvas(true, true);
        highlight();
      });
      strip.appendChild(card);
    }
    highlight();
    growTo(node, node.computeSize()[1]);
  };

  const w = idWidget();
  if (w) {
    const prev = w.callback;
    w.callback = function () {
      const r = prev?.apply(this, arguments);
      highlight();
      return r;
    };
  }
  node.onConnectionsChange = ((prev) => function () {
    const r = prev?.apply(this, arguments);
    setTimeout(() => node._mjrRefresh?.(), 0);
    return r;
  })(node.onConnectionsChange);
  node.onRemoved = ((prev) => function () {
    video.removeAttribute("src");
    video.load();
    return prev?.apply(this, arguments);
  })(node.onRemoved);
}

// ---- Shot Assemble: output timeline (the video itself is ComfyUI's standard preview) -------------------------

function setupAssemble(node) {
  const root = el("div", "mjr-root");
  const bar = el("div", "mjr-bar");
  const info = el("div", "mjr-info", "Run the graph to see the final shot order.");
  root.append(bar, info);
  mountWidget(node, "assembly_timeline", root, () => 30 + 6 + info.textContent.split("
").length * 16 + 8);

  node._mjrRenderAssembly = (a) => {
    const total = a.shots.reduce((sum, s) => sum + s.duration, 0);
    let at = 0;
    bar.replaceChildren();
    for (const s of a.shots) {
      const seg = el("button", s.take === "original" ? "mjr-seg" : "mjr-seg mjr-mod", s.id.replace("SHOT_", ""));
      seg.type = "button";
      seg.style.left = `${(at / total) * 100}%`;
      seg.style.width = `${(s.duration / total) * 100}%`;
      seg.title = `${s.id} · ${s.take} · ${fmt(at)}–${fmt(at + s.duration)}`;
      bar.appendChild(seg);
      at += s.duration;
    }
    const changed = a.shots.filter((s) => s.take !== "original").length;
    info.textContent = [`${a.shots.length} shots · ${changed} replaced · ${fmt(total)}`, ...a.warnings.map((w) => `⚠ ${w}`)].join("
");
    growTo(node, node.computeSize()[1]);
  };
}

function refreshAll() {
  for (const n of app.graph?._nodes ?? []) n._mjrRefresh?.();
}

app.registerExtension({
  name: "Majoor.VideoTools",

  nodeCreated(node) {
    if (node.comfyClass === DETECT) {
      addStyle();
      setupDetect(node);
    } else if (node.comfyClass === SELECT) {
      addStyle();
      setupSelect(node);
    } else if (node.comfyClass === ASSEMBLE) {
      addStyle();
      setupAssemble(node);
    }
  },

  // Saved workflows carry the last payload in node.properties, so the widgets come back without a re-run.
  loadedGraphNode(node) {
    const p = saved(node);
    if (p && node.comfyClass === DETECT) node._mjrRender?.(p);
    if (node.properties?.majoor_assembly && node.comfyClass === ASSEMBLE) node._mjrRenderAssembly?.(node.properties.majoor_assembly);
  },

  afterConfigureGraph() {
    setTimeout(() => {
      for (const n of app.graph?._nodes ?? []) {
        if (n.comfyClass === DETECT && saved(n)) n._mjrRender?.(saved(n));
      }
      refreshAll();
    }, 0);
  },

  setup() {
    api.addEventListener("executed", ({ detail }) => {
      const assembly = detail?.output?.majoor_assembly?.[0];
      if (assembly) {
        const target = app.graph?.getNodeById(detail.display_node ?? detail.node);
        if (target?.comfyClass === ASSEMBLE) {
          target.properties = target.properties || {};
          target.properties.majoor_assembly = assembly;
          target._mjrRenderAssembly?.(assembly);
        }
        return;
      }
      const payload = detail?.output?.majoor_shots?.[0];
      if (!payload) return;
      const node = app.graph?.getNodeById(detail.display_node ?? detail.node);
      if (!node || !WITH_PAYLOAD.has(node.comfyClass)) return;
      store(node, payload);
      if (node.comfyClass === DETECT) node._mjrRender?.(payload);
      refreshAll();
    });
  },
});
