import { clipAt, dialogueFrames, editLength, EditHistory, takeFor } from "./timeline_edit_logic.js";

const CSS = `
.mjr-edit {width:min(1150px,94vw);max-height:92vh;overflow:auto;background:var(--comfy-menu-bg,#202127);color:var(--input-text,#eee);border:1px solid #666;border-radius:10px;padding:18px;font:13px sans-serif}
.mjr-edit::backdrop {background:#0009}
.mjr-edit h2 {margin:0 0 8px}
.mjr-edit .mjr-edit-header {display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px}
.mjr-edit .mjr-edit-header h2 {margin:0}
.mjr-edit .mjr-edit-close {display:grid;place-items:center;flex-shrink:0;width:30px;height:30px;padding:0;border:1px solid #bc3448;border-radius:7px;background:#a52639;color:#fff;font-size:23px;line-height:1}
.mjr-edit .mjr-edit-close:hover:not(:disabled) {background:#ca3048;border-color:#e34c62}
.mjr-edit .mjr-edit-row {display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0}
.mjr-edit button,.mjr-edit select,.mjr-edit input {background:var(--comfy-input-bg,#30323a);color:inherit;border:1px solid #666;border-radius:4px;padding:5px}
.mjr-edit button {cursor:pointer}
.mjr-edit button:disabled {opacity:.4;cursor:default}
.mjr-edit .mjr-edit-loop[aria-pressed=true] {background:#77bbff;color:#151921;border-color:#77bbff}
.mjr-edit video {display:block;width:100%;height:min(36vh,340px);object-fit:contain;background:#000}
.mjr-edit .mjr-edit-scroll {overflow-x:auto;border:1px solid #555}
.mjr-edit .mjr-edit-track {position:relative;min-width:100%;padding-top:26px;min-height:130px;box-sizing:border-box}
.mjr-edit .mjr-dialogue-lane {position:relative;min-height:54px;background:var(--comfy-input-bg,#292631)}
.mjr-edit .mjr-dialogue-lane:empty::before {content:"Dialogue";position:absolute;top:17px;left:10px;font-size:11px;opacity:.6;pointer-events:none}
.mjr-edit .mjr-dialogue-clip {position:absolute;height:48px;box-sizing:border-box;border:1px solid #a68bcc;background:#443957;overflow:hidden;touch-action:none;cursor:grab}
.mjr-edit .mjr-dialogue-clip[data-selected=true] {outline:2px solid #c9a6ff;outline-offset:-2px}
.mjr-edit .mjr-dialogue-clip canvas {height:28px;pointer-events:none;background:transparent}
.mjr-edit .mjr-dialogue-clip span {display:block;padding:2px 9px;font-size:10px;white-space:nowrap;pointer-events:none}
.mjr-edit .mjr-dialogue-clip .mjr-edit-handle {background:#c9a6ff88}
.mjr-edit .mjr-dialogue-inspector {border-top:1px solid #666;padding-top:8px}
.mjr-edit .mjr-dialogue-warning {color:#ffb4a9;white-space:pre-wrap}
.mjr-edit .mjr-edit-clips {display:flex;height:44px}
.mjr-edit .mjr-edit-clip {position:relative;box-sizing:border-box;overflow:hidden;flex-shrink:0;background:#33475e}
.mjr-edit .mjr-edit-body {width:100%;height:100%;border-radius:0;text-align:left;overflow:hidden;white-space:nowrap;padding:5px 10px;background:transparent}
.mjr-edit .mjr-edit-clip[data-selected=true] {outline:2px solid #77bbff;outline-offset:-3px}
.mjr-edit .mjr-edit-handle {position:absolute;top:0;bottom:0;width:8px;padding:0;border-radius:0;background:#83adcc88;cursor:ew-resize;touch-action:none}
.mjr-edit .mjr-edit-ruler {position:absolute;top:0;left:0;right:0;height:26px;cursor:crosshair;touch-action:none}
.mjr-edit .mjr-edit-tick {position:absolute;top:3px;border-left:1px solid #777;padding:0 3px;font-size:10px;pointer-events:none}
.mjr-edit canvas {display:block;height:56px;width:100%;background:#151921;cursor:crosshair;touch-action:none}
.mjr-edit .mjr-edit-head {position:absolute;top:0;bottom:0;width:2px;background:#ff635c;cursor:ew-resize;touch-action:none;z-index:2}
.mjr-edit .mjr-edit-head::before {content:"";position:absolute;top:0;bottom:0;left:-6px;width:14px}
.mjr-edit .mjr-edit-head::after {content:"";position:absolute;top:0;left:-4px;border-left:5px solid transparent;border-right:5px solid transparent;border-top:8px solid currentColor}
.mjr-edit .mjr-edit-error {color:#ffb4a9;white-space:pre-wrap;min-height:18px}
.mjr-edit .mjr-edit-note {opacity:.8}
.mjr-edit input[type=number] {width:86px}
.mjr-edit input[type=range] {flex:1;min-width:150px}
.mjr-edit .mjr-source {width:100%;min-width:0}
.mjr-edit .mjr-source-heading {display:flex;justify-content:space-between;gap:12px;margin:6px 0;font-size:11px}
.mjr-edit .mjr-source-track {position:relative;height:66px;background:#151921;border:1px solid #666;border-radius:6px;touch-action:none}
.mjr-edit .mjr-source-images {display:flex;height:100%;overflow:hidden;border-radius:5px;opacity:.65}
.mjr-edit .mjr-source-images img {width:12.5%;height:100%;object-fit:cover;pointer-events:none}
.mjr-edit .mjr-source-window {position:absolute;top:0;bottom:0;border:2px solid #77bbff;background:#77bbff18;box-sizing:border-box;cursor:grab;touch-action:none}
.mjr-edit .mjr-source-window:active {cursor:grabbing}
.mjr-edit .mjr-source-grip {position:absolute;top:0;bottom:0;width:10px;padding:0;min-height:0;border:0;border-radius:0;background:#77bbff;color:#151921;cursor:ew-resize;touch-action:none}
.mjr-edit .mjr-source-grip[data-edge=start] {left:-5px}
.mjr-edit .mjr-source-grip[data-edge=end] {right:-5px}
.mjr-edit .mjr-source-cursor {position:absolute;top:0;bottom:0;width:2px;background:#ff635c;pointer-events:none}
.mjr-edit .mjr-source-hint {font-size:11px;opacity:.8;margin:7px 0}
.mjr-edit .mjr-source-advanced {width:100%}
.mjr-edit .mjr-source-advanced summary {cursor:pointer;font-size:11px}
`;

function el(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

function mediaEvent(media, event, set, signal) {
  return new Promise((resolve, reject) => {
    const clear = () => {
      clearTimeout(timer);
      media.removeEventListener(event, done);
      media.removeEventListener("error", fail);
      signal.removeEventListener("abort", abort);
    };
    const done = () => { clear(); resolve(); };
    const fail = () => { clear(); reject(new Error("Cannot load preview media. Check the source file and browser codec support.")); };
    const abort = () => { clear(); reject(new Error("Preview cancelled.")); };
    const timer = setTimeout(() => { clear(); reject(new Error("Preview loading timed out.")); }, 15000);
    media.addEventListener(event, done, { once: true });
    media.addEventListener("error", fail, { once: true });
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    else {
      try { set(); } catch (error) { clear(); reject(error); }
    }
  });
}

function startMedia(media, signal) {
  return new Promise((resolve, reject) => {
    const clear = () => { clearTimeout(timer); signal.removeEventListener("abort", abort); };
    const abort = () => { clear(); reject(new Error("Preview cancelled.")); };
    const timer = setTimeout(() => {
      clear(); reject(new Error("Preview playback timed out. Check the media and try Play again."));
    }, 15000);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) { abort(); return; }
    try {
      Promise.resolve(media.play()).then(
        () => { clear(); resolve(); },
        (error) => { clear(); reject(error); },
      );
    } catch (error) { clear(); reject(error); }
  });
}

export function openTimelineEditor(payload, doc, { urlFor, onChange, onClose, onSave, onRender, labels = {}, theme }) {
  const history = new EditHistory(doc, payload);
  const fps = doc.fps_num / doc.fps_den;
  const dialog = el("dialog");
  dialog.className = "mjr-edit";
  if (theme === "studio") dialog.classList.add("mjr-edit-studio");
  dialog.setAttribute("aria-label", labels.title || "Timeline Edit");
  const style = el("style"); style.textContent = CSS;
  const title = el("h2", "Timeline Edit");
  const note = el("p", labels.preview || "Raw-take preview. Export is authoritative for timing and audio. Dialogue is independent of picture cuts; music starts at 00:00.");
  note.className = "mjr-edit-note";
  const video = el("video"); video.muted = true; video.playsInline = true; video.preload = "auto";
  const audio = el("audio"); audio.preload = "auto";
  if (payload.music) audio.src = urlFor(payload.music.file);
  const toolbar = el("div"); toolbar.className = "mjr-edit-row";
  toolbar.classList.add("mjr-edit-transport");
  const play = el("button", "Play");
  play.className = "mjr-edit-play";
  const loop = el("button", "Loop");
  loop.className = "mjr-edit-loop";
  loop.setAttribute("aria-label", "Loop playback");
  loop.setAttribute("aria-pressed", "false");
  loop.title = "Repeat the entire montage";
  const back = el("button", "-1 frame"), forward = el("button", "+1 frame");
  const time = el("span", "00:00.000");
  time.className = "mjr-edit-time";
  const scrub = el("input"); scrub.type = "range"; scrub.min = "0"; scrub.step = "1";
  const close = el("button", "\u00d7");
  close.className = "mjr-edit-close";
  close.setAttribute("aria-label", "Close");
  close.title = "Close";
  const header = el("div"); header.className = "mjr-edit-header"; header.append(title, close);
  scrub.setAttribute("aria-label", labels.position || "Playback position");
  toolbar.append(play, loop, back, forward, time, scrub);
  const save = onSave ? el("button", labels.save || "Save montage") : null;
  const exportButton = onRender ? el("button", labels.render || "Save and export") : null;
  if (save) save.className = "mjr-edit-save";
  if (exportButton) exportButton.className = "mjr-edit-export";
  if (save) toolbar.append(save);
  if (exportButton) toolbar.append(exportButton);
  const tools = el("div"); tools.className = "mjr-edit-row";
  tools.classList.add("mjr-edit-tools");
  const undo = el("button", "Undo"), redo = el("button", "Redo");
  const cut = el("button", "Cut at cursor"), dup = el("button", "Duplicate"), del = el("button", "Ripple delete");
  const left = el("button", "Move left"), right = el("button", "Move right");
  del.className = "mjr-edit-delete";
  const zoom = el("input"); zoom.type = "range"; zoom.min = "10"; zoom.max = "240"; zoom.value = "60";
  const zoomLabel = el("label", "Zoom px/s "); zoomLabel.append(zoom);
  tools.append(undo, redo, cut, dup, del, left, right, zoomLabel);
  const scroll = el("div"); scroll.className = "mjr-edit-scroll";
  const track = el("div"); track.className = "mjr-edit-track";
  track.tabIndex = 0;
  track.setAttribute("role", "slider");
  track.setAttribute("aria-label", "Timeline position");
  track.setAttribute("aria-valuemin", "0");
  track.title = "Drag the ruler, waveform or playhead to seek. Arrow keys: one frame; Home/End: start/end.";
  const ruler = el("div"); ruler.className = "mjr-edit-ruler";
  const clips = el("div"); clips.className = "mjr-edit-clips";
  const canvas = el("canvas");
  const dialogueLane = el("div"); dialogueLane.className = "mjr-dialogue-lane";
  dialogueLane.setAttribute("aria-label", "Dialogue track");
  const head = el("div"); head.className = "mjr-edit-head";
  track.append(ruler, clips, canvas, dialogueLane, head); scroll.append(track);
  const inspector = el("div"); inspector.className = "mjr-edit-row";
  inspector.classList.add("mjr-edit-inspector");
  const selectedLabel = el("span"), takes = el("select");
  selectedLabel.className = "mjr-edit-selection";
  takes.setAttribute("aria-label", "Take");
  const input = el("input"), output = el("input"), slip = el("input");
  for (const field of [input, output, slip]) { field.type = "number"; field.step = "1"; }
  input.min = "0"; output.min = "1"; slip.value = "0";
  const label = (text, field) => { const l = el("label", text); l.append(field); return l; };
  const addDialogue = el("button", "Dialogue from selected take");
  addDialogue.className = "mjr-dialogue-add";
  const dialogueInspector = el("section"); dialogueInspector.className = "mjr-dialogue-inspector";
  const dialogueFields = el("div"); dialogueFields.className = "mjr-edit-row";
  const dialogueLabel = el("span", "Dialogue"), dialogueAt = el("input"), dialogueIn = el("input"), dialogueOut = el("input");
  const dialogueGain = el("input"), musicGain = el("input");
  for (const [field, name] of [[dialogueAt, "Dialogue position frame"], [dialogueIn, "Dialogue in frame"], [dialogueOut, "Dialogue out frame"]]) {
    field.type = "number"; field.step = "1"; field.min = "0"; field.setAttribute("aria-label", name);
  }
  for (const [field, name] of [[dialogueGain, "Dialogue volume"], [musicGain, "Music volume"]]) {
    field.type = "number"; field.min = "0"; field.max = "1"; field.step = ".05"; field.setAttribute("aria-label", name);
  }
  const applyDialogue = el("button", "Apply dialogue"), deleteDialogue = el("button", "Delete dialogue");
  const dialogueWarning = el("div"); dialogueWarning.className = "mjr-dialogue-warning"; dialogueWarning.setAttribute("role", "status");
  dialogueFields.append(dialogueLabel, label("Position (frame) ", dialogueAt), label("In ", dialogueIn),
    label("Out ", dialogueOut), label("Volume (0 = mute) ", dialogueGain), applyDialogue, deleteDialogue);
  const dialogueHelp = el("p", "Drag dialogue to place it; handles trim independently (J/L cuts). Video edits do not move dialogue. Extend the picture or trim explicitly if audio exceeds the montage.");
  dialogueHelp.className = "mjr-source-hint";
  dialogueInspector.append(addDialogue, label(" Music volume ", musicGain), dialogueFields, dialogueWarning, dialogueHelp);
  const trim = el("button", "Apply trim"), slipButton = el("button", "Apply slip");
  const source = el("section"); source.className = "mjr-source";
  source.setAttribute("aria-label", "Selected source portion");
  const sourceHeading = el("div"); sourceHeading.className = "mjr-source-heading";
  const sourceTitle = el("span", "Selected portion"), sourceTime = el("output");
  sourceHeading.append(sourceTitle, sourceTime);
  const sourceTrack = el("div"); sourceTrack.className = "mjr-source-track";
  const sourceImages = el("div"); sourceImages.className = "mjr-source-images"; sourceImages.setAttribute("aria-hidden", "true");
  const sourceWindow = el("div"); sourceWindow.className = "mjr-source-window";
  sourceWindow.tabIndex = 0; sourceWindow.setAttribute("role", "slider"); sourceWindow.setAttribute("aria-label", "Slip selected portion");
  for (const edge of ["start", "end"]) {
    const grip = el("button", "II"); grip.className = "mjr-source-grip"; grip.dataset.edge = edge;
    grip.setAttribute("aria-label", `Source trim ${edge}`); sourceWindow.append(grip);
  }
  const sourceCursor = el("div"); sourceCursor.className = "mjr-source-cursor";
  sourceTrack.append(sourceImages, sourceWindow, sourceCursor);
  const sourceHint = el("p", "Drag the window to slip. Drag either handle to ripple trim. Arrow keys: one frame.");
  sourceHint.className = "mjr-source-hint";
  source.append(sourceHeading, sourceTrack, sourceHint);
  const advanced = el("details"); advanced.className = "mjr-source-advanced";
  advanced.append(el("summary", "Frame controls"));
  const fields = el("div"); fields.className = "mjr-edit-row";
  fields.append(label("In frame ", input), label("Out frame ", output), trim, label("Slip frames ", slip), slipButton);
  advanced.append(fields);
  inspector.append(selectedLabel, takes, source, advanced);
  const status = el("div"); status.className = "mjr-edit-error"; status.setAttribute("role", "status");
  dialog.append(style, header, note, video, audio, toolbar, tools, scroll, inspector, dialogueInspector, status);
  document.body.append(dialog);
  let selected = doc.clips[0].id, frame = 0, playing = false, looping = false, requestedPlayback = false, saving = false, closed = false, raf = 0, epoch = 0;
  let current = null, dragged = null, pending = null;
  let navigation = null;
  let audioSelected = null, audioGesture = null, activeDialogue = "";
  const dialoguePlayers = new Map();
  const dialogueClips = () => visibleDoc().dialogue ?? [];
  const audibleAt = (at) => dialogueClips().filter((c) => (c.gain ?? 1) > 0 && at >= c.at_frame && at < c.at_frame + c.out_frame - c.in_frame);
  const audibleKey = (at) => audibleAt(at).map((c) => c.id).join("|");
  let previewDoc = null, sourceGesture = null, filmKey = "", filmAbort = null;
  const visibleDoc = () => previewDoc || history.doc;
  const musicEnabled = () => Boolean(payload.music) && !(payload.music.source_audio && "dialogue" in visibleDoc());
  const report = (error) => { status.dataset.state = "error"; status.textContent = error.message || String(error); };
  const selectedClip = () => visibleDoc().clips.find((c) => c.id === selected);
  const length = () => editLength(visibleDoc());
  const pause = () => {
    playing = false; play.textContent = "Play"; video.pause(); audio.pause();
    for (const player of dialoguePlayers.values()) player.pause();
    cancelAnimationFrame(raf); raf = 0;
  };
  const stop = () => {
    ++epoch; pending?.abort(); pending = null; requestedPlayback = false;
    pause(); play.setAttribute("aria-busy", "false");
  };
  const updateCursor = () => {
    scrub.value = String(frame);
    track.setAttribute("aria-valuemax", String(Math.max(0, length() - 1)));
    track.setAttribute("aria-valuenow", String(frame));
    head.style.left = `${frame / fps * Number(zoom.value)}px`;
    const seconds = frame / fps;
    time.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${(seconds % 60).toFixed(3).padStart(6, "0")} / ${(length() / fps).toFixed(3)}s`;
    track.setAttribute("aria-valuetext", time.textContent);
    const clip = selectedClip(), take = takeFor(payload, clip);
    const at = clipAt(visibleDoc(), frame);
    sourceCursor.hidden = at.clip.id !== clip.id;
    sourceCursor.style.left = `${100 * (clip.in_frame + frame - at.start) / take.frames}%`;
  };
  const loadFilmstrip = async (take) => {
    const key = JSON.stringify([take.file, take.offset, take.frames]);
    if (key === filmKey) return;
    filmKey = key; filmAbort?.abort(); filmAbort = new AbortController();
    const signal = filmAbort.signal;
    sourceImages.replaceChildren();
    const decoder = el("video"); decoder.muted = true; decoder.playsInline = true; decoder.preload = "auto";
    const image = el("canvas"); image.width = 120; image.height = 72;
    try {
      await mediaEvent(decoder, "loadeddata", () => { decoder.src = urlFor(take.file); decoder.load(); }, signal);
      const context = image.getContext("2d");
      if (!context) throw new Error("Cannot draw the source filmstrip.");
      for (let i = 0; i < 8; i++) {
        const target = take.offset + Math.min(take.frames - 1, (i + .5) * take.frames / 8) / fps;
        if (Math.abs(decoder.currentTime - target) > .0001)
          await mediaEvent(decoder, "seeked", () => { decoder.currentTime = target; }, signal);
        if (signal.aborted || closed) return;
        const scale = Math.max(image.width / decoder.videoWidth, image.height / decoder.videoHeight);
        context.drawImage(decoder, (image.width - decoder.videoWidth * scale) / 2,
          (image.height - decoder.videoHeight * scale) / 2, decoder.videoWidth * scale, decoder.videoHeight * scale);
        const thumb = el("img"); thumb.alt = ""; thumb.src = image.toDataURL("image/jpeg", .65); sourceImages.append(thumb);
      }
    } catch (error) {
      if (!signal.aborted && !closed) report(error);
    } finally { decoder.removeAttribute("src"); decoder.load(); }
  };
  const paintWave = () => {
    const width = Math.max(1, Math.ceil(length() / fps * Number(zoom.value)));
    canvas.style.width = `${width}px`;
    canvas.width = Math.min(width, 16384); canvas.height = 56;
    const ctx = canvas.getContext("2d"); ctx.clearRect(0, 0, canvas.width, 56);
    if (!musicEnabled()) {
      ctx.fillStyle = "#aaa";
      ctx.fillText(payload.music?.source_audio ? "Source soundtrack replaced by the dialogue track" : "No music connected", 10, 30);
      return;
    }
    const { peaks, duration } = payload.music, total = length() / fps;
    ctx.fillStyle = getComputedStyle(dialog).getPropertyValue("--mjr-wave").trim() || "#65d3b5";
    for (let x = 0; x < canvas.width; x++) {
      const second = x / canvas.width * total;
      if (second >= duration) break;
      const a = Math.floor(second / duration * peaks.length);
      const b = Math.min(peaks.length, Math.max(a + 1, Math.ceil((x + 1) / canvas.width * total / duration * peaks.length)));
      let peak = 0;
      for (let i = a; i < b; i++) peak = Math.max(peak, peaks[i]);
      const h = Math.max(1, peak * 50);
      ctx.fillRect(x, (56 - h) / 2, 1, h);
    }
  };
  const syncSource = (clip) => {
    const take = takeFor(payload, clip);
    selectedLabel.textContent = `${clip.id} (${take.frames} available frames)`;
    sourceTime.textContent = `${(clip.in_frame / fps).toFixed(2)} - ${(clip.out_frame / fps).toFixed(2)} s / ${(take.frames / fps).toFixed(2)} s`;
    sourceWindow.style.left = `${100 * clip.in_frame / take.frames}%`;
    sourceWindow.style.width = `${100 * (clip.out_frame - clip.in_frame) / take.frames}%`;
    sourceWindow.setAttribute("aria-valuemin", "0");
    sourceWindow.setAttribute("aria-valuemax", String(take.frames - (clip.out_frame - clip.in_frame)));
    sourceWindow.setAttribute("aria-valuenow", String(clip.in_frame));
    sourceWindow.setAttribute("aria-valuetext", sourceTime.textContent);
    void loadFilmstrip(take);
    takes.replaceChildren();
    for (const t of payload.library.find((s) => s.id === clip.shot_id).takes) {
      const option = el("option", t.id); option.value = t.id; takes.append(option);
    }
    takes.value = clip.revision_id; input.value = String(clip.in_frame); output.value = String(clip.out_frame);
  };
  const render = () => {
    if (!selectedClip()) selected = history.doc.clips[0].id;
    const clip = selectedClip();
    clips.replaceChildren();
    let clipStart = 0;
    for (const c of visibleDoc().clips) {
      const start = clipStart;
      clipStart += c.out_frame - c.in_frame;
      const box = el("div"); box.className = "mjr-edit-clip"; box.draggable = true;
      box.style.width = `${(c.out_frame - c.in_frame) / fps * Number(zoom.value)}px`;
      box.dataset.selected = String(c.id === selected);
      const button = el("button", `${c.shot_id} / ${c.revision_id}`);
      button.className = "mjr-edit-body";
      button.title = `${c.id}: ${c.in_frame}..${c.out_frame} frames`;
      button.setAttribute("aria-pressed", String(c.id === selected));
      button.onclick = (event) => {
        const bounds = button.getBoundingClientRect();
        const local = Math.max(0, Math.min(c.out_frame - c.in_frame - 1,
          Math.floor((event.clientX - bounds.left) / Number(zoom.value) * fps)));
        selected = c.id; render(); void seek(start + local);
      };
      box.ondragstart = (event) => { dragged = c.id; event.dataTransfer.setData("text/plain", c.id); };
      box.ondragover = (event) => event.preventDefault();
      box.ondrop = (event) => {
        event.preventDefault();
        if (dragged) command({ type: "move", id: dragged, index: history.doc.clips.findIndex((v) => v.id === c.id) });
        dragged = null;
      };
      box.ondragend = () => { dragged = null; };
      box.append(button);
      for (const edge of ["start", "end"]) {
        const handle = el("button"); handle.className = "mjr-edit-handle";
        handle.style[edge === "start" ? "left" : "right"] = "0";
        handle.setAttribute("aria-label", `Trim ${edge} ${c.id}`);
        handle.title = `Drag to ripple trim ${edge} (arrow keys: 1 frame)`;
        handle.onclick = (event) => event.stopPropagation();
        handle.ondragstart = (event) => { event.preventDefault(); event.stopPropagation(); };
        handle.onkeydown = (event) => {
          if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
          event.preventDefault(); event.stopPropagation();
          const delta = event.key === "ArrowRight" ? 1 : -1;
          command({ type: "trim", id: c.id, in_frame: c.in_frame + (edge === "start" ? delta : 0),
            out_frame: c.out_frame + (edge === "end" ? delta : 0) });
        };
        handle.onpointerdown = (event) => {
          if (event.button !== 0 || saving) return;
          event.preventDefault(); event.stopPropagation();
          stop();
          const x = event.clientX, available = takeFor(payload, c).frames;
          let start = c.in_frame, end = c.out_frame;
          selected = c.id; syncSource(c);
          handle.setPointerCapture(event.pointerId);
          handle.onpointermove = (move) => {
            const delta = Math.round((move.clientX - x) * fps / Number(zoom.value));
            if (edge === "start") start = Math.max(0, Math.min(c.out_frame - 1, c.in_frame + delta));
            else end = Math.max(c.in_frame + 1, Math.min(available, c.out_frame + delta));
            box.style.width = `${(end - start) / fps * Number(zoom.value)}px`;
            syncSource({ ...c, in_frame: start, out_frame: end });
            status.textContent = `Trim ${c.id}: ${start}..${end} frames`;
          };
          handle.onpointerup = (up) => {
            handle.releasePointerCapture(up.pointerId);
            handle.onpointermove = handle.onpointerup = handle.onpointercancel = null;
            selected = c.id;
            command({ type: "trim", id: c.id, in_frame: start, out_frame: end });
          };
          handle.onpointercancel = () => {
            handle.onpointermove = handle.onpointerup = handle.onpointercancel = null;
            render(); void seek(frame);
          };
        };
        box.append(handle);
      }
      clips.append(box);
    }
    const laneLength = Math.max(length(), ...dialogueClips().map((c) => c.at_frame + c.out_frame - c.in_frame));
    track.style.width = `${Math.max(1, laneLength / fps * Number(zoom.value))}px`;
    dialogueLane.replaceChildren();
    const entries = dialogueClips();
    const rows = [];
    for (const c of [...entries].sort((a, b) => a.at_frame - b.at_frame)) {
      const end = c.at_frame + c.out_frame - c.in_frame;
      let row = rows.findIndex((previous) => previous <= c.at_frame);
      if (row < 0) row = rows.length;
      rows[row] = end;
      const box = el("div"); box.className = "mjr-dialogue-clip"; box.dataset.id = c.id;
      box.dataset.selected = String(c.id === audioSelected); box.tabIndex = 0;
      box.setAttribute("role", "button"); box.setAttribute("aria-label", `Dialogue ${c.id}`);
      box.style.left = `${c.at_frame / fps * Number(zoom.value)}px`;
      box.style.width = `${(c.out_frame - c.in_frame) / fps * Number(zoom.value)}px`;
      box.style.top = `${row * 54}px`;
      box.append(el("span", `${c.shot_id} / ${c.revision_id}${c.gain === 0 ? " (muted)" : ""}`));
      const wave = el("canvas"); wave.width = Math.min(16384, Math.max(1, Math.ceil((c.out_frame - c.in_frame) / fps * Number(zoom.value)))); wave.height = 28;
      const ctx = wave.getContext("2d"), take = takeFor(payload, c), data = take.audio;
      ctx.fillStyle = "#c9a6ff";
      if (data) for (let x = 0; x < wave.width; x++) {
        const second = take.offset + (c.in_frame + x / wave.width * (c.out_frame - c.in_frame)) / fps;
        const peak = data.peaks[Math.min(data.peaks.length - 1, Math.floor(second / data.duration * data.peaks.length))] || 0;
        const h = Math.max(1, peak * 26); ctx.fillRect(x, (28 - h) / 2, 1, h);
      }
      box.append(wave);
      for (const edge of ["start", "end"]) {
        const grip = el("button"); grip.className = "mjr-edit-handle"; grip.dataset.edge = edge;
        grip.style[edge === "start" ? "left" : "right"] = "0";
        grip.setAttribute("aria-label", `Dialogue trim ${edge} ${c.id}`); box.append(grip);
        grip.onkeydown = (event) => {
          if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
          event.preventDefault(); event.stopPropagation();
          const delta = event.key === "ArrowRight" ? 1 : -1;
          audioSelected = c.id;
          command({ type: "dialogue-update", id: c.id,
            ...(edge === "start" ? { in_frame: c.in_frame + delta, at_frame: c.at_frame + delta } : { out_frame: c.out_frame + delta }) });
        };
      }
      box.onpointerdown = (event) => {
        if (event.button !== 0 || saving || sourceGesture || audioGesture) return;
        event.preventDefault(); event.stopPropagation(); stop(); audioSelected = c.id;
        audioGesture = { clip: c, x: event.clientX, edge: event.target.dataset.edge, next: { ...c } };
        box.setPointerCapture(event.pointerId);
      };
      box.onpointermove = (event) => {
        if (!audioGesture || audioGesture.clip.id !== c.id) return;
        const g = audioGesture, scale = track.getBoundingClientRect().width / (track.offsetWidth || parseFloat(track.style.width));
        const delta = Math.round((event.clientX - g.x) / scale * fps / Number(zoom.value));
        const next = { ...c };
        if (g.edge === "start") {
          const shift = Math.max(-c.in_frame, -c.at_frame, Math.min(c.out_frame - c.in_frame - 1, delta));
          next.in_frame += shift; next.at_frame += shift;
        } else if (g.edge === "end") next.out_frame = Math.max(c.in_frame + 1, Math.min(dialogueFrames(take), c.out_frame + delta));
        else next.at_frame = Math.max(0, c.at_frame + delta);
        g.next = next;
        box.style.left = `${next.at_frame / fps * Number(zoom.value)}px`;
        box.style.width = `${(next.out_frame - next.in_frame) / fps * Number(zoom.value)}px`;
        dialogueAt.value = String(next.at_frame); dialogueIn.value = String(next.in_frame); dialogueOut.value = String(next.out_frame);
      };
      box.onpointerup = () => {
        if (!audioGesture) return;
        const next = audioGesture.next; audioGesture = null;
        if (next.at_frame !== c.at_frame || next.in_frame !== c.in_frame || next.out_frame !== c.out_frame)
          command({ type: "dialogue-update", ...next });
        else render();
      };
      box.onpointercancel = box.onlostpointercapture = () => { if (audioGesture) { audioGesture = null; render(); } };
      box.onkeydown = (event) => {
        if (event.target !== box) return;
        if (["Enter", " "].includes(event.key)) { event.preventDefault(); event.stopPropagation(); audioSelected = c.id; render(); }
        else if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
          event.preventDefault(); event.stopPropagation(); audioSelected = c.id;
          command({ type: "dialogue-update", id: c.id, at_frame: c.at_frame + (event.key === "ArrowRight" ? 1 : -1) });
        }
      };
      dialogueLane.append(box);
    }
    dialogueLane.style.height = `${Math.max(1, rows.length) * 54}px`;
    const selectedAudio = entries.find((c) => c.id === audioSelected);
    dialogueLabel.textContent = selectedAudio?.id || "Select a dialogue excerpt";
    for (const field of [dialogueAt, dialogueIn, dialogueOut, dialogueGain, applyDialogue, deleteDialogue]) field.disabled = !selectedAudio;
    if (selectedAudio) {
      dialogueAt.value = String(selectedAudio.at_frame); dialogueIn.value = String(selectedAudio.in_frame);
      dialogueOut.value = String(selectedAudio.out_frame); dialogueGain.value = String(selectedAudio.gain ?? 1);
    }
    musicGain.value = String(history.doc.music_gain ?? 1); musicGain.disabled = !musicEnabled();
    addDialogue.disabled = !takeFor(payload, clip).audio;
    dialogueWarning.textContent = entries.some((c) => (c.gain ?? 1) > 0 && c.at_frame + c.out_frame - c.in_frame > length())
      ? "Dialogue exceeds the picture: export is blocked until you extend the video or explicitly trim/move this excerpt." : "";
    for (const [id, player] of dialoguePlayers) if (!entries.some((c) => c.id === id)) {
      dialoguePlayers.delete(id); player.pause(); player.removeAttribute("src"); player.load(); player.remove();
    }
    ruler.replaceChildren();
    const step = Math.max(1, Math.ceil(70 / Number(zoom.value)));
    for (let second = 0; second < length() / fps; second += step) {
      const tick = el("span", `${second}s`); tick.className = "mjr-edit-tick";
      tick.style.left = `${second * Number(zoom.value)}px`; ruler.append(tick);
    }
    syncSource(clip);
    undo.disabled = !history.past.length; redo.disabled = !history.future.length;
    del.disabled = history.doc.clips.length === 1;
    left.disabled = history.doc.clips[0].id === clip.id;
    right.disabled = history.doc.clips.at(-1).id === clip.id;
    scrub.max = String(Math.max(0, length() - 1));
    paintWave(); updateCursor();
  };
  // At a media boundary pause the audio clock until the next take is ready.
  // This avoids silently drifting, but does not promise gapless proxy playback.
  const seek = async (target, resume = false) => {
    if (closed) return;
    stop();
    const token = epoch;
    pending = new AbortController();
    const signal = pending.signal;
    requestedPlayback = resume;
    play.textContent = resume ? "Pause" : "Play";
    play.setAttribute("aria-busy", "true");
    frame = Math.max(0, Math.min(Math.round(target), length() - 1));
    updateCursor(); status.dataset.state = ""; status.textContent = "Loading preview...";
    try {
      const at = clipAt(visibleDoc(), frame), take = takeFor(payload, at.clip);
      const url = urlFor(take.file);
      if (video.dataset.source !== url || video.readyState < 1) {
        await mediaEvent(video, "loadedmetadata", () => { video.src = url; video.dataset.source = url; video.load(); }, signal);
      }
      if (closed || token !== epoch) return;
      const position = take.offset + (at.clip.in_frame + frame - at.start) / fps;
      if (video.seeking || Math.abs(video.currentTime - position) > .0001) {
        await mediaEvent(video, "seeked", () => { video.currentTime = position; }, signal);
      }
      if (closed || token !== epoch) return;
      current = at;
      audio.volume = visibleDoc().music_gain ?? 1;
      const voices = [];
      for (const clip of audibleAt(frame)) {
        const take = takeFor(payload, clip);
        if (!take.audio) throw new Error(`Dialogue ${clip.id}: source audio is unavailable. Reload the editor or select another take.`);
        let player = dialoguePlayers.get(clip.id);
        if (!player) {
          player = el("audio"); player.preload = "auto"; player.dataset.dialogue = clip.id;
          const voice = player;
          player.addEventListener("error", () => { if (!closed && dialoguePlayers.get(clip.id) === voice) failMedia(); });
          player.addEventListener("waiting", () => { if (audibleAt(frame).some((c) => c.id === clip.id)) bufferMedia(); });
          dialoguePlayers.set(clip.id, player); dialog.append(player);
        }
        const url = urlFor(take.audio.file);
        if (player.dataset.source !== url || player.readyState < 1)
          await mediaEvent(player, "loadedmetadata", () => { player.src = url; player.dataset.source = url; player.load(); }, signal);
        if (closed || token !== epoch) return;
        const position = take.offset + (clip.in_frame + frame - clip.at_frame) / fps;
        if (player.seeking || Math.abs(player.currentTime - position) > .0001)
          await mediaEvent(player, "seeked", () => { player.currentTime = position; }, signal);
        if (closed || token !== epoch) return;
        player.volume = clip.gain ?? 1;
        voices.push(player);
      }
      activeDialogue = audibleKey(frame);
      if (musicEnabled()) {
        if (audio.readyState < 1) await mediaEvent(audio, "loadedmetadata", () => audio.load(), signal);
        if (closed || token !== epoch) return;
        const audioPosition = Math.min(frame / fps, payload.music.duration);
        if (audio.seeking || Math.abs(audio.currentTime - audioPosition) > .0001)
          await mediaEvent(audio, "seeked", () => { audio.currentTime = audioPosition; }, signal);
      }
      if (closed || token !== epoch) return;
      if (resume) {
        const useAudio = musicEnabled() && frame / fps < payload.music.duration;
        if (video.readyState < 3) await mediaEvent(video, "canplay", () => {}, signal);
        if (useAudio && audio.readyState < 3) await mediaEvent(audio, "canplay", () => {}, signal);
        for (const player of voices) if (player.readyState < 3) await mediaEvent(player, "canplay", () => {}, signal);
        if (closed || token !== epoch) return;
        status.textContent = "Starting playback...";
        // Never start audible music while the muted video is still unable to play.
        await startMedia(video, signal);
        if (closed || token !== epoch) return;
        if (useAudio) await startMedia(audio, signal);
        if (closed || token !== epoch) return;
        for (const player of voices) {
          await startMedia(player, signal);
          if (closed || token !== epoch) return;
        }
        playing = true; play.textContent = "Pause"; raf = requestAnimationFrame(tick);
      }
      status.textContent = "";
    } catch (error) {
      if (!closed && token === epoch) { stop(); report(error); }
    } finally {
      if (token === epoch) play.setAttribute("aria-busy", "false");
    }
  };
  const finishPlayback = () => {
    if (looping) { void seek(0, true); return; }
    frame = length() - 1; stop(); updateCursor();
  };
  const tick = () => {
    if (!playing || closed || !current) return;
    const take = takeFor(payload, current.clip);
    const videoTime = current.start / fps + video.currentTime - take.offset - current.clip.in_frame / fps;
    const useAudio = musicEnabled() && !audio.ended && frame / fps < payload.music.duration;
    const seconds = useAudio ? audio.currentTime : videoTime;
    frame = Math.max(0, Math.floor(seconds * fps + .00001));
    if (frame >= length()) { finishPlayback(); return; }
    const next = clipAt(history.doc, frame);
    if (next.index !== current.index) { void seek(frame, true); return; }
    if (activeDialogue !== audibleKey(frame)) { void seek(frame, true); return; }
    for (const clip of audibleAt(frame)) {
      const player = dialoguePlayers.get(clip.id), source = takeFor(payload, clip);
      const position = source.offset + (clip.in_frame + frame - clip.at_frame) / fps;
      if (!player || player.ended || Math.abs(player.currentTime - position) > .12) { void seek(frame, true); return; }
    }
    const expected = take.offset + (current.clip.in_frame + frame - current.start) / fps;
    if (useAudio && Math.abs(video.currentTime - expected) > .12) { void seek(frame, true); return; }
    updateCursor(); raf = requestAnimationFrame(tick);
  };
  const command = (action) => {
    if (saving || sourceGesture || audioGesture) return;
    stop();
    try {
      history.apply(action); status.textContent = "";
      if (action.type === "dialogue-add") audioSelected = history.doc.dialogue.at(-1).id;
      onChange(history.doc); frame = Math.min(frame, length() - 1);
      render(); void seek(frame);
    } catch (error) { report(error); render(); }
  };
  const sourceEdit = (clip, edge, delta, available) => {
    let start = clip.in_frame, end = clip.out_frame;
    if (edge === "start") start = Math.max(0, Math.min(end - 1, start + delta));
    else if (edge === "end") end = Math.max(start + 1, Math.min(available, end + delta));
    else {
      const shift = Math.max(-start, Math.min(available - end, delta));
      start += shift; end += shift;
    }
    return { ...clip, in_frame: start, out_frame: end };
  };
  const finishSourceGesture = (cancel = false) => {
    const gesture = sourceGesture;
    if (!gesture) return;
    sourceGesture = null;
    const next = selectedClip();
    previewDoc = null;
    if (cancel) { frame = gesture.frame; render(); void seek(frame); return; }
    if (next.in_frame !== gesture.clip.in_frame || next.out_frame !== gesture.clip.out_frame)
      command({ type: "trim", id: next.id, in_frame: next.in_frame, out_frame: next.out_frame });
    else { render(); void seek(frame); }
  };
  sourceTrack.onpointerdown = (event) => {
    if (event.button !== 0 || saving || sourceGesture) return;
    const target = event.target.closest(".mjr-source-window");
    if (!target) return;
    event.preventDefault(); event.stopPropagation();
    const clip = { ...selectedClip() }, take = takeFor(payload, clip);
    const width = sourceTrack.getBoundingClientRect().width;
    if (width <= 0) return;
    stop();
    sourceGesture = { clip, edge: event.target.closest(".mjr-source-grip")?.dataset.edge,
      x: event.clientX, width, available: take.frames, frame };
    sourceTrack.setPointerCapture(event.pointerId);
  };
  sourceTrack.onpointermove = (event) => {
    if (!sourceGesture) return;
    const g = sourceGesture;
    const next = sourceEdit(g.clip, g.edge, Math.round((event.clientX - g.x) / g.width * g.available), g.available);
    previewDoc = { ...history.doc, clips: history.doc.clips.map((clip) => clip.id === next.id ? next : clip) };
    const at = previewDoc.clips.findIndex((clip) => clip.id === next.id);
    frame = previewDoc.clips.slice(0, at).reduce((sum, clip) => sum + clip.out_frame - clip.in_frame, 0)
      + (g.edge === "end" ? next.out_frame - next.in_frame - 1 : 0);
    render(); void seek(frame);
  };
  sourceTrack.onpointerup = (event) => {
    if (!sourceGesture) return;
    finishSourceGesture();
    if (sourceTrack.hasPointerCapture(event.pointerId)) sourceTrack.releasePointerCapture(event.pointerId);
  };
  sourceTrack.onpointercancel = () => finishSourceGesture(true);
  sourceTrack.onlostpointercapture = () => finishSourceGesture(true);
  sourceWindow.onkeydown = (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key) || saving) return;
    event.preventDefault(); event.stopPropagation();
    const clip = selectedClip(), edge = event.target.dataset.edge;
    const next = sourceEdit(clip, edge, event.key === "ArrowRight" ? 1 : -1, takeFor(payload, clip).frames);
    command({ type: "trim", id: next.id, in_frame: next.in_frame, out_frame: next.out_frame });
  };
  play.onclick = () => {
    if (sourceGesture || navigation || saving) return;
    if (playing || requestedPlayback) { stop(); status.textContent = ""; }
    else void seek(frame >= length() - 1 ? 0 : frame, true);
  };
  loop.onclick = () => {
    looping = !looping;
    loop.setAttribute("aria-pressed", String(looping));
  };
  const bufferMedia = () => {
    if (playing) void seek(frame, true);
  };
  video.addEventListener("waiting", bufferMedia);
  audio.addEventListener("waiting", bufferMedia);
  video.addEventListener("ended", () => {
    if (playing && current) {
      if (current.end < length()) void seek(current.end, true);
      else finishPlayback();
    }
  });
  const failMedia = () => { stop(); report(new Error("Preview media cannot be decoded.")); };
  video.addEventListener("error", failMedia); audio.addEventListener("error", failMedia);
  scrub.oninput = () => void seek(Number(scrub.value));
  back.onclick = () => void seek(frame - 1);
  forward.onclick = () => void seek(frame + 1);
  const navigate = (target, resume = false) => {
    frame = Math.max(0, Math.min(Math.round(target), length() - 1));
    selected = clipAt(history.doc, frame).clip.id;
    render(); void seek(frame, resume);
  };
  const pointerFrame = (event) => {
    const box = track.getBoundingClientRect();
    const scale = box.width / (track.offsetWidth || parseFloat(track.style.width));
    return (event.clientX - box.left) / scale / Number(zoom.value) * fps;
  };
  track.onpointerdown = (event) => {
    if (event.button !== 0 || saving || sourceGesture || navigation) return;
    if (![track, ruler, canvas, head].includes(event.target)) return;
    event.preventDefault(); event.stopPropagation();
    navigation = { pointerId: event.pointerId, frame, selected, resume: playing || requestedPlayback };
    track.focus({ preventScroll: true });
    track.setPointerCapture(event.pointerId);
    navigate(pointerFrame(event));
  };
  track.onpointermove = (event) => {
    if (!navigation || event.pointerId !== navigation.pointerId) return;
    const viewport = scroll.getBoundingClientRect();
    if (event.clientX < viewport.left + 20) scroll.scrollLeft -= 20;
    else if (event.clientX > viewport.right - 20) scroll.scrollLeft += 20;
    navigate(pointerFrame(event));
  };
  const finishNavigation = (cancel = false) => {
    if (!navigation) return;
    const previous = navigation;
    navigation = null;
    if (cancel) selected = previous.selected;
    const target = cancel ? previous.frame : frame;
    if (cancel) { frame = target; render(); void seek(frame, previous.resume); }
    else navigate(target, previous.resume);
    if (track.hasPointerCapture(previous.pointerId)) track.releasePointerCapture(previous.pointerId);
  };
  track.onpointerup = (event) => {
    if (!navigation || event.pointerId !== navigation.pointerId) return;
    navigate(pointerFrame(event));
    finishNavigation();
  };
  track.onpointercancel = () => finishNavigation(true);
  track.onlostpointercapture = () => finishNavigation(true);
  track.onkeydown = (event) => {
    if (event.target !== track || saving || navigation || sourceGesture) return;
    const targets = { ArrowLeft: frame - 1, ArrowRight: frame + 1,
      Home: 0, End: length() - 1, PageUp: frame - Math.round(fps), PageDown: frame + Math.round(fps) };
    if (!(event.key in targets)) return;
    event.preventDefault(); event.stopPropagation(); navigate(targets[event.key]);
  };
  zoom.oninput = render;
  addDialogue.onclick = () => command({ type: "dialogue-add", id: selected });
  applyDialogue.onclick = () => command({ type: "dialogue-update", id: audioSelected, at_frame: Number(dialogueAt.value),
    in_frame: Number(dialogueIn.value), out_frame: Number(dialogueOut.value), gain: Number(dialogueGain.value) });
  deleteDialogue.onclick = () => command({ type: "dialogue-delete", id: audioSelected });
  musicGain.onchange = () => command({ type: "music-volume", gain: Number(musicGain.value) });
  trim.onclick = () => command({ type: "trim", id: selected, in_frame: Number(input.value), out_frame: Number(output.value) });
  slipButton.onclick = () => command({ type: "slip", id: selected, frames: Number(slip.value) });
  takes.onchange = () => command({ type: "take", id: selected, revision_id: takes.value });
  cut.onclick = () => {
    let start = 0;
    for (const clip of history.doc.clips) {
      if (clip.id === selected) break;
      start += clip.out_frame - clip.in_frame;
    }
    command({ type: "cut", id: selected, frame: frame - start });
  };
  dup.onclick = () => command({ type: "duplicate", id: selected });
  del.onclick = () => command({ type: "delete", id: selected });
  left.onclick = () => command({ type: "move", id: selected, index: history.doc.clips.findIndex((c) => c.id === selected) - 1 });
  right.onclick = () => command({ type: "move", id: selected, index: history.doc.clips.findIndex((c) => c.id === selected) + 1 });
  const travel = (method) => {
    if (saving || sourceGesture || audioGesture) return;
    stop();
    try {
      history[method](); onChange(history.doc);
      frame = Math.min(frame, length() - 1); render(); void seek(frame);
    } catch (error) { report(error); render(); }
  };
  undo.onclick = () => travel("undo"); redo.onclick = () => travel("redo");
  const persist = async (handler) => {
    if (saving || sourceGesture || audioGesture) return;
    if (handler === onRender && dialogueClips().some((c) => (c.gain ?? 1) > 0 && c.at_frame + c.out_frame - c.in_frame > length())) {
      report(new Error("Dialogue exceeds the picture. Extend the video or explicitly trim/move/mute the excerpt before exporting.")); return;
    }
    stop(); saving = true;
    const buttons = [...dialog.querySelectorAll("button,input,select")];
    const disabled = buttons.map((button) => button.disabled);
    for (const button of buttons) button.disabled = true;
    status.dataset.state = ""; status.textContent = labels.saving || "Saving montage...";
    try {
      await handler(JSON.parse(JSON.stringify(history.doc)));
      if (!closed) status.textContent = labels.saved || "Montage saved.";
    } catch (error) {
      if (!closed) report(error);
    } finally {
      saving = false;
      buttons.forEach((button, index) => { button.disabled = disabled[index]; });
      if (!closed) render();
    }
  };
  if (save) save.onclick = () => void persist(onSave);
  if (exportButton) exportButton.onclick = () => void persist(onRender);
  dialog.addEventListener("keydown", (event) => {
    if (saving) { event.preventDefault(); event.stopPropagation(); return; }
    if (["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
    if (event.code === "Space") { event.preventDefault(); event.stopPropagation(); play.click(); }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      event.preventDefault(); event.stopPropagation(); travel(event.shiftKey ? "redo" : "undo");
    }
  });
  const cleanup = () => {
    if (closed) return;
    closed = true; stop(); filmAbort?.abort();
    for (const media of [video, audio, ...dialoguePlayers.values()]) { media.removeAttribute("src"); media.load(); }
    dialoguePlayers.clear();
    dialog.remove(); onClose();
  };
  close.onclick = () => dialog.close();
  dialog.addEventListener("close", cleanup, { once: true });
  dialog.showModal(); render(); void seek(0);
  return () => { dialog.close(); cleanup(); };
}
