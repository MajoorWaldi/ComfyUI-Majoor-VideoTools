# RFC: canonical editorial graph and delivery profiles

Status: partially implemented and locally tested, not a fully qualified canonical renderer. Social remains the default. Explicit SDR master profiles and a first shared editorial-intent compiler now exist; the distinctions below are release constraints, not just future design notes.

## G14: one composition contract

The integration point is the retained ShotList / Timeline Edit document. `core/editorial_graph.py` is pure Python, does not import ComfyUI, and introduces a versioned rational graph alongside legacy manifests rather than replacing generation modes.

Target composition contract:

- Graph identity: schema version, project revision, input content fingerprints, compiler build and selected output profile.
- Timebase: positive rational fps/time base; frame indices and rational [in,out) positions, never accumulated binary float durations.
- Clip occurrence: unique occurrence ID distinct from shot ID; selected take ID, source asset, source window, output window, speed map, layers and transition.
- Audio buses: locked music, source-following/take audio, independent dialogue and SFX; gains/fades/ducking with explicit routing and source fingerprints.
- Continuity: subject/wardrobe/location/light/motion state, intent, incoming state, visible action and outgoing state; planning metadata is not pixel-level proof.
- Operations: non-generative trim/slip/reorder/duplicate/FX versus explicit generation of a new take. Retake one occurrence without regenerating unchanged assets.
- Provenance: provider/model revision, seed when available, input asset identifiers, rights status and authorial review state.

Migration: decode legacy manifests unchanged; compile both old automatic and manual paths to a side-by-side canonical representation; compare frame/audio windows and hashes. Promote the graph only after identical synthetic outputs and approved real projects. Rollback preserves legacy manifests and never rewrites raw takes. Runtime paths stay outside serialized manifests. Shared pure graph validation must not import ComfyUI.

Implemented: immutable clip occurrences with distinct occurrence/shot identity, rational source/output windows, selected media identity, compiler/schema version, source context and deterministic hashes. `compile_project` accepts automatic ShotLists or manual documents; `export_shot_list` preserves the old assembler contract. `compile_edit` and assembler base ordering/windows use it. Backend preview payloads include a raw-take adapter. Tests pass for portable legacy migration, manual preview/export windows, 1000 frames at 30000/1001 fps, deterministic and incrementally changed hashes.

Still pending: a resolved FX/speed/layer/audio render graph consumed by every client. Final duration-policy/FX expansion remains in assembler `_plan` / `_fx_segments`; the JavaScript editor still computes its local raw edits. Sidecars deliberately call the graph `editorial_intent`, and preview adapters say `raw_takes_not_plan_fx`. These are not pixel/timing parity claims for plan FX. G14 remains open.

## G13: explicit delivery profiles

Existing social output remains H.264 / CRF 18 / yuv420p, MP4 or MOV. A MOV wrapper alone is not a VFX master.

Shot Assemble now has optional trailing `delivery_profile` and `color_policy` inputs; old schemas/defaults remain compatible:

| Profile | Container / codec | Working / output pixels |
|---|---|---|
| social (default) | MP4 or MOV / libx264 CRF 18 | yuv420p / yuv420p |
| prores_422_hq | MOV / prores_ks profile 3 | yuv444p10le / yuv422p10le |
| dnxhr_hqx | MOV / dnxhd dnxhr_hqx | yuv444p10le / yuv422p10le |
| prores_4444 | MOV / prores_ks profile 4, alpha_bits 16 | yuva444p10le; decoded by FFmpeg as yuva444p12le |

Masters require explicit MOV, available encoders and SDR BT.709 input tags by default. `assume_bt709` explicitly permits missing tags with a warning; contradictory HDR/other tags are rejected, not transformed. Input normalization keeps the high-depth working format; known legacy `eq`, `hue`, `chromashift` and `noise` chains are rejected because their precision is not qualified. Alpha is preserved only when the input/composition actually supplies alpha. DNxHR requires at least 256x120, without implicit upscale. Audio is PCM24, including loudness-normalized output.

Local decoded fixtures pass: >512 distinct luma levels, maximum ramp error <5, >240 alpha levels, codec/pixel format/frame count and BT.709 metadata. ProRes MOV nclc does not signal range like nclx: ffprobe may omit it. The sidecar explicitly records legal-range convention, and decoded levels are tested instead of inventing a full/limited metadata flag.

Still pending: exhaustive overlay/split/text/finishing chains, field projects, complete disk-budget and color corpus. HDR/OCIO, image sequences and 4K upscale are not implied. G13 is implemented beyond an RFC but not globally closed.

## G15: editorial benchmark

Use owned or procedurally generated 5–15 s inputs only. Record seeds/model hashes, source/output shot order, cut-frame error, duration, measured musical accents, transition coverage and single-shot retake hashes. Suggested cases: light transferred between locations; product impact/reveal; paper character escaping a poster; reordered tone/color clips; quiet held action versus dense bursts.

Lock structure, constrain identity/action, leave creative scene details open. Every planned shot needs a distinct state change, not the same global synopsis repeated five times. Human review separately scores identity, wardrobe, action readability, inter-shot continuity, typography and musical phrasing. Heuristic boundary/onset scores cannot certify narrative equivalence to Katana. No automatic semantic approval button is introduced.

`scripts/benchmark_editorial.py --output-dir <private-directory>` generates owned procedural colors/tones, detects three shots, then slips/trims/reorders/duplicates four occurrences. The six-second output passes decoded 144-frame/cut-position/tone checks; a second export verifies music stays at 220 Hz across every occurrence. `benchmark.json` contains graph/occurrence/media fingerprints and explicitly leaves model generation and human review NOT RUN, release approval false. It is not the full narrative benchmark.
