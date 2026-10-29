// Majoor VideoTools - Edit Mode.
//
// The Edit Mode node holds the mode (creative or remix), the options (from_video, ref_video, own_music, the reference pictures) and the remix settings. Nodes of the graph say what the mode
// does to them in properties.majoor_mode: {"modes": [...], "toggle": "ref_video", "any": ["remix_replace", "from_video"], "unless": "own_music", "values": {"widget": {"mode or toggle": value, "*": other}}}.
// A node with "modes" / "toggle" / "any" / "unless" is enabled when its mode is listed, its toggle is on, the mode is listed or one of the "any" toggles is on, and the "unless" toggle is off; bypassed otherwise;
// "values" sets widgets (the rhythm source, the shot list switch...): the key is the mode, or a toggle that is on (the first one that is). "request": true marks the base request of the remix LLM (it gets remix_instruction);
// "profile": true marks a node that only takes the profile (the music); "enhancer": true marks the prompt enhancer: it gets the line of the mode skill for it as extra_instructions;
// "pose": true marks a block that is not made by Deploy Shots: it gets the strength of the pose ControlNet like the blocks of the shots; "planner": true marks the planner: it gets the profile, genre, reference_mode and instructions of the mode skill (skills/mode_<mode>.md, read from /majoor/modes), the video ones when from_video is on.
// The camera look of Edit Mode is added to the planner and the enhancer in the creative mode. The nodes are set when the mode or an option that changes values changes and when the graph is queued; "values" only on those changes, so that you can still adjust them by hand.
// The style replaces the profile of the mode. Before a queue the nodes of the graph that the frontend does not know (a node pack that is not installed) are named, in words the user can act on.
// The shot blocks (made by Deploy Shots) get the pose ControlNet strength (remix only) and, in the remix, the replacement instruction.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE = "MajoorEditMode";
const ALWAYS = 0;
const BYPASS = 4;
const MUTE = 2;
const REMIX = "remix_replace";
const STYLE_DEFAULT = "Mode default";
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
  const active = (name) => name === mode || widgetOf(controller, name)?.value === true;
  for (const node of graph._nodes ?? []) {
    const tag = node.properties?.majoor_mode;
    if (!tag) continue;
    if (tag.modes || tag.toggle || tag.any || tag.unless) {
      const on = (!tag.modes || tag.modes.includes(mode)) && (!tag.toggle || active(tag.toggle)) && (!tag.any || tag.any.some(active)) && (!tag.unless || !active(tag.unless));
      node.mode = on ? ALWAYS : BYPASS;
    }
    if (!values) continue;
    for (const [name, by] of Object.entries(tag.values ?? {})) {
      const key = Object.keys(by).find((k) => k !== "*" && active(k));
      setWidget(node, name, key === undefined ? by["*"] : by[key]);
    }
  }
  graph.setDirtyCanvas?.(true, true);
}

// What the skill of the mode says (read again each time: an edited file is used at once): the planner, the enhancer, and with defaults the settings of the controller (the video, the remix).
export async function applyModeSettings(graph, controller, { defaults = false } = {}) {
  const mode = widgetOf(controller, "mode")?.value;
  let settings = null;
  let look = "";
  try {
    const answer = await (await api.fetchApi("/majoor/modes")).json();
    settings = answer.modes?.[mode] ?? null;
    look = mode === REMIX ? "" : answer.cameras?.[widgetOf(controller, "camera")?.value] ?? "";  // the camera look is for the creative mode: the remix keeps the camera of the video
  } catch {
    return;
  }
  if (!settings) return;
  if (defaults) {
    setWidget(controller, "from_video", settings.from_video);
    setWidget(controller, "pose_strength", settings.pose_strength);
    setWidget(controller, "remix_instruction", settings.remix_instruction);
  }
  const video = widgetOf(controller, "from_video")?.value === true;
  const style = widgetOf(controller, "style")?.value;
  const profile = style && style !== STYLE_DEFAULT ? style : video ? settings.profile_from_video ?? settings.profile : settings.profile;
  const join = (text, more, on) => (on && more ? `${text} ${more}` : text);
  for (const node of graph._nodes ?? []) {
    const tag = node.properties?.majoor_mode;
    if (tag?.planner) {
      setWidget(node, "genre", settings.genre);
      setWidget(node, "reference_mode", settings.reference_mode || video);
      setWidget(node, "extra_instructions", join(join(settings.extra_instructions, settings.from_video_instructions, video), look, true));
      setWidget(node, "profile", profile);
    } else if (tag?.profile) setWidget(node, "profile", profile);  // the music of the edit takes the profile of the planner
    if (tag?.enhancer) setWidget(node, "extra_instructions", join(join(settings.enhancer, settings.enhancer_from_video, video), look, true));  // the prompt enhancer is told what the mode is for
  }
}

// The edit request of a block is the node its string_b input is linked to (the one every block shares), else the widget of the block.
function writeRequest(graph, block, text) {
  const link = block.inputs?.find((i) => i.name === "string_b")?.link;
  const origin = link == null ? null : graph.getNodeById((graph.links ?? graph._links)?.get?.(link)?.origin_id);
  if (origin) setWidget(origin, "value", text);
  else setWidget(block, "string_b", text);
}

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

// What would fail when the graph is queued: nodes the frontend does not know.
export function preflight(graph, registered = globalThis.LiteGraph?.registered_node_types) {
  const nodes = activeNodes(graph);
  const problems = [];
  const unknown = [...new Set(nodes.filter((n) => !n.subgraph).map((n) => n.comfyClass ?? n.type))].filter((type) => type && registered && !(type in registered) && !SUBGRAPH_ID.test(type));
  if (unknown.length) problems.push(`Missing custom nodes: ${unknown.join(", ")}. Install the node packs that provide them (Manager > Install Missing Custom Nodes) and restart ComfyUI.`);
  return problems;
}

// The blocks of the shots (made by Deploy Shots). The pose ControlNet of H3 follows the pose of the original shot: it is on in the remix (pose_strength,
// off with pose_control) and off in the other modes, where the shot is only a placeholder card; at strength 0 H3 skips it. The remix instruction is the edit request.
export function applyBlocks(graph, controller = controllerOf(graph)) {
  if (!controller) return;
  const remix = widgetOf(controller, "mode")?.value === REMIX;
  const pose = remix && widgetOf(controller, "pose_control")?.value !== false ? widgetOf(controller, "pose_strength")?.value : 0;
  const instruction = String(widgetOf(controller, "remix_instruction")?.value ?? "").trim();
  const base = (graph._nodes ?? []).filter((n) => n.properties?.majoor_mode?.request);
  if (remix && instruction) for (const node of base) setWidget(node, "value", instruction);
  for (const node of graph._nodes ?? []) {
    if (node.properties?.majoor_mode?.pose) setWidget(node, "strength", pose);  // a block of the graph that is not made by Deploy Shots
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
    on("style", () => applyModeSettings(app.graph, node));
    on("mode", async () => {
      applyMode(app.graph, node);
      await applyModeSettings(app.graph, node, { defaults: true });
      applyMode(app.graph, node);  // the video option that the mode skill sets
      applyBlocks(app.graph, node);
    });
    on("camera", () => applyModeSettings(app.graph, node));
    for (const name of ["from_video", "own_music", "voice", "quality_check"]) on(name, async () => {
      applyMode(app.graph, node);
      await applyModeSettings(app.graph, node);
    });
    for (const name of ["reference_2", "reference_3", "reference_4", "reference_5", "ref_video"]) on(name, () => applyMode(app.graph, node, { values: false }));
    for (const name of ["pose_control", "pose_strength", "remix_instruction"]) on(name, () => applyBlocks(app.graph, node));
  },

  setup() {
    const queue = app.queuePrompt;
    app.queuePrompt = async function (...args) {
      const controller = controllerOf(app.graph);
      if (controller) {
        applyMode(app.graph, controller, { values: false });
        const problems = preflight(app.graph);
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
      if (controller) {
        applyMode(app.graph, controller, { values: false });
        applyBlocks(app.graph, controller);  // the strength of a block never stays at a value that was saved for another widget
      }
      return build.apply(this, args);
    };
  },
});
