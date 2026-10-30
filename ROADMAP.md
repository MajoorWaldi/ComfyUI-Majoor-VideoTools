# Majoor VideoTools and HyperKut — roadmap

The VideoTools pack provides shot detection, identified takes, metadata, assembly and the shared Timeline Edit editor. HyperKut Studio is a separate **beta** application using these nodes. Finishing is **experimental**, optional and disabled by default in the Studio.

## Implemented

- Shot detection/splitting, selection, metadata updates and assembly from retained takes.
- Timeline Edit: frame-based trim/slip, cut/reorder/duplicate, take selection, undo/redo and export.
- ComfyUI API workflows for local Remix, Text and Music creation.
- Experimental unified HyperFrames graphics, word animation and audio-event timing.
- Experimental opt-in style packs and subject-derived accent color in the Studio adapter; not universal automatic defaults.
- Tone-generated optional SFX palette and explicit runtime installers.

## Improve and qualify

- [ ] Clean-install model-backed workflows with pinned checkpoint revisions and authorized inputs.
- [ ] Dense-edit narrative continuity, action/identity consistency and musical phrasing.
- [ ] Experimental compositor performance, browser coverage and preview/export agreement.
- [ ] Manual montage interaction with new takes and experimental extension candidates.
- [ ] Portable presets and clear first-run diagnostics.

## Planned

Continuous narration/transcription/subtitles; data-driven infographic layouts and numeric counters; semantic clipping; subject-aware reframing; additional selectable video backends; integrated 4K upscale; project ZIP import.

Generated quality is model-dependent and needs human review. The local Studio expects shared media storage; public multi-user hosting and remote artifact transfer are not qualified. Model, dependency and media terms remain separate.

[Pack README](README.md) · [Model inventory](docs/models-and-downloads.md) · [License scope](LICENSES.md) · [Studio source](https://github.com/MajoorWaldi/HyperKut-Studio)


## Audit remediation tracking

Robustness work now has executed local evidence: output-key export locks, actual-workspace media URLs, source-offset-aware cut/layer limits, non-finite FX rejection, persistent audio, saved-detection reconciliation, corruption checks and lease-protected cache retention. See the [qualification matrix](docs/qualification-matrix.md) for precise PASS scope and still-open acceptance cases.

Explicit SDR master delivery and the first rational editorial-intent compiler are [partially implemented and tested](docs/editorial-engine-rfc.md), no longer RFC-only. Complete FX/render-graph unification, broad master qualification and narrative/human approval remain open. Jury admission exists in the separate Studio, but public multi-user deployment remains outside the qualified boundary.
