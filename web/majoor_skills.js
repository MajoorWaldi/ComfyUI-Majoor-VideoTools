// Majoor VideoTools - Edit Skills.
//
// Two buttons on the Edit Skills node: "Reload skills" re-reads the skills folder and refreshes the lists of the skill and profile
// widgets (a file added to the folder shows up without restarting ComfyUI), "Copy prompt" copies the system prompt the
// node would send, with the current settings.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE = "MajoorEditSkills";
const DIALS = ["cut_density", "transition_intensity", "creative_freedom", "reference_fidelity", "narrative_coherence"];
const SETTINGS = ["skill", "overlays_splits", "text_overlays", "reference_mode", "genre", "duration", "fps", "aspect_ratio", "n_pictures", "text_allowed", "extra_instructions", "profile", ...DIALS];

export const widgetValue = (node, name) => node.widgets?.find((w) => w.name === name)?.value;

export function settingsOf(node) {
  return Object.fromEntries(SETTINGS.map((name) => [name, widgetValue(node, name)]));
}

async function call(path, body) {
  const response = await api.fetchApi(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? `HTTP ${response.status}`);
  return data;
}

export async function reloadSkills(node) {
  const { skills, profiles } = await call("/majoor/skills");
  const profile = node.widgets?.find((w) => w.name === "profile");
  if (profile && profiles?.length) {
    profile.options.values = profiles;
    if (!profiles.includes(profile.value)) profile.value = profiles[0];
  }
  const widget = node.widgets?.find((w) => w.name === "skill");
  if (!widget || !skills.length) return skills;
  widget.options.values = skills;
  if (!skills.includes(widget.value)) widget.value = skills[0];
  node.setDirtyCanvas?.(true, true);
  return skills;
}

export async function copyPrompt(node) {
  const { text, words } = await call("/majoor/skills/compose", settingsOf(node));
  await navigator.clipboard.writeText(text);
  return words;
}

function status(node, message) {
  node.title = message ? `Edit Skills - ${message}` : "Edit Skills";
  node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: "Majoor.EditSkills",
  nodeCreated(node) {
    if (node.comfyClass !== NODE) return;
    // a workflow saved before the profile existed has the values of the two buttons where the profile widgets now are
    node.onConfigure = ((prev) => function () {
      const result = prev?.apply(this, arguments);
      for (const name of ["profile", ...DIALS]) {
        const w = this.widgets?.find((x) => x.name === name);
        if (w?.options?.values && !w.options.values.includes(w.value)) w.value = w.options.values[0];
      }
      return result;
    })(node.onConfigure);
    const run = (work) => async () => {
      try {
        status(node, await work());
      } catch (error) {
        status(node, String(error.message ?? error));
      }
    };
    node.addWidget("button", "Reload skills", null, run(async () => `${(await reloadSkills(node)).length} skills`));
    node.addWidget("button", "Copy prompt", null, run(async () => `${await copyPrompt(node)} words copied`));
  },
});
