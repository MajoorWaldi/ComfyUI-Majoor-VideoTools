# Local Tone.js sound design

The existing automatic sound-effects switch now uses a locally synthesized Tone.js palette when installed. No new Studio panel, model, paid API or third-party samples. Music remains unchanged; one SFX bus is mixed by the existing assembler. Disabling automatic effects bypasses this path.

Install explicitly with `scripts/install_tone.ps1` (Node 22+, local Chrome/Edge). Tone.js 15.1.22 and puppeteer-core 25.16.0 are pinned; generation never installs packages or launches a browser. The installer renders 30 mono/stereo PCM48k cues with Tone.Offline. The original 16 are: impact, hit, whoosh, swell, shutter, glitch, sub drop, riser, reverse, downlifter, click, pop, tick, sparkle, tape stop and stutter. Synthesized approximations are not recordings of physical objects.

Actual transition cues and cut density select the automatic palette. Sparse cuts remain sparse; dense edits vary short accents. No fictional timing of footsteps, cap removal or spraying is inferred from prose. Rhythm accents follow detected attacks when available. The existing user WAV manifest supports all 30 names and overrides matching synthesized cues. Per-type gains and conservative bus headroom avoid a full-volume effect on every cut. Explicit voice/music handling and the existing final limiter are retained.

The full palette is available for explicit cue scheduling through the core renderer; automatic selection intentionally uses only the sounds justified by current transition metadata. It does not impose tape stops, sparkles or sub drops on every project. Missing Tone runtime preserves the six legacy procedural sounds. Invalid installed banks fail clearly instead of being silently accepted. File hashes and synthesis version participate in assembly caching.

Tone.js is MIT-licensed and puppeteer-core is Apache-2.0; their installed license files must be preserved on redistribution. There are no downloaded sample packs or model-weight licenses. This does not constitute confirmation of eligibility by competition organizers.

## Expanded palette (v2)

Additional cues: ui_click_soft, ui_click_crisp, notification_soft, notification_confirm, notification_alert, metal_tick, metal_chime, glass_ping, stereo_whoosh_lr, stereo_whoosh_rl, stereo_sweep, logo_soft, logo_bold and logo_sparkle. All are synthesized locally, including the metallic accents with Tone.MetalSynth. No branded notification or logo sound is sampled.

Cut accents may vary between understated clicks and metallic ticks. Whips select alternating directional stereo transitions. Automatic event count stays bounded by existing cue thinning; musical notifications and sonic signatures are only explicit events, not automatically attached to every cut or product. Stereo is retained through bank loading, user WAV loading and the SFX bus. Existing 16-cue installations stay compatible until their bank is rebuilt.

The installer, renderer and user WAV notices are summarized in [LICENSES.md](../LICENSES.md), [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) and [installation](install-finishing.md).

## Shared editorial accent arbitration

Automatic transition cues and explicit motion-layer cues now pass through the same final limiter, after palette selection. Optional layer `event_role` values are `action`, `reveal`, `narrative`, and `decoration` (default), in that priority order. This describes declared editing intent, not physical action inferred from pixels. No timestamps are moved and no visual layers are removed.

Shots marked `story.protect_action: true` exclude unrelated sound accents during their final timeline window. Only explicitly declared action cues survive there. The normal policy allows one accent per 0.4 s, the same cue at most once per 0.8 s, and at most four accents in two seconds. Held shots of at least three seconds with sparse measured music attacks receive wider gaps: 0.8 s, 1.6 s, and two accents per two seconds. This uses measured cadence and actual holds; it does not classify mood semantically.

The assembly score records kept and dropped cues and their reasons when a shared score is written. Separate music/SFX audio tracks are unaffected; cues selected from a user cue library still participate in arbitration. The existing sound-effects switch remains authoritative. No new Studio panel is introduced. Assembly cache version 4 prevents reuse of mixes produced by the previous policy.
