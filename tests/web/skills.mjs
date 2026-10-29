// The Reload skills and Copy prompt buttons of Edit Skills: node tests/web/skills.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = fs.mkdtempSync(path.join(os.tmpdir(), "mjr-skills-"));
fs.mkdirSync(path.join(root, "scripts"));
fs.mkdirSync(path.join(root, "ext/web"), { recursive: true });
fs.writeFileSync(path.join(root, "package.json"), '{"type":"module"}');
fs.writeFileSync(path.join(root, "scripts/app.js"), `export const app = { exts: [], registerExtension(e) { this.exts.push(e); } };`);
fs.writeFileSync(path.join(root, "scripts/api.js"), `export const api = { calls: [], async fetchApi(url, init) { this.calls.push([url, init && JSON.parse(init.body)]); const ok = url.endsWith("compose") ? { text: "PROMPT", words: 1 } : { skills: ["a", "b"], profiles: ["none", "p"] }; return { ok: true, json: async () => ok }; } };`);
fs.copyFileSync(new URL("../../web/majoor_skills.js", import.meta.url), path.join(root, "ext/web/majoor_skills.js"));
let copied = null;
Object.defineProperty(globalThis, "navigator", { value: { clipboard: { writeText: async (t) => { copied = t; } } }, configurable: true });
const { app } = await import(pathToFileURL(path.join(root, "scripts/app.js")).href);
const { api } = await import(pathToFileURL(path.join(root, "scripts/api.js")).href);
await import(pathToFileURL(path.join(root, "ext/web/majoor_skills.js")).href);

const widgets = [{ name: "skill", value: "gone", options: { values: ["gone"] } }, { name: "genre", value: "ugc" }, { name: "profile", value: "removed", options: { values: ["none", "removed"] } }];
const buttons = {};
const node = { comfyClass: "MajoorEditSkills", title: "Edit Skills", widgets, addWidget(type, name, _v, cb) { buttons[name] = cb; }, setDirtyCanvas() {} };
const other = { comfyClass: "SaveVideo", addWidget() { throw new Error("must not be touched"); } };
app.exts.forEach((e) => { e.nodeCreated?.(node); e.nodeCreated?.(other); });
await buttons["Reload skills"]();
const reloaded = JSON.stringify(widgets[0].options.values) === '["a","b"]' && widgets[0].value === "a" && node.title.includes("2 skills") && JSON.stringify(widgets[2].options.values) === '["none","p"]' && widgets[2].value === "none";
await buttons["Copy prompt"]();
const sent = api.calls.at(-1)[1];
// a workflow saved before the profile existed puts the values of the two buttons on the profile widgets
const profile = widgets[2], dial = { name: "cut_density", value: null, options: { values: ["auto", "low"] } };
profile.value = null;
node.widgets.push(dial);
node.onConfigure();
const reset = profile.value === "none" && dial.value === "auto";
const ok = reset && reloaded && copied === "PROMPT" && sent.skill === "a" && sent.genre === "ugc" && Object.keys(buttons).length === 2;
console.log(ok ? "skills buttons ok" : "FAILED " + JSON.stringify({ reset, reloaded, copied, sent, title: node.title }));
fs.rmSync(root, { recursive: true, force: true });
process.exit(ok ? 0 : 1);
