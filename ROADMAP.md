# HyperKut — capabilities and roadmap

Reviewed **27 October 2026** against the current local Studio, exported workflows and tests. This is a feature/status roadmap, not a promise of release dates or equivalent output quality to another product.

**Available** means a maintained implementation exists. **Partial** means useful pieces exist but the complete user workflow or its validation is missing. **Planned** means the feature is not available in the current Studio. Checked items do not certify every generated video's artistic quality.

## Current capabilities

| Capability | Status | Scope and remaining work |
|---|---|---|
| Idea → multi-shot short video | Available | Text mode, enriched brief, visual plan, generated takes and assembly. Narrative/prompt adherence still needs visual review. |
| Product-photo advertising | Available | Reference-driven generation and product briefs; object geometry and labels are not guaranteed across takes. No automatic product-URL research/import. |
| Hook-first and dynamic edits | Available, improve | Short inserts, sub-cuts, transitions and measured timing. Explicit take counts and edit-cut counts are distinguished; live planner compliance needs broader evaluation. |
| Short stories / several scenes | Available, improve | Shot-local prompts and state handoffs. Long sequences, hand actions and physical transformations remain model-dependent. |
| Character/product references | Available, improve | Up to five UI image references. Scene illustrations may be uploaded manually with an explicit role in the prompt; no dedicated UI role selector or exact-first-frame guarantee. |
| Original music and sound effects | Available, improve | Local YuE2 music, H3 shot audio and Tone.js SFX. Timing uses measured audio events; exact composition structure is not guaranteed. |
| Motion graphics and animated text | Available, improve | Shared HyperFrames renderer, per-shot layers, word reveal, safe boxes, outline and onset sync. Subject-derived accents, style layer packs and dedicated animated counters remain unfinished. |
| Vertical, square and landscape generation | Available | Maintained 9:16, 1:1 and 16:9 workflows. This is not a dedicated automatic reframe tool for a finished video. |
| Edit prompts, regenerate takes, re-edit | Available | Per-shot revisions and active take selection; finishing can be changed without regenerating footage. |
| Simple animated infographics | Partial | Text/vector primitives exist. No complete data-to-chart/diagram pipeline, validated numeric counters or infographic authoring flow. |
| Talking character / UGC-style clip | Partial | Reference identity, voice sample and timed dialogue can guide H3. No dedicated avatar product, guaranteed lip-sync or validated long-form voice identity. |
| Faceless / narrated explainer | Partial | Multi-scene generation is available; one continuous narrator track, script-driven pacing and automatic subtitles are not a complete maintained workflow. |
| Speech transcription and synchronized subtitles | Planned | Existing text animation and visual overlay reading are not speech recognition or word-level subtitle alignment. |
| YouTube / long-video semantic clipping | Planned | Local shot detection and Remix exist; automatic URL ingestion and selection of the most meaningful passage do not. |
| Translation / voice-preserving dubbing | Planned | EN/FR interface localization is available; translation and audio localization are separate missing features. |
| Automatic subject-aware reframe | Planned | Crops/focus exist as edit effects; no dedicated finished-video resize workflow that tracks the subject and protects text. |
| Multiple selectable video-model backends | Planned | Maintained video generation uses H3. Other installed ComfyUI models are not integrated Studio choices. |
| Integrated 4K upscaling | Planned | XHigh 1.5 MP is a generation setting, not a 4K upscale pipeline. |
| Conversational tool-orchestrating agent | Planned | Current UI is a guided Studio with forms, jobs and per-shot actions, not an agent chat. |
| Product URL / brand research | Planned | Manual brief and photo input work; URL-to-brand extraction, palette/logo intake and claim verification are not implemented. |

The comparison scope comes from [Higgsfield's AI Short Video Generator page](https://higgsfield.ai/ai-short-video-generator), reviewed on 27 October 2026. That page groups several products/skills. Its marketing claims are not a tested quality benchmark, and HyperKut does not include all of Higgsfield's platform.

## Implemented foundation

- [x] Local ComfyUI execution through the official SDK and local proxy; Remix, Text and Music modes.
- [x] React Studio with EN/FR interface, progressive reference inputs and folded secondary controls.
- [x] Per-job projects, persisted request handles, take revisions, prompt edits, regeneration and re-editing.
- [x] H3 generation; YuE2 new music; Tone.js SFX; unified HyperFrames finishing; optional subject masks.
- [x] Visual-narrative-first planning for Text music direction, without a separate extra planning call; this is not a continuous voice-over feature.
- [x] H3 shot writer scoped to the current shot instead of receiving the whole-film brief again.
- [x] Continuity instructions separate stable identity/design from evolving location, light, emotion and prop state.
- [x] Set-dressed location plates: fixed furniture, objects, practical lights and mounted artwork described and carried into local prompts. The visual checker remains fallible.
- [x] Word-by-word text ordering across lines/repeats, final-word accent control, shared safe areas, eased fades and reading-time advisories.
- [x] Shot-local text/music timing constrained to the owning shot.
- [x] Removed the planner's one-take-per-1.2s ceiling; separated generated takes from editorial segments.
- [x] Studio Music grid used as timing guidance instead of fixing one take every three seconds; Text/Music density guards preserve protected actions and existing cuts.
- [x] CPU assembly check: five procedural source takes, twenty edit segments, fifteen seconds / 360 frames, including three-frame inserts. This is a technical montage check, not an H3 artistic benchmark.
- [x] Draft (~0.35 MP, commonly called 0.4 MP), Standard 0.6 MP, Max ~0.98 MP and XHigh 1.5 MP settings.
- [x] Six creative auditions exported locally: Gravity Off, Chrome Bloom, Paper Rebel, Pocket Storm, The Last Color and Bass Architect. Their technical success is not approval as bundled presets.
- [x] Old presets removed as requested; saving/importing user presets remains supported.
- [x] Honest creative controls: three named fidelity/freedom levels in Text/Music, real pose-strength range in Remix, accessible labels, enrichment/planner wiring, and retained/reusable manually edited briefs. Legacy numeric job settings remain compatible.

## Next: reliability and creative quality

- [ ] Evaluate new planner rules on short/long, narrative, abstract and performance prompts, including explicit twenty-cut and twenty-independent-take requests. Record count adherence, duration, protected actions and useful viewpoint diversity.
- [ ] Validate dense edits with actual H3 footage after the deterministic checks. Do not assume crops create new viewpoints or five-frame experiments replace normal takes.
- [ ] Improve narrative handoffs, one-time actions and prop/identity consistency using reviewed failure cases; keep mood pieces free from a mandatory plot formula.
- [ ] Improve audio/visual phrasing across the full edit while preserving the requested musical genre. Test measured sync against human listening, not only timing metrics.
- [ ] Broaden HyperFrames preview/performance coverage; keep useful diagnostics internal and the Studio simple.
- [x] Optional tech/editorial/pop layer packs and conservative reference-color accents, with explicit settings preserved and protected actions skipped. Available through the existing layer JSON; not enabled globally.
- [ ] Dedicated animated counters from real approved data; no fabricated progress or product numbers.
- [x] No-pulse rhythm fallback, linked SFX preparation/landing, optional sound palettes, encoded-boundary advisories and effective text-layout reports. These diagnostics are not artistic guarantees.
- [x] Extract active effect frames only, with complete-frame fallback for optical tracking.
- [ ] Review the six auditions, select/rework the strongest ones, and only then create localized presets and authorized demo media. Do not restore the retired presets automatically.
- [ ] Evaluate explicit reference roles (identity/product/style/scene) without complicating ordinary uploads; prevent a scene guide from replacing subject identity.
- [ ] Compare generated outputs across creative-control levels with fixed seeds and multiple subjects; semantic wiring tests do not establish a perceptually linear model response.
- [ ] Keep clean-install, project recovery and export checks current. Test ZIP import separately before advertising it.

## Next: complete narrated shorts

- [ ] **Continuous narration:** a script → one narrator audio track → scene timing workflow, independent of per-shot dialogue. Define voice consistency, pauses, ducking and review criteria.
- [ ] **Speech recognition:** local transcription of supplied or generated speech, with language handling and uncertainty reporting.
- [ ] **Aligned subtitles:** phrase/word timestamps, editable captions, safe margins, animated emphasis and subtitle export/burn-in options.
- [ ] **Explainer / faceless flow:** combine narration, relevant scenes, captions and music into one simple authoring path. Validate factual text and timing rather than treating a cinematic prompt as a finished explainer.
- [ ] **UGC flow:** portrait dialogue presets, product-reference handling and explicit lip-sync/voice review; no implied avatar-training capability.
- [ ] **Infographics:** structured data → charts/diagrams/counters, accurate values, paced labels and reusable HyperFrames layouts.

## Later: editing and reach

- [ ] Long-video semantic clipping: identify candidate passages, preserve context, expose the choice for review and support local files first.
- [ ] Optional YouTube/URL ingestion for authorized media, with a local-file fallback and bounded downloads; scene-cut detection alone is not semantic highlight selection.
- [ ] Subject-aware reframing of finished clips, with composition and text-safe review for vertical/square/landscape versions.
- [ ] Translation, voice-preserving dubbing and optional lip-sync as an explicit workflow; separate it from UI-language settings.
- [ ] Product URL / brand intake with editable extracted information and explicit source/media provenance.
- [ ] Optional 4K upscaling with measured quality, runtime/VRAM cost and licensing documentation.
- [ ] Additional open-weight video backends through a common take contract; compare output and licensing before exposing choices. Closed APIs would be a separately labelled optional path, not part of the current local-only claim.
- [ ] Optional conversational orchestration after the underlying functions are reliable; preserve visible job controls, bounded costs and resumable state.

## Release and distribution

- [ ] Reproduce installation from a clean checkout with documented model/runtime versions.
- [ ] Review code/dependency/model licenses and required authorizations; publish the corresponding notices. MIT code does not license model weights or user media.
- [ ] Select demo media with appropriate rights and document actual product limits.
- [ ] Verify repository visibility, release packaging and any competition submission acknowledgment separately. Local test success is not publication or contest acceptance.
- [ ] Design remote execution around artifact transfer rather than shared local-disk assumptions; add authentication/quotas before a public deployment.

See [license scope](LICENSES.md), [submission readiness](docs/submission-readiness.md) and the Studio's [historical issue notes](HyperKut%20Studio/docs/known-issues-and-roadmap.md).

## Experiments not adopted

- **Scene illustration before every H3 take:** tested with FLUX.2 Klein and H3 short-frame extraction, then explicitly set aside. Keep the current generation path. Manually uploaded scene references and the existing optional set-dressed location plate remain available.
- **Remotion / a second graphics engine:** not adopted; improve the existing HyperFrames pipeline first.
- **Music-model alternatives:** historical auditions do not change the maintained YuE2 path.

No feature in the unchecked sections was implemented merely by adding it to this roadmap. Update a checkbox only with code/workflow evidence and relevant validation, and distinguish technical availability from reviewed creative quality.
