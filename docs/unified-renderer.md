# Unified finishing renderer

SECATOR now composites typography and motion graphics with HyperFrames. `MajoorMotionGraphics` is retained as a compatibility node and delegates to the same renderer; its former frame-by-frame video encoder has been removed. The JSON contract remains available, including text, emoji, boxes, brackets, outlines, frame/subject/background effects and tracked labels.

The Studio final graphs (Text, Music, Remix) contain one `MajoorHyperFrames` directly after `MajoorShotAssemble`. Planner text is translated to shared layers with its timing, position, font, color, rotation and repetition. Assembly text drawing is disabled for this path, while the user-facing text switch remains effective. Standalone assembly workflows retain their existing behavior; they are not rewritten automatically.

The assembler still handles editing operations: cuts, sub-cuts, speed/retiming, camera crops, transitions between pieces, split/overlay video layouts and audio mixing. These are not a second typography/motion compositor. Visual appearance is not promised pixel-identical to the former Pillow/OpenCV rasterization: browser font rendering and footage effects can differ.

## BiRefNet

BiRefNet remains a useful **optional mask producer**, not an animation engine. It is requested lazily for:

- outlines and halos around a subject;
- effects restricted to the subject or background;
- points/labels anchored to the subject.

Plain typography, rectangles, emoji, full-frame effects and optical-flow points do not request it. Any compatible ComfyUI MASK can replace BiRefNet. The obsolete manual Studio mask switch is hidden; actual layers determine the requirement. Automatic source-overlay restoration in Remix remains lazy and keeps its existing LLM; no additional LLM pass was added.

Mask interpolation, edge morphology and optical-flow coordinates are prepared by Python/OpenCV. HyperFrames performs the final composition. Masks and decoded footage are loaded a few frames at a time through the documented `hf-seek`/`waitUntil` protocol, rather than keeping a full video in browser memory. Frame effects need lossless source-frame assets; projects with these effects use more disk space than typography-only projects.

## Editing and compatibility

Manual layers and the actual rendered layer report are separate. The report also includes automatic source layers and planner typography and is shown read-only, avoiding their duplication on subsequent re-edits. A project report is written to `exports/hyperframes.json`. Original audio is remuxed unchanged. Existing Motion Graphics nodes use HyperFrames too, so their npm runtime must be installed when graphics are requested.

Prepared projects and content hashes include layer parameters, renderer templates and mask contents. Unsupported/invalid inputs and missing required masks fail explicitly; no effects are silently dropped. Existing low-level drawing helpers remain for API compatibility, but are not called by the production render path.

Run `scripts/install_hyperframes.ps1` for the local optional runtime. No hosted generation is used. Limits: 180 seconds, 60 fps, 120 combined layers. Windows is the validated environment. This change does not remove the BiRefNet weights or segmentation nodes used by other workflows.
