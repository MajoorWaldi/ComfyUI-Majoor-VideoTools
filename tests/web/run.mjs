// Loads web/majoor_videotools.js against a fake DOM and fake ComfyUI app/api: node tests/web/run.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = fs.mkdtempSync(path.join(os.tmpdir(), "mjr-web-"));
fs.mkdirSync(path.join(root, "scripts"));
fs.mkdirSync(path.join(root, "ext/web"), { recursive: true });
fs.writeFileSync(path.join(root, "package.json"), '{"type":"module"}');
fs.writeFileSync(path.join(root, "scripts/app.js"), `export const app = { exts: [], graph: { _nodes: [], getNodeById(id) { return this._nodes.find(n => n.id == id); }, setDirtyCanvas() {} }, registerExtension(e) { this.exts.push(e); } };`);
fs.writeFileSync(path.join(root, "scripts/api.js"), `const listeners = {}; export const api = { apiURL: (r) => "/api" + r, addEventListener(n, f) { (listeners[n] ||= []).push(f); }, emit(n, detail) { (listeners[n] || []).forEach(f => f({ detail })); } };`);
for (const f of ["majoor_videotools.js", "majoor_media.js"]) fs.copyFileSync(new URL(`../../web/${f}`, import.meta.url), path.join(root, "ext/web", f));
const load = (p) => import(pathToFileURL(path.join(root, p)).href);

function mk(tag) {
  const e = { tag, children: [], style: {}, dataset: {}, className: "", textContent: "", listeners: {}, _cls: new Set(),
    classList: { toggle(c, on) { on ? e._cls.add(c) : e._cls.delete(c); } },
    append(...c) { e.children.push(...c); }, appendChild(c) { e.children.push(c); return c; }, replaceChildren(...c) { e.children = [...c]; },
    addEventListener(n, f) { (e.listeners[n] ||= []).push(f); }, removeAttribute() {}, load() {}, pause() {}, play() {}, setAttribute() {} };
  return e;
}
globalThis.document = { createElement: mk, getElementById: () => null, head: mk("head") };
globalThis.requestAnimationFrame = () => 1; globalThis.cancelAnimationFrame = () => {};
globalThis.URLSearchParams = URLSearchParams;
const { app } = await load("scripts/app.js");
const { api } = await load("scripts/api.js");
await load("ext/web/majoor_videotools.js");
await load("ext/web/majoor_media.js");
const call = (hook, ...args) => app.exts.forEach((e) => e[hook]?.(...args));
app.nodeOutputs = {};
app.graph._links = { get: () => ({ origin_slot: 0 }) };
function node(cls, id, inputs = [], widgets = []) {
  const n = { comfyClass: cls, id, size: [400, 300], properties: {}, inputs, widgets, graph: app.graph,
    addDOMWidget(name, type, el, opts) { const w = { name, type, el, opts }; n.widgets.push(w); n.domOpts = opts; return w; },
    setSize(s) { n.size = s; }, computeSize: () => [340, 200], getInputNode(i) { return n._up?.[i] ?? null; } };
  return n;
}
const detect = node("MajoorSceneDetectSplit", 1);
const apply = node("MajoorApplyShotMetadata", 2, [{ name: "shot_list", link: 1 }, { name: "metadata", link: 2 }, { name: "video", link: 3 }]);
const sel = node("MajoorSelectShot", 3, [{ name: "shot_list", link: 4 }], [{ name: "shot_id", value: "SHOT_002", callback() {} }]);
const asm = node("MajoorShotAssemble", 4, [{ name: "shot_list", link: 5 }]);
const other = node("SaveImage", 5);
const loadVideo = node("LoadVideo", 7, [], [{ name: "file", value: "clips/live.mp4 [input]" }]);
const cmp = node("MajoorCompareVideo", 6, [{ name: "video_a", link: 11 }, { name: "video_b", link: null }], [{ name: "mode", value: "wipe", callback() {} }, { name: "label_a", value: "orig" }, { name: "label_b", value: "gen" }]);
apply._up = { 0: detect }; sel._up = { 0: apply };
cmp._up = { 0: loadVideo };
app.graph._nodes = [detect, apply, sel, asm, other, cmp, loadVideo];
for (const n of app.graph._nodes) call("nodeCreated", n);
call("setup");
console.log("DOM widgets on other node:", other.widgets.length, "| detect:", detect.widgets.length, "sel:", sel.widgets.length, "asm:", asm.widgets.length);
const payload = { base: "MajoorVideoTools/p_1", revision: 1, source: { file: "sources/source.mp4", fps: 30, duration: 26, width: 1812, height: 970 },
  shots: [0, 1, 2].map(i => ({ id: `SHOT_00${i + 1}`, start: i * 2, duration: 2, frames: 60, thumb: `cache/thumbnails/SHOT_00${i + 1}.jpg`, active: i == 1 ? "take_001" : "original", takes: ["original"] })) };
api.emit("executed", { node: "1", output: { majoor_shots: [payload], text: ["x"] } });
api.emit("executed", { node: "2", output: { majoor_shots: [{ ...payload, revision: 2 }] } });
api.emit("executed", { node: "3", output: { majoor_shots: [{ ...payload, clip: "cache/clips/a.mp4", selected: "SHOT_002" }] } });
api.emit("executed", { node: "4", output: { majoor_assembly: [{ shots: [{ id: "SHOT_001", take: "original", duration: 2 }, { id: "SHOT_002", take: "take_001", duration: 2 }], warnings: ["w"] }] } });
const ref = (f, w) => ({ file: f, folder: "majoor_compare", kind: "temp", width: w, height: 540, fps: 24, duration: 5 });
api.emit("executed", { node: "6", output: { majoor_compare: [{ a: ref("a.mp4", 960), b: ref("b.mp4", 1280) }] } });
cmp.widgets.find((w) => w.name === "mode").value = "side_by_side";
cmp.widgets.find((w) => w.name === "mode").callback();
api.emit("executed", { node: "5", output: { images: [{ filename: "a.png" }] } });
call("afterConfigureGraph"); await new Promise(r => setTimeout(r, 20));
call("loadedGraphNode", detect); call("loadedGraphNode", asm); call("loadedGraphNode", other);
console.log("heights:", detect.domOpts.getMinHeight(), sel.domOpts.getMinHeight(), asm.domOpts.getMinHeight());
console.log("detect segs:", detect.widgets[0].el.children[1].children.length, "| select cards:", sel.widgets.find(w => w.name === "shots_picker").el.children[0].children.length, "| asm segs:", asm.widgets[0].el.children[0].children.length);
console.log("other props:", JSON.stringify(other.properties));
await new Promise((r) => setTimeout(r, 20));
const stage = cmp.widgets.find((w) => w.name === "compare_view").el.children[0];
const compareOk = stage._cls.has("mjr-side") && !stage._cls.has("mjr-wipe") && stage.children[0].dataset.src.includes("clip") && stage.children[0].dataset.src.includes("type=input") && stage.children[1].dataset.src.includes("b.mp4") && cmp.properties.majoor_compare;
console.log("compare:", !!compareOk);
const ok = compareOk && detect.widgets[0].el.children[1].children.length === 4 && sel.widgets.find((w) => w.name === "shots_picker").el.children[0].children.length === 3 && asm.widgets[0].el.children[0].children.length === 2 && other.widgets.length === 0;
if (!ok) { console.error("FAILED"); process.exit(1); }
console.log("web widgets ok");
fs.rmSync(root, { recursive: true, force: true });
process.exit(0);
