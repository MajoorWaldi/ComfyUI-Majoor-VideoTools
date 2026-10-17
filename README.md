# Majoor VideoTools

Four ComfyUI nodes that turn a video into a collection of identified shots, let any workflow replace one shot, and rebuild the video without touching the source.

Quatre nodes ComfyUI : une vidéo devient une collection de shots identifiés, n'importe quel workflow peut en remplacer un, puis la vidéo est remontée sans toucher à la source.

```
Load Video → Scene Detect & Split → Select Shot ─┬─ video / images → (your generator, VLM, API…) ─┐
                    │                            └─ metadata ─────────────────────────────────────┤
                    └─ shot_list ─────────────────────────────────────────────────────→ Apply Shot Metadata → Shot Assemble → Video
```

Category: `Majoor/VideoTools`.

| Node | Output | Role |
|---|---|---|
| Majoor Scene Detect & Split | `shot_list` | PySceneDetect (adaptive / content / threshold_fade) or manual `cut_points`. Writes a manifest, no clip is encoded. |
| Majoor Select Shot | `video`, `images`, `metadata` | Pick a shot by `shot_id` (or `index`) and a take. The clip is cut frame-accurately on first use and cached. |
| Majoor Apply Shot Metadata | `updated_shot_list` | Stores a generated video as a new take of the shot. Returns a new list; earlier lists and takes are kept. |
| Majoor Shot Assemble | `video` | Rebuilds the video from the active take of every shot (original order or `manual_order`). |

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
`scenedetect` depends on `opencv-python`; if your environment already uses `opencv-python-headless`, install with `pip install scenedetect --no-deps` and keep your OpenCV build. No network access is made by this pack.

## Status

Tested here (`python -m pytest tests`, real FFmpeg, 24 fps hard-cut fixtures): detection and manual cuts, cache and ids, selection and sampling, apply / idempotence / restore / concurrent patches, assembly with every duration and audio policy, manual order, missing media, corrupt input.

Not verified yet: execution inside a running ComfyUI (the machine used for development had no torch, so the nodes were only compiled and checked against `comfy_api.latest` source), VFR and rotated fixtures, 4K, Linux, and the optional frontend widgets (none are shipped; every input works headless). No example workflow JSON is shipped until one has been run in ComfyUI.

Not implemented: cache TTL/purge, `.mov` beyond a container switch, `shot_audio` crossfades (by design).
