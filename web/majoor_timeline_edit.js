import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { openTimelineEditor } from "./timeline_edit_panel.js";
import { validateEdit } from "./timeline_edit_logic.js";

const CLASS = "MajoorTimelineEdit", PROP = "majoor_timeline";
const panels = new Map();

function save(node, document) {
  const widget = node.widgets?.find((w) => w.name === "edit_json");
  if (!widget) throw new Error("Timeline Edit: edit_json widget is missing.");
  node.graph?.beforeChange?.();
  widget.value = typeof document === "string" ? document : JSON.stringify(document);
  widget.callback?.(widget.value);
  node.graph?.afterChange?.();
  app.graph?.setDirtyCanvas(true, true);
}

function mount(node) {
  if (node._mjrTimelineMounted) return;
  node._mjrTimelineMounted = true;
  const root = document.createElement("div");
  root.style.cssText = "display:flex;gap:8px;align-items:center;flex-wrap:wrap;color:var(--input-text,#ddd);font:12px sans-serif";
  const button = document.createElement("button"); button.textContent = "Open Timeline Edit";
  const reset = document.createElement("button"); reset.textContent = "Reset edit";
  const info = document.createElement("span"); info.textContent = "Run once to load the takes and music.";
  root.append(button, reset, info);
  const widget = node.addDOMWidget("timeline_editor", "majoorTimeline", root, { serialize: false, hideOnZoom: false, getMinHeight: () => 55 });
  if (widget) widget.serialize = false;
  reset.onclick = () => {
    if (!window.confirm("Discard this montage? Source takes will not change. Run the node again to load a new edit.")) return;
    panels.get(node)?.(); save(node, "");
    if (node.properties) delete node.properties[PROP];
    info.textContent = "Edit reset. Run the node to reload sources.";
  };
  button.onclick = () => {
    panels.get(node)?.();
    try {
      const payload = node.properties?.[PROP];
      if (!payload) throw new Error("Run Timeline Edit once to load its connected shot list and music.");
      const text = node.widgets.find((w) => w.name === "edit_json").value;
      const doc = text.trim() ? JSON.parse(text) : payload.document;
      validateEdit(doc, payload);
      const close = openTimelineEditor(payload, doc, {
        urlFor(file) {
          const index = file.lastIndexOf("/");
          const params = new URLSearchParams({ filename: file.slice(index + 1), type: "output",
            subfolder: [payload.base, index < 0 ? "" : file.slice(0, index)].filter(Boolean).join("/") });
          return api.apiURL(`/view?${params}`);
        },
        onChange: (next) => { save(node, next); info.textContent = "Edit saved. Run the graph to update the export."; },
        onClose: () => panels.delete(node),
      });
      panels.set(node, close);
    } catch (error) { info.textContent = error.message; }
  };
  // Comfy has no extension hook for disposing this custom DOM editor.
  const removed = node.onRemoved;
  node.onRemoved = function (...args) {
    panels.get(node)?.();
    return removed?.apply(this, args);
  };
}

app.registerExtension({
  name: "Majoor.VideoTools.TimelineEdit",
  nodeCreated(node) { if (node.comfyClass === CLASS) mount(node); },
  afterConfigureGraph() {
    for (const close of [...panels.values()]) close();
    for (const node of app.graph?._nodes || []) if (node.comfyClass === CLASS) mount(node);
  },
  setup() {
    api.addEventListener("executed", ({ detail }) => {
      const payload = detail?.output?.majoor_timeline?.[0];
      if (!payload) return;
      const node = app.graph?.getNodeById(detail.node);
      if (!node || node.comfyClass !== CLASS) return;
      panels.get(node)?.();
      node.properties ||= {};
      node.properties[PROP] = payload;
      const widget = node.widgets?.find((w) => w.name === "edit_json");
      if (widget && !widget.value.trim()) save(node, payload.document);
    });
  },
});
