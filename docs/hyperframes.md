# Optional HyperFrames finishing

> **Experimental finishing.** HyperKut Studio is beta. Finishing starts disabled; review the encoded result when enabling these features.


The Studio enables animated design by default, with the added music mix at zero. Its presets choose a compatible graphic style. Existing explicit edit settings remain authoritative. The standalone node still requires activation.

Connect **Shot Assemble → Motion Design — HyperFrames → Save Video**. Existing Motion Graphics nodes are compatibility adapters to the same compositor. The Studio uses a single finishing node; do not add a second graphics pass by default. `enabled=false` disables decorative design; separately requested layers can still render and require the runtime. A pass with neither decoration nor layers can bypass rendering.

Install Node.js 22+, FFmpeg and local Chrome, then run `powershell -ExecutionPolicy Bypass -File scripts/install_hyperframes.ps1`. The npm runtime is separate from Python and is optional. `MAJOOR_HYPERFRAMES_RUNTIME` can point at another runtime folder containing `node_modules`. Generation never runs npm, logs in, publishes a project or uses hosted generation. HyperFrames itself may obtain/cache fonts and browser resources; offline installations must provision these beforehand.

## Direction

This first version uses prepared animations. A plain brief selects a bounded preset: minimal/sobre/discret/soft → minimal; énergique/dynamique/energetic/nerveux/bold → energetic; otherwise editorial. A six-digit hexadecimal color in the brief sets the accent. This is a shorthand, not semantic LLM interpretation.

For precise direction:

```json
{"preset":"editorial","accent":"#e4c081","intensity":0.6,"reactive":true,"title":"NEW DROP"}
```

No title is invented. With no explicit text, only graphic decoration is rendered. `shot_cues` is a JSON list:

```json
[{"shot_id":"SHOT_001","text":"MATIÈRE","position":"top"},{"shot_id":"SHOT_003","text":"SIGNATURE","position":"bottom"}]
```

`timeline` must contain actual final-edit timing, not raw generation duration:

```json
[{"id":"SHOT_001","start":0,"duration":3},{"id":"SHOT_003","start":3,"duration":4}]
```

Alternatively omit shot_id and specify start/end in final seconds. Overlapping titles, unknown shot ids, invalid intervals, arbitrary code and unknown JSON keys are rejected. Shared layers also support optical-flow tracking, subject anchors, masks and outlines. BiRefNet is requested only when the actual layers need a subject mask; no semantic placement based on image understanding is claimed.

The final video's audio drives corner pulses and a seven-band spectrum. Title timings remain explicit: the node does not silently move words across shot boundaries. Without audio, motion is timed but not described as audio-reactive. Limits: 180 seconds, 60 fps, 30 title cues and 120 combined shared layers.

## Shot-local layers and preview checks

See [coordinated motion scenes](motion-scenes.md) for layer dependencies, named design defaults, vectors, transforms and shared sound cues.

The planner can add `motion` layers to each shot. The Studio transfers them to the shared compositor with that shot's id; explicit manual layers addressed to the same shot replace its planned motion. Turning off animated design suppresses planned motion; the text switch still suppresses text/emoji. Existing manual absolute-time layers and legacy `fx.text` keep their behavior.

```json
[{"type":"text","shot_id":"SHOT_002","content":"FEEL THE BASS","start":"10%","end":"85%","font":"clean","position":"bottom_left","animation":"slide_up","sync":"onset","safe":true}]
```

With `shot_id`, start/end use local edited-shot seconds or percentages, resolved against the final timeline. Without it they remain absolute. `sync:"onset"` may move only the entrance, by at most 150 ms, onto a measured attack in the final audio mix, never outside the shot or beyond the layer's end. No nearby attack or no audio leaves timing unchanged. This detects attacks in the mix, not isolated musical stems. Reports record requested/resolved times and whether a match occurred.

Before full encoding, HyperFrames captures up to 16 representative composition frames (entrances, settled layers and shot middles). PNG decoding, count and dimensions are checked; a failure stops the full render and retains the source. Stills, contact sheet and a report are saved in the render project's `previews/` folder and linked from the finishing report. This is a technical check, not automatic semantic/aesthetic approval or face detection. Subject-aware typography is directed by the planner's shot description; a person can inspect the contact sheet. No extra model call or Studio panel is added.

## Reuse and failure

Content hashes of the source, GSAP, direction and resolved cues select a project under `output/MajoorVideoTools/hyperframes/`. HTML, assets, measured audio data, direction, report and render log remain editable. Equal requests reuse the existing output. Original audio is remuxed from the final source, never newly generated. If the original codec cannot be remuxed to MP4, the node reports an error instead of silently replacing the mix.

Cancellation terminates the rendering process tree on Windows. Invalid inputs and cancellation remain errors. If the optional local renderer/runtime itself is unavailable or fails, both the finishing node and the compatibility Motion Graphics node deliver the unchanged source video and log a warning with the specific cause; they do not overwrite a previous successful export. The report retains the stable `optional:hyperframes:unavailable` warning code and includes `warning_details` with the cause. The Motion Graphics passthrough is not cached, so a later execution can retry after installing or repairing HyperFrames. A 15-minute render timeout avoids indefinite waits. The Studio bypasses rendering when decorative design, manual/planned layers and source-layer restoration are all inactive. A disabled decoration toggle alone is not a guarantee that no graphics are requested.

If the pinned CLI announces a completed, validated render but keeps its process alive, the adapter allows five seconds for normal shutdown, then verifies dimensions, fps, frame count, duration and full video decoding before closing only that child process tree and continuing the audio remux. Missing completion markers or an invalid artifact still fail; cancellation remains authoritative. The finishing report records `recovered_shutdown` when this recovery was used.

## Licenses

SECATOR's own adapter and templates remain MIT. HyperFrames is Apache-2.0; retain its license/attributions when distributing it, and identify modified upstream files if any. This integration does not modify upstream HyperFrames. GSAP has its own standard license (linked by its package metadata; do not assume a LICENSE file is included in every package build); Apache-2.0 does not apply to every transitive dependency. Fonts/media retain their own licenses. The installer obtains upstream packages rather than embedding them in the pack.

## Unified renderer

See [unified-renderer.md](unified-renderer.md) for the shared layer contract, planner typography, lazy mask behavior and compatibility with the original Motion Graphics node.

See [installation scope](install-finishing.md), [license reference](../LICENSES.md) and [third-party notices](../THIRD_PARTY_NOTICES.md).
