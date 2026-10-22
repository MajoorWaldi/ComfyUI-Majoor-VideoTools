// Regenerate one shot against a fake ComfyUI app: node tests/web/regen.mjs
import assert from "node:assert";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = fs.mkdtempSync(path.join(os.tmpdir(), "mjr-regen-"));
fs.mkdirSync(path.join(root, "scripts"));
fs.mkdirSync(path.join(root, "ext/web"), { recursive: true });
fs.writeFileSync(path.join(root, "package.json"), '{"type":"module"}');
fs.writeFileSync(path.join(root, "scripts/app.js"), "export const app = { queued: 0, graph: { _nodes: [], links: new Map(), getNodeById(id) { return this._nodes.find((n) => n.id == id); }, setDirtyCanvas() {} }, async queuePrompt() { this.queued++; } };");
fs.copyFileSync(new URL("../../web/majoor_regen.js", import.meta.url), path.join(root, "ext/web/majoor_regen.js"));
const { app } = await import(pathToFileURL(path.join(root, "scripts/app.js")).href);
const { regenerateShot } = await import(pathToFileURL(path.join(root, "ext/web/majoor_regen.js")).href);

const seed = (value) => ({ name: "noise_seed", value, options: { max: 2 ** 53 } });
const select = (id, shot) => ({ id, comfyClass: "MajoorSelectShot", widgets: [{ name: "shot_id", value: shot }], outputs: [{ links: [1] }] });
const sampler = { id: 2, comfyClass: "Sampler", widgets: [seed(7)], outputs: [{ links: [2] }] };
const apply = { id: 3, comfyClass: "MajoorApplyShotMetadata", widgets: [], outputs: [] };
const other = { id: 4, comfyClass: "Sampler", widgets: [seed(9)], properties: { majoor_deploy: { shot: "SHOT_002" } } };
const stamped = { id: 5, comfyClass: "Sampler", widgets: [seed(11)], properties: { majoor_deploy: { shot: "SHOT_001" } } };
app.graph._nodes = [select(1, "SHOT_001"), sampler, apply, other, stamped];
app.graph.links.set(1, { target_id: 2 });
app.graph.links.set(2, { target_id: 3 });

const message = await regenerateShot("SHOT_001");
assert.equal(app.queued, 1);
assert.notEqual(sampler.widgets[0].value, 7, "the seed downstream of the Select Shot changes");
assert.notEqual(stamped.widgets[0].value, 11, "the seed of a stamped node changes");
assert.equal(other.widgets[0].value, 9, "another shot is left alone");
assert.match(message, /SHOT_001 queued/);
assert.match(await regenerateShot("SHOT_099"), /No seed found for SHOT_099/);
assert.equal(app.queued, 1, "nothing is queued without a seed");
console.log("regen ok");
