# Music-driven edit timing

When beat snapping is enabled, Create Timeline first builds its existing tempo grid, then adjusts grid points toward nearby measured audio attacks. The adjustment is limited to two output frames and preserves grid order. The existing shot-length and micro-cut limits still apply. Weak or absent attacks leave the grid unchanged. Snapping disabled leaves the original edit timing unchanged.

The music is neither stretched nor rewritten. Reference-remake shot positions are not globally retimed by this change: only Create Timeline's explicitly enabled music snapping uses the refinement. Existing cached projects stay available; new timelines use cache version 5.

The approved music brief and ACE-Step Turbo remain unchanged. No new UI or measurement panels are introduced. This is a local onset correction, not guaranteed vocal recognition, perfect downbeat detection, or a replacement for human judgment about groove.

Validation: synthetic attacks slightly ahead of/behind a beat, silent audio, distant attacks and dense grids; existing music-fit, micro-cut and timeline/render tests.
