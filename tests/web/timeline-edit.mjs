import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = fs.mkdtempSync(path.join(os.tmpdir(), "mjr-timeline-"));
try {
  const file = path.join(root, "logic.mjs");
  fs.copyFileSync(new URL("../../web/timeline_edit_logic.js", import.meta.url), file);
  const { EditHistory, editCommand, editLength, clipAt, validateEdit } = await import(pathToFileURL(file));
  const initial = { version: 1, project_id: "p_12345678", source_signature: "abc", fps_num: 24, fps_den: 1,
    clips: [1, 2, 3, 4, 5].map((n) => ({ id: `clip_${n}`, shot_id: `S${n}`, revision_id: "take1", in_frame: 0, out_frame: 48 })) };
  const payload = { initial, library: [1, 2, 3, 4, 5].map((n) => ({ id: `S${n}`, takes: [
    { id: "take1", frames: 96 }, { id: "short", frames: 24 }, { id: "other", frames: 96 },
  ] })) };
  const history = new EditHistory(initial, payload);
  history.apply({ type: "move", id: "clip_4", index: 1 });
  assert.deepEqual(history.doc.clips.map((c) => c.shot_id), ["S1", "S4", "S2", "S3", "S5"]);
  history.apply({ type: "cut", id: "clip_1", frame: 24 });
  assert.equal(history.doc.clips[1].in_frame, 24);
  assert.equal(editLength(history.doc), 240);
  history.apply({ type: "duplicate", id: "clip_1" });
  assert.equal(editLength(history.doc), 264);
  assert.equal(new Set(history.doc.clips.map((c) => c.id)).size, 7);
  history.apply({ type: "slip", id: "clip_1", frames: 12 });
  assert.equal(history.doc.clips[0].in_frame, 12);
  history.apply({ type: "take", id: "clip_1", revision_id: "other" });
  assert.equal(history.doc.clips[0].revision_id, "other");
  history.undo(); assert.equal(history.doc.clips[0].revision_id, "take1");
  history.redo(); assert.equal(history.doc.clips[0].revision_id, "other");
  history.undo();
  history.apply({ type: "delete", id: "clip_5" });
  assert.equal(history.future.length, 0);
  history.apply({ type: "trim", id: "clip_1", in_frame: 1, out_frame: 25 });
  assert.deepEqual([history.doc.clips[0].in_frame, history.doc.clips[0].out_frame], [1, 25]);
  assert.equal(clipAt(history.doc, 24).index, 1);
  for (const action of [
    { type: "take", id: "clip_4", revision_id: "short" },
    { type: "slip", id: "clip_1", frames: -100 },
    { type: "cut", id: "clip_1", frame: 0 },
    { type: "cut", id: "clip_1", frame: 24 },
    { type: "trim", id: "clip_1", in_frame: .5, out_frame: 20 },
    { type: "move", id: "clip_1", index: -1 },
  ]) assert.throws(() => editCommand(history.doc, payload, action));
  const single = { ...initial, clips: [initial.clips[0]] };
  assert.throws(() => editCommand(single, payload, { type: "delete", id: "clip_1" }));
  assert.throws(() => validateEdit({ ...initial, source_signature: "changed" }, payload));
  assert.equal(initial.clips.length, 5);
  assert.equal(initial.clips[0].out_frame, 48);
  payload.library[0].takes[0].audio = {file: "voice.wav", duration: 4, peaks: [1]};
  const spoken = new EditHistory(initial, payload);
  spoken.apply({type: "dialogue-add", id: "clip_1"});
  const voice = spoken.doc.dialogue[0];
  assert.deepEqual([voice.at_frame, voice.in_frame, voice.out_frame], [0, 0, 96]);
  spoken.apply({type: "cut", id: "clip_1", frame: 24});
  spoken.apply({type: "duplicate", id: "clip_1"});
  spoken.apply({type: "take", id: "clip_1", revision_id: "other"});
  assert.deepEqual(spoken.doc.dialogue, [voice]);
  spoken.apply({type: "dialogue-update", id: voice.id, at_frame: 12, in_frame: 6, out_frame: 66, gain: .5});
  spoken.apply({type: "music-volume", gain: .3});
  assert.equal(spoken.doc.music_gain, .3);
  const positioned = JSON.parse(JSON.stringify(spoken.doc));
  spoken.apply({type: "dialogue-delete", id: voice.id});
  assert.deepEqual(spoken.doc.dialogue, []);
  spoken.undo(); assert.deepEqual(spoken.doc, positioned);
  for (const bad of [{gain: null}, {gain: NaN}, {gain: 2}, {at_frame: -1}, {out_frame: 97}, {in_frame: .5}])
    assert.throws(() => editCommand(spoken.doc, payload, {type: "dialogue-update", id: voice.id, ...bad}));
  assert.throws(() => editCommand(spoken.doc, payload, {type: "dialogue-add", id: "clip_2"}));
  payload.library[1].takes[0].audio = {file: "source.mp4", duration: 10, frames: 192, peaks: [1]};
  spoken.apply({type: "dialogue-add", id: "clip_2"});
  assert.equal(spoken.doc.dialogue.at(-1).out_frame, 192);
  assert.equal(spoken.doc.clips.find(c => c.id === "clip_2").out_frame, 48);
  console.log("Timeline editorial commands: reorder, split, trim, slip, takes, duplicate, delete, undo/redo and boundaries OK");
} finally {
  fs.rmSync(root, { recursive: true, force: true });
}
