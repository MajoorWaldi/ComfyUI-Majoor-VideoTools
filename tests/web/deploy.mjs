// The Create shots button of Deploy Shots against a fake DOM and a fake ComfyUI app/api: node tests/web/deploy.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = fs.mkdtempSync(path.join(os.tmpdir(), "mjr-deploy-"));
fs.mkdirSync(path.join(root, "scripts"));
fs.mkdirSync(path.join(root, "ext/web"), { recursive: true });
fs.writeFileSync(path.join(root, "package.json"), '{"type":"module"}');
fs.writeFileSync(path.join(root, "scripts/app.js"), `export const app = { exts: [], loaded: [], graph: { _nodes: [], getNodeById(id) { return this._nodes.find(n => n.id == id); }, setDirtyCanvas() {}, serialize() { return { nodes: [{ id: 10 }], links: [] }; } },
  registerExtension(e) { this.exts.push(e); }, async loadGraphData(...args) { this.loaded.push(args); }, extensionManager: { workflow: { activeWorkflow: { name: "active" } } } };`);
fs.writeFileSync(path.join(root, "scripts/api.js"), `export const api = { calls: [], reply: null, apiURL: (r) => "/api" + r, addEventListener() {},
  async fetchApi(url, init) { this.calls.push({ url, body: JSON.parse(init.body) }); return this.reply(); } };`);
fs.copyFileSync(new URL("../../web/majoor_videotools.js", import.meta.url), path.join(root, "ext/web/majoor_videotools.js"));
fs.copyFileSync(new URL("../../web/majoor_mode.js", import.meta.url), path.join(root, "ext/web/majoor_mode.js"));
fs.copyFileSync(new URL("../../web/majoor_regen.js", import.meta.url), path.join(root, "ext/web/majoor_regen.js"));
fs.copyFileSync(new URL("../../web/majoor_deploy.js", import.meta.url), path.join(root, "ext/web/majoor_deploy.js"));
const load = (p) => import(pathToFileURL(path.join(root, p)).href);

function mk(tag) {
  const e = { tag, children: [], style: {}, dataset: {}, className: "", textContent: "", listeners: {}, classList: { toggle() {} },
    append(...c) { e.children.push(...c); }, appendChild(c) { e.children.push(c); return c; }, replaceChildren(...c) { e.children = [...c]; },
    addEventListener() {}, removeAttribute() {}, load() {}, pause() {}, play() {}, setAttribute() {} };
  return e;
}
globalThis.document = { createElement: mk, getElementById: () => null, head: mk("head") };
globalThis.window = globalThis;
let asked = [];
globalThis.confirm = (text) => { asked.push(text); return confirmAnswer; };
let confirmAnswer = true;
const { app } = await load("scripts/app.js");
const { api } = await load("scripts/api.js");
await load("ext/web/majoor_videotools.js");
await load("ext/web/majoor_deploy.js");
const call = (hook, ...args) => app.exts.forEach((e) => e[hook]?.(...args));

function node(cls, id, extra = {}) {
  const n = { comfyClass: cls, type: cls, id, size: [400, 300], properties: {}, inputs: [], widgets: [], graph: app.graph, ...extra,
    addDOMWidget(name, type, el, opts) { const w = { name, type, el, opts }; n.widgets.push(w); return w; },
    addWidget(type, name, value, callback) { const w = { type, name, value, callback }; n.widgets.push(w); return w; },
    setSize(s) { n.size = s; }, computeSize: () => [340, 200], getInputNode(i) { return n._up?.[i] ?? null; } };
  return n;
}
const value = (name, v) => ({ name, value: v });
const deployer = node("MajoorDeployShots", 10, { inputs: [{ name: "shot_list", link: 1 }, { name: "max_shots", link: null }],
  widgets: [value("recipe", "minimax_h3_ref2va"), value("max_shots", 0), value("columns", 2), value("include_finale", true), value("replace_existing", true)] });
const getter = node("GetNode", 11, { type: "GetNode", widgets: [value("Constant", "SHOT_LIST")] });
const setter = node("SetNode", 12, { type: "SetNode", widgets: [value("Constant", "SHOT_LIST")], inputs: [{ name: "MAJOOR_SHOT_LIST", link: 2 }] });
const detect = node("MajoorSceneDetectSplit", 13);
deployer._up = { 0: getter }; setter._up = { 0: detect };
app.graph._nodes = [deployer, getter, setter, detect];
for (const n of app.graph._nodes) call("nodeCreated", n);

const button = deployer.widgets.find((w) => w.type === "button");
const info = deployer.widgets.find((w) => w.name === "deploy_report").el.children[0];
const settle = () => new Promise((r) => setTimeout(r, 10));
let failures = 0;
const check = (name, ok) => { console.log(ok ? "ok  " : "FAIL", name); if (!ok) failures++; };

check("button and report widgets exist", !!button && button.name === "Create shots" && /Run Scene Detect/.test(info.textContent));

await button.callback(); await settle();
check("without a payload: asks to run the source node, nothing is sent", api.calls.length === 0 && /Run Scene Detect/.test(info.textContent));

detect.properties.majoor_ui = { base: "p", source: {}, shots: [{ id: "SHOT_001" }, { id: "SHOT_002" }, { id: "SHOT_003" }] };
const merged = { nodes: [{ id: 10, properties: { majoor_deploy: { recipe: "SHOT_001", shots: ["SHOT_001", "SHOT_002", "SHOT_003"] } } }], links: [] };
api.reply = async () => ({ ok: true, json: async () => ({ workflow: merged, report: { created: ["SHOT_001", "SHOT_002", "SHOT_003"], replaced: [], warnings: ["No Set node for: REF"], nodes_added: 33 } }) });
await button.callback(); await settle();
const sent = api.calls[0];
check("request goes to the deploy route with the recipe, the shots found through Get/Set, the anchor and the widgets",
  sent.url === "/majoor/deploy_shots" && sent.body.recipe === "minimax_h3_ref2va" && JSON.stringify(sent.body.shots) === '["SHOT_001","SHOT_002","SHOT_003"]'
  && sent.body.anchor === 10 && sent.body.columns === 2 && sent.body.include_finale === true && sent.body.workflow.nodes[0].id === 10);
check("the merged graph is loaded in the active workflow without clearing the view", app.loaded.length === 1 && app.loaded[0][0] === merged && app.loaded[0][1] === true && app.loaded[0][2] === false && app.loaded[0][3].name === "active");
check("warnings of the report are kept on the node", merged.nodes[0].properties.majoor_deploy.warnings[0] === "No Set node for: REF");

deployer.widgets.find((w) => w.name === "max_shots").value = 2;
await button.callback(); await settle();
check("max_shots limits the shots sent", JSON.stringify(api.calls[1].body.shots) === '["SHOT_001","SHOT_002"]');

const primitive = node("PrimitiveInt", 14, { widgets: [value("value", 1)] });
deployer._up[1] = primitive; deployer.inputs[1].link = 5;
await button.callback(); await settle();
check("a number linked to max_shots wins over the widget", JSON.stringify(api.calls[2].body.shots) === '["SHOT_001"]');
deployer._up[1] = detect;
await button.callback(); await settle();
check("the shot_count of a source node deploys every shot it lists", JSON.stringify(api.calls[3].body.shots) === '["SHOT_001","SHOT_002","SHOT_003"]');
const other = node("MajoorCreateTimeline", 15);
other.properties.majoor_ui = { base: "q", source: {}, shots: [{ id: "A" }] };
const choose = node("ComfySwitchNode", 16, { type: "ComfySwitchNode", widgets: [value("switch", true)], inputs: [{ name: "on_false", link: 6 }, { name: "on_true", link: 7 }] });
choose._up = { 0: other, 1: detect };
deployer._up[1] = choose;
await button.callback(); await settle();
check("a switch between two counts follows the one it selects", JSON.stringify(api.calls[4].body.shots) === '["SHOT_001","SHOT_002","SHOT_003"]');
choose.widgets[0].value = false;
await button.callback(); await settle();
check("and the other when it flips (its one shot)", api.calls[5].body.shots.length === 1);
deployer.inputs[1].link = null;

api.reply = async () => ({ ok: true, json: async () => ({ workflow: merged, report: { created: ["SHOT_001"], replaced: ["SHOT_001"], warnings: [], nodes_added: 11 } }) });
confirmAnswer = false;
const loadedBefore = app.loaded.length;
await button.callback(); await settle();
check("replacing hand-made blocks asks first, and declining leaves the graph alone", asked.length === 1 && /SHOT_001/.test(asked[0]) && app.loaded.length === loadedBefore && /Cancelled/.test(info.textContent));

api.reply = async () => ({ ok: false, status: 400, json: async () => ({ error: "Unknown recipe 'x'" }) });
await button.callback(); await settle();
check("a backend error is shown and nothing is loaded", /Unknown recipe/.test(info.textContent) && app.loaded.length === loadedBefore);

deployer.properties.majoor_deploy = { recipe: "r", shots: ["A", "B"], warnings: ["w"] };
call("loadedGraphNode", deployer);
check("a saved graph shows the last deployment", /2 shots deployed from 'r'/.test(info.textContent) && /⚠ w/.test(info.textContent));

fs.rmSync(root, { recursive: true, force: true });
if (failures) { console.error(`${failures} failed`); process.exit(1); }
console.log("deploy widget ok");
process.exit(0);
