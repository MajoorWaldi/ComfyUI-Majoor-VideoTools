# Majoor VideoTools

Four ComfyUI nodes that turn a video into a collection of identified shots, let any workflow replace one shot, and rebuild the video without touching the source.

Quatre nodes ComfyUI : une vidéo devient une collection de shots identifiés, n'importe quel workflow peut en remplacer un, puis la vidéo est remontée sans toucher à la source.

```
Load Video → Scene Detect & Split → Select Shot ─┬─ video / images → (your generator, VLM, API…) ─┐
                    │                            └─ metadata ─────────────────────────────────────┤
                    └─ shot_list ─────────────────────────────────────────────────────→ Apply Shot Metadata → Shot Assemble → Video
```

Category: `Majoor/VideoTools`.

**Create Timeline** builds the same `shot_list` without footage, to use as a template, from a JSON edit plan (`source = json`), from the bars and beats of a music (`music`) or from the cuts of a reference video (`video`); the sources are described after the JSON plan below. Each shot of the template: each shot is a color card in a generated video (with the brief of the shot written on it, see `card_text`), optionally with music as its audio. Take every shot with **Select Shot** (its `prompt`, `image_prompt` and `generation_frames` outputs feed a generator), regenerate it, put it back with **Apply Shot Metadata**, and rebuild with **Shot Assemble**. Effects (cuts inside a take, speed, zoom, transitions, text) are written in the plan and rendered by Shot Assemble, see below. Shots still holding their placeholder make Shot Assemble stop, unless `missing_shot_policy` is `use_original` (the card is kept, for an animatic).

```json
{ "fps": 24, "aspect_ratio": "9:16",
  "shots": [ { "id": "SHOT_001", "duration": 2.5, "prompt": "…", "image_prompt": "…", "notes": "…", "color": "yellow",
               "layers": [ { "layout": "left", "color": "#2255ff" }, { "rect": [0.55, 0.1, 0.35, 0.5], "color": "red", "opacity": 0.6 } ] },
             { "duration": "60f", "prompt": "…" }, { "duration": "00:03.5", "prompt": "…" } ] }
```

- **`source = music`**: connect `music`; the node detects the tempo and puts a cut on every `cut_every` (`half_beat`, `beat`, `2_beats`, `bar`, `2_bars`, `4_bars`) from the first beat. `duration` (0 = the whole music), `shots` (0 = one shot per grid step, otherwise that many with their cuts spread over the grid), `bpm` (0 = detect), `beats_per_bar` and `downbeat` (the tempo is detected, the bars are not: shift the first bar by hand). The music is the audio of the template.
- **`source = video`**: connect `video`; its cuts are detected (PySceneDetect, like Scene Detect & Split) and become the rhythm of the template. Each shot is generated once, so cuts in a row shorter than `min_shot_seconds` are grouped into one shot whose original cuts are its `sub_cuts`: a 15 s reference with 80 cuts gives about 10 shots that cut like the reference. `fps` and `aspect_ratio` follow the video when left on auto.
- **`source = none`**: no rhythm (empty `plan_json` and `rhythm_text`), to let the LLM decide in a workflow that switches between music, video and nothing. With `source = video` and a music connected, `cut_snap` moves the cuts of the video to its beats.
- **`skeleton_json`** (input, with `source = json`): the `plan_json` of another Create Timeline (music or video). Its shots, durations and the cuts inside them are kept; the plan of the LLM only brings the prompts and the effects, matched by shot id (or position), its sub-cuts by position. The LLM may leave every duration out. Language models are poor at adding up durations: this is how a rhythm taken from a reference is applied reliably.
- With `source = json`, the prompts of the plan are cleaned of negative boilerplate ("One continuous take, no cuts, no text."): it contradicts the sub-cuts. Descriptions of the role, the cuts, the framing and the transitions are kept.
- Outputs besides `shot_list`: `plan_json` (the plan that was built, to read, edit or save) and `rhythm_text` (the rhythm in words: shot ids, durations, cuts inside each shot), to hand to the LLM that writes the prompts, see `examples/prompts/timeline_planner.txt`.
- `duration` is seconds, `"60f"` frames or a timecode; Markdown fences around the JSON are accepted.
- Cards: `color` per shot (a CSS name such as `"yellow"` or `"#ffd400"`; without it, a distinct color per shot), and `layers` drawn over it in order, for split screens and inset cards:
  `{"layout": "left", "color": "#2255ff", "opacity": 1}`, with `layout` one of `full, left, right, top, bottom, top_left, top_right, bottom_left, bottom_right, center, pip`, or `"rect": [x, y, width, height]` as fractions of the frame. With `card_text` (on by default) each card shows the brief of its shot: id, place and length, role, transition, cuts, effects and the whole prompt. The text is wrapped to the card and the letters are shrunk until everything fits, so nothing is cut off, however long the prompt. Turn `card_text` off for plain cards, which are clean layout references for Select Shot's `images`. The id, duration and prompt of each shot are also shown in Select Shot's picker.
- **Dynamic edits.** A shot is generated once, but it can be cut into many pieces and styled in post, all rendered by Shot Assemble on the generated takes (the placeholder cards stay plain). Per shot, and again per sub-cut where it overrides the shot:
  `sub_cuts`: `[{"duration": 0.25, "start": 1.0, "zoom": 1.9, "focus": [0.5, 0.2], "flip": true, "speed": 2, "look": "mono", "transition": "whip"}, ...]` (several cuts out of ONE take; with no shot `duration`, the sub-cuts make it; at least 3 frames each; the cuts keep the proportions of the plan, and snap to half beats when `cut_snap` is on) ·
  `zoom` (1 to 4, or `[from, to]`) with `focus` `[x, y]` · `flip` · `speed` (0.1 to 8) or `speed_ramp` `[from, to]` · `look` (`mono`, `contrast`, `negative`) ·
  `transition` into the shot (`flash`, `flash_black`, `fade_black`, `fade_white`, `whip`, `whip_v`, `blur`, `punch`, `glitch`, `shake`, `strobe`, `invert`; an unknown name is a plain cut; or `{"type": "whip", "frames": 5}`) ·
  `text` `{"content", "position", "size", "color", "background", "repeat", "rotate"}` drawn over the whole shot (rendered with Pillow, font `impact.ttf`/`arialbd.ttf` or `MAJOOR_FONT`).
  `overlay` (a surimpression): a list of up to 3 layers `{"source": "self" | a shot id, "offset": seconds, "opacity": 0-1, "blend": normal|screen|multiply|overlay|add|lighten|darken|difference|softlight, "scale": 0.1-1, "position": ..., "zoom", "focus", "flip", "look"}` blended over the picture; `scale` below 1 makes a picture in picture ·
  `split` (a split screen): `{"layout": left_right|top_bottom|columns_3|rows_3|grid_4, "panels": [{"source": "self" | a shot id, "offset", "zoom", "focus", "flip", "look"}, ...]}`, one panel per cell (missing panels show the shot) ·
  `refs` `[1, 2]`: the pictures a shot shows, passed on in `fx_json` for workflows with several references.
  `overlay` and `split` work on the shot or on a sub-cut (`"split": null` turns the shot's value off for one cut). A `source` other than `self` is a shot of the same plan: its generated take is read at the same moment (shifted by `offset`); while that shot has no take, the shot itself stands in and Shot Assemble warns. They cost no generation. An unknown shot id is replaced by `self` when the timeline is created, with a warning.
  A `punch` transition and the zoom filters need a take; shots that keep their placeholder, or takes that use `keep_generated`, ignore the effects. `cut_snap = half_beat` snaps top-level cuts to the beat and the offbeats; the sub-cuts always snap to half beats.
- `generation_profile = minimax_h3` computes the frames to request per shot (at least 124, on the 17k+5 grid) and puts it in `generation_frames`.
- To have an LLM write the JSON (from an image, a music description or just a brief), use the system prompt in `examples/prompts/timeline_planner.txt` (dense edits: bursts of sub-cuts, speed ramps, transitions, text); its worked example, `examples/timeline_fashion_motion.json`, is a valid 8 s plan with 20 cuts. The previous prompt (one long cut per shot, 15 s example `timeline_aura_farming.json`) is kept as `examples/prompts/timeline_planner_v1.txt`; every prompt of the workflows is listed in `examples/prompts/README.md`.
- With `music`, `cut_snap` moves each cut to the nearest half beat, beat or bar (tempo detected, or `bpm`), keeping shots at least 6 frames long; the music is the template's audio, kept by `audio_policy = source_master`.
- Select Shot's `start_from_previous` makes `images` the last frame of the previous shot's active take, to continue from it: generate the shots one after the other.

Select Shot also tells what a shot of a timeline plan asks of the edit: `fx_json` (its transition, the cuts inside it with their lengths in seconds and effects, speed, zoom, look, text) and `rhythm_text` (the same in words: `transition in: flash (4 frames)`, `cuts (4): 0.25s / 0.25s (zoom 2, flip) / ...`). The node's preview shows it above the prompt, and the plan recipe has a preview of it next to the prompt preview. They are not sent to the generator by default (a shot is one take, the cuts and transitions are made when assembling): use them to write your own prompt or logic.

Two utility nodes sit outside the chain. **Preview Video** previews a `VIDEO` or an `IMAGE` batch (with its `fps`), with optional `AUDIO`, inside the node; nothing is written to the output folder. **Compare Video** is not part of the chain: connect any two `VIDEO`s (for example a shot's original and its generated take) and it plays them in sync inside the node, as a wipe slider (drag on the video) or side by side, with the size / fps / duration of each and a warning when they differ.

**Music and sound effects.** Generate the music on the grid of the edit (the BPM and length from `music_brief_from_plan`, ACE-Step for example), generate the sound effects with MMAudio / Foley, then connect both to **Shot Assemble** (`music`, `sfx`, with `audio_policy = mute`). The music is cut or padded to the edit and fades out; the effects track is mixed with it.

**Edit Skills** loads a system prompt from the `skills/` folder of the pack and gives it to your LLM node (`system_prompt` output), with a `user_message` made of your brief, the `<Picture N>` tags and the `rhythm_text` of Create Timeline / Cut Markers. The switches (`overlays_splits`, `text_overlays`, `reference_mode`, `genre`) take the matching parts out of the prompt and out of its example plan, so a small model reads less; `duration`, `fps`, `aspect_ratio` and `text_allowed` are written into it. Shipped skills: `dynamic_edit_skill` (the whole edit plan), `timeline_planner` (the planner of the AutoEdit workflow), `h3_shot_prompt_from_plan` (the prompt of one MiniMax H3 shot), `music_brief_from_plan` (BPM, structure and sound effects for a music model such as ACE-Step, from the rhythm of the edit). To add one, drop a `.md` file in `skills/` (header `name`, `kind`, `description`; parts between `<<module name>>` and `<<end>>`, variables like `{{DURATION}}`) and press Reload skills.

**Cut Markers** is a timeline editor for the rhythm of an edit. Connect a `video` and/or a `music` (both optional), run the node once to load them in the editor, then place the cuts by hand over the waveform of the music, its beats and the cuts detected in the video:

- click or drag on the timeline = move the playhead (the video and the music follow); `Space` plays and pauses;
- double-click, `M` or **+ marker** adds a marker at the playhead; drag a marker to move it; right-click or `Delete` removes it; `Ctrl+Z` undoes;
- markers stick to a grid chosen in the snap list (frames, half beats, beats, bars, the cuts of the video); hold `Alt` to drag without snapping;
- the wheel zooms, `Shift` + wheel pans, **Fit** shows everything;
- **Fill from…** puts markers on every half beat, beat, 2 beats, bar, 2 or 4 bars of the music, or on the cuts of the video, to correct by hand afterwards;
- under the waveform, the shots the markers will make are shown (cuts shorter than `min_shot_seconds` in a row are grouped into one shot whose cuts become sub-cuts, like Create Timeline's video source).

The markers are kept as seconds in the node's `markers` text (you can also type them: seconds `12.5`, timecodes `1:02.5` or frames `36f`). Outputs: `plan_json` (connect it to the `skeleton_json` of Create Timeline, so the LLM only writes prompts and effects) and `rhythm_text`. `fps` and `duration` follow the video, else the music; `bpm`, `beats_per_bar` and `downbeat` set the beat grid. With no media, set `duration` and type the markers. The editor plays a light copy of the music kept under `temp/majoor_cuts/` and the video from `temp/majoor_compare/`: after a restart of ComfyUI, run the node again to reload them.

## Katana-style edits with ComfyUI

Higgsfield's **Katana** is a skill for Claude (through the Higgsfield MCP connector, `/katana`): you give a reference edit and up to five photos of your people or products, it reads the shots, pacing, cuts and audio of the reference, regenerates the shots with your subjects on Higgsfield models, and rebuilds an MP4 with the duration, format and soundtrack of the reference; corrections are asked in the chat and only the affected shots are generated again. Its internals are not published. The same result, locally, with this pack:

1. **Rebuild a reference edit with new subjects** (Katana's "personalized edit"): `Load Video` (the reference) -> **Scene Detect & Split** (its shots and cuts; or **Create Timeline** `source = video` for a rhythm that groups the short cuts) -> a vision model reads the frames of each shot (`examples/prompts/shot_analyzer_v1.0.txt`) and rewrites the shot for your subject (`h3_shot_edit_director_v2.1.txt`, subject from `<Picture 1>`, motion and camera from the reference video) -> MiniMax H3 Ref2VA with the shot as motion reference -> **Apply Shot Metadata** -> **Shot Assemble** with `audio_policy = source_master`, so the cuts and the soundtrack of the reference stay. **Deploy Shots** with the `minimax_h3_ref2va` recipe builds the per-shot blocks for you.
2. **Make a new dynamic edit from a brief, pictures and a rhythm** (Katana's presets, without a reference): **Cut Markers** or **Create Timeline** (`source = music` or `video`) give the rhythm skeleton; a vision-language model with `examples/prompts/dynamic_edit_skill.txt` writes the prompts, the cuts and the effects (zooms, transitions, text, overlays, split screens) from your pictures and the `rhythm_text`; **Create Timeline** `source = json` with `skeleton_json` applies it; **Deploy Shots** (`Minimax H3 TimelineShot Creator`) generates the shots; **Shot Assemble** renders the edit on the music.
3. **Rebuild the effects of a reference too**: give the frames of the reference (labelled with their time) to the skill, "MODE B": it describes the framing, the speed, the transitions, the overlays and the split screens of each cut and writes the same structure for your subject.

Corrections: change the prompt of one shot and run again, only that shot is generated again (ComfyUI keeps the others); effects, cuts, overlays and split screens are changed in the plan and re-rendered by Shot Assemble without any generation.

**Deploy Shots** builds the per-shot part of a workflow for you. Run **Scene Detect & Split** (or **Create Timeline**) once so its shots are known, pick a `recipe`, press **Create shots**: for every shot the graph gets a block (Select Shot, analysis, generation, Apply Shot Metadata, Compare Video...), the Apply nodes are chained one after the other, and the last one feeds **Shot Assemble** (added with a Save Video when the graph has none). Pressing it again replaces the previous deployment; a block you made by hand for one of the shots is replaced after a confirmation (`replace_existing`).

- A **recipe** is a normal workflow saved in `recipes/` (a combo lists them; the pack ships `minimax_h3_ref2va`, the MiniMax H3 Ref2VA shot edit, which also opens as a complete starter workflow). It holds ONE shot block: a Select Shot with `SHOT_001`, the Set/Get nodes named after it (`SHOT_001`, `SHOT_001_META`, `SHOT_001_GENERATED`...) and whatever is wired to them (sub-graphs included). Everything the block shares with the rest of the graph goes through KJNodes Set/Get nodes (`REF`, `SHOT_LIST`, `OLLAMA`, `MODEL_*`...), or through a node outside the block that all shots read (an edit-request text): that node is created once and reused.
- The name of a block comes from its Set/Get nodes (`SHOT_001` in `SHOT_001_META`): the `shot_id` of the Select Shot of a recipe can be left on any shot. Every group around the Select Shot is copied (a group inside a group too), a Reroute is only a wire.
- To make your own recipe: build the block for one shot as you would by hand, with `SHOT_001`, save the workflow into `recipes/`, reload the page. The first Apply Shot Metadata starts from the shot list; the following ones are chained by the node. Blocks that read `prompt`, `image_prompt` and `generation_frames` of Select Shot work the same way for plan-based shots (Create Timeline).
- In the copy of a block every `SHOT_001` becomes the new shot id (nodes, titles, Set/Get names, sub-graph names), every sub-graph definition gets its own id, and Select Shot gets its `shot_id` and `index`. The Set nodes the recipe's Get nodes need (`REF`, `OLLAMA`, `MODEL_FULL`...) must exist in the graph; the report lists the missing ones.
- Three recipes ship. **`Minimax H3 TimelineShot Creator`** is the one of the working AutoEdit workflow: the brief of the shot (`rhythm_text`, `prompt`, `fx_json` of Select Shot) goes through the H3 prompt writer (`examples/prompts/h3_shot_prompt_from_plan.txt`), then H3, then Apply Shot Metadata, with a preview. The blocks it creates read the shot list **straight from Create Timeline or Scene Detect & Split** (the node feeding the Deploy Shots `shot_list`, else the one feeding a `Set SHOT_LIST`, else the only one of the graph): no Get node or Reroute in between. Also `minimax_h3_ref2va` (shots cut from a video: analysis of the shot, pose control, the shot as reference video) and `minimax_h3_ref2va_plan` (shots of a plan: the prompt of the plan, the length from `generation_seconds`, no analysis of the placeholder cards, no pose control; also a complete starter workflow). `recipe = auto` takes a recipe of kind `plan` when the shots come with prompts (the highest `priority` wins, so the TimelineShot Creator), a recipe of kind `video` otherwise. A recipe says it with `extra.majoor_recipe` in its workflow: `{"title": ..., "kind": "plan" | "video", "priority": 10}`; without it, a name ending with `_plan` means plan. Each block gets its own noise seed (the recipe's plus the shot's number).
- `max_shots` (0 = all), `columns` (blocks per row), `include_finale`. Requires KJNodes (Set/Get) and the nodes used by the recipe.

| Node | Output | Role |
|---|---|---|
| Scene Detect & Split | `shot_list` | PySceneDetect (adaptive / content / threshold_fade) or manual `cut_points`. Writes a manifest, no clip is encoded. |
| Select Shot | `video`, `images`, `metadata`, `prompt`, `image_prompt`, `generation_frames`, `generation_seconds`, `fx_json`, `rhythm_text` | Pick a shot by `shot_id` (or `index`) and a take. The clip is cut frame-accurately on first use and cached. |
| Apply Shot Metadata | `updated_shot_list` | Stores a generated video as a new take of the shot. Returns a new list; earlier lists and takes are kept. |
| Shot Assemble | `video` | Rebuilds the video from the active take of every shot (original order or `manual_order`). Toggles for a timeline plan: `effects` (speed, zoom, flip, look, transitions, text) and `sub_cuts` (the cuts inside a shot), to switch them without generating again; `audio_policy` mutes or keeps the music. |

## Previews in the nodes

After a run, **Scene Detect & Split** shows the source video with a timeline of the detected shots (click a segment to jump to it), **Shot Assemble** adds a timeline of the final shot order under ComfyUI's own video preview (replaced shots in orange); click a shot and press Regenerate to give a new seed to its generation block and queue the graph (only that shot is generated again, the rest comes from ComfyUI's cache), and **Select Shot** shows a filmstrip of the connected list: click a shot to fill `shot_id`, and the shot plays in the node (the source, until the node has run). The last result is saved with the workflow. **Compare Video** reads what is connected to it without running the graph (a Load Video file, a Select Shot clip, or the last output of any upstream node that has a video preview) and updates when the connection or the upstream file changes; otherwise it shows the result of the last run. **Preview Video** uses ComfyUI's own video preview after a run. The widgets live in `web/` and are optional; the nodes work the same through the API.

## Start in three steps (Edit Mode)

1. Pick a preset on the **Edit Mode** node: `Image to Reel`, `Remix` or `Music Edit` (`Advanced` offers all five modes), and a style if you want one.
2. Drop what the preset needs (your hero picture, the video to modify, or the song) and write one sentence.
3. Run. If Ollama is off, a model is not installed or a node pack is missing, a message says what to do before anything runs.

## Behaviour worth knowing

- **Not destructive.** The source is hard-linked (or copied) into the project and never modified. Takes are copied into `generated/`.
- **Projects** live in `ComfyUI/output/MajoorVideoTools/<project_id>/` (`manifest.json` is the latest collection, `manifests/` keeps every version). The project id is derived from the source content and the detection settings, so the same video with the same settings always returns the same shot ids; another sensitivity is a new collection.
- **Several shots:** chain `Select → generator → Apply` once per shot, feeding the updated list into the next `Select`.
- **Restore a take:** connect `Select Shot` (`take = original` or `revision_id`) straight into `Apply Shot Metadata` with its own `metadata`; the take is re-activated instead of duplicated. Applying the same generated file twice never creates a second take.
- **Durations.** A shot keeps its original duration by default (`trim_or_pad_last_frame`). `retime_to_target`, `trim_or_error` and `use_generated_duration` are available, and `Apply`'s `keep_generated` makes one take keep its own length. With `source_master` audio, any shot whose length changed produces a warning, because the source audio is no longer in sync after it.
- **Exports** are named `<output_name>_<hash>.mp4` and are never overwritten; an identical request reuses the existing file. Writing goes through a temporary file that is validated before it is renamed.
- Audio: `source_master` (source soundtrack, 48 kHz stereo AAC), `shot_audio` (per-shot audio, silence where missing), `mute`.
- `cut_points` (manual mode): integers are frame numbers; `hh:mm:ss.ff`, `mm:ss` or `12.5s` are times.

## Install

```
pip install -r requirements.txt
```

FFmpeg and FFprobe must be on `PATH` (or set `MAJOOR_FFMPEG` / `MAJOOR_FFPROBE` to their full paths).
`scenedetect` depends on `opencv-python`; if your environment already uses `opencv-python-headless`, install with `pip install scenedetect --no-deps` and keep your OpenCV build. The pack reaches no remote server; the only request it makes is the check before a run, which asks the Ollama of this machine (localhost) which models it has.

### The SECATOR workflows (automatic edits)

The nodes above need nothing more. The workflows of `recipes/` and the SECATOR engine also use:

- **Node packs**: [comfyui-ollama](https://github.com/stavsap/comfyui-ollama) (the LLM nodes), [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) (Set / Get nodes), [comfyui-easy-use](https://github.com/yolain/ComfyUI-Easy-Use) (frees GPU memory between steps) and [comfyui_controlnet_aux](https://github.com/Fannovel16/comfyui_controlnet_aux) (the pose of the remix).
- **Ollama** running on this machine, with the vision models the workflow names: `ollama pull gemma4` and `ollama pull qwen3.8` (qwen3.8 reads the details of the pictures far better, gemma4 is faster).
- **Comfy API nodes** (MiniMax H3 for the shots, MiniMax Music for the song): you must be signed in to your Comfy account in ComfyUI.

Open a workflow, pick a preset on the Edit Mode node and press Run; if Ollama or a model is missing a message says so before anything runs.

## Status

Tested here (`python -m pytest tests`, plus `node tests/web/run.mjs` for the widgets against a fake DOM, real FFmpeg, 24 fps hard-cut fixtures): detection and manual cuts, cache and ids, selection and sampling, apply / idempotence / restore / concurrent patches, assembly with every duration and audio policy, manual order, missing media, corrupt input.

Not verified yet: execution inside a running ComfyUI (the machine used for development had no torch, so the nodes were only compiled and checked against `comfy_api.latest` source), VFR and rotated fixtures, 4K, Linux, and the preview widgets (three nodes) in a browser (written against the ComfyUI frontend 1.42 API, never run). No example workflow JSON is shipped until one has been run in ComfyUI.

Not implemented: cache TTL/purge, `.mov` beyond a container switch, `shot_audio` crossfades (by design).
