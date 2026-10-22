// A Majoor node saved before it had some outputs gets them back when the graph loads: node tests/web/outputs.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = fs.mkdtempSync(path.join(os.tmpdir(), "mjr-outputs-"));
fs.mkdirSync(path.join(root, "scripts"));
fs.mkdirSync(path.join(root, "ext/web"), { recursive: true });
fs.writeFileSync(path.join(root, "package.json"), '{"type":"module"}');
fs.writeFileSync(path.join(root, "scripts/app.js"), `export const app = { exts: [], graph: { _nodes: [], getNodeById() { return null; }, setDirtyCanvas() {} }, registerExtension(e) { this.exts.push(e); } };`);
fs.writeFileSync(path.join(root, "scripts/api.js"), `export const api = { apiURL: (r) => r, addEventListener() {} };`);
fs.copyFileSync(new URL("../../web/majoor_videotools.js", import.meta.url), path.join(root, "ext/web/majoor_videotools.js"));
fs.copyFileSync(new URL("../../web/majoor_regen.js", import.meta.url), path.join(root, "ext/web/majoor_regen.js"));
globalThis.document = { createElement: () => ({ style: {}, classList: { toggle() {} }, append() {}, appendChild() {}, addEventListener() {}, dataset: {} }), getElementById: () => null, head: { appendChild() {} } };
const { app } = await import(pathToFileURL(path.join(root, "scripts/app.js")).href);
await import(pathToFileURL(path.join(root, "ext/web/majoor_videotools.js")).href);

const def = { output_name: ["video", "images", "prompt", "generation_seconds", "rhythm_text", "notes"], output: ["VIDEO", "IMAGE", "STRING", "FLOAT", "STRING", "STRING"] };
const make = (comfyClass, names) => {
  const added = [];
  return { comfyClass, constructor: { nodeData: def }, outputs: names.map((name) => ({ name, links: [3] })), added, addOutput(name, type) { added.push([name, type]); this.outputs.push({ name, type }); } };
};
const old = make("MajoorSelectShot", ["video", "images", "prompt"]);
const current = make("MajoorSelectShot", def.output_name);
const other = make("SaveVideo", ["video"]);
for (const n of [old, current, other]) app.exts.forEach((e) => e.loadedGraphNode?.(n));
const ok = JSON.stringify(old.added) === JSON.stringify([["generation_seconds", "FLOAT"], ["rhythm_text", "STRING"], ["notes", "STRING"]])
  && old.outputs.slice(0, 3).every((o) => o.links?.[0] === 3) && current.added.length === 0 && other.added.length === 0;
console.log(ok ? "outputs sync ok" : "FAILED " + JSON.stringify([old.added, current.added, other.added]));
fs.rmSync(root, { recursive: true, force: true });
process.exit(ok ? 0 : 1);
