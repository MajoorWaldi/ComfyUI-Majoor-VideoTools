# Timeline Edit

Non-destructive editing of **raw takes**, after generation and before Shot Assemble.
No generation models are required for editorial operations.

## Wiring

`Load Shot List` (or the final `Apply Shot Metadata`) -> `Timeline Edit` ->
`Shot Assemble`. Optionally connect `AUDIO` to `music`, and the node's `music`
output to Shot Assemble's `music`. Use `audio_policy=mute`, `music_fade=0` and
disable auto SFX / external motion layers to compare the musical preview.

Run the graph once to load the library, then choose **Open Timeline Edit**.
Changes save to `edit_json`; run the graph again to render the edited result.
For repeated editing use Load Shot List rather than rerunning generation.

## Controls

- Drag clips onto other clips to reorder, or use Move left/right.
- Drag a clip's edge handles to ripple trim; arrow keys on a handle trim one frame.
- The selected clip's source filmstrip shows the full available take. Drag its
  window edges to trim, or the window body to slip. Timeline selection, trim,
  take changes and undo/redo update the same source window. A drag previews
  live and commits one undoable command on release; cancellation discards it.
- Expand **Frame controls** for exact numeric In/Out and slip adjustments.
- Toggle **Loop** next to Play to repeat the whole montage, restarting music
  from zero. Loop is preview-only, off when the editor opens, and never changes
  the saved edit or export.
- Click or drag the ruler, music waveform or playhead to navigate the edit.
  The source inspector follows the clip under the cursor. Playback pauses while
  dragging and resumes on release only if it was playing before. Cancellation
  restores the previous position. With the timeline focused, use Left/Right for
  one frame, Page Up/Down for one second, and Home/End for the edit boundaries.
- In/Out are integer source frames, with an exclusive Out bound.
- Slip changes both bounds without changing duration.
- Select a clip, seek inside it, then Cut at cursor.
- Duplicate and Ripple delete never delete media files.
- Take changes only this occurrence. A shorter take is rejected until the range fits.
- Undo/Redo keep up to 100 commands while the editor is open.
- Play/Pause, one-frame steps, ruler/waveform seek and zoom help musical alignment.
  Space toggles playback when focus is not in an input.

Music is fixed at zero. The measured waveform is normalized for display only;
the AUDIO output is unchanged. **Music volume** is saved as an assembly setting.
Without an explicit dialogue track, browser take audio remains muted (legacy behavior).

## Independent dialogue

Select a video occurrence and choose **Dialogue from selected take**. The excerpt
starts aligned with that occurrence's source In, but keeps the remaining available
take audio beyond the visual cut. It is not speech detection or voice isolation:
ambience and other sounds baked into the take remain audible.

- Drag an excerpt to position it independently, including J/L cuts over picture cuts.
- Its own handles trim the audio, without trimming the picture. Left-edge trimming
  keeps the remaining sound in place. Arrow keys move/trim one frame.
- Exact Position, In, Out and Volume controls are independent of video controls.
  Volume zero mutes the excerpt; Delete dialogue removes it. Undo/redo includes audio.
- Source windows use integer frames at the document timebase; Out is exclusive.
  Original-source audio can extend beyond its detected shot boundary into the
  remaining source file; the video occurrence still keeps its original bounds.
- Video reorder, duplicate, delete, take replacement and ripple trim **do not**
  move or duplicate dialogue. Reposition it explicitly if picture edits change sync.
- Overlaps are mixed; overlapping clips are displayed on separate visual rows.
- Preview transport, seeks, pause, loop and error cancellation synchronize the
  selected dialogue windows with music. No take audio is mixed twice.
- An audible excerpt extending beyond the montage blocks export with an explicit
  error. Extend the picture within available source frames, move/trim the audio,
  or mute it; the exporter never cuts the end silently.

The optional version-1 `dialogue` array is backward compatible: absent preserves
legacy assembly audio; present (even empty) replaces cut-linked take audio.
Music does not mute this explicit dialogue bus. Lower Music volume for speech;
manual export does not add automatic ducking or other audio effects. Standalone
Shot Assemble can optionally use `duck_music` with an independent dialogue bus.
Studio replaces its original-source-soundtrack fallback when explicit dialogue
is present, preventing that same source speech from being played twice; separate
retained/replacement music is unaffected.
It also accepts an optional `dialogue` AUDIO input starting at zero, or
`voice_shots=true, preserve_dialogue=true` to retain full available take audio.
The latter disables internal cuts and speed effects, and refuses an overlong
audio tail rather than silently trimming it. Existing standalone workflows keep
the old default (`preserve_dialogue=false`).

Existing saved edits are not automatically populated or rewritten. Raw takes and
generation plans are never modified. Speech missing from the raw take cannot be
restored by this editor.

## Limits

One sequential video track; no gaps, transitions, speed changes or compositing.
Automatic plan effects, sub-cuts, text and motion layers are **not reapplied**:
their timings would be wrong after arbitrary cuts. The original list is untouched.
This editor does not yet provide Regenerate or AI Extend. Unused source frames
can already be revealed by extending the trim within the available take.

At source switches, playback may pause while media loads. The audio clock pauses
with it, rather than silently drifting. This is not a gapless or frame-perfect
NLE preview; proxy preloading and measured synchronization remain planned.
Seeks and playback starts are cancellable. Music starts only once the muted
video has started, and both players stop on a decoding/startup failure.
Each media wait/start has a 15-second timeout with an explicit error and can
be retried with Play. During startup, Pause cancels the pending request.
Superseded requests cannot pause or restart a newer playback session.

The edit, take references and preview metadata survive workflow save/reload.
If source contents/takes change, an incompatible document is rejected. Back up
`edit_json` before using **Reset edit**; reset discards the montage, not its media.
Keep this node downstream of generation: do not feed its derived shot IDs back
into Apply Shot Metadata.

## Francais

Monter les prises sans modifier la generation : brancher la liste de shots et
la musique, executer une fois, puis ouvrir l'editeur. Glisser les clips pour les
reordonner, leurs bords pour les trimmer; utiliser Cut, Slip, Duplicate et
Undo/Redo. La waveform correspond a la vraie musique. Les modifications sont
sauvegardees dans le workflow; executer de nouveau pour exporter.

Cette premiere version monte les prises brutes, sans les effets du plan
automatique. La regeneration et l'extension IA ne sont pas encore integrees.
