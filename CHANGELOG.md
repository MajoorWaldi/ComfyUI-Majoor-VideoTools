# Changelog

## Current development version

- Shot identification, scene splitting, metadata and retained-take assembly.
- Shared Timeline Edit editor and Studio adapter for frame-based manual montage.
- Visual workflows and exported Studio API graphs for Remix, Text and Music.
- Gemma planning, MiniMax H3 video and YuE2 music in the maintained Studio workflow.
- Shot-local prompts, narrative handoff, optional location/pose/mask branches and audio-event timing.
- Experimental unified HyperFrames graphics and Tone-generated optional sound palette.
- Explicit installers, portable preset inputs and documented model/dependency/media terms.

The legacy SECATOR workflow filenames remain compatible. HyperKut Studio is distributed separately and remains beta. Finishing is experimental and starts disabled in the Studio.

See [roadmap](ROADMAP.md), [model inventory](docs/models-and-downloads.md) and [licenses](LICENSES.md).


## Unreleased — 2026-10-30 audit corrections

- Prepare export serialization per output key, owned temporary files and atomic SFX/text cache publication.
- Resolve ComfyUI preview URLs from actual project storage rather than a fixed legacy directory.
- Bound cut/layer reads after take slip; explicit padding policy and warnings.
- Reject non-finite effects/options; repair math-wiring tests and add mutation coverage.
- Keep persistent music identity and versioned delivery metadata; preserve saved takes on unchanged redetection and refuse incompatible remapping.
- Strengthen assembly/HyperFrames cache keys and metadata validation.
- Add engineering contracts and an executed qualification matrix; model-backed runs remain NOT RUN.
- Keep supplied music in indexed persistent sources; add lease-protected regenerable-cache retention and explicit free-space refusal.
- Add explicit SDR ProRes HQ, DNxHR HQX and ProRes 4444 alpha delivery with high-depth intermediates, color checks and PCM24 audio; social remains the default.
- Introduce a pure rational editorial-intent compiler and legacy/manual adapters; full resolved FX/frontend unification remains pending.
- Preserve delayed source/take audio timestamps instead of advancing late audio to zero.
- Add a six-second procedural frame/audio benchmark and real parallel/cancel/recovery export regressions.
- Qualify local engine, separate Studio backend/frontend, offline CPU ComfyUI API and Chromium media/player paths; record external and human gates as open.
- Separate Studio changes add fail-closed local/jury admission and upload budgets; no public deployment or multi-user authorization is claimed.
