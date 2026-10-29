// The logic of the Cut Markers editor, then the editor itself against a fake DOM: node tests/web/cuts.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

let failures = 0;
const check = (name, ok) => { console.log(ok ? "ok  " : "FAIL", name); if (!ok) failures++; };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ---- the pure logic ---------------------------------------------------------------------------------------------------
const L = await import(new URL("../../web/majoor_cuts_logic.js", import.meta.url).href);

check("markers are read in seconds, timecodes and frames", same(L.parseMarkers("1.5, 3 0:04.25 1:02 36f 2.5s", 24), [1.5, 2.5, 3, 4.25, 62]));
check("nothing, zero and garbage give no marker", same(L.parseMarkers("", 24), []) && same(L.parseMarkers("0 soon", 24), []));
check("the text round-trips", L.formatMarkers([3, 1.5, 4.25]) === "1.5 3 4.25" && same(L.parseMarkers(L.formatMarkers([0.125, 7.333])), [0.125, 7.333]));

const view = new L.View(10, 1000);
check("time and pixels convert both ways", view.toX(5) === 500 && view.toT(250) === 2.5);
view.zoomAt(5, 0.5);
check("zoom keeps the time under the pointer", Math.abs(view.toX(5) - 500) < 1e-6 && view.span === 5);
view.pan(100); check("pan stays inside the media", view.start === 5);
view.zoomAt(5, 100); check("zoom out stops at the whole media", view.span === 10 && view.start === 0);
view.zoomAt(5, 1e-9); check("zoom in stops at a quarter of a second", view.span === 0.25);
view.fit();

const beats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5];
const ctx = { beats, bpb: 4, downbeat: 1, videoCuts: [1.23, 3.9], fps: 24 };
check("snapping to beats, half beats and bars", L.snapTime(1.07, "beat", ctx) === 1.0 && L.snapTime(1.28, "half_beat", ctx) === 1.25 && L.snapTime(2.8, "bar", ctx, 0.3) === 3.0 && L.snapTime(2.6, "bar", ctx, 0.3) === 2.6);
check("a bar starts on the downbeat", same(L.snapPoints("bar", ctx), [1.0, 3.0]));
check("it only snaps when close", L.snapTime(1.3, "beat", ctx, 0.1) === 1.3 && L.snapTime(1.3, "off", ctx) === 1.3 && L.snapTime(1.2, "video_cuts", ctx) === 1.23);
check("frame snapping", Math.abs(L.snapTime(1.0123, "frame", ctx) - 1.0) < 1e-9);

let m = [];
m = L.addMarker(m, 2, 10); m = L.addMarker(m, 1, 10); m = L.addMarker(m, 2.0001, 10); m = L.addMarker(m, 0, 10); m = L.addMarker(m, 10, 10);
check("markers are added sorted, not twice, not at the ends", same(m, [1, 2]));
const moved = L.moveMarker(m, 0, 3, 10);
check("a moved marker is re-sorted and keeps its index", same(moved.markers, [2, 3]) && moved.index === 1);
check("it cannot land on another marker", same(L.moveMarker(m, 0, 2, 10).markers, m));
check("removing", same(L.removeMarker(m, 0), [2]));
view.fit();
check("a marker is hit within a few pixels", L.hitMarker(m, 102, view) === 0 && L.hitMarker(m, 200, view) === 1 && L.hitMarker(m, 150, view) === -1);

check("markers from every beat, every bar and every half beat",
  same(L.markersFromBeats(beats, "1", { duration: 4 }), [0.5, 1, 1.5, 2, 2.5, 3, 3.5]) && same(L.markersFromBeats(beats, "bar", { bpb: 4, downbeat: 1, duration: 10 }), [1, 3]) && same(L.markersFromBeats(beats, "half", { duration: 2 }), [0.5, 0.75, 1, 1.25, 1.5, 1.75]));
check("markers from the cuts of the video", same(L.markersFromVideoCuts([0, 1.2, 99], 10), [1.2]));

const preview = L.planPreview([0.25, 0.5, 0.75, 2.0, 2.25, 4.0], 6, 24, 1);
check("the preview groups cuts like the backend (shots of 2 s: cuts 6/6/6/30, 6/42 and 48 frames)",
  preview.cuts === 7 && preview.shots.length === 3 && same(preview.shots[0].cuts.map((c) => Math.round(c * 24)), [6, 6, 6, 30]) && same(preview.shots[1].cuts.map((c) => Math.round(c * 24)), [6, 42]) && preview.shots[2].end === 6);
check("a cut one frame after another is merged, none gives one shot", L.planPreview([1, 1.04], 4, 24, 0.2).cuts === 2 && L.planPreview([], 4, 24, 1).shots.length === 1);
check("labels and ticks", L.formatTime(75.5) === "01:15.50" && L.tickStep(10) === 2 && L.tickStep(0.4) === 0.05);

// ---- the editor against a fake DOM ------------------------------------------------------------------------------------
const root = fs.mkdtempSync(path.join(os.tmpdir(), "mjr-cuts-"));
fs.mkdirSync(path.join(root, "scripts"));
fs.mkdirSync(path.join(root, "ext/web"), { recursive: true });
fs.writeFileSync(path.join(root, "package.json"), '{"type":"module"}');
fs.writeFileSync(path.join(root, "scripts/app.js"), `export const app = { exts: [], graph: { _nodes: [], getNodeById(id) { return this._nodes.find(n => n.id == id); }, setDirtyCanvas() {} }, registerExtension(e) { this.exts.push(e); } };`);
fs.writeFileSync(path.join(root, "scripts/api.js"), `const listeners = {}; export const api = { apiURL: (r) => "/api" + r, addEventListener(n, f) { (listeners[n] ||= []).push(f); }, emit(n, detail) { (listeners[n] || []).forEach(f => f({ detail })); } };`);
for (const f of ["majoor_videotools.js", "majoor_regen.js", "majoor_cuts.js", "majoor_cuts_logic.js"]) fs.copyFileSync(new URL(`../../web/${f}`, import.meta.url), path.join(root, "ext/web", f));
const load = (p) => import(pathToFileURL(path.join(root, p)).href);

function mk(tag) {
  const e = { tag, children: [], style: {}, dataset: {}, className: "", textContent: "", listeners: {}, value: "", _cls: new Set(),
    classList: { toggle() {} }, append(...c) { e.children.push(...c); }, appendChild(c) { e.children.push(c); return c; }, replaceChildren(...c) { e.children = [...c]; },
    addEventListener(n, f) { (e.listeners[n] ||= []).push(f); }, removeAttribute(a) { delete e[a]; }, load() {}, pause() { e.paused = true; }, play() { e.paused = false; return Promise.resolve(); }, paused: true,
    focus() {}, setPointerCapture() {}, getBoundingClientRect: () => ({ left: 0, top: 0 }) };
  return e;
}
globalThis.document = { createElement: mk, getElementById: () => null, head: mk("head") };
globalThis.window = globalThis;
globalThis.requestAnimationFrame = () => 1;
globalThis.cancelAnimationFrame = () => {};
const { app } = await load("scripts/app.js");
const { api } = await load("scripts/api.js");
await load("ext/web/majoor_videotools.js");
await load("ext/web/majoor_cuts.js");
const call = (hook, ...args) => app.exts.forEach((e) => e[hook]?.(...args));

function makeNode(id, properties, markersValue) {
  const n = { comfyClass: "MajoorCutMarkers", id, size: [500, 400], properties, inputs: [], graph: app.graph,
    widgets: [{ name: "markers", value: markersValue, callback() {} }, { name: "min_shot_seconds", value: 1.0 }],
    addDOMWidget(name, type, element, opts) { const w = { name, type, element, opts }; n.widgets.push(w); n.domOpts = opts; return w; },
    setSize(sz) { n.size = sz; }, computeSize: () => [500, 400] };
  return n;
}
const node = makeNode(5, {}, "");
const markersWidget = node.widgets[0];
app.graph._nodes = [node];
call("setup");
call("nodeCreated", node);
const editor = node.widgets.find((w) => w.name === "cuts_editor").element;
const [video, audio, bar, canvas, info] = editor.children;
check("the editor shows a hint before the first run", /Run the node once/.test(info.textContent) && node.domOpts.getMinHeight() === 34 + 170 + 56);

const payload = { duration: 6, fps: 24, video: { file: "ref.mp4", folder: "", kind: "temp" }, audio: { file: "m.wav", folder: "majoor_cuts", kind: "temp" },
  peaks: [0.1, 0.9, 0.5, 1], beats: [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5], bpm: 120, beats_per_bar: 4, downbeat: 0, video_cuts: [0.5, 1.5, 2.5], markers: [] };
api.emit("executed", { node: "5", output: { majoor_cuts: [payload] } });
check("after a run: the media are loaded, the payload is kept with the workflow",
  video.src.includes("ref.mp4") && audio.src.includes("majoor_cuts") && audio.src.includes("type=temp") && node.properties.majoor_cuts_ui === payload && video.style.display === "");
check("the summary counts what the markers make", /0 markers → 1 cuts → 1 shots/.test(info.textContent) && /120 BPM/.test(info.textContent) && /3 cuts detected/.test(info.textContent));
const [playBtn, addBtn, snapSel, fillSel] = bar.children;
check("snap defaults to the beats when there is a music", snapSel.value === "beat" && node.domOpts.getMinHeight() === 230 + 34 + 170 + 56);

const key = (k, extra = {}) => editor.listeners.keydown.forEach((f) => f({ key: k, target: {}, preventDefault() {}, stopPropagation() {}, ...extra }));
key("ArrowRight", { shiftKey: true }); key("ArrowRight", { shiftKey: true });
check("arrows move the playhead (a second with shift) and both media follow", audio.currentTime === 2 && video.currentTime === 2);
key("m");
check("M adds a marker at the playhead and writes the text widget", markersWidget.value === "2" && /1 markers → 2 cuts → 2 shots/.test(info.textContent));
key("ArrowRight", { shiftKey: true }); key("m"); key("m");
check("a second marker, never twice at the same time", markersWidget.value === "2 3");
key("z", { ctrlKey: true });
check("undo", markersWidget.value === "2");
fillSel.listeners.change.forEach((f) => { fillSel.value = "beats:bar"; f(); });
check("fill from the bars of the music (a bar every 4 beats of 0.5 s, from the first beat)", markersWidget.value === "0.5 2.5 4.5");
fillSel.listeners.change.forEach((f) => { fillSel.value = "video"; f(); });
check("fill from the cuts of the video", markersWidget.value === "0.5 1.5 2.5" && /3 markers → 4 cuts/.test(info.textContent));
key("z", { ctrlKey: true }); key("z", { ctrlKey: true });
bar.children.find((b) => b.textContent === "Clear").listeners.click.forEach((f) => f());
check("clear removes every marker", markersWidget.value === "");

markersWidget.value = "1 2.5 4";
markersWidget.callback("1 2.5 4");
check("typing the markers updates the editor", /3 markers → 4 cuts/.test(info.textContent));
key(" ");
check("space starts the music and the video", audio.paused === false && video.paused === false && video.muted === true);
key(" ");
check("and stops them", audio.paused === true && video.paused === true);

const second = makeNode(6, { majoor_cuts_ui: { ...payload, audio: null, peaks: [], beats: [] } }, "1");
app.graph._nodes.push(second);
call("nodeCreated", second);
call("loadedGraphNode", second);
check("a saved graph reopens with its media, and without music snaps to frames", second.widgets.find((w) => w.name === "cuts_editor").element.children[2].children[2].value === "frame");

fs.rmSync(root, { recursive: true, force: true });
if (failures) { console.error(`${failures} failed`); process.exit(1); }
console.log("cut markers editor ok");
process.exit(0);
