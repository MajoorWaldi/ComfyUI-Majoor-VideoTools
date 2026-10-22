// Edit Mode against a fake ComfyUI app: node tests/web/mode.mjs
import assert from "node:assert";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = fs.mkdtempSync(path.join(os.tmpdir(), "mjr-mode-"));
fs.mkdirSync(path.join(root, "scripts"));
fs.mkdirSync(path.join(root, "ext/web"), { recursive: true });
fs.writeFileSync(path.join(root, "package.json"), '{"type":"module"}');
fs.writeFileSync(path.join(root, "scripts/app.js"), "export const app = { exts: [], graph: { _nodes: [], setDirtyCanvas() {} }, registerExtension(e) { this.exts.push(e); }, built: 0, graphToPrompt() { this.built++; return {}; } };");
fs.writeFileSync(path.join(root, "scripts/api.js"), `export const api = { sent: [], async fetchApi(url, options) { if (url.includes("preflight")) { this.sent.push(JSON.parse(options.body)); return { ok: true, json: async () => ({ problems: ["Ollama does not have the model 'qwen3.8:latest'. Install it with: ollama pull qwen3.8:latest"] }) }; } return { json: async () => ({ presets: { "Image to Reel": "image_to_edit", Remix: "remix_replace", "Music Edit": "music_to_edit" }, modes: {
  music_to_edit: { profile: "music_video", genre: "all", reference_mode: false, reference_video: false, enhancer: "music enhancer line", extra_instructions: "on the kick" },
  text_to_edit: { profile: "narrative_cinematic", genre: "all", reference_mode: false, reference_video: false, extra_instructions: "no picture" },
  remix_replace: { pose_strength: 0.8, remix_instruction: "Replace the man", reference_video: true } } }) }; } };`);
fs.copyFileSync(new URL("../../web/majoor_mode.js", import.meta.url), path.join(root, "ext/web/majoor_mode.js"));
const { app } = await import(pathToFileURL(path.join(root, "scripts/app.js")).href);
const { api } = await import(pathToFileURL(path.join(root, "scripts/api.js")).href);
const { applyBlocks, preflight } = await import(pathToFileURL(path.join(root, "ext/web/majoor_mode.js")).href);

const widget = (name, value) => ({ name, value, callback() { this.called = true; } });
const controller = {
  comfyClass: "MajoorEditMode",
  widgets: [widget("preset", "Image to Reel"), widget("style", "Mode default"), widget("mode", "image_to_edit"), widget("reference_2", false), widget("reference_3", false), widget("reference_4", false), widget("reference_5", false), widget("pose_control", true), widget("pose_strength", 0.72), widget("remix_instruction", "Replace the man"), widget("reference_video", true)],
};
const node = (modes, extra = {}) => ({ comfyClass: "X", mode: 0, properties: { majoor_mode: { modes, ...extra } }, widgets: [widget("source", "none"), widget("switch", false)] });
const image = node(["image_to_edit", "reference_to_edit", "music_to_edit", "remix_replace"]);
const music = node(["music_to_edit"]);
const remix = node(["remix_replace"]);
const timeline = node(["image_to_edit", "reference_to_edit", "music_to_edit", "text_to_edit"], { values: { source: { reference_to_edit: "video", music_to_edit: "music", "*": "none" }, switch: { remix_replace: true, "*": false } } });
const second = { comfyClass: "X", mode: 4, properties: { majoor_mode: { toggle: "reference_2" } }, widgets: [] };
const fifth = { comfyClass: "X", mode: 4, properties: { majoor_mode: { toggle: "reference_5" } }, widgets: [] };
const video = { comfyClass: "X", mode: 0, properties: { majoor_mode: { toggle: "reference_video" } }, widgets: [] };
const planner = { comfyClass: "X", mode: 0, properties: { majoor_mode: { planner: true } }, widgets: [widget("profile", "viral_aura_farming"), widget("genre", "all"), widget("reference_mode", false), widget("extra_instructions", "")] };
const musicOnly = { comfyClass: "X", mode: 0, properties: { majoor_mode: { profile: true } }, widgets: [widget("profile", "none"), widget("genre", "keep")] };
const enhancer = { comfyClass: "X", mode: 0, properties: { majoor_mode: { enhancer: true } }, widgets: [widget("extra_instructions", "")] };
const plain = { comfyClass: "X", mode: 0, properties: {}, widgets: [] };
const request = { id: 900, comfyClass: "PrimitiveStringMultiline", mode: 0, properties: { majoor_deploy: { shot: "shared" } }, widgets: [widget("value", "old request")] };
const base = { id: 901, comfyClass: "PrimitiveStringMultiline", mode: 4, properties: { majoor_mode: { modes: ["remix_replace"], request: true } }, widgets: [widget("value", "")] };
const block = (shot, link = null) => ({ comfyClass: "Y", mode: 0, properties: { majoor_deploy: { shot } }, inputs: [{ name: "string_b", link }], widgets: [widget("strength", 0.5), widget("string_b", "old")] });
const blocks = [block("SHOT_001", 9), block("SHOT_002", 9), block("shared")];
app.graph.links = new Map([[9, { origin_id: 900 }]]);
app.graph.getNodeById = (id) => app.graph._nodes.find((n) => n.id === id);
app.graph._nodes = [controller, image, music, remix, timeline, second, fifth, video, musicOnly, enhancer, planner, plain, request, base, ...blocks];
app.exts.forEach((e) => { e.nodeCreated?.(controller); e.setup?.(); });

const set = async (name, value) => { const w = controller.widgets.find((x) => x.name === name); w.value = value; await w.callback(); await new Promise((r) => setTimeout(r, 5)); };
const modes = () => [image, music, remix, timeline, second, fifth, plain].map((n) => n.mode).join("");

await set("mode", "music_to_edit");
assert.equal(controller.widgets[0].value, "Music Edit", "the preset follows the mode");
assert.equal(modes(), "0040440");
assert.equal(timeline.widgets[0].value, "music");
assert.equal(planner.widgets[0].value, "music_video", "the planner gets the profile of the mode");
assert.equal(planner.widgets[3].value, "on the kick");
assert.equal(blocks[0].widgets[0].value, 0, "the pose ControlNet is off outside the remix");
assert.equal(blocks[2].widgets[0].value, 0.5, "a node that is no shot block is left alone");
assert.equal(controller.widgets.find((w) => w.name === "reference_video").value, false, "the mode skill says whether the reference video is used");
assert.equal(musicOnly.widgets[0].value, "music_video", "the music takes the profile of the mode");
assert.equal(musicOnly.widgets[1].value, "keep", "and nothing else");
assert.equal(enhancer.widgets[0].value, "music enhancer line", "the prompt enhancer is told what the mode is for");
await set("reference_2", true);
await set("reference_5", true);
assert.equal(modes(), "0040000", "toggles turn their nodes on");
planner.widgets[0].value = "beauty_premium"; // adjusted by hand
app.graphToPrompt();
assert.equal(planner.widgets[0].value, "beauty_premium", "a queue does not undo what was adjusted by hand");
await set("style", "beauty_premium");
assert.equal(planner.widgets[0].value, "beauty_premium", "the style replaces the profile of the mode");
assert.equal(musicOnly.widgets[0].value, "beauty_premium", "and the one of the music");
await set("style", "Mode default");
assert.equal(planner.widgets[0].value, "music_video", "the mode default comes back");
await set("preset", "Remix");
assert.equal(controller.widgets[2].value, "remix_replace", "a preset sets the mode and the nodes follow");
assert.equal(remix.mode, 0);
await set("preset", "Advanced");
assert.equal(controller.widgets[2].value, "remix_replace", "Advanced leaves the mode where it is");
await set("preset", "Music Edit");
await set("reference_video", false);
assert.equal(video.mode, 4, "the reference video nodes are bypassed when it is off");
await set("reference_video", true);
assert.equal(video.mode, 0);
await set("mode", "remix_replace");
assert.equal(modes(), "0404000");
assert.equal(timeline.widgets[1].value, true, "the switch is set for the remix");
assert.deepEqual(blocks.map((b) => b.widgets[0].value), [0.8, 0.8, 0.5], "pose strength goes to the blocks of the shots only");
assert.equal(base.mode, 0, "the base request of the remix LLM is on in the remix");
assert.equal(base.widgets[0].value, "Replace the man", "the instruction goes into the base request of the remix LLM");
assert.equal(request.widgets[0].value, "old request", "the request the blocks read is then the answer of the LLM, not written here");
assert.equal(blocks[1].widgets[1].value, "old", "not into the widget that a link overrides");
assert.equal(controller.widgets.find((w) => w.name === "pose_strength").value, 0.8, "the remix skill sets the pose strength");
await set("pose_strength", 0.9);
assert.equal(blocks[0].widgets[0].value, 0.9);
await set("pose_control", false);
assert.equal(blocks[0].widgets[0].value, 0, "pose_control off: no ControlNet in the remix either");
await set("pose_control", true);
await set("remix_instruction", "");
blocks[0].widgets[1].value = "my own";
applyBlocks(app.graph); // what Create shots calls after a deployment
assert.equal(blocks[0].widgets[1].value, "my own", "an empty instruction leaves the blocks' own");
await set("mode", "reference_to_edit");
assert.equal(timeline.widgets[0].value, "video");
assert.equal(timeline.widgets[1].value, false);
assert.equal(plain.mode, 0, "a node without a tag is left alone");
// without a remix LLM in the graph the instruction goes into the request that the blocks are linked to
app.graph._nodes = app.graph._nodes.filter((n) => n !== base);
await set("mode", "remix_replace");
await set("remix_instruction", "Replace the man by the woman");
assert.equal(request.widgets[0].value, "Replace the man by the woman");
// a controller saved before the preset and the style existed
const old = { comfyClass: "MajoorEditMode", widgets: controller.widgets.map((w) => ({ ...w })) };
const saved = ["remix_replace", false, false, false, false, true, 0.7, "Replace it", true];
app.exts[0].nodeCreated(old);
old.onConfigure({ widgets_values: saved });
assert.deepEqual(old.widgets.map((w) => w.value), ["Advanced", "Mode default", ...saved], "the saved values go to the widgets they belong to");

// the check before a queue
const connection = (mode, url, model) => ({ comfyClass: "OllamaConnectivityV2", mode, widgets: [widget("url", url), widget("model", model)] });
const inside = { comfyClass: "SubgraphInstance", type: "2f1c9a60-1111-4222-8333-444455556666", mode: 0, subgraph: { _nodes: [connection(0, "http://127.0.0.1:11434", "qwen3.8:latest"), connection(4, "http://127.0.0.1:11434", "bypassed:1b"), { comfyClass: "SetNode", mode: 0 }] } };
const problems = await preflight({ _nodes: [inside, { comfyClass: "KJLostNode", mode: 0 }, { comfyClass: "Muted", mode: 2 }] }, { SetNode: {}, OllamaConnectivityV2: {}, "2f1c9a60-1111-4222-8333-444455556666": {} });
assert.deepEqual(api.sent, [{ ollama: [{ url: "http://127.0.0.1:11434", model: "qwen3.8:latest" }] }], "the Ollama nodes that run are asked about, the bypassed one is not");
assert.match(problems[0], /Missing custom nodes: KJLostNode\./, "an unknown node is named");
assert.doesNotMatch(problems[0], /Muted|2f1c9a60/, "a muted node and a subgraph are not missing");
assert.match(problems[1], /ollama pull qwen3\.8/);
console.log("mode ok");
fs.rmSync(root, { recursive: true, force: true });
