// Majoor VideoTools - Edit Mode.
//
// The Edit Mode node holds the mode, the reference toggles and the remix settings. Nodes of the graph say what the mode does to them in
// properties.majoor_mode: {"modes": [...], "toggle": "reference_2", "values": {"widget": {"mode": value, "*": other}}}.
// A node with "modes" / "toggle" is enabled when its mode is listed and its toggle is on, bypassed otherwise;
// "values" sets widgets (the rhythm source, the shot list switch...). "request": true marks the base request of the remix LLM (it gets remix_instruction); "profile": true marks a node that only takes the profile (the music); "enhancer": true marks the prompt enhancer: it gets the line of the mode skill for it as extra_instructions; "planner": true marks the planner: it gets the profile, genre, reference_mode and
// instructions of the mode skill (skills/mode_<mode>.md, read from /majoor/modes). The nodes are set when the mode changes
// and when the graph is queued; "values" only when the mode changes, so that you can still adjust them by hand.
// The preset names the three usual modes ("Image to Reel", "Remix", "Music Edit"); "Advanced" leaves the mode to the combo below it. The style replaces the profile of the mode.
// Before a queue the Ollama nodes of the graph are checked (the model is installed, the server answers) and the nodes the frontend does not know are named, in words the user can act on.
// The shot blocks (made by Deploy Shots) get the pose ControlNet strength (remix only) and, in the remix, the replacement instruction.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE = "MajoorEditMode";
const ALWAYS = 0;
const BYPASS = 4;
const MUTE = 2;
const REMIX = "remix_replace";
const ADVANCED = "Advanced";
const STYLE_DEFAULT = "Mode default";
const OLLAMA = "OllamaConnectivityV2";
const SUBGRAPH_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-/;

const widgetOf = (node, name) => node.widgets?.find((w) => w.name === name);
const setWidget = (node, name, value) => {
  const widget = widgetOf(node, name);
  if (!widget || value === undefined || widget.value === value) return;
  widget.value = value;
  widget.callback?.(value);
};

export const controllerOf = (graph) => graph?._nodes?.find((n) => n.comfyClass === NODE);

export function applyMode(graph, controller, { values = true } = {}) {
  const mode = widgetOf(controller, "mode")?.value;
  for (const node of graph._nodes ?? []) {
    const tag = node.properties?.majoor_mode;
    if (!tag) continue;
    if (tag.modes || tag.toggle) {
      const on = (!tag.modes || tag.modes.includes(mode)) && (!tag.toggle || widgetOf(controller, tag.toggle)?.value);
      node.mode = on ? ALWAYS : BYPASS;
    }
    if (!values) continue;
    for (const [name, byMode] of Object.entries(tag.values ?? {})) setWidget(node, name, mode in byMode ? byMode[mode] : byMode["*"]);
  }
  graph.setDirtyCanvas?.(true, true);
}

// What the skill of the mode says (read again each time: an edited file is used at once): the planner, and the remix settings of the controller.
export async function applyModeSettings(graph, controller) {
  const mode = widgetOf(controller, "mode")?.value;
  let settings = null;
  try {
    const answer = await (await api.fetchApi("/majoor/modes")).json();
    settings = answer.modes?.[mode] ?? null;
    setWidget(controller, "preset", Object.keys(answer.presets ?? {}).find((name) => answer.presets[name] === mode) ?? ADVANCED);
  } catch {
    return;
  }
  if (!settings) return;
  const style = widgetOf(controller, "style")?.value;
  const profile = style && style !== STYLE_DEFAULT ? style : settings.profile;
  for (const node of graph._nodes ?? []) {
    const tag = node.properties?.majoor_mode;
    if (tag?.planner) {
      for (const name of ["genre", "reference_mode", "extra_instructions"]) setWidget(node, name, settings[name]);
      setWidget(node, "profile", profile);
    } else if (tag?.profile) setWidget(node, "profile", profile);  // the music of the edit takes the profile of the planner
    if (tag?.enhancer) setWidget(node, "extra_instructions", settings.enhancer);  // the prompt enhancer is told what the mode is for
  }
  setWidget(controller, "reference_video", settings.reference_video);
  setWidget(controller, "pose_strength", settings.pose_strength);
  setWidget(controller, "remix_instruction", settings.remix_instruction);
}

// The edit request of a block is the node its string_b input is linked to (the one every block shares), else the widget of the block.
function writeRequest(graph, block, text) {
  const link = block.inputs?.find((i) => i.name === "string_b")?.link;
  const origin = link == null ? null : graph.getNodeById((graph.links ?? graph._links)?.get?.(link)?.origin_id);
  if (origin) setWidget(origin, "value", text);
  else setWidget(block, "string_b", text);
}

// The blocks of the shots (made by Deploy Shots). The pose ControlNet of H3 follows the pose of the original shot: it is on in the remix (pose_strength,
// off with pose_control) and off in the other modes, where the shot is only a placeholder card; at strength 0 H3 skips it. The remix instruction is the edit request.
// The nodes that run: not bypassed or muted, the ones inside an active subgraph too.
function activeNodes(graph) {
  const found = [];
  for (const node of graph?._nodes ?? graph?.nodes ?? []) {
    if (node.mode === BYPASS || node.mode === MUTE) continue;
    found.push(node);
    const inside = node.subgraph;
    if (inside) found.push(...activeNodes(inside));
  }
  return found;
}

// What would fail when the graph is queued: nodes the frontend does not know, an Ollama that does not answer or that lacks the model.
export async function preflight(graph, registered = globalThis.LiteGraph?.registered_node_types) {
  const nodes = activeNodes(graph);
  const problems = [];
  const unknown = [...new Set(nodes.filter((n) => !n.subgraph).map((n) => n.comfyClass ?? n.type))].filter((type) => type && registered && !(type in registered) && !SUBGRAPH_ID.test(type));
  if (unknown.length) problems.push(`Missing custom nodes: ${unknown.join(", ")}. Install the node packs that provide them (Manager > Install Missing Custom Nodes) and restart ComfyUI.`);
  const ollama = nodes.filter((n) => n.comfyClass === OLLAMA).map((n) => ({ url: widgetOf(n, "url")?.value, model: widgetOf(n, "model")?.value }));
  if (ollama.length) {
    try {
      const answer = await api.fetchApi("/majoor/preflight", { method: "POST", body: JSON.stringify({ ollama }) });
      if (answer.ok) problems.push(...(await answer.json()).problems);
    } catch {
      // the check itself failed: the run goes on
    }
  }
  return problems;
}

export function applyBlocks(graph, controller = controllerOf(graph)) {
  if (!controller) return;
  const remix = widgetOf(controller, "mode")?.value === REMIX;
  const pose = remix && widgetOf(controller, "pose_control")?.value !== false ? widgetOf(controller, "pose_strength")?.value : 0;
  const instruction = String(widgetOf(controller, "remix_instruction")?.value ?? "").trim();
  const base = (graph._nodes ?? []).filter((n) => n.properties?.majoor_mode?.request);
  if (remix && instruction) for (const node of base) setWidget(node, "value", instruction);
  for (const node of graph._nodes ?? []) {
    if (!String(node.properties?.majoor_deploy?.shot ?? "").startsWith("SHOT_")) continue;
    setWidget(node, "strength", pose);
    if (remix && instruction && !base.length) writeRequest(graph, node, instruction);
  }
  graph.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: "Majoor.EditMode",

  nodeCreated(node) {
    if (node.comfyClass !== NODE) return;
    const on = (name, work) => {
      const widget = widgetOf(node, name);
      if (!widget) return;
      const previous = widget.callback;
      widget.callback = function () {
        const result = previous?.apply(this, arguments);
        work();
        return result;
      };
    };
    // a controller saved before the preset and the style existed has two values less: they go to the widgets they belong to, the preset reads Advanced
    const configure = node.onConfigure;
    node.onConfigure = function (info) {
      const saved = info?.widgets_values;
      if (saved && saved.length === node.widgets.length - 2) {
        node.widgets[0].value = ADVANCED;
        node.widgets[1].value = STYLE_DEFAULT;
        node.widgets.slice(2).forEach((w, i) => { w.value = saved[i]; });
      }
      return configure?.apply(this, arguments);
    };
    on("preset", async () => {
      const preset = widgetOf(node, "preset").value;
      if (preset === ADVANCED) return;
      try {
        setWidget(node, "mode", (await (await api.fetchApi("/majoor/modes")).json()).presets?.[preset]);  // the mode callback does the rest
      } catch {
        // the server does not answer: the mode stays
      }
    });
    on("style", () => applyModeSettings(app.graph, node));
    on("mode", async () => {
      applyMode(app.graph, node);
      await applyModeSettings(app.graph, node);
      applyBlocks(app.graph, node);
    });
    for (const name of ["reference_2", "reference_3", "reference_4", "reference_5", "reference_video"]) on(name, () => applyMode(app.graph, node, { values: false }));
    for (const name of ["pose_control", "pose_strength", "remix_instruction"]) on(name, () => applyBlocks(app.graph, node));
  },

  setup() {
    const queue = app.queuePrompt;
    app.queuePrompt = async function (...args) {
      const controller = controllerOf(app.graph);
      if (controller) {
        applyMode(app.graph, controller, { values: false });
        const problems = await preflight(app.graph);
        if (problems.length) {
          const detail = problems.join(" ");
          const toast = app.extensionManager?.toast;
          if (toast) toast.add({ severity: "error", summary: "Fix this before running", detail, life: 20000 });
          else alert(detail);
          return;
        }
      }
      return queue.apply(this, args);
    };
    // an app-mode or API queue builds the prompt too: the nodes follow the mode first
    const build = app.graphToPrompt;
    app.graphToPrompt = function (...args) {
      const controller = controllerOf(app.graph);
      if (controller) applyMode(app.graph, controller, { values: false });
      return build.apply(this, args);
    };
  },
});
