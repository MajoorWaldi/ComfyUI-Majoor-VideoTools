# Audit checklist (text, music, motion, lipsync)

Source: the audit document "HyperKut Studio — Audit & plan créatif" of 2026-10-31. Done means code and tests exist and pass without a GPU. Items that need a model, a GPU run or a UI are listed as open with the reason.

## P0 Text and audio as the backbone
- [x] Word list with times, checked (`core/words.py` `parse_words`)
- [x] Lyrics without times spread over the vocal phrases (`align_lyrics`; an estimate by letter count, not a forced alignment)
- [x] Cuts on the vocal phrases (music edit mode `phrases`, `core/music_cuts.py`)
- [x] Word groups, accent words on beats, word offsets for a text layer (`phrase_groups`, `mark_accents`, `word_offsets`)
- [x] Node Music Words and Structure (`nodes/music_words.py`)
- [ ] Transcription of a track (needs a local speech model, e.g. WhisperX; give `words_json` meanwhile)
- [ ] Forced alignment on sung voice (needs a model)
- [x] Real word times in the HyperFrames text renderer: a text layer takes `word_times` (seconds from its start) instead of the fixed `word_stagger`
- [ ] Planner receives the phrase boundaries in its prompt

## P1 Kinetic typography
- [x] Accent words get a bigger size and a color (`kinetic_lyrics` template)
- [x] 11 fonts: `impact`, `clean`, `serif`, `mono`, `garamond`, `code`, `league`, `archivo`, `montserrat`, `poppins`, `space` (SIL OFL, resolved by the HyperFrames compiler; the first render of a family needs the network). The frame renderer uses system fonts
- [x] New animations `scale_pop`, `blur_in`, `wiggle`, `mask_reveal`, `scramble`, `split_letters`, `karaoke_fill` (HyperFrames compositor; the frame renderer of `core/motion.py` approximates them: letters appear, no blur)
- [x] Text behind the subject (`behind: true`, template `title_behind`; both renderers, needs the subject mask)
- [x] Particles: Lottie stickers (`burst`, `sparkle`) and the parametric `particles` effect (count, speed, size, color; fixed formula, repeatable)

## P2 Motion library
- [x] Templates that expand into the existing layers: `end_card`, `rec_hud`, `caption_mono`, `punch_word`, `kinetic_lyrics` (`core/motion_library.py`)
- [x] Templates accepted in layer JSON (`{"template": name, ...}` in `parse_layers`)
- [x] Layout templates `split_diagonal`, `split_stack`, `circle_mask`, `picture_in_picture`, checked in a real HyperFrames render
- [x] Grid layout `tiles_grid` (the picture repeated 2 by 2)
- [x] Overlay transitions as templates: `flash_hit`, `whip_wipe` (effects `flash`, `wipe`, drawn by both renderers)
- [x] Frame overlays `letterbox`, `polaroid_frame` (effects `letterbox`, `frame`)
- [x] `glitch_hit`, `zoom_punch` (a push that reads as a match cut when two shots are cut on it)
- [x] `cutout_echo`: outline and offset copies behind the subject
- [x] The planner skill lists the templates; rows are checked against that list. Not yet qualified with the real LLM
- [x] Lottie layer type: names limited to `web/lottie/*.json`, `lottie-web` 5.12.2 in the HyperFrames runtime

## P3 Understanding the music
- [x] Sections intro, build, drop, break, outro (`core/music_structure.py` `track_sections`)
- [x] Downbeats (`find_downbeats`)
- [ ] Stem separation (voice, drums, bass; needs a model)
- [ ] Rules that put strong transitions on downbeats and drops (planner and cut rules)

## P4 Lipsync
- [ ] Qualify the native H3 audio reference (needs GPU runs)
- [ ] Dedicated lipsync model (LatentSync, InfiniteTalk, Wan 2.2 S2V: availability, VRAM and licences to check)
- [ ] TTS and animated subtitles chain

## P5 Recipe profiles
- [x] `kinetic_lyrics`, `punch_text_anime`, `editorial_layouts`, `camera_rec_hud`, `cutout_collage`, `lipsync_rap`, `brand_film_noir`
- [x] Recipes selectable in the Studio style list (settings.ts, i18n.ts)
- [x] Recipe cards with drawn thumbnails in the Studio gallery
- [ ] Presets with generated sample media

## P6 Interface
- [x] Template gallery and text track in Options, both editing `motion_layers`
- [x] Choosing a recipe turns finishing on (`motion_design`)
- [ ] Text track under the main timeline: the track is in Options; layers are in edit time, the main timeline is per shot
- [ ] Live HyperFrames preview: the compositor lives in VideoTools, the Studio would have to host it

## P7 Quality loop
- [x] Sync score of events against accents (`core/sync_score.py`, reported by Music Words)
- [x] Text layers scored against the accents in the edit report (`text_sync`, numeric layer starts only)
- [x] `edit_review` skill for a vision model reading the contact sheets. Not run: needs the LLM on the GPU

## Done earlier in this work
- [x] Character casting: planner skill, validation, Apply Casting node, Studio option and workflow
- [x] Casting of several characters from one prompt, with a shared look

## Checked on GPU in the Studio (music mode, 9 s vocal track)
- [x] Casting of three characters from one prompt, with the vocal phrases given to the planner
- [x] Cuts on vocal phrases, particles, flashes, end card, letterbox, `scramble`, `karaoke_fill`, kinetic lyrics
- [x] Subject mask jobs (BiRefNet): outline, text behind the subject, diagonal split, 2x2 tiles. Default mask frames lowered to 30
- [ ] Echo copies on a dark scene, lipsync on the generated faces, a Text-mode job with generated music
