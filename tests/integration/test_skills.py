import json
import re

import pytest

from majoor_videotools.core import skills as sk
from majoor_videotools.core.errors import MajoorError

ROOT = sk.SKILLS.parent


def test_parse_header_modules_and_nesting():
    text = "---\nname: T\nkind: planner\n---\nalways {{DURATION}}\n<<module a>>\nA <<module b default=off>>B<<end>> A2\n<<end>>\ninline <<module c>>C<<end>> end\n"
    skill = sk.parse_skill("t", text)
    assert (skill.name, skill.kind, skill.modules) == ("T", "planner", ["a", "b", "c"])
    full, on = sk.compose(skill, {"b": True}, {"DURATION": 12})
    assert "always 12" in full and "A B A2" in full and "inline C end" in full and on == ["a", "b", "c"]
    default, _ = sk.compose(skill)
    assert "B" not in default.replace("A", "")  # b is off by default
    nothing, _ = sk.compose(skill, {"a": False, "c": False})
    assert nothing.strip() == "always 8\n\ninline  end".strip() or "A" not in nothing
    assert "C" not in nothing


@pytest.mark.parametrize("text, message", [
    ("<<module a>>x", "not closed"),
    ("x<<end>>", "no <<module>>"),
    ("---\nkind: nope\n---\nx", "unknown kind"),
    ("---\nname: x\nbody", "not closed"),
])
def test_parse_errors(text, message):
    with pytest.raises(MajoorError, match=message):
        sk.parse_skill("t", text)


def test_unknown_skill_and_bad_names():
    with pytest.raises(MajoorError, match="Unknown skill"):
        sk.load_skill("does_not_exist")
    with pytest.raises(MajoorError, match="Invalid"):
        sk.load_skill("../core/skills")


def test_the_shipped_skills_load():
    assert set(sk.prompt_skills()) == {"dynamic_edit_skill", "timeline_planner", "h3_shot_prompt_from_plan", "music_brief_from_plan", "music_brief_minimax3", "music_brief_yue2", "prompt_enhancer", "remix_shot_prompt", "shot_reader", "clip_judge", "overlay_reader"}
    assert {i for i in sk.list_skills() if i not in sk.prompt_skills()} == {i for i in sk.list_skills() if i.startswith(("profile_", "mode_"))}  # profiles and modes are data, not prompts
    assert sk.list_skills("h3_writer") == ["h3_shot_prompt_from_plan", "remix_shot_prompt"]
    assert sk.list_skills("music_writer") == ["music_brief_from_plan", "music_brief_minimax3", "music_brief_yue2"]
    assert all(sk.load_skill(i).description for i in sk.list_skills())


def test_copies_in_examples_match_the_skills():
    for skill_id in ("timeline_planner", "h3_shot_prompt_from_plan", "dynamic_edit_skill"):  # the prompt that Edit Skills gives with its default settings
        skill = sk.load_skill(skill_id)
        text, _ = sk.compose(skill, sk.module_states(skill))
        assert text == (ROOT / "examples/prompts" / f"{skill_id}.txt").read_text(encoding="utf-8"), skill_id


def test_switches_remove_their_text_and_shrink_the_prompt():
    d = sk.load_skill("dynamic_edit_skill")
    full, _ = sk.compose(d, sk.module_states(d))
    bare, on = sk.compose(d, sk.module_states(d, overlays_splits=False, text_overlays=False, reference_mode=False, genre="none"))
    assert len(bare.split()) < len(full.split())
    assert not re.search(r"ghost cop|double exposure|split screen|MODE B|surimpression", bare, re.I)
    assert "not_reference_mode" in on and "genre_header" not in on
    assert "overlay" in full.lower() and "MODE B" in full


def test_genre_keeps_only_its_advice():
    d = sk.load_skill("dynamic_edit_skill")
    states = sk.module_states(d, genre="product_ad")
    assert states["genre_product_ad"] and not states["genre_ugc"]
    text, _ = sk.compose(d, states)
    assert "Product ad:" in text and "Motion graphics:" not in text
    with pytest.raises(MajoorError, match="genre"):
        sk.module_states(d, genre="western")


def test_variables_and_extra_instructions():
    d = sk.load_skill("dynamic_edit_skill")
    text, _ = sk.compose(d, {}, {"DURATION": "12", "ASPECT": "16:9", "FPS": ""}, "Brand: Aura.")
    assert "12" in text and "16:9" in text and "{{" not in text
    assert text.rstrip().endswith("Brand: Aura.") and "EXTRA INSTRUCTIONS" in text


def test_example_plan_loses_the_effects_that_are_off():
    d = sk.load_skill("dynamic_edit_skill")

    def example(**kw):
        text, _ = sk.compose(d, sk.module_states(d, **kw))
        return json.loads(text[text.rindex('{\n  "title"'):])

    full = example()
    assert any("overlay" in s for s in full["shots"]) and any("split" in s for s in full["shots"]) and any("text" in s for s in full["shots"])
    bare = example(overlays_splits=False, text_overlays=False)
    assert not any({"overlay", "split", "text"} & set(s) for s in bare["shots"])
    assert len(bare["shots"]) == len(full["shots"])


def test_user_message():
    message = sk.user_message("a cream ad", "EDIT RHYTHM: 1 s", 2)
    assert message.startswith("BRIEF\na cream ad") and "<Picture 1> <Picture 2>" in message and message.endswith("EDIT RHYTHM: 1 s")
    assert sk.user_message("", "", 0) == ""


def test_the_message_announces_the_pictures_and_the_frames_of_each_video():
    text = sk.user_message("a brief", "EDIT RHYTHM", 2, ((1, 3, 10), (2, 11, 18)))
    assert "<Picture 1> <Picture 2> are the images of this chat" in text
    assert "<Video 1> = images 3 to 10 of this chat (8 frames in time order" in text and "<Video 2> = images 11 to 18" in text
    assert "VIDEOS" not in sk.user_message("a brief", "", 2)
    writer = sk.load_skill("h3_shot_prompt_from_plan").body
    assert "VIDEOS block" in writer and "Never write a <Video k> that the VIDEOS block does not list" in writer


def test_the_prompt_enhancer_keeps_the_brief_reads_the_pictures_and_the_videos():
    skill = sk.load_skill("prompt_enhancer")
    assert skill.kind == "other" and "prompt_enhancer" in sk.prompt_skills()
    text, _ = sk.compose(skill, extra="A reference video (<Video 1>) gives the rhythm.")
    for needed in ("Keep the intent", "Read the pictures", "<Video 1>", "EXTRA INSTRUCTIONS FROM THE USER", "OUTPUT", "Never describe a face in detail"):
        assert needed in text, needed
    assert "Shot 1" in text and "Do not write" in text  # the shots are the planner's: the enhancer is told not to write them


def test_the_transitions_that_the_skills_teach_are_the_ones_the_engine_renders():
    import re

    from majoor_videotools.core.fx import LOOKS, TRANSITIONS

    named = re.compile(r'"((?:flash|whip|fade|dissolve|crossfade)\w*|blur|punch|glitch|shake|strobe|invert|cut)"')
    for skill_id in (i for i in sk.list_skills() if i != "overlay_reader"):  # its quoted names are the animations of Motion Graphics, not transitions
        taught = set(named.findall((ROOT / "skills" / f"{skill_id}.md").read_text(encoding="utf-8")))
        assert taught <= set(TRANSITIONS), (skill_id, sorted(taught - set(TRANSITIONS)))
    planner = (ROOT / "skills" / "timeline_planner.md").read_text(encoding="utf-8")
    assert all(f'"{name}"' in planner for name in TRANSITIONS), "the planner names every transition"
    assert all(f'"{name}"' in planner for name in LOOKS), "and every look"


def test_a_voice_and_a_dialogue_switch_the_dialogue_module_on():
    message = sk.user_message("brief", "Shot 1", 1, (), voice=True, dialogue='0-3 s: "Welcome."')
    assert "<Audio 1> = the voice sample of <Subject 1>" in message and 'DIALOGUE (the lines spoken in this shot' in message and '0-3 s: "Welcome."' in message
    assert "AUDIO" not in sk.user_message("brief") and "DIALOGUE" not in sk.user_message("brief")
    for skill_id in ("remix_shot_prompt", "h3_shot_prompt_from_plan"):
        skill = sk.load_skill(skill_id)
        off, _ = sk.compose(skill, sk.module_states(skill))
        on, _ = sk.compose(skill, sk.module_states(skill, dialogue=True))
        assert "<Audio 1>" not in off and "<Audio 1>" in on, skill_id
        assert ("no dialogue" in off.lower()) and ("no dialogue, no singing" not in on.lower()), skill_id


def test_a_shot_gets_the_lines_that_start_inside_it():
    from majoor_videotools.core.dialogue import lines_of_shot

    dialogue = '0-3 s: "Welcome."\n10-13 s: "Same man. Different era."\n00:13-00:15: Watch this.'
    assert lines_of_shot("Shot 1 of 6 · 00:11.47–00:12.33 · 0.87 s", dialogue) == ""  # the second line started before this shot
    assert lines_of_shot("Shot · 00:09.00–00:10.50", dialogue) == '1.00-1.50 s: "Same man. Different era."'  # times counted from the start of the shot, cut at its end
    assert lines_of_shot("Shot · 00:00.00–00:02.00", dialogue) == '0.00-2.00 s: "Welcome."'
    assert lines_of_shot("a header without times", dialogue) == dialogue  # no times: every line
    assert lines_of_shot("Shot · 00:00.00–00:02.00", "Welcome everybody") == "Welcome everybody"  # no line has times: kept as it is


def test_locations_and_the_plate_of_a_shot():
    planner, writer = sk.load_skill("timeline_planner"), sk.load_skill("h3_shot_prompt_from_plan")
    asked = sk.compose(planner, sk.module_states(planner, locations=True))[0]
    assert "- location:" in asked and "- location:" not in sk.compose(planner, sk.module_states(planner))[0]
    assert "PLACE block" in sk.compose(writer, sk.module_states(writer, plate=True))[0] and "PLACE block" not in sk.compose(writer, sk.module_states(writer))[0]
    message = sk.user_message("b", "", 3, (), plate=True)
    assert "<Picture 1> <Picture 2> <Picture 3> are the images" in message and "<Picture 3> is the empty plate of the place" in message
    assert "PLACE" not in sk.user_message("b", "", 3)


def test_the_remix_writer_knows_whether_h3_gets_the_source_frames():
    writer = sk.load_skill("remix_shot_prompt")
    edit, _ = sk.compose(writer, sk.module_states(writer, reference_mode=True))
    pose, _ = sk.compose(writer, sk.module_states(writer, reference_mode=False))
    assert "[video editing]" in edit and "H3 receives <Video 1> itself" in edit and "[reference generation]" not in edit
    assert "[reference generation]" in pose and "H3 does NOT receive the frames" in pose and "[video editing]" not in pose and "Never write <Video 1>" in pose
    assert "<Video 1> (pose, framing, camera and timing" in edit and "<Video 1> (pose, framing, camera and timing" not in pose
    for text in (edit, pose):
        assert "SEVERAL PEOPLE" in text and "OUTFITS" in text
    reader = sk.load_skill("shot_reader").body
    assert "GROUP: yes or no, always written" in reader and "PEOPLE (<Video 1>)" in reader
