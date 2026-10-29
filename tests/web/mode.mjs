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
fs.writeFileSync(path.join(root, "scripts/api.js"), `export const api = { async fetchApi() { return { json: async () => ({ cameras: { film_16mm: "CAMERA LOOK: a classic 16 mm film camera." }, modes: {
  creative: { from_video: false, enhancer: "creative enhancer", enhancer_from_video: "from the video", profile: "viral_aura_farming", profile_from_video: "none", genre: "all", reference_mode: false, extra_instructions: "pictures and brief", from_video_instructions: "follow the EDIT RHYTHM" },
  remix_replace: { from_video: true, enhancer: "remix enhancer", pose_strength: 0.8, remix_instruction: "Replace the man" } } }) }; } };`);
fs.copyFileSync(new URL("../../web/majoor_mode.js", import.meta.url), path.join(root, "ext/web/majoor_mode.js"));
const { app } = await import(pathToFileURL(path.join(root, "scripts/app.js")).href);
const { applyBlocks, preflight } = await import(pathToFileURL(path.join(root, "ext/web/majoor_mode.js")).href);

const widget = (name, value) => ({ name, value, callback() { this.called = true; } });
const controller = {
  comfyClass: "MajoorEditMode",
  widgets: [widget("style", "Mode default"), widget("mode", "creative"), widget("reference_2", false), widget("reference_3", false), widget("reference_4", false), widget("reference_5", false), widget("pose_control", true), widget("pose_strength", 0.72), widget("remix_instruction", "Replace the man"), widget("from_video", false), widget("ref_video", false), widget("own_music", false), widget("voice", false), widget("camera", "none"), widget("quality_check", false)],
};
const node = (tag, widgets = []) => ({ comfyClass: "X", mode: 0, properties: { majoor_mode: tag }, widgets });
const creative = node({ modes: ["creative"] });
const remix = node({ modes: ["remix_replace"] });
const video = node({ any: ["remix_replace", "from_video"] });
const refVideo = node({ toggle: "ref_video" });
const music = node({ modes: ["creative"], toggle: "own_music" });
const generated = node({ modes: ["creative"], unless: "own_music" });
const second = node({ toggle: "reference_2", modes: ["creative", "remix_replace"] });
const fifth = node({ toggle: "reference_5" });
const timeline = node({ modes: ["creative"], values: { source: { from_video: "video", own_music: "music", "*": "none" }, switch: { remix_replace: true, "*": false } } }, [widget("source", "none"), widget("switch", false)]);
const shots = node({ values: { switch: { remix_replace: true, "*": false } } }, [widget("switch", false)]);
const planner = node({ planner: true }, [widget("profile", "viral_aura_farming"), widget("genre", "all"), widget("reference_mode", false), widget("extra_instructions", "")]);
const musicOnly = node({ profile: true }, [widget("profile", "none"), widget("genre", "keep")]);
const enhancer = node({ enhancer: true }, [widget("extra_instructions", "")]);
const inline = node({ modes: ["remix_replace"], pose: true }, [widget("strength", 193129495093947)]);
const assemble = node({ values: { audio_policy: { voice: "shot_audio", "*": "source_master" } } }, [widget("audio_policy", "source_master")]);
const plain = { comfyClass: "X", mode: 0, properties: {}, widgets: [] };
const request = { id: 900, comfyClass: "PrimitiveStringMultiline", mode: 0, properties: { majoor_deploy: { shot: "shared" } }, widgets: [widget("value", "old request")] };
const base = { id: 901, comfyClass: "PrimitiveStringMultiline", mode: 4, properties: { majoor_mode: { modes: ["remix_replace"], request: true } }, widgets: [widget("value", "")] };
const block = (shot, link = null) => ({ comfyClass: "Y", mode: 0, properties: { majoor_deploy: { shot } }, inputs: [{ name: "string_b", link }], widgets: [widget("strength", 0.5), widget("string_b", "old")] });
const blocks = [block("SHOT_001", 9), block("SHOT_002", 9), block("shared")];
app.graph.links = new Map([[9, { origin_id: 900 }]]);
app.graph.getNodeById = (id) => app.graph._nodes.find((n) => n.id === id);
app.graph._nodes = [assemble, inline, controller, creative, remix, video, refVideo, music, generated, second, fifth, timeline, shots, musicOnly, enhancer, planner, plain, request, base, ...blocks];
app.exts.forEach((e) => { e.nodeCreated?.(controller); e.setup?.(); });

const set = async (name, value) => { const w = controller.widgets.find((x) => x.name === name); w.value = value; await w.callback(); await new Promise((r) => setTimeout(r, 5)); };
const get = (name) => controller.widgets.find((w) => w.name === name).value;
const modes = (...nodes) => nodes.map((n) => n.mode).join("");

await set("mode", "remix_replace");
assert.equal(modes(creative, remix, video, refVideo, music, second, fifth, plain, generated), "400444404", "the remix: its nodes and the video are on, the creative ones are off");
assert.equal(get("from_video"), true, "the remix always works on a video");
assert.equal(shots.widgets[0].value, true, "the switches of the remix are set");
assert.deepEqual(blocks.map((b) => b.widgets[0].value), [0.8, 0.8, 0.5], "pose strength goes to the blocks of the shots only");
assert.equal(base.mode, 0, "the base request of the remix LLM is on in the remix");
assert.equal(base.widgets[0].value, "Replace the man", "the instruction goes into the base request of the remix LLM");
assert.equal(request.widgets[0].value, "old request", "the request the blocks read is then the answer of the LLM, not written here");
assert.equal(blocks[1].widgets[1].value, "old", "not into the widget that a link overrides");
assert.equal(enhancer.widgets[0].value, "remix enhancer");
assert.equal(inline.widgets[0].value, 0.8, "a block of the graph tagged pose follows the strength of the controller, whatever was saved in its widget");
assert.equal(get("pose_strength"), 0.8, "the remix skill sets the pose strength");

await set("mode", "creative");
assert.equal(modes(creative, remix, video, refVideo, music), "04444", "creative: no video unless asked");
assert.equal(get("from_video"), false);
assert.equal(timeline.widgets[0].value, "none");
assert.equal(shots.widgets[0].value, false);
assert.equal(planner.widgets[0].value, "viral_aura_farming", "the planner gets the profile of the mode");
assert.equal(planner.widgets[2].value, false);
assert.equal(planner.widgets[3].value, "pictures and brief");
assert.equal(musicOnly.widgets[0].value, "viral_aura_farming", "the music takes the profile of the mode");
assert.equal(musicOnly.widgets[1].value, "keep", "and nothing else");
assert.equal(enhancer.widgets[0].value, "creative enhancer", "the prompt enhancer is told what the mode is for");
assert.deepEqual(blocks.map((b) => b.widgets[0].value), [0, 0, 0.5], "the pose ControlNet is off outside the remix");

await set("camera", "film_16mm");
assert.equal(planner.widgets[3].value, "pictures and brief CAMERA LOOK: a classic 16 mm film camera.", "the camera look goes into the instructions of the planner");
assert.equal(enhancer.widgets[0].value, "creative enhancer CAMERA LOOK: a classic 16 mm film camera.", "and into the ones of the enhancer");
await set("camera", "none");
assert.equal(planner.widgets[3].value, "pictures and brief");
await set("voice", true);
assert.equal(assemble.widgets[0].value, "shot_audio", "with a voice the shots keep their own audio");
await set("voice", false);
assert.equal(assemble.widgets[0].value, "source_master");
await set("from_video", true);
assert.equal(video.mode, 0, "from_video turns the video on");
assert.equal(timeline.widgets[0].value, "video", "and the rhythm follows it");
assert.equal(planner.widgets[0].value, "none", "the profile of a video edit");
assert.equal(planner.widgets[2].value, true, "reference_mode");
assert.equal(planner.widgets[3].value, "pictures and brief follow the EDIT RHYTHM");
assert.equal(enhancer.widgets[0].value, "creative enhancer from the video");
await set("own_music", true);
assert.equal(music.mode, 0, "own_music turns the MUSIC file on");
assert.equal(generated.mode, 4, "and the music generated for the edit off");
assert.equal(timeline.widgets[0].value, "video", "the video comes first");
await set("from_video", false);
assert.equal(timeline.widgets[0].value, "music", "the rhythm follows the music of the user");
assert.equal(video.mode, 4);
await set("own_music", false);
assert.equal(timeline.widgets[0].value, "none");
assert.equal(generated.mode, 0);
await set("ref_video", true);
assert.equal(refVideo.mode, 0, "the reference video is a toggle of its own");
await set("reference_2", true);
await set("reference_5", true);
assert.equal(modes(second, fifth), "00", "toggles turn their nodes on");
await set("style", "beauty_premium");
assert.equal(planner.widgets[0].value, "beauty_premium", "the style replaces the profile of the mode");
assert.equal(musicOnly.widgets[0].value, "beauty_premium", "and the one of the music");
await set("style", "Mode default");
assert.equal(planner.widgets[0].value, "viral_aura_farming", "the mode default comes back");
planner.widgets[0].value = "beauty_premium"; // adjusted by hand
app.graphToPrompt();
assert.equal(planner.widgets[0].value, "beauty_premium", "a queue does not undo what was adjusted by hand");

await set("camera", "film_16mm");
await set("mode", "remix_replace");
assert.equal(enhancer.widgets[0].value, "remix enhancer", "the remix keeps the camera of the video: no camera look");
await set("camera", "none");
await set("remix_instruction", "");
blocks[0].widgets[1].value = "my own";
applyBlocks(app.graph); // what Create shots calls after a deployment
assert.equal(blocks[0].widgets[1].value, "my own", "an empty instruction leaves the blocks' own");
await set("pose_control", false);
assert.equal(blocks[0].widgets[0].value, 0, "pose_control off: no ControlNet in the remix either");
// without a remix LLM in the graph the instruction goes into the request that the blocks are linked to
app.graph._nodes = app.graph._nodes.filter((n) => n !== base);
await set("remix_instruction", "Replace the man by the woman");
assert.equal(request.widgets[0].value, "Replace the man by the woman");
assert.equal(plain.mode, 0, "a node without a tag is left alone");

// the check before a queue
const inside = { comfyClass: "SubgraphInstance", type: "2f1c9a60-1111-4222-8333-444455556666", mode: 0, subgraph: { _nodes: [{ comfyClass: "SetNode", mode: 0 }, { comfyClass: "KJBypassed", mode: 4 }] } };
const problems = preflight({ _nodes: [inside, { comfyClass: "KJLostNode", mode: 0 }, { comfyClass: "Muted", mode: 2 }] }, { SetNode: {}, "2f1c9a60-1111-4222-8333-444455556666": {} });
assert.equal(problems.length, 1);
assert.match(problems[0], /Missing custom nodes: KJLostNode\./, "an unknown node is named");
assert.doesNotMatch(problems[0], /Muted|KJBypassed|2f1c9a60/, "a muted or bypassed node and a subgraph are not missing");
console.log("mode ok");
fs.rmSync(root, { recursive: true, force: true });
