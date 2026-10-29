# Incremental finishing options

These options reuse the installed H3, YuE2, HyperFrames and Tone.js engines. No new dependencies or model calls are added. Existing projects keep their manual layers and explicit settings.

## Optional layer packs

The existing Motion Graphics layer JSON accepts a wrapper with a `pack`:

```json
{
  "pack": "tech",
  "accent_from_subject": true,
  "layers": []
}
```

Packs: `tech` (fine line and point), `editorial` (restrained rule), `pop` (bold ring). They add no copy, skip protected actions and very short shots, and respect layers already assigned to a shot. Turning animated design off disables the pack. They are optional defaults, not mandatory effects on every generation.

`accent_from_subject` samples the first uploaded reference conservatively. It may abstain; it is not a semantic subject detector. Explicit direction accents or a wrapper `accent` in `#RRGGBB` take priority. The existing accent remains the fallback. It does not load BiRefNet. Reference order still matters; use an explicit accent for a scene/style reference whose subject color is ambiguous.

The old plain JSON layer array remains supported. For example, an empty array keeps the existing planner/manual behavior.

## Optional sound palettes

A motion layer can carry `sound_palette`: `subtle`, `electronic` or `metallic`. One consistent palette across the layers guides the automatic editorial SFX bus. Conflicting or missing choices keep its legacy selection. User samples and explicit scene sounds remain authoritative; the sound-effects switch still controls the bus. Palettes use only the installed bank and introduce no physical action sounds that were not planned.

Prepared risers and their impacts now share a landing event rather than cancelling each other. Updated banks may provide `anchor_sample`; existing banks retain their historical lead offsets, and custom user samples retain their start offsets. Rebuilding the bank is not required for existing installations.

## Internal checks

- No reliable rhythmic pulse: preserve the audio window and narrative timing instead of claiming measured BPM/bar cuts. An explicit BPM is labelled as an intentional user grid. Confidence is heuristic, not a probability or quality score.
- Short-music looping uses requested energy and moments when choosing a window; a manual start takes priority. Seam smoothing and a replacement attack detector are not enabled without broader listening evidence.
- Assembly writes a fingerprinted `.delivery.json` companion with actual segment boundaries. HyperFrames reviews the encoded picture around those boundaries. Results are advisory: a flash, declared transition or static image is not automatically a failed cut.
- Preview layout reports use the actual Canvas text wrapping and transformations, plus HTML bounds. Existing subject masks can flag text bounds overlapping the subject, without another segmentation pass. Without masks this is not evaluated. This does not recognize faces or guarantee contrast, identity or artistic quality.
- SFX/music balance reports use RMS, not LUFS or perceived audibility; no automatic gain escalation is performed.
- Short effect windows extract only required source frames. Optical tracking retains the complete source-frame path.

Diagnostics remain in project/export reports. The main Studio does not add a technical panel.

## H3 prompt contract

Writers retain shot-local state and action. Instructions identify text-only versus reference inputs, avoid implicit keyframe claims, use the current dialogue notation and voice-reference relationship, and preserve spoken text verbatim. Performance/optics hints are short and selected from the local shot only. Prompt compliance, voice identity and lip sync still require real-output review.

## Graphic handoff

`core.motion_scenes.graphic_handoff(cut, before=.35, after=.35, velocity=(.2,0), at=(.5,.7), color='#e4c081')` returns two ordinary vector layers with matching position and relative velocity at the cut. This is an explicit composition helper, not automatic semantic tracking or a new renderer. It does not force motion or blur into calm scenes.
