# Majoor VideoTools

**ComfyUI nodes for shot-based video generation and editing.** Split footage into identified shots, keep generated takes, refine the montage and assemble the result. This pack is the engine companion to [HyperKut Studio](https://github.com/MajoorWaldi/HyperKut-Studio), a separate local **beta** application.

Original pack code: **MIT**. Models, dependencies and media keep their own terms: [licenses](LICENSES.md) · [third-party notices](THIRD_PARTY_NOTICES.md).

## What it provides

| Stage | Tools |
|---|---|
| Analyze | Scene detection, shot identifiers, source sampling and audio/rhythm information. |
| Generate | Select a shot, use a chosen workflow, apply its metadata and retain takes. |
| Edit | Shared Timeline Edit panel with frame-based trim/slip, cuts, reorder, duplication, take selection and undo/redo. |
| Assemble | Rebuild from retained takes, selected timing and audio policy. |
| Experimental finishing | Unified HyperFrames text/graphics/effects and optional Tone-generated sound cues. |

The generation model is not called by ordinary manual montage gestures. Assembly/rendering still uses local compute. Generated identity, motion and narrative quality require visual review.

## Installation

Install this folder under `ComfyUI/custom_nodes/ComfyUI-Majoor-VideoTools`, then install `requirements.txt` using **ComfyUI's Python environment** and restart ComfyUI when no job is active. FFmpeg and ffprobe must be available on PATH.

For HyperKut's maintained API graphs, use recent native ComfyUI model nodes and `comfyui_controlnet_aux`. KJNodes and Easy-Use are additional visual-workflow editing dependencies. Model weights are downloaded separately; see [configured filenames and sources](docs/models-and-downloads.md).

Optional: `pip install faster-whisper` (or `pip install .[transcribe]`) in ComfyUI's Python to read the words of a voice or a song. Nothing else in the pack needs it.

The Studio has its own source repository and Python environment. Keep it adjacent to the pack modules as described in [Studio installation](docs/studio-installation.md).

## Ready visual workflows

The legacy `SECATOR` prefix is retained in these filenames for compatibility; the application is called HyperKut.

| File in `workflows/` | Starting point |
|---|---|
| `SECATOR Remix.json` | Reference video and character/product images. |
| `SECATOR Creative Text.json` | Creative brief and optional references. |
| `SECATOR Creative Music.json` | Supplied music, brief and references. |

Open a workflow in ComfyUI and read its GUIDE, DEPENDENCIES and WIRING notes. Visual workflows and the Studio's exported API graphs are distinct entry points; their saved defaults can differ. The maintained Studio video path uses MiniMax H3, Gemma planning and YuE2 for newly generated music.

## What the Text and Music workflows add

Everything below is a node of this pack that the maintained Studio graphs use; each is off, or inert, when its input is missing.

| Feature | Nodes and skills | Needs |
|---|---|---|
| Story, then casting | `story_planner` and `casting_planner` skills, `Apply Casting`: the story of the edit is written before the shots, each shot gets its character, place and look. | Gemma. |
| Words of the music or of a voice | `Transcribe Voice`, `Music Words and Structure`: the sung or spoken words with their times reach the shot prompts, the phrase cuts and the casting. | `faster-whisper` and the `large-v3` folder, see [models](docs/models-and-downloads.md). Without them the nodes return empty text and the edit goes on. |
| Visual memory | `Save Shot Memory`, `Shot Memory`: a character keeps the face, build and outfit of its earlier shots, not their pose or framing. | Nothing more. |
| Camera moves | `Camera Moves`: every shot gets a move of twelve, none twice in a row; a brief asking for a fixed camera turns it off. | Nothing more. |
| Best of two takes | `take_judge` skill: two takes with two seeds, six frames of each, the local vision model keeps one. | Gemma; the shots stage takes about twice as long. |
| Kinetic lyrics | `Save Project Lyrics` and the `kinetic_lyrics` motion template: the words appear one at a time, a bigger one on the beats. | HyperFrames finishing and a voice in the music. |
| Lip sync check | `Lip Sync Check`: the mouth against the voice of a take, with a chance level. Not wired into the Studio graphs yet. | OpenCV. |
| Pika H3 Flex | A Studio option: six steps and the Flex LoRA instead of the turbo LoRA. | The LoRA file, see [models](docs/models-and-downloads.md). |

### Optional dependencies

| Optional dependency | What it adds | Without it |
|---|---|---|
| `faster-whisper` and the `large-v3` folder | The words of a voice or a song. | No words: the prompts have no lyrics, the cuts do not follow phrases, no kinetic lyrics. The edit goes on. |
| Pika H3 Flex LoRA | The Flex option (six steps). | The turbo LoRA is used; the user is told when the option was on. |
| FLUX files (`flux-2-klein-4b-fp8`, `qwen_3_4b`, `flux2-vae`) | Images of the places of the shots. | The shots are made without them; the user is told when the option was on. |
| YuE2 music model | Music generated for a Text edit. | The edit is cut on a steady grid and has no generated music; the user is told. Music mode (your own track) never needs it. |
| `comfyui_controlnet_aux`, DWPose and YOLOX files, the H3 pose patch, the Marigold node | Pose control. | Not needed by Text and Music shots: they are made without it. Only a Remix that asks for pose only needs them. |
| HyperFrames (Node.js 22+, a browser) | Text, graphics, kinetic lyrics, effects. | The video is kept as assembled, with a warning. |
| Tone bank (`install_tone.ps1`) | Generated sound effects. | No generated effects, with a warning. |
| BiRefNet | Layers that need the subject cut out. | Those layers are skipped, with a warning. |
| KJNodes, Easy-Use | Editing the visual workflows by hand. | The Studio graphs do not use them. |

Required, and reported with a clear message when missing: ComfyUI with the native H3, Gemma and YuE2 nodes, Majoor VideoTools, the Gemma planner files, the H3 model, encoder, VAEs and turbo LoRA, FFmpeg. A missing optional dependency must never stop a generation or the final montage; if one ever does, it is a bug to report.

## Manual montage

Connect the shot list to **Timeline Edit**, then to **Shot Assemble**. Optional audio passes through the editor. A retained shot list lets you edit without rerunning generation. The Studio's Manual montage uses the same editor, with a scoped Studio appearance.

Shot Assemble keeps `social` H.264 as default. Explicit `prores_422_hq`, `dnxhr_hqx` and `prores_4444` profiles require MOV and validated SDR color input; unsupported high-depth effects fail explicitly. See [delivery contracts and remaining graph work](docs/editorial-engine-rfc.md). Local tests and a procedural benchmark are recorded in the [qualification matrix](docs/qualification-matrix.md); they are not model/narrative or release approval.

[Timeline Edit guide](docs/timeline-edit.md) · [Node reference](web/docs/MajoorTimelineEdit.md) · [API wiring example](examples/timeline_edit.api.json)

## Experimental finishing

Effects, internal sub-cuts, text, motion graphics, animated design, sound design and SFX are experimental and disabled by default in HyperKut Studio. Requested graphic layers need the shared HyperFrames runtime; subject-dependent layers may also need a mask. Ordinary typography does not need BiRefNet.

Run only the installers for features you intend to enable, from the pack root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_hyperframes.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\install_tone.ps1
```

Node.js 22+, npm and a suitable browser are needed by these optional runtimes. The Tone installer builds its WAV bank once; mixing it does not open a browser per edit. No npm installation runs during a generation request.

[Finishing setup](docs/install-finishing.md) · [Graphic options](docs/finishing-options.md) · [HyperFrames](docs/hyperframes.md) · [Sound palette](docs/tone-sound-design.md)

## Validation and limits

Run `python -m pytest tests` with the environment providing the pack dependencies. Browser-widget checks live in `tests/web/`; ComfyUI integration checks are in `tests/comfy/`. Test contracts and model-backed output review are different evidence.

Windows is the documented Studio integration path. Source-switch previews may pause; review exported media. VFR/rotation, high-resolution outputs, browser/platform coverage and complete clean-install GPU reproduction need further qualification. No fixed hardware minimum or inference-speed promise is made.

[Roadmap](ROADMAP.md) · [Changelog](CHANGELOG.md) · [Release checklist](docs/submission-readiness.md)


## Engineering contracts

[Audio policies](docs/audio-policy-contract.md) · [Export transactions and caches](docs/export-transactions.md) · [Qualification matrix](docs/qualification-matrix.md) · [Local security boundary](docs/local-security-boundary.md)

Current audit corrections are prepared in source; runtime acceptance remains pending. See [the tracked checklist](docs/AUDIT_CORRECTIFS_CODEX_2026-10-30.md). New master-render and canonical-graph work is [design-stage](docs/editorial-engine-rfc.md), not an available production feature.
