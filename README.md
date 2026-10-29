# Majoor VideoTools

ComfyUI nodes to **cut a video into identified shots, regenerate any shot with any workflow, and rebuild the video without touching the source**, plus three ready workflows for automatic edits with local models (MiniMax H3, YuE2 for the music, Gemma 4 as the LLM, FLUX.2 klein for the places, BiRefNet for the subject mask).

Des nodes ComfyUI pour découper une vidéo en shots identifiés, régénérer n'importe quel shot avec n'importe quel workflow et remonter la vidéo sans toucher à la source, et trois workflows prêts à l'emploi pour des montages automatiques avec des modèles locaux.

Category of the nodes: `Majoor/VideoTools`. Original code: MIT ([LICENSE](LICENSE)). Model weights and dependencies retain separate terms: [LICENSES.md](LICENSES.md) and [third-party notices](THIRD_PARTY_NOTICES.md).

The Studio also includes local planned-shot rendering, location-plate checks and final energy/audio reports. See [implementation and limits](docs/submission-readiness.md).

## Manual post-generation editing: Timeline Edit

Connect the final shot list to **Timeline Edit**, then its shot-list output to
**Shot Assemble**. Optionally connect music to the editor and pass its AUDIO
output to the assembler. Run once to load the takes, open the editor, then run
again to export changes. For repeated edits, **Load Shot List** avoids rerunning
the generation graph.

The first version supports ripple trim (edge handles or frame inputs), slip,
cut, reorder/drag-drop, duplicate, ripple delete, per-occurrence take selection,
undo/redo, a measured music waveform, play/pause, seek, zoom and frame steps.
The edit is saved in the workflow; source media and the generation manifest are
not modified. **It edits raw takes, not the automatic plan effects.** AI
regeneration/extension, retimed overlays and gapless proxy playback remain
planned. Browser preview may pause at source switches and is not certified
frame-perfect.

See [node help](web/docs/MajoorTimelineEdit.md), the
[implementation checklist](docs/notes/timeline-edit-implementation.md) and a
[portable API wiring example](examples/timeline_edit.api.json). Replace both
example project IDs with a real project with retained music; without music,
remove node 2 and the `music` connections. For matching musical preview/export,
use `audio_policy=mute`, `music_fade=0`, with auto SFX and external motion layers off.

## Current Studio capabilities and roadmap — 27 October 2026

The maintained [capability matrix and checklist](ROADMAP.md) distinguishes implemented features, partial workflows, improvements and future work. Availability does not guarantee identity, action, story or musical quality in every generated result.

| Capability | Current state |
|---|---|
| Text → multi-shot video, hooks, product ads and short stories | Available; narrative/action consistency and creative quality still need review. |
| Remix and music-driven editing | Available; generated takes and editorial cuts are distinct. Music timing guides the Studio planner rather than imposing a fixed take count. |
| Up to five character/product/style/scene images | Available; describe each image's role in the prompt. No dedicated role selector or exact-first-frame guarantee. |
| Original music, shot audio and SFX | YuE2, H3 and Tone.js available; improve full-edit musical phrasing and measured sync. |
| Animated text and motion graphics | Unified HyperFrames available; style layer packs, subject-derived accent colors and numeric counters remain to finish. |
| Social formats and per-shot editing | Vertical/square/landscape, prompt edits, take selection, regeneration and re-editing available. Dedicated automatic finished-video reframe is not implemented. |
| Animated infographics | Partial: text/vector tools exist; structured charts, data-driven layouts and counters are planned. |
| UGC/talking characters | Partial: identity references, voice samples and timed H3 dialogue exist; no dedicated validated avatar workflow. |
| Faceless/narrated explainers | Partial: scenes exist; continuous narrator audio and script-driven timing remain to build. |
| Speech recognition and aligned subtitles | Not implemented in the Studio. Visual overlay reading and animated titles are not speech transcription. |
| YouTube/long-video semantic highlights | Not implemented. Existing scene detection and Remix do not choose the most meaningful passage. |
| Translation and voice-preserving dubbing | Not implemented as a dedicated workflow; EN/FR interface localization is separate. |
| Product URL / brand research | Not implemented; manual product photos and briefs are supported. |
| Selectable video backends, integrated 4K upscale, conversational agent | Planned; the maintained local video path uses H3. XHigh 1.5 MP is not 4K upscaling. |

**Recent work:** shot-local H3 prompts, clearer narrative state handoffs, furnished location plates, shared text safe areas and word timing, adaptive dense-edit planning and a fifteen-second CPU assembly check with twenty segments including three-frame inserts. The normal H3 workflow still requests at least 124 frames per generated take; twenty independent takes cost more than twenty cuts reused from fewer takes.

**Presets and experiments:** old presets were removed deliberately. Six creative auditions have local final exports; choosing the best outputs and creating new reviewed presets/demo media is still pending. Scene-illustration pre-generation was tested and set aside, so it is not part of the maintained pipeline. See the [roadmap](ROADMAP.md) for priorities, deferred experiments and release checks.

**Creative controls:** Text/Music use named fidelity/freedom levels rather than pseudo-percentages; Remix shows its actual pose-guidance range. These choices apply to new jobs, preserve manually edited briefs when changed, and do not replace the original settings of an existing take during regeneration. See the [Studio README](HyperKut%20Studio/README.md).

## Installation and current Studio finishing

For the original nodes, install this pack in ComfyUI/custom_nodes and its requirements into the **ComfyUI Python environment**. The Studio has its own Python environment and [installation guide](docs/studio-installation.md).

The current Studio uses unified HyperFrames graphics and a locally synthesized 30-sound Tone.js palette. Follow [finishing installation](docs/install-finishing.md), including Node.js 22+, FFmpeg and a suitable local browser. Animated design is enabled by default; these are not merely frontend build tools. Tone synthesis happens during explicit installation, not as an extra model call per edit.

Download locations, exact configured names and outstanding checkpoint provenance: [model inventory](docs/models-and-downloads.md). Read [model/territory licenses](LICENSES.md) before using or presenting outputs. The old visual-workflow descriptions below are not a substitute for the maintained Studio API guide.

## Start here: three workflows (`workflows/`)

Drag a file of the `workflows/` folder into ComfyUI. Each one does one job and carries three notes: **GUIDE** (the steps and the options), **DEPENDENCIES** (node packs, every model with its folder and download link) and **WIRING** (what each Set / Get name carries, what each sub-graph takes and gives). From top to bottom: CONTROLS (toggles, numbers, texts), INPUTS (up to 5 pictures, a video, a voice, a music), MODELS, the pipeline, the block of one shot, assembly. The technical steps are sub-graphs; the optional loaders are bypassed (select one and press Ctrl+B to use it).

| Workflow | You give | You get |
|---|---|---|
| **`SECATOR Remix`** | a video (the **template**: its cuts, rhythm, effects and camera stay), up to 5 pictures (REF 1 is the subject that replaces: a person, an animal, a product, kept exactly as the picture shows it), optionally one reference video, a sentence about what to replace | the same edit with your subject. Each shot is read by an LLM (up to 96 frames), its audio is heard, the H3 prompt is written, MiniMax H3 replaces the subject and keeps pose, motion and timing |
| **`SECATOR Creative Text`** | an idea, up to 5 pictures and/or one reference video, the mood of the sound | a visual plan, then YuE2 music directed by that plan and your music preferences; Music Fit selects a suitable window and the editor aligns planned accents to measured audio. H3 makes the independent takes at the chosen format/quality. Exact generated musical structure and visual fidelity need review. |
| **`SECATOR Creative Music`** | your music, an idea, up to 5 pictures and/or one reference video | an edit built on your music (a song of any length: **Music Fit** takes its strongest window, or the start you give): its beats are read, the cuts and the effects follow them |

Steps (all three): load your media and fill the controls; run once (Remix: Scene Detect cuts the video and measures its energy; Creative: the idea is enhanced, the plan and the beats are made); press **Create shots** in **Deploy Shots** (one block per shot is added below); run again.

- **Sound in the Remix** (toggles at the top): by default the soundtrack of the video is kept. **REPLACE THE SOUND** makes a new soundtrack with YuE2 (the **SOUND MOOD** are its tags, the **BPM** is given to it) and **Music Fit** cuts its strongest window to the length of the video; the cuts of the template stay where they are, so the music fits the pace, not each cut. A video **without sound** gets a new soundtrack by itself. **VOICE ON** (+ a VOICE sample and the DIALOGUE): H3 speaks the lines in that voice and the shots keep their own audio.
- **Format and quality** (Creative): **FORMAT AND QUALITY** uses Resolution Selector, with dimensions aligned to multiples of 32. Studio settings are Draft 0.35 MP (often called 0.4 MP in auditions), Standard 0.6 MP, Max 0.98 MP (about 1 MP) and XHigh 1.5 MP. XHigh is an above-baseline generation option with higher memory/runtime demands, not a 4K upscaler or a quality guarantee. Native visual-workflow quality controls retain their configured defaults; in Remix source geometry and the quality cap also affect the result.
- **Effects on the beat** (Creative): **CREATE TIMELINE** snaps the cuts of the plan, and the cuts inside a shot where the zoom punches, flips, flashes and speed ramps start, to the half beats of the music (`cut_snap = half_beat`, with the kick-following grid of **Music Fit** and Create Timeline). Measured on a 13.5 s edit at 159 BPM: 24 cut points, median distance to the nearest half beat 0.045 s without it (the 0.19 s between two half beats makes 0.047 s what chance gives) and 0.009 s with it, all of them within 0.02 s.
- **Sound of the shots, sound effects, bad takes** (Creative): **SOUND DESIGN** keeps the sound that H3 makes with each shot (ambiences, foley, hits) and mixes it with the music, which gives way to it (**Shot Assemble** `shot_volume`, `duck_music`); **SOUND EFFECTS** (`auto_sfx`, also in Remix, off by default) uses the installed Tone.js palette under actual cuts/transitions, with the historical six-sound fallback when no bank is installed (see [sound-design setup](docs/tone-sound-design.md)); **RETRY BAD TAKES** checks every take with **Take Check** and generates it again once, with another seed, when it is black, white or only noise. **SUBJECT MASK FRAMES** (96) sets how many frames BiRefNet reads for the contour, which glides between two masks and is blurred a little instead of trembling.
- **Switches** (all three workflows): **EFFECTS** (the zoom, speed, flip, look, transitions and sub-cuts of the plan; in Remix the flashes, shakes and punch-ins measured on the template), **TEXT** (Creative: the planner stops writing text and Shot Assemble draws none; its new `text` input), and **MOTION GRAPHICS ON** (the node does not run when it is off). **SUBJECT MASK** only matters for the layers that use the subject.
- **Creative**: the **profile** of `Skill · timeline_planner` is the style (`viral_aura_farming` by default; `glow_up`, `outfit_change`, `beauty_premium`, `product_advertising`, `narrative_cinematic`, `music_video`); **CAMERA LOOK** takes one of the looks of the note beside it; **PLACES** gives every shot a place and the empty plate of that place as a reference (see below); a **reference video** gives H3 its motion and camera and makes the enhancer end with the TRICK of the video (the one device that makes it work).
- **Remix, several people** (a lineup of looks, clones, cut-outs, faded copies): given the source frames as its reference video, H3 tends to replace one person only. The reader counts the people (`GROUP: no` is the only answer that keeps the source frames: a missing line counts as a group), and every shot with more than one person is redrawn from its pose map and the prompt (`[reference generation]`): every person becomes REF 1, with the outfit of its position when WHAT TO REPLACE says that the outfits come from the shot (an outfit check, a lookbook; the GUIDE note of the workflow has an example prompt). The cost: the graphics and the background of such a shot are redrawn, not kept. **POSE ONLY** forces this for every shot; **POSE STRENGTH** is 0.9 by default (the pose is the only thing that holds the positions in that mode).
- **Remix, cuts**: a shot must be ONE continuous scene for H3, and at least 5 frames long (a shot under 5 frames keeps its original take). The workflow starts at `sensitivity` 0.5 (adaptive); if a generated take mixes several scenes or leaves part of the original subject, raise it (0.1 merges quick cuts; 0.9 also splits on fast motion). The shot ids of Deploy Shots are those of the shot list; the `rhythm_text` groups the shortest cuts into one shot, so its numbering can differ: read the ids in Scene Detect & Split, not in the text.
- **Text of the video**: **REDRAW THE TEXT OF THE VIDEO** (Remix) reads the titles and frames of the template and draws them again, animated, with the Motion Graphics node (below); the Creative workflows have a **MOTION GRAPHICS** control for your own layers.
- **Remix options**: REF 2-5, REF VIDEO, QUALITY CHECK (a judge compares each take with REF 1 and a failed take is generated once more with the fault in the prompt). A shot with nothing to replace keeps its original take and H3 does not run for it.
- The three files are also in `recipes/`: Deploy Shots copies their `SHOT_001` block.
- Not run end to end with H3 on the development machine yet (see Status).

## How the pack works

```
Load Video → Scene Detect & Split → Select Shot ─┬─ video / images → (your generator, VLM, API…) ─┐
                    │                            └─ metadata ─────────────────────────────────────┤
                    └─ shot_list ─────────────────────────────────────────────────────→ Apply Shot Metadata → Shot Assemble → Video
```

**Create Timeline** builds the same `shot_list` without footage, to use as a template, from a JSON edit plan (`source = json`), from the bars and beats of a music (`music`) or from the cuts of a reference video (`video`). Each shot of the template is a color card in a generated video (with the brief of the shot written on it, see `card_text`), optionally with the music as its audio. Take every shot with **Select Shot** (its `prompt`, `image_prompt`, `generation_frames` and `location` outputs feed a generator), regenerate it, put it back with **Apply Shot Metadata**, and rebuild with **Shot Assemble**. Effects (cuts inside a take, speed, zoom, transitions, text) are written in the plan and rendered by Shot Assemble. Shots still holding their placeholder make Shot Assemble stop, unless `missing_shot_policy` is `use_original` (the card is kept, for an animatic).

| Node | Role | Main outputs |
|---|---|---|
| **Scene Detect & Split** | PySceneDetect (adaptive / content / threshold_fade) or manual `cut_points`; `energy` measures the flashes, shakes and punch-ins and cleans the cuts. Writes a manifest, no clip is encoded. | `shot_list`, `rhythm_text`, `skeleton_json`, `shot_count` |
| **Select Shot** | Pick a shot by `shot_id` (or `index`) and a take. The clip is cut frame-accurately on first use and cached. | `video`, `images`, `metadata`, `prompt`, `image_prompt`, `generation_frames`, `generation_seconds`, `fx_json`, `rhythm_text`, `notes`, `location` |
| **Apply Shot Metadata** | Stores a generated video as a new take of the shot. Returns a new list; earlier lists and takes are kept. | `updated_shot_list` |
| **Shot Assemble** | Rebuilds the video from the active take of every shot (original order or `manual_order`). `effects` and `sub_cuts` switch the effects of a plan; `audio_policy` (`source_master`, `shot_audio`, `mute`), `music` and `sfx` (mixed over it), `replace_source_audio` and `voice_shots` (two toggles that override the policy). | `video` |
| **Create Timeline** | The template without footage (above); `skeleton_json` keeps the rhythm of another plan and takes only the prompts and effects of the LLM; `width` and `height` (optional, 0 = off) give the size in pixels of the placeholder video instead of `aspect_ratio` and `resolution`: connect ComfyUI's **Resolution Selector**. **Edit Skills** has the same two inputs and then names the closest ratio in the prompt. | `shot_list`, `plan_json`, `rhythm_text`, `shot_count` |
| **Cut Markers** | A timeline editor for the rhythm of an edit (below). | `plan_json`, `rhythm_text`, `shot_count` |
| **Take Check** | Looks at a generated take (eight frames): black or white from start to end, or only noise, is bad; a dark, busy or still shot is not, and a smeared face is not caught (the judge of the Remix is for that). The Creative workflows generate a bad take again once. | `ok`, `report` |
| **Music Fit** | Cuts a long music to the length of the edit, on its bars: the window starts on a downbeat, on the strongest part (a drop) unless `start` says otherwise; a music that is too short is looped by whole bars. | `music`, `info` |
| **Audio Rhythm** | The kicks, snares and hi-hats of a music, shot by shot, in the `rhythm_text`, so that the LLM puts the strong moves on the kick and snare. | `rhythm_text`, `hits_json` |
| **Music Brief** | Reads the JSON of a `music_brief_*` skill: the caption, the tempo, the length and the lyrics for a music model. | `music_prompt`, `bpm`, `duration`, `sfx_json`, `lyrics` |
| **Edit Skills** | Loads a skill (a system prompt of `skills/`), switches its parts, writes the user message and the numbered pictures (below). | `system_prompt`, `user_message`, `info`, `images` |
| **Deploy Shots** | One block per shot, from a recipe (below). | |
| **Edit Mode** | One controller for the whole graph of the older single-engine workflows (below). | |
| **Get Video Components Advanced** | Get Video Components with the size, length, frame count and fps as numbers, a choice of frames (`0-10, 24`, `~8`) and `has_audio`; `load_images` off reads only the numbers. | `video`, `width`, `height`, `duration`, `fps`, `frame_count`, `images`, `audio`, `frame_indices`, `has_audio` |
| **Load Video Advanced** | Load a video, trim it in time, crop it, keep only chosen frames. | `VIDEO`, `images`, `frame_indices` |
| **Select Every N Frames** | One frame out of N, or `max_frames` spread from the first to the last frame, for a model that reads a few pictures. | `images`, `frame_indices` |
| **Motion Graphics** | Animated texts, boxes, corner brackets, emojis, glitch / chromatic aberration / grid / dots effects, an outline around the subject and points that track something, drawn over a video from a JSON list of layers (below); the video is encoded again with its own audio. Optional `mask` input (the subject). | `video`, `info` |
| **Preview Video** / **Compare Video** | Previews with ComfyUI's own player; Compare plays two videos in sync (wipe or side by side). | |

## Create Timeline and the plan

```json
{ "fps": 24, "aspect_ratio": "9:16",
  "locations": { "L1": "a zinc rooftop terrace in Paris at dusk, string lights" },
  "shots": [ { "id": "SHOT_001", "duration": 2.5, "location": "L1", "prompt": "…", "image_prompt": "…", "notes": "…", "color": "yellow",
               "layers": [ { "layout": "left", "color": "#2255ff" }, { "rect": [0.55, 0.1, 0.35, 0.5], "color": "red", "opacity": 0.6 } ] },
             { "duration": "60f", "prompt": "…" }, { "duration": "00:03.5", "prompt": "…" } ] }
```

- **`source = music`**: connect `music`; the node detects the tempo and puts a cut on every `cut_every` (`half_beat`, `beat`, `2_beats`, `bar`, `2_bars`, `4_bars`) from the first beat. `duration` (0 = the whole music), `shots` (0 = one shot per grid step, otherwise that many with their cuts spread over the grid), `bpm` (0 = detect), `beats_per_bar` and `downbeat` (the tempo is detected, the bars are not: shift the first bar by hand). The music is the audio of the template.
- **`source = video`**: connect `video`; its cuts are detected (PySceneDetect, like Scene Detect & Split) and become the rhythm of the template. Each shot is generated once, so cuts in a row shorter than `min_shot_seconds` are grouped into one shot whose original cuts are its `sub_cuts`: a 15 s reference with 80 cuts gives about 10 shots that cut like the reference. `fps` and `aspect_ratio` follow the video when left on auto.
- **`source = none`**: no rhythm (empty `plan_json` and `rhythm_text`), to let the LLM decide in a workflow that switches between music, video and nothing. With `source = video` and a music connected, `cut_snap` moves the cuts of the video to its beats.
- **`skeleton_json`** (input, with `source = json`): the `plan_json` of another Create Timeline (music or video). Its shots, durations and the cuts inside them are kept; the plan of the LLM only brings the prompts and the effects, matched by shot id (or position), its sub-cuts by position. The LLM may leave every duration out. Language models are poor at adding up durations: this is how a rhythm taken from a reference is applied reliably.
- With `source = json`, the prompts of the plan are cleaned of negative boilerplate ("One continuous take, no cuts, no text."): it contradicts the sub-cuts. Descriptions of the role, the cuts, the framing and the transitions are kept.
- Outputs besides `shot_list`: `plan_json` (the plan that was built, to read, edit or save) and `rhythm_text` (the rhythm in words: shot ids, durations, cuts inside each shot), to hand to the LLM that writes the prompts.
- `duration` is seconds, `"60f"` frames or a timecode; Markdown fences around the JSON are accepted.
- Cards: `color` per shot (a CSS name such as `"yellow"` or `"#ffd400"`; without it, a distinct color per shot), and `layers` drawn over it in order, for split screens and inset cards: `{"layout": "left", "color": "#2255ff", "opacity": 1}`, with `layout` one of `full, left, right, top, bottom, top_left, top_right, bottom_left, bottom_right, center, pip`, or `"rect": [x, y, width, height]` as fractions of the frame. With `card_text` (on by default) each card shows the brief of its shot: id, place and length, role, transition, cuts, effects and the whole prompt, wrapped and shrunk to fit. Turn `card_text` off for plain cards, which are clean layout references for Select Shot's `images`.
- `generation_profile = minimax_h3` computes the frames to request per shot (at least 124, on the 17k+5 grid) and puts it in `generation_frames`.
- With `music`, `cut_snap` moves each cut to the nearest half beat, beat or bar (tempo detected, or `bpm`), keeping shots at least 6 frames long; the music is the template's audio, kept by `audio_policy = source_master`.
- Select Shot's `start_from_previous` makes `images` the last frame of the previous shot's active take, to continue from it: generate the shots one after the other.
- To have an LLM write the JSON (from a picture, a music description or just a brief), use the skills of **Edit Skills** (below). `examples/timeline_fashion_motion.json` is a valid 8 s plan with 20 cuts, `examples/timeline_aura_farming.json` a 15 s one with one long cut per shot, `examples/dynamic_edit_product_ad.json` a product ad; `examples/prompts/` holds the prompts as text files.

### Dynamic edits

A shot is generated once, but it can be cut into many pieces and styled in post, all rendered by Shot Assemble on the generated takes (the placeholder cards stay plain). Per shot, and again per sub-cut where it overrides the shot:

- `sub_cuts`: `[{"duration": 0.25, "start": 1.0, "zoom": 1.9, "focus": [0.5, 0.2], "flip": true, "speed": 2, "look": "mono", "transition": "whip"}, ...]`: several cuts out of ONE take; with no shot `duration`, the sub-cuts make it; at least 3 frames each; the cuts keep the proportions of the plan and snap to half beats when `cut_snap` is on.
- `zoom` (1 to 4, or `[from, to]`) with `focus` `[x, y]` · `flip` · `speed` (0.1 to 8) or `speed_ramp` `[from, to]` · `look` (`mono`, `contrast`, `negative`).
- `transition` into the shot: `flash`, `flash_black`, `fade_black`, `fade_white`, `whip`, `whip_v`, `blur`, `punch`, `glitch`, `shake`, `strobe`, `invert` (an unknown name is a plain cut; or `{"type": "whip", "frames": 5}`).
- `text` `{"content", "position", "size", "color", "background", "repeat", "rotate"}` drawn over the whole shot (rendered with Pillow, font `impact.ttf` / `arialbd.ttf` or `MAJOOR_FONT`).
- `overlay` (a surimpression): a list of up to 3 layers `{"source": "self" | a shot id, "offset": seconds, "opacity": 0-1, "blend": normal|screen|multiply|overlay|add|lighten|darken|difference|softlight, "scale": 0.1-1, "position": ..., "zoom", "focus", "flip", "look"}`; `scale` below 1 makes a picture in picture.
- `split` (a split screen): `{"layout": left_right|top_bottom|columns_3|rows_3|grid_4, "panels": [{"source": "self" | a shot id, "offset", "zoom", "focus", "flip", "look"}, ...]}`, one panel per cell (missing panels show the shot).
- `refs` `[1, 2]`: the pictures a shot shows, passed on in `fx_json` for workflows with several references. `location` is the id of the place of a shot (see Location plates).
- `overlay` and `split` work on the shot or on a sub-cut (`"split": null` turns the shot's value off for one cut). A `source` other than `self` is a shot of the same plan: its generated take is read at the same moment (shifted by `offset`); while that shot has no take, the shot itself stands in and Shot Assemble warns. They cost no generation. An unknown shot id is replaced by `self` when the timeline is created, with a warning.
- A `punch` transition and the zoom filters need a take; shots that keep their placeholder, or takes that use `keep_generated`, ignore the effects. `cut_snap = half_beat` snaps top-level cuts to the beat and the offbeats; the sub-cuts always snap to half beats.

Select Shot also tells what a shot of a timeline plan asks of the edit: `fx_json` (its transition, the cuts inside it with their lengths in seconds and effects, speed, zoom, look, text) and `rhythm_text` (the same in words: `transition in: flash (4 frames)`, `cuts (4): 0.25s / 0.25s (zoom 2, flip) / ...`). They are not sent to the generator by default (a shot is one take, the cuts and transitions are made when assembling): the skills read them, or use them to write your own prompt.

## Text and motion design: Motion Graphics

Generated footage is intended to stay free of editorial text. **Motion Graphics** adds titles and graphic frames after assembly through the shared HyperFrames renderer, from layers such as `text`, `box`, `brackets`, vectors and effects. `start`/`end` may be seconds or percentages; shot-local layers stay within their own shot. Text animations include `words` (masked word-by-word reveal), `typewriter`, fades and slides; `out: "fade"` handles the exit. Dedicated animated numeric counters are not yet implemented. Visual overlay reading can recover text from a reference, but it is not speech transcription or a guarantee of exact source-graphics reconstruction.

```json
[{"type": "text", "content": "WHICH ONE?", "position": "top_left", "size": 0.07, "color": "#111111", "start": "5%", "end": "40%", "animation": "typewriter", "out": "fade"},
 {"type": "brackets", "rect": [0.2, 0.25, 0.3, 0.55], "color": "#d11a1a", "start": "35%", "animation": "draw"},
 {"type": "box", "rect": [0, 0.9, 1, 0.1], "color": "#000000", "opacity": 0.6, "animation": "slide_up"}]
```

Four more kinds of layer, for the look of a motion-design edit:

```json
[{"type": "outline", "color": "#ffffff", "width": 0.006, "style": "neon", "glow": 0.6},
 {"type": "effect", "kind": "chromatic", "amount": 0.6, "start": 1.2, "end": 1.6},
 {"type": "effect", "kind": "grid", "target": "background", "color": "#00ff88", "spacing": 0.08, "amount": 0.7},
 {"type": "emoji", "content": "🔥", "position": "top_right", "size": 0.12, "animation": "pop"},
 {"type": "track", "anchor": "subject_top", "label": "LOOK 06", "emoji": "👀", "shape": "ring", "line": true},
 {"type": "track", "at": [0.5, 0.4], "label": "this", "shape": "cross"}]
```

- `outline`: a contour drawn around the subject (`style` `solid`, `double`, `dashed`, `neon`; `width`, `glow`). **Needs the `mask` input**: any segmentation node gives it (the core *Remove Background* with the BiRefNet model, or SAM 3).
- `effect`: `kind` `chromatic` (red and blue channels pulled apart), `glitch` (bands shifted, channels split), `grid`, `dots`, `scanlines` (`color`, `spacing`, `thickness`, `radius`, `speed`, `flicker` blinks per second); `target` `frame` (default), `subject` or `background` (these two need the mask); `amount` is the strength.
- `emoji`: a color emoji drawn like a text (`content`, `position` or `x` / `y`, `size`, `rotate`, any animation). It needs a color emoji font: Segoe UI Emoji on Windows, Noto Color Emoji or Apple Color Emoji elsewhere, or the path of one in the environment variable `MAJOOR_EMOJI_FONT`.
- `track`: a point that follows something, with an optional `label` and `emoji` joined to it by a line (`line`, `offset`). `at: [x, y]` is followed from frame to frame by optical flow (a spot of the picture: a bag, a shoe); `anchor` (`subject_top`, `subject_center`, `subject_bottom`, `subject_left`, `subject_right`) follows the mask of the subject (needs the `mask` input). `shape` `dot`, `ring`, `cross`, `none`.

A text takes `content`, `position` (`center`, `top`, `bottom`, `left`, `right`, `top_left`...) or `x` / `y`, `size` (the height of the text as a fraction of the height of the frame), `color`, `background`, `stroke`, `rotate`; a box and brackets take `rect` `[x, y, width, height]` as fractions of the frame, `color`, `thickness`; every layer takes `opacity` and `in_time`. A value out of range is brought into range and an unknown animation becomes `none`; an empty list gives the video back untouched. The node draws with Pillow and encodes with FFmpeg: **no other pack and no browser are needed**. The result is cached by the video and the layers (`output/MajoorVideoTools/motion/`).

**Reading the text of a video**: the skill `overlay_reader` looks at 24 or so frames of the source and writes the layers (the words as written, the color, the size, the place, the start and the end, the animation: letters that appear one after the other are one `typewriter` text). The Remix workflow does this when **REDRAW THE TEXT OF THE VIDEO** is on. Measured on an outfit-check edit (Gemma 4 12B): the words and the order are right (OUTFIT CHECK, WHICH ONE?, THIS ONE, OBVIOUSLY...), the times are in steps of half a second, and a word typed letter by letter sometimes comes out as several captions. Shots that were kept as they are already carry their text, which is then drawn twice.

**HyperFrames?** [HyperFrames](https://github.com/heygen-com/hyperframes) (HeyGen, Apache-2.0) renders HTML, CSS and GSAP / Lottie / Three.js animations to MP4 through headless Chrome (Puppeteer) and FFmpeg: it is the tool for rich motion design written as web pages, and it needs Node and a Chrome. It is not needed for text, boxes, brackets and these animations, which this node does alone; it would be worth adding as an optional second engine for layouts that Pillow cannot draw (gradients, charts, 3D, Lottie).

## The energy of a video

A generated take comes back calmer than the footage it replaces: its flashes, shake bursts and punch-ins are lost. **Scene Detect & Split** with `energy = events` (or `events_and_camera`) reads a small gray copy of every frame and measures them (`core/energy.py`: the mean luma for the flashes, white or black; the global motion between two frames, by optical flow, for the shakes, the punch-ins, the whips and, with `events_and_camera`, the slow push of the camera). Two things follow:

- **A flash is not a cut**: the cuts that a detector puts on the frames of a flash are dropped when the picture is the same around it.
- What each shot did becomes its `fx` (a transition into the shot, sub-cuts with a transition at each event, a zoom for the push), and **Shot Assemble** puts it on the generated take; a shot kept as it is does not get it. The skill `remix_shot_prompt` never describes these effects: they are made when assembling.

## Sound, voice and dialogue

- **Music brief and soundtrack** (including historical experimental recipes): the skills `music_brief_minimax3`, `music_brief_yue2` and `music_brief_from_plan` write the brief of a music model from a mood, a length and the rhythm of the cuts; **Music Brief** reads their JSON. MiniMax Music 3 fills the length it is asked for (5 s gives 4.99 s, 12 s gives 11.99 s) and follows a tempo loosely.
- **Sync on the beats**: **Create Timeline** `source = music` cuts on the bars and beats; **Audio Rhythm** describes the kick, snare and hi-hat under each shot so the planner puts the strong moves on them. Music first, then the cuts: this is how the Creative workflows sync. The phase of the beat grid follows the kick (the low band), not the hi-hats and claps on the off-beat. The maintained workflows generate a YuE2 score and audio, allow duration headroom, then let **Music Fit** select the strongest matching window. Tempo and event timing are measured from the actual waveform; a requested BPM or accent is not a guarantee of sample-accurate output.
- **Voice and dialogue**: the `voice` input of **Edit Skills** (a voice sample, H3 `ref_audio_0`, `<Audio 1>` in the prompt) and the `dialogue` text (`0-3 s: "Welcome."`, one line per line). A shot gets the lines that start inside it (`core/dialogue.py`), with their times counted from its start; H3 speaks them. A deep sample gives a deep voice, but the timbre follows the sample only in part (measured).
- **Shot Assemble**: `audio_policy` `source_master` (the soundtrack of the source, 48 kHz stereo AAC), `shot_audio` (the audio of each shot, silence where missing) or `mute`; `music` and `sfx` are mixed over it (cut or padded to the edit, fading out); `replace_source_audio` mutes the source so that the music is the only audio; `voice_shots` uses the audio each shot comes with (the voice).
- Sound effects: generate them with MMAudio / Foley on the assembled edit and connect them to `sfx`.

## Edit Skills and the skills

**Edit Skills** loads a system prompt from the `skills/` folder of the pack and gives it to your LLM node (`system_prompt`), with a `user_message` made of your `brief`, the numbered pictures (`<Picture N>`), the frames of up to two videos (`<Video 1>`, `<Video 2>`: the message says which images of the chat they are), the voice (`<Audio 1>`), the dialogue and the `rhythm_text`. `images` outputs the pictures then the video frames in that order: connect it to the LLM. Numbers go by presence, as H3 numbers its references, so a picture that is not connected does not leave a gap. The switches (`overlays_splits`, `text_overlays`, `reference_mode`, `genre`, `locations`) take parts out of the prompt, so that a small model reads less; `duration`, `fps`, `aspect_ratio` and `text_allowed` are written into it; a `profile` (a style: rhythm, camera, art direction) and its dials (`cut_density`, `transition_intensity`, `creative_freedom`, `reference_fidelity`, `narrative_coherence`) are added at the end. The optional `plate` input is a place (below).

To add a skill, drop a `.md` file in `skills/` (header `name`, `kind`, `description`; parts between `<<module name>>` and `<<end>>`, `default=off` for a part that is off unless a setting asks for it; variables like `{{DURATION}}`) and press Reload skills. The `examples/prompts/` copies of three skills are kept identical by a test.

| Skill | Kind | What it does |
|---|---|---|
| `timeline_planner` | planner | The plan of an edit from pictures and a brief, or the prompts and effects on a given EDIT RHYTHM; with `locations` a place per shot |
| `dynamic_edit_skill` | planner | The whole plan for any dynamic video (character, product ad, motion graphics, UGC, trailer), optionally from the frames of a reference edit |
| `h3_shot_prompt_from_plan` | h3_writer | The MiniMax H3 prompt of one shot of a plan, in the full-reference format (`<Subject N>`, `[Shot N]`); modules for a voice, a dialogue and a place |
| `remix_shot_prompt` | h3_writer | The H3 prompt of a remix shot from its reading, its sound, the pictures and the request: only what is asked changes |
| `shot_reader` | analyzer | What the frames of a shot show, and `REPLACE: yes / no` (a shot with nothing to replace keeps its take) |
| `clip_judge` | analyzer | PASS or FAIL for a generated take against the picture of the subject and the prompt |
| `overlay_reader` | analyzer | The overlays of a video (titles, words that appear, counters, frames) as the layers of Motion Graphics |
| `prompt_enhancer` | other | The few words of the user, the pictures and the frames of the videos become a richer brief |
| `music_brief_minimax3`, `music_brief_yue2`, `music_brief_from_plan` | music_writer | The brief for MiniMax Music 3, YuE2, or YuE2 and others (BPM, structure, sound effects) |
| `profile_*` (7) | profile | The styles: `beauty_premium`, `glow_up`, `music_video`, `narrative_cinematic`, `outfit_change`, `product_advertising`, `viral_aura_farming` |
| `mode_creative`, `mode_remix_replace` | mode | The settings of the two modes of Edit Mode |

In every skill, the subject of `<Picture 1>` (a person, an animal, a product, an object) is preserved as the picture shows it and changed only when the brief says so. The LLM is ComfyUI's *Generate Text* with a Gemma 4 text encoder; one skill per call, never all at once (measured: a small model finds fewer facts when several tasks share a call).

## Location plates

With `locations` on, the planner gives each shot a `location` id and describes each distinct place once in `locations`: architecture, materials, lighting AND useful fixed furniture, objects, lamps and mounted artwork, with relevant placement. FLUX.2 klein 4B generates an **unoccupied, set-dressed plate**, not necessarily a bare room (configured branch: 720 x 1280, 4 steps). ComfyUI can reuse the plate for the same description. A visual check rejects actual people or uncertain images; clearly mounted printed artwork is allowed as set dressing. This check is fallible. The plate reaches H3 as an environment reference; the shot writer names relevant set elements and preserves their placement while actor identity comes from its own photo. Movable/action props follow the current shot state rather than resetting to the cached plate. This existing optional PLACES branch is distinct from the abandoned scene-illustration pre-generation experiment.

## Cut Markers

A timeline editor for the rhythm of an edit. Connect a `video` and/or a `music` (both optional), run the node once to load them in the editor, then place the cuts by hand over the waveform of the music, its beats and the cuts detected in the video:

- click or drag on the timeline = move the playhead (the video and the music follow); `Space` plays and pauses;
- double-click, `M` or **+ marker** adds a marker at the playhead; drag a marker to move it; right-click or `Delete` removes it; `Ctrl+Z` undoes;
- markers stick to a grid chosen in the snap list (frames, half beats, beats, bars, the cuts of the video); hold `Alt` to drag without snapping;
- the wheel zooms, `Shift` + wheel pans, **Fit** shows everything;
- **Fill from…** puts markers on every half beat, beat, 2 beats, bar, 2 or 4 bars of the music, or on the cuts of the video, to correct by hand afterwards;
- under the waveform, the shots the markers will make are shown (cuts shorter than `min_shot_seconds` in a row are grouped into one shot whose cuts become sub-cuts, like Create Timeline's video source).

The markers are kept as seconds in the node's `markers` text (you can also type them: seconds `12.5`, timecodes `1:02.5` or frames `36f`). Outputs: `plan_json` (connect it to the `skeleton_json` of Create Timeline, so the LLM only writes prompts and effects), `rhythm_text`, `shot_count`. `fps` and `duration` follow the video, else the music; `bpm`, `beats_per_bar` and `downbeat` set the beat grid. With no media, set `duration` and type the markers. The editor plays a light copy of the music kept under `temp/majoor_cuts/` and the video from `temp/majoor_compare/`: after a restart of ComfyUI, run the node again to reload them.

## Deploy Shots and recipes

**Deploy Shots** builds the per-shot part of a workflow. Run **Scene Detect & Split** (or **Create Timeline**) once so its shots are known, pick a `recipe`, press **Create shots**: for every shot the graph gets a block (Select Shot, analysis, generation, Apply Shot Metadata, Compare Video...), the Apply nodes are chained one after the other, and the last one feeds **Shot Assemble** (added with a Save Video when the graph has none). Pressing it again replaces the previous deployment; a block you made by hand for one of the shots is replaced after a confirmation (`replace_existing`). `max_shots` (0 = all), `columns` (blocks per row), `include_finale`. Requires KJNodes (Set / Get) and the nodes used by the recipe.

- A **recipe** is a normal workflow saved in `recipes/` (a combo lists them). It holds ONE shot block: a Select Shot with `SHOT_001`, the Set / Get nodes named after it (`SHOT_001`, `SHOT_001_META`, `SHOT_001_GENERATED`...) and whatever is wired to them (sub-graphs included, flat or not). Everything the block shares with the rest of the graph goes through KJNodes Set / Get nodes (`REF1`, `SHOT_LIST`, `LLM`, `MODEL_*`...), through sub-graph inputs, or through a node outside the block that all shots read (an edit-request text): that node is created once and reused. Save Video nodes are not part of a block (the last Apply feeds the final one).
- The name of a block comes from its Set / Get nodes (`SHOT_001` in `SHOT_001_META`): the `shot_id` of the Select Shot of a recipe can be left on any shot. Every group around the Select Shot is copied (a group inside a group too), a Reroute is only a wire.
- In the copy of a block every `SHOT_001` becomes the new shot id (nodes, titles, Set / Get names, sub-graph names), every sub-graph definition gets its own id, and Select Shot gets its `shot_id` and `index`. The Set nodes the Get nodes of the recipe need (`REF1`, `LLM`, `MODEL_FULL`...) must exist in the graph; the report lists the missing ones. The `noise_seed` of a node that has it in `widgets_values_named` moves by the number of the shot, so that no two shots move alike.
- To make your own recipe: build the block for one shot as you would by hand, with `SHOT_001`, save the workflow into `recipes/`, reload the page. The first Apply Shot Metadata starts from the shot list; the following ones are chained by the node. Blocks that read `prompt`, `image_prompt`, `location` and `generation_frames` of Select Shot work the same way for plan-based shots (Create Timeline).
- Six recipes ship: **`SECATOR Remix`**, **`SECATOR Creative Text`** and **`SECATOR Creative Music`** (the blocks of the three workflows) and, older, **`Minimax H3 TimelineShot Creator`** (a plan block: the brief of the shot goes through the H3 prompt writer, then H3, with a preview), **`Remix Mode Minimax H3`** and **`Text Audio & Refs Mode Minimax H3`** (the blocks of the single-engine graphs of Edit Mode). `recipe = auto` takes a recipe of kind `plan` when the shots come with prompts, of kind `video` otherwise (the highest `priority` wins). A recipe says it with `extra.majoor_recipe` in its workflow: `{"title": ..., "kind": "plan" | "video", "priority": 10}`; without it, a name ending with `_plan` means plan.

## Edit Mode (one graph, two modes)

The workflows above need no controller. **Edit Mode** is the older way, for a single graph that does both jobs: pick `creative` or `remix_replace` and a style, and the nodes tagged for each mode are enabled or bypassed (`properties.majoor_mode`: `modes`, `toggle`, `any`, `unless`, `values`, plus tags for the planner, the enhancer, the profile, the request and the pose), the rhythm source and the shot-list switch are set, and the planner gets the profile, genre and instructions of the mode (`skills/mode_*.md`, applied by `web/majoor_mode.js`). Options: `from_video`, `ref_video`, `own_music`, `voice`, `camera` (one of eight looks: `digital_cinema`, `film_70mm`, `film_16mm`, `anamorphic`, `vintage_70s`, `portrait_bokeh`, `macro_detail`, `ultra_wide`), `quality_check`, REF 2-5, the pose control, the pose strength and the replacement instruction. Queueing such a graph first names a node pack that is missing.

## Katana-style edits with ComfyUI

Higgsfield's **Katana** is a skill for Claude (through the Higgsfield MCP connector) that takes a reference edit and photos of your people or products and rebuilds the edit with your subjects. The same kind of result, locally, with this pack:

1. **Rebuild a reference edit with new subjects**: the `SECATOR Remix` workflow (above), or by hand: `Load Video` → **Scene Detect & Split** → a vision model reads the frames of each shot (`shot_reader`) and rewrites it for your subject (`remix_shot_prompt`; subject from `<Picture 1>`, motion and camera from the reference video) → MiniMax H3 Ref2VA with the shot as motion reference → **Apply Shot Metadata** → **Shot Assemble** with `audio_policy = source_master`, so the cuts and the soundtrack of the reference stay.
2. **Make a new dynamic edit from a brief, pictures and a rhythm**: the `SECATOR Creative Text` / `Creative Music` workflows, or by hand: **Cut Markers** or **Create Timeline** (`source = music` or `video`) give the rhythm skeleton; an LLM with `timeline_planner` or `dynamic_edit_skill` writes the prompts, cuts and effects (zooms, transitions, text, overlays, split screens); **Create Timeline** `source = json` with `skeleton_json` applies it; **Deploy Shots** generates the shots; **Shot Assemble** renders the edit on the music.
3. **Rebuild the effects of a reference too**: give the frames of the reference (labelled with their time) to `dynamic_edit_skill`, "MODE B": it describes the framing, the speed, the transitions, the overlays and the split screens of each cut and writes the same structure for your subject. With `energy` on, Scene Detect already measures the flashes, shakes and punch-ins.

Corrections: change the prompt of one shot and run again, only that shot is generated again (ComfyUI keeps the others); effects, cuts, overlays and split screens are changed in the plan and re-rendered by Shot Assemble without any generation.

## Previews in the nodes

After a run, **Scene Detect & Split** shows the source video with a timeline of the detected shots (click a segment to jump to it), **Shot Assemble** adds a timeline of the final shot order under ComfyUI's own video preview (replaced shots in orange); click a shot and press Regenerate to give a new seed to its generation block and queue the graph (only that shot is generated again, the rest comes from ComfyUI's cache), and **Select Shot** shows a filmstrip of the connected list: click a shot to fill `shot_id`, and the shot plays in the node (the source, until the node has run). The last result is saved with the workflow. **Compare Video** reads what is connected to it without running the graph (a Load Video file, a Select Shot clip, or the last output of any upstream node that has a video preview) and updates when the connection or the upstream file changes; otherwise it shows the result of the last run. **Preview Video** previews a `VIDEO` or an `IMAGE` batch (with its `fps`) with optional `AUDIO`, with ComfyUI's own preview; nothing is written to the output folder. The widgets live in `web/` and are optional; the nodes work the same through the API.

## Behaviour worth knowing

- **Not destructive.** The source is hard-linked (or copied) into the project and never modified. Takes are copied into `generated/`.
- **Projects** live in `ComfyUI/output/MajoorVideoTools/<project_id>/` (`manifest.json` is the latest collection, `manifests/` keeps every version). The project id is derived from the source content and the detection settings (the `energy` setting included), so the same video with the same settings always returns the same shot ids; another sensitivity is a new collection.
- **Several shots:** chain `Select → generator → Apply` once per shot, feeding the updated list into the next `Select` (Deploy Shots does it for you).
- **Restore a take:** connect `Select Shot` (`take = original` or `revision_id`) straight into `Apply Shot Metadata` with its own `metadata`; the take is re-activated instead of duplicated. Applying the same generated file twice never creates a second take.
- **Durations.** A shot keeps its original duration by default (`trim_or_pad_last_frame`). `retime_to_target`, `trim_or_error` and `use_generated_duration` are available, and `Apply`'s `keep_generated` makes one take keep its own length. With `source_master` audio, any shot whose length changed produces a warning, because the source audio is no longer in sync after it.
- **Exports** are named `<output_name>_<hash>.mp4` and are never overwritten; an identical request reuses the existing file. Writing goes through a temporary file that is validated before it is renamed.
- `cut_points` (manual mode): integers are frame numbers; `hh:mm:ss.ff`, `mm:ss` or `12.5s` are times.
- No network access is made by this pack (the detection, the energy, the assembly and the skills are local); the models you load in the workflows run on your machine.

## Install

```
pip install -r requirements.txt
```

`requirements.txt`: `scenedetect>=0.7` (PySceneDetect, which brings OpenCV: the energy of a video needs `cv2` too) and `filelock`. NumPy and Pillow come with ComfyUI. FFmpeg and FFprobe must be on `PATH` (or set `MAJOOR_FFMPEG` / `MAJOOR_FFPROBE` to their full paths). If your environment already uses `opencv-python-headless`, install with `pip install scenedetect --no-deps` and keep your OpenCV build. ComfyUI must be recent enough to have *Generate Text*, the MiniMax H3 and YuE2 nodes and sub-graphs (the registry minimum in `pyproject.toml` is 0.41.0).

### What the workflows need

The nodes above need nothing more. The three workflows also use (each workflow lists them in its DEPENDENCIES note):

- **Node packs**: [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) (Set / Get nodes), [comfyui-easy-use](https://github.com/yolain/ComfyUI-Easy-Use) (frees GPU memory between steps, inside the H3 sub-graph) and [comfyui_controlnet_aux](https://github.com/Fannovel16/comfyui_controlnet_aux) (the pose map of H3; its pose models download on the first run).
- **Models** (all local; in `ComfyUI/models/<folder>`):

| Role | File | Folder | Download |
|---|---|---|---|
| LLM vision (reads, writes) | `gemma4_12b_int8_convrot.safetensors` | `text_encoders` | [Comfy-Org/Gemma4](https://huggingface.co/Comfy-Org/Gemma4) |
| LLM (hears, plans) | `gemma4_e4b_it_fp8_scaled.safetensors` | `text_encoders` | [Comfy-Org/Gemma4](https://huggingface.co/Comfy-Org/Gemma4) |
| H3 diffusion model | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `diffusion_models` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) |
| H3 turbo LoRA (8 steps) | `minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors` | `loras` | your local file: the repo lists `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors`; pick the one you have in the LoRA node |
| H3 text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `text_encoders` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) |
| H3 video / audio VAE | `minimax_h3_video_vae_int8_convrot.safetensors`, `minimax_h3_audio_vae_fp32.safetensors` | `vae` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) |
| H3 pose ControlNet | `minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors` | `model_patches` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) |
| Music (Remix when sound is replaced, Creative Text) | `yue2_3b_int8_convrot.safetensors` (combined model, text encoder and audio VAE) | `checkpoints` | [Comfy-Org/YuE2](https://huggingface.co/Comfy-Org/YuE2) |
| Plates (Creative) | `flux-2-klein-4b-fp8.safetensors` (Apache 2.0) | `diffusion_models` | [black-forest-labs/FLUX.2-klein-4b-fp8](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8) |
| Plates | `qwen_3_4b.safetensors`, `flux2-vae.safetensors` | `text_encoders`, `vae` | [Comfy-Org/flux2-klein](https://huggingface.co/Comfy-Org/flux2-klein) (`split_files/`) |

The file names are the ones the workflows ask for; each is picked in a loader node you can change. The LLM measurements behind the choice of the two Gemma 4 files are in the CHANGELOG (12B reads the frames best and writes the prompts faithfully but does not hear audio; E4B hears it).

## Tests and status

Run the tests with the Python that has the requirements installed (without `scenedetect` the detection tests are skipped):

```
python -m pytest tests                                   # core, plans, skills, deploy, workflows (real FFmpeg, 24 fps fixtures)
for f in tests/web/*.mjs; do node $f; done              # the widgets against a fake DOM and a fake ComfyUI app
ComfyUI/.venv/Scripts/python.exe custom_nodes/ComfyUI-Majoor-VideoTools/tests/comfy/check_schemas.py   # every schema builds
ComfyUI/.venv/Scripts/python.exe custom_nodes/ComfyUI-Majoor-VideoTools/tests/comfy/check_nodes.py     # every node on real media, inside ComfyUI
```

Checked here: detection and manual cuts, cache and ids, selection and sampling, apply / idempotence / restore / concurrent patches, assembly with every duration and audio policy, the energy of a video on a synthetic clip (flash, shake, punch, push) and on a real reference, plans with locations, skills and their modules, the three workflows (they open in the ComfyUI frontend, their API prompts are accepted by ComfyUI in the default state and with every option on, the five pictures reach the LLM and H3, Deploy Shots clones their block, no node overlaps another), the LLM reading, hearing, writing and judging steps and the H3 voice and plate tests on a GPU server (see the CHANGELOG for the measurements).

Not verified yet: a full run of the three workflows end to end with H3 (the GPU server of the development machine has to be restarted to load the newest node inputs), VFR and rotated fixtures, 4K, Linux, and the preview widgets in more than one browser.

Not implemented: cache TTL / purge, `.mov` beyond a container switch, `shot_audio` crossfades (by design).

## License

Optional finishing: **Motion Design — HyperFrames** runs after assembly. It is enabled by default in the Studio and remains optional. Prepared typography and graphics can follow the final audio; global and per-shot cues are supported. See [setup, usage and third-party licenses](docs/hyperframes.md). No additional Python dependency is required; its Node.js runtime is installed separately.

MIT for the original pack code (see [LICENSE](LICENSE)); model weights, GSAP and all other dependencies keep their own terms. See [LICENSES.md](LICENSES.md).

### Studio runtime versus visual workflow editing

The Studio API graphs use native ComfyUI nodes plus this pack and `comfyui_controlnet_aux`. KJNodes and easy-use remain dependencies of the visual workflow editor graphs (Set/Get and GPU cleanup), not of the exported Studio prompts. The active music generator is YuE2; historical experimental recipes are not maintained Studio entry points. See [the Studio installation scope](docs/studio-installation.md).

### Unified graphics renderer

Typography, legacy motion layers and HyperFrames finishing share one local HyperFrames compositor. BiRefNet is requested only for subject-dependent effects. Existing Motion Graphics nodes are compatibility adapters. See [architecture and mask behavior](docs/unified-renderer.md).

Optional style packs, subject-color accents, sound palettes and internal delivery checks are described in [finishing options](docs/finishing-options.md). They preserve existing layer arrays and do not add a technical panel or a new generation engine.

The video application is branded **HyperKut (HK)**. Legacy Studio directory, workflow filenames and `SECATOR_*` variables remain compatible; new environment variables use `HYPERKUT_*`.
