// Majoor VideoTools - Deploy Shots.
//
// The "Create shots" button of the Deploy Shots node sends the graph, the chosen recipe and the shot ids to the backend
// (core/deploy.py), which returns the same graph with one block per shot added, chained and sent to Shot Assemble, and
// the graph is loaded back. The shots come from the nearest Scene Detect & Split / Create Timeline that has run once.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyle, el, growTo, mountWidget, saved } from "./majoor_videotools.js";
import { applyBlocks } from "./majoor_mode.js";

const DEPLOYER = "MajoorDeployShots";
const SOURCES = ["MajoorSceneDetectSplit", "MajoorCreateTimeline"];

const widgetValue = (node, name) => node.widgets?.find((w) => w.name === name)?.value;

// The node feeding `node` through its shot list. KJNodes Get nodes are followed back to their Set node.
function upstream(node) {
  const graph = node.graph ?? app.graph;
  const wanted = node.type === "ComfySwitchNode" ? (widgetValue(node, "switch") ? "on_true" : "on_false") : "shot_list";
  const slot = node.inputs?.findIndex((i) => i.name === wanted || (node.type === "SetNode" && i === node.inputs[0])) ?? -1;
  if (slot < 0 || node.inputs[slot].link == null) return null;
  const origin = node.getInputNode(slot);
  if (origin?.type === "GetNode") {
    const name = origin.widgets?.[0]?.value;
    const setter = graph._nodes.find((n) => n.type === "SetNode" && n.widgets?.[0]?.value === name);
    return setter ?? null;
  }
  return origin;
}

// max_shots, or the shot_count of the node that feeds it (Create Timeline, Scene Detect & Split: the shots they list; Cut Markers or a primitive: the number it holds)
function maxShots(node) {
  const slot = node.inputs?.findIndex((i) => i.name === "max_shots") ?? -1;
  let origin = slot >= 0 && node.inputs[slot].link != null ? node.getInputNode(slot) : null;
  for (let hops = 0; origin && hops < 32; hops++) {  // through a Get / Set pair or a switch (the one that EDIT MODE sets) to the node that holds the number
    const graph = origin.graph ?? app.graph;
    let next = null;
    if (origin.type === "GetNode") next = graph._nodes.find((n) => n.type === "SetNode" && n.widgets?.[0]?.value === origin.widgets?.[0]?.value);
    else if (origin.type === "SetNode") next = origin.getInputNode(0);
    else if (origin.type === "ComfySwitchNode") {
      const wanted = widgetValue(origin, "switch") ? "on_true" : "on_false";
      const pick = origin.inputs?.findIndex((i) => i.name === wanted) ?? -1;
      next = pick >= 0 && origin.inputs[pick].link != null ? origin.getInputNode(pick) : null;
    }
    if (!next) break;
    origin = next;
  }
  if (origin && SOURCES.includes(origin.comfyClass)) return saved(origin)?.shots?.length ?? 0;
  if (origin) return Number(widgetValue(origin, "value")) || Number(saved(origin)?.markers?.length) + 1 || 0;
  return Number(widgetValue(node, "max_shots")) || 0;
}

function shotsFor(node) {
  let cur = node;
  for (let hops = 0; cur && hops < 32; hops++) {
    cur = upstream(cur);
    const payload = cur && SOURCES.includes(cur.comfyClass) ? saved(cur) : null;
    if (payload) return payload;
  }
  // not connected: the first source of the graph that has run
  for (const n of app.graph?._nodes ?? []) {
    if (SOURCES.includes(n.comfyClass) && saved(n)) return saved(n);
  }
  return null;
}

function describe(deployed) {
  if (!deployed) return "Run Scene Detect & Split (or Create Timeline) once, then press Create shots.";
  const lines = [`${deployed.shots?.length ?? 0} shots deployed from '${deployed.recipe ?? "?"}'.`];
  for (const w of deployed.warnings ?? []) lines.push(`⚠ ${w}`);
  return lines.join("\n");
}

function setupDeployer(node) {
  addStyle();
  const root = el("div", "mjr-root");
  const info = el("div", "mjr-info", describe(node.properties?.majoor_deploy));
  root.append(info);
  mountWidget(node, "deploy_report", root, () => 20 + info.textContent.split("\n").length * 16);
  node._mjrDeployInfo = (text) => {
    info.textContent = text;
    growTo(node, node.computeSize()[1]);
  };

  let busy = false;
  node.addWidget("button", "Create shots", "create", async () => {
    if (busy) return;
    busy = true;
    try {
      await create(node);
    } catch (e) {
      node._mjrDeployInfo(`⚠ ${e?.message ?? e}`);
    } finally {
      busy = false;
    }
  });
}

async function create(node) {
  const payload = shotsFor(node);
  if (!payload?.shots?.length) {
    node._mjrDeployInfo(describe(null));
    return;
  }
  const limit = maxShots(node);
  const shots = payload.shots.map((s) => s.id).slice(0, limit > 0 ? limit : undefined);
  const graph = app.rootGraph ?? app.graph;
  node._mjrDeployInfo(`Deploying ${shots.length} shots…`);
  const response = await api.fetchApi("/majoor/deploy_shots", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      recipe: widgetValue(node, "recipe"),
      has_plan: payload.shots.some((s) => s.prompt),
      workflow: graph.serialize(),
      shots,
      anchor: node.id,
      columns: widgetValue(node, "columns"),
      include_finale: widgetValue(node, "include_finale"),
      replace_existing: widgetValue(node, "replace_existing"),
    }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? `HTTP ${response.status}`);
  const { workflow, report } = data;
  if (report.replaced.length && !window.confirm(`Replace the blocks already in the graph for ${report.replaced.join(", ")} with the recipe's blocks?`)) {
    node._mjrDeployInfo("Cancelled, the graph is unchanged.");
    return;
  }
  const anchor = workflow.nodes.find((n) => n.id === node.id);
  if (anchor) anchor.properties.majoor_deploy.warnings = report.warnings;
  await app.loadGraphData(workflow, true, false, app.extensionManager?.workflow?.activeWorkflow ?? null);
  applyBlocks(app.graph);
  const fresh = app.graph.getNodeById(node.id);
  fresh?._mjrDeployInfo?.(describe(fresh.properties?.majoor_deploy));
}

app.registerExtension({
  name: "Majoor.DeployShots",
  nodeCreated(node) {
    if (node.comfyClass === DEPLOYER) setupDeployer(node);
  },
  loadedGraphNode(node) {
    if (node.comfyClass === DEPLOYER) node._mjrDeployInfo?.(describe(node.properties?.majoor_deploy));
  },
});
