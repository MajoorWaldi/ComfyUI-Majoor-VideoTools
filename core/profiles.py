"""Editing profiles: a starting strategy for an edit (rhythm, camera, art direction and five dials), written for the LLM that plans it.

A profile is a skill file of kind `profile` in the skills folder (`profile_<id>.md`): its header gives the length and the value of each dial,
its text the rhythm, the camera and the art direction. Add a file to add a profile. A profile never restricts: the brief of the user
and the extra instructions always win, and the text says so."""
from .errors import MajoorError
from .skills import list_skills, load_skill

PREFIX = "profile_"

# five dials, each with the words the LLM reads
DIALS = {
    "cut_density": {"low": "few cuts (about 0.5 to 1 per second), long takes", "medium": "a steady pace (about 1 to 2 cuts per second)", "high": "dense cutting (2.5 to 4 cuts per second) with bursts"},
    "transition_intensity": {"subtle": "mostly hard cuts and soft dissolves, no flashy transitions", "moderate": "a transition on about a quarter of the cuts, chosen with intent", "bold": "visible transitions (whip, flash, punch) on about a third of the cuts"},
    "creative_freedom": {"faithful": "stay close to the brief and the references, add nothing it does not suggest", "balanced": "follow the brief and add your own ideas where it is silent", "free": "take liberties: surprising angles, effects and ideas that serve the brief"},
    "reference_fidelity": {"loose": "references give the mood only", "balanced": "keep the identity, the outfit and the look of the references, vary the rest", "strict": "keep the identity, the outfit, the colors and the objects of the references exactly in every shot"},
    "narrative_coherence": {"low": "shots may be independent moments, a mood more than a story", "medium": "a clear beginning, middle and end, shots may jump in time or place", "high": "one continuous story: each cut is motivated, space and time stay consistent from shot to shot"},
}


def list_profiles() -> list[str]:
    return [i[len(PREFIX):] for i in list_skills("profile") if i.startswith(PREFIX)]


def music_text(profile: str, **dials: str) -> str:
    """What the profile asks of a music: its own direction and the density of the cuts. 'none' gives an empty block."""
    if profile == "none":
        return ""
    if profile not in list_profiles():
        raise MajoorError(f"Unknown profile '{profile}'. Available: {['none', *list_profiles()]}")
    meta = load_skill(PREFIX + profile).meta
    density = dials.get("cut_density", "auto")
    density = meta.get("cut_density", "") if density == "auto" else density
    lines = [f"MUSIC DIRECTION OF THE PROFILE ({load_skill(PREFIX + profile).name}; the BRIEF wins when it differs)"]
    if meta.get("music"):
        lines.append(f"Music: {meta['music']}")
    if density in DIALS["cut_density"]:
        lines.append(f"The edit has {DIALS['cut_density'][density]}: the music must carry that energy.")
    return chr(10).join(lines)


def profile_text(profile: str, **dials: str) -> str:
    """The EDITING PROFILE block. A dial left on 'auto' takes the profile's own value. 'none' gives an empty block."""
    if profile == "none":
        return ""
    if profile not in list_profiles():
        raise MajoorError(f"Unknown profile '{profile}'. Available: {['none', *list_profiles()]}")
    skill = load_skill(PREFIX + profile)
    lines = [f"EDITING PROFILE: {skill.name} (a starting strategy, never a restriction: the BRIEF and any instruction of the user win when they differ)"]
    if skill.meta.get("length"):
        lines.append(f"Suggested length: {skill.meta['length']} (only when the brief and the rhythm give none)")
    lines.append(skill.body.strip())
    for name, words in DIALS.items():
        value = dials.get(name, "auto")
        if value != "auto" and value not in words:
            raise MajoorError(f"{name} '{value}' is not supported. Available: {['auto', *words]}")
        value = skill.meta.get(name, "") if value == "auto" else value
        if value not in words:
            raise MajoorError(f"Profile '{profile}': the header needs {name}: one of {list(words)}")
        lines.append(f"{name.replace('_', ' ').capitalize()}: {value}, {words[value]}")
    lines.append("Where an EDIT RHYTHM is given, its cuts are fixed: cut density only guides the rest.")
    return chr(10).join(lines)
