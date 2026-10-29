# Prompts

The workflows of this pack do not paste prompts: **Edit Skills** loads them from `../../skills/` at run time (one skill per LLM call), so a skill file edited there is used at once. The files of this folder are for people who want to read a prompt, or paste it into a plain *Generate Text* node of their own graph.

| File | What it is | Where it comes from |
|---|---|---|
| `timeline_planner.txt` | **System.** The edit planner: few generated shots, many `sub_cuts`, speed, zoom, transitions, text; names the character `<Picture 1>`; given an EDIT RHYTHM it writes only prompts and effects. Writes the JSON that Create Timeline `source = json` reads. Example plan: `../timeline_fashion_motion.json`. | Skill `timeline_planner`, composed with the default settings of Edit Skills (the `locations` part is off: switch it on in Edit Skills to get a place per shot) |
| `dynamic_edit_skill.txt` | **System.** The general prompt for a vision-language model: writes the whole edit plan for any dynamic video (character, product, ad, motion graphics, UGC, trailer) from a brief, pictures (`<Picture 1..5>`) and optionally the frames of a reference edit to rebuild with new subjects. Knows every effect of the engine: cuts, speed, zoom, transitions, text, overlays, split screens. Example plan: `../dynamic_edit_product_ad.json`. | Skill `dynamic_edit_skill`, default settings |
| `h3_shot_prompt_from_plan.txt` | **System.** Turns the brief of one shot of a plan (`rhythm_text`, `prompt`, `fx_json` of Select Shot) into the MiniMax H3 full-reference prompt: `<Subject N>`, the task tag, one `[Shot N]` per cut, the camera words of the guide. The dialogue and plate parts are off here (Edit Skills turns them on with a voice, a dialogue or a place). | Skill `h3_shot_prompt_from_plan`, default settings |
| `timeline_planner_v1.txt` | **System.** The first planner: one long cut per shot, no effects. Example: `../timeline_aura_farming.json`. Kept for reference. | |
| `timeline_planner_user_request_*.txt` | **User request** to send with the picture to the planner (an aura-farming edit; a dynamic edit). | |
| `h3_edit_request_selective_identity.txt` | **Edit request** of a remix: replace the model of the shot with `<Picture 1>`, keep positions and timing. The `WHAT TO REPLACE` control of `SECATOR Remix` starts from a later version of the same request that also keeps the subject of `<Picture 1>` as the picture shows it (`remix_instruction` in `skills/mode_remix_replace.md`); this file is the earlier one, from the external workflow it was written for. | |

The three skill copies are kept identical to what Edit Skills gives with its default settings by a test (`test_copies_in_examples_match_the_skills`): after editing a skill, regenerate the copy.

The skills that have no copy here (`shot_reader`, `remix_shot_prompt`, `clip_judge`, `prompt_enhancer`, `music_brief_*`, the `profile_*` styles and the `mode_*` settings) are read from `../../skills/` only; the table of all the skills is in the main README.

**Feeding `h3_shot_prompt_from_plan.txt` by hand**: the prompt of the LLM chat is the brief of the shot, for example a StringConcatenate chain of Select Shot's `rhythm_text`, a line break, `prompt`, a line break, `fx_json`, and `TAKE LENGTH: <generation_seconds> s`. Use `format = text`, thinking off, and the character picture as the chat image.
