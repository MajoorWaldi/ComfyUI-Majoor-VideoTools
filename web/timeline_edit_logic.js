// Pure editorial commands. Positions and source windows are integer frames.
export const cloneEdit = (doc) => JSON.parse(JSON.stringify(doc));
export const editLength = (doc) => doc.clips.reduce((n, c) => n + c.out_frame - c.in_frame, 0);
export const dialogueFrames = (take) => take.audio?.frames ?? take.frames;

export function clipAt(doc, frame) {
  let start = 0;
  for (let index = 0; index < doc.clips.length; index++) {
    const clip = doc.clips[index], end = start + clip.out_frame - clip.in_frame;
    if (frame >= start && frame < end) return { clip, index, start, end };
    start = end;
  }
  return null;
}

export function takeFor(payload, clip) {
  const shot = payload.library.find((s) => s.id === clip.shot_id);
  const take = shot?.takes.find((t) => t.id === clip.revision_id);
  if (!take) throw new Error(`Unknown take: ${clip.shot_id}/${clip.revision_id}`);
  return take;
}

export function validateEdit(doc, payload) {
  const initial = payload.initial;
  if (doc.version !== 1 || doc.project_id !== initial.project_id ||
      doc.source_signature !== initial.source_signature ||
      doc.fps_num !== initial.fps_num || doc.fps_den !== initial.fps_den) {
    throw new Error("Sources changed. Reset explicitly and run the node to load a new edit.");
  }
  if (!Array.isArray(doc.clips) || doc.clips.length < 1 || doc.clips.length > 10000) {
    throw new Error("An edit needs 1 to 10000 clips.");
  }
  const ids = new Set();
  for (const clip of doc.clips) {
    const take = takeFor(payload, clip);
    if (!/^[A-Za-z0-9_-]{1,80}$/.test(clip.id) || ids.has(clip.id)) throw new Error("Invalid or duplicate clip id.");
    ids.add(clip.id);
    if (!Number.isSafeInteger(clip.in_frame) || !Number.isSafeInteger(clip.out_frame) ||
        clip.in_frame < 0 || clip.out_frame <= clip.in_frame || clip.out_frame > take.frames) {
      throw new Error(`Clip ${clip.id}: source in/out must fit inside 0..${take.frames} frames.`);
    }
  }
  if ("dialogue" in doc) {
    if (!Array.isArray(doc.dialogue) || doc.dialogue.length > 256) throw new Error("Dialogue supports at most 256 excerpts.");
    const audioIds = new Set();
    for (const clip of doc.dialogue) {
      const take = takeFor(payload, clip);
      if (typeof clip.id !== "string" || !/^[A-Za-z0-9_-]{1,80}$/.test(clip.id) || audioIds.has(clip.id)) throw new Error("Invalid or duplicate dialogue id.");
      audioIds.add(clip.id);
      if (!Number.isSafeInteger(clip.in_frame) || !Number.isSafeInteger(clip.out_frame) ||
          clip.in_frame < 0 || clip.out_frame <= clip.in_frame || clip.out_frame > dialogueFrames(take) ||
          !Number.isSafeInteger(clip.at_frame) || clip.at_frame < 0 || clip.at_frame > 3600 * doc.fps_num / doc.fps_den) {
        throw new Error("Dialogue position/window must be valid integer frames inside its source.");
      }
      const gain = "gain" in clip ? clip.gain : 1;
      if (typeof gain !== "number" || !Number.isFinite(gain) || gain < 0 || gain > 1)
        throw new Error("Dialogue volume must be between 0 and 1.");
    }
  }
  if ("music_gain" in doc && (typeof doc.music_gain !== "number" || !Number.isFinite(doc.music_gain) || doc.music_gain < 0 || doc.music_gain > 1))
    throw new Error("Music volume must be between 0 and 1.");
}

function nextId(doc) {
  const ids = new Set(doc.clips.map((c) => c.id));
  let n = 1;
  while (ids.has(`clip_${n}`)) n++;
  return `clip_${n}`;
}

export function editCommand(doc, payload, action) {
  const result = cloneEdit(doc);
  if (action.type === "music-volume") {
    result.music_gain = action.gain;
    validateEdit(result, payload);
    return result;
  }
  if (action.type.startsWith("dialogue-")) {
    const entries = result.dialogue ?? [];
    if (action.type === "dialogue-add") {
      const video = result.clips.find((c) => c.id === action.id);
      if (!video) throw new Error("Select a video clip first.");
      if (!takeFor(payload, video).audio) throw new Error("This take has no available audio.");
      let n = 1;
      while (entries.some((c) => c.id === `dialogue_${n}`)) n++;
      const at = result.clips.slice(0, result.clips.indexOf(video)).reduce((sum, c) => sum + c.out_frame - c.in_frame, 0);
      // Start linked to the picture, but retain the remaining phrase beyond its cut.
      entries.push({ ...video, id: `dialogue_${n}`, out_frame: dialogueFrames(takeFor(payload, video)), at_frame: at, gain: 1 });
    } else {
      const index = entries.findIndex((c) => c.id === action.id);
      if (index < 0) throw new Error("Select a dialogue excerpt first.");
      if (action.type === "dialogue-update") {
        for (const key of ["in_frame", "out_frame", "at_frame", "gain"])
          if (key in action) entries[index][key] = action[key];
      } else if (action.type === "dialogue-delete") entries.splice(index, 1);
      else throw new Error(`Unknown dialogue operation: ${action.type}`);
    }
    result.dialogue = entries;
    validateEdit(result, payload);
    return result;
  }
  const index = result.clips.findIndex((c) => c.id === action.id);
  if (index < 0) throw new Error("Select a clip first.");
  const clip = result.clips[index];
  switch (action.type) {
    case "trim":
      clip.in_frame = action.in_frame;
      clip.out_frame = action.out_frame;
      break;
    case "slip":
      clip.in_frame += action.frames;
      clip.out_frame += action.frames;
      break;
    case "cut": {
      const length = clip.out_frame - clip.in_frame;
      if (!Number.isSafeInteger(action.frame) || action.frame <= 0 || action.frame >= length) {
        throw new Error("Cut must be inside the selected clip, not on its edge.");
      }
      const right = { ...clip, id: nextId(result), in_frame: clip.in_frame + action.frame };
      clip.out_frame = right.in_frame;
      result.clips.splice(index + 1, 0, right);
      break;
    }
    case "duplicate":
      result.clips.splice(index + 1, 0, { ...clip, id: nextId(result) });
      break;
    case "delete":
      result.clips.splice(index, 1);
      break;
    case "move":
      if (!Number.isSafeInteger(action.index) || action.index < 0 || action.index >= result.clips.length) {
        throw new Error("Move target is outside the timeline.");
      }
      result.clips.splice(index, 1);
      result.clips.splice(action.index, 0, clip);
      break;
    case "take":
      clip.revision_id = action.revision_id;
      break;
    default:
      throw new Error(`Unknown edit operation: ${action.type}`);
  }
  validateEdit(result, payload);
  return result;
}

export class EditHistory {
  constructor(doc, payload) {
    validateEdit(doc, payload);
    this.doc = cloneEdit(doc);
    this.payload = payload;
    this.past = [];
    this.future = [];
  }
  apply(action) {
    const next = editCommand(this.doc, this.payload, action);
    this.past.push(this.doc);
    if (this.past.length > 100) this.past.shift();
    this.doc = next;
    this.future = [];
    return this.doc;
  }
  undo() {
    if (this.past.length) {
      this.future.push(this.doc);
      this.doc = this.past.pop();
    }
    return this.doc;
  }
  redo() {
    if (this.future.length) {
      this.past.push(this.doc);
      this.doc = this.future.pop();
    }
    return this.doc;
  }
}
