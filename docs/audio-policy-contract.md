# Audio policies and editorial operations

This contract documents the existing engine; it does not rename serialized settings.

| Intent | Existing settings | Picture edits | Audio behavior |
|---|---|---|---|
| Original soundtrack locked | `audio_policy=source_master` | Reorder, trim and slip are allowed | The original source soundtrack stays continuous from zero; it does not follow reordered clips. Duration changes may cut/pad it. Explicit warnings identify this behavior. |
| Audio follows picture | `audio_policy=shot_audio` | Selected take and seek window | Each segment reads its own input audio at the same seek. Constant speed uses atempo; a speed ramp is silent because matching time-warped audio is not implemented. Silent inputs produce silence. |
| Music only | `audio_policy=mute` plus music | Any supported montage operation | Supplied music starts at zero, independent of clip order. Gain, optional end fade and explicit ducking apply. |
| Independent dialogue | Dialogue input or Timeline Edit dialogue clips | Independent picture cuts | Dialogue replaces the source/take bus, is mixed at its explicit positions, and cannot silently extend past picture duration. |
| Protected take dialogue | `voice_shots` + `preserve_dialogue` | Protected raw speaking takes | Internal cuts/speed are omitted; longer speech requires extending or explicitly editing the dialogue. |

Priority in Shot Assemble: `voice_shots` selects shot audio; otherwise `replace_source_audio` selects mute; otherwise audio_policy applies. An independent dialogue bus replaces that selected bus. Timeline Edit dialogue and an explicit dialogue input cannot be combined. Music and additional SFX are separate inputs; their gains are not source/take volume. Music ducking requires an audible dialogue/take bus.

Timeline Edit is a raw-take editor. It does not rerun plan FX or generation. The original manifest/takes remain intact. Its dialogue excerpts can include ambience and are not isolated speech stems. Reordering original footage under source_master is intentionally different from audio following picture.

No automatic phrase-completion or semantic speech detection is claimed. A trim is an explicit editorial decision; the user reviews it. Test fixtures must distinguish silent source, two different tones, duplicate/reorder/slip, speed ramps, longer-than-picture dialogue and locked music. Runtime qualification is tracked separately.

Decoded regressions now cover reorder/duplication/trim/slip, locked music and dialogue. Source/take resampling uses `async=1:first_pts=0` at 48 kHz so a late audio stream retains its initial silence instead of being advanced to zero. A +250 ms fixture verifies silence at 50-150 ms and audible tone afterward; a nonzero video-PTS/multiple-track fixture verifies output origin/frame count and selection of the first audio track. This does not certify every VFR or audio-leading source.

The procedural six-second benchmark measures cut frames 36/72/108 exactly, reordered take tones 880/440/660/880 Hz and continuous 220 Hz music in all four windows. These are technical measurements, not approval of speech phrasing or musical/narrative quality. Explicit master profiles keep PCM24 audio through loudness normalization; social output keeps its existing AAC behavior.
