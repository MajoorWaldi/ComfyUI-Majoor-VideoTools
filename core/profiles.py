"""Editing profiles: a starting strategy for an edit (rhythm, camera, art direction and five dials), written for the LLM that plans it.

A profile is a skill file of kind `profile` in the skills folder (`profile_<id>.md`): its header gives the length and the value of each dial,
its text the rhythm, the camera and the art direction. Add a file to add a profile. A profile never restricts: the brief of the user
and the extra instructions always win, and the text says so."""
from .errors import MajoorError
from .skills import list_skills, load_skill

PREFIX = "profile_"

# five dials, each with the words the LLM reads
DIALS = {
    "cut_density": {"low": "few cuts, long takes: each shot holds long enough to read its action (usually 3 s or more), no sub_cuts unless the brief asks", "medium": "a steady pace: most cuts last 1.5 to 3 s, with two or three sub_cuts on a shot whose action has accents", "high": "dense editing across the useful sequence, not a single token burst: combine distinct useful viewpoints with brief 3-to-6-frame accents and readable holds, guided by mood. Respect an explicit edit-cut count or independently generated-take count and distinguish them. Protect essential actions; crops reuse one take, new viewpoints require new takes. No universal minimum shot duration beyond feasible frames"},
    "transition_intensity": {"subtle": "hard cuts and, at most, a soft blur or a dip to black: no flash, whip, strobe, glitch or punch", "moderate": "a transition on about a quarter of the cuts, chosen with intent", "bold": "visible transitions (whip, flash, punch) on about a third of the cuts"},
    "creative_freedom": {"faithful": "stay close to the brief and the references, add nothing it does not suggest", "balanced": "follow the brief and add your own ideas where it is silent", "free": "take liberties: surprising angles, effects and ideas that serve the brief"},
    "reference_fidelity": {"loose": "preserve subject identity, outfit and product design; freely reinterpret reference framing, background and visual treatment where the brief leaves them open", "balanced": "preserve identity, outfit and product design while adapting reference composition and treatment to the brief", "strict": "preserve identity, outfit, product design and relevant reference visual choices, except changes explicitly requested or caused by the planned action; reference pose is not mandatory unless requested"},
    "narrative_coherence": {"low": "shots may be independent moments, a mood more than a story", "medium": "a clear beginning, middle and end, shots may jump in time or place", "high": "one causally connected story: each cut inherits the prior state; motivated changes of location, time or light are allowed unless the brief fixes them"},
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
    """The EDITING PROFILE block. A dial left on 'auto' takes the profile's own value. With profile 'none' only the dials the user chose are written (nothing when all are 'auto')."""
    if profile != "none" and profile not in list_profiles():
        raise MajoorError(f"Unknown profile '{profile}'. Available: {['none', *list_profiles()]}")
    skill = load_skill(PREFIX + profile) if profile != "none" else None
    chosen = [name for name in DIALS if dials.get(name, "auto") != "auto"]
    lines = []
    for name, words in DIALS.items():
        value = dials.get(name, "auto")
        if value != "auto" and value not in words:
            raise MajoorError(f"{name} '{value}' is not supported. Available: {['auto', *words]}")
        if skill:
            value = skill.meta.get(name, "") if value == "auto" else value
            if value not in words:
                raise MajoorError(f"Profile '{profile}': the header needs {name}: one of {list(words)}")
        if value != "auto":
            lines.append(f"{name.replace('_', ' ').capitalize()}: {value}, {words[value]}")
    if not skill and not chosen:
        return ""
    head = [f"EDITING PROFILE: {skill.name} (a starting strategy, never a restriction: the BRIEF and any instruction of the user win when they differ)" if skill else "EDITING SETTINGS chosen by the user"]
    if skill and skill.meta.get("length"):
        head.append(f"Suggested length: {skill.meta['length']} (only when the brief and the rhythm give none)")
    if skill:
        head.append(skill.body.strip())
    if skill and chosen:
        lines.append("The settings the user chose (" + ", ".join(n.replace("_", " ") for n in chosen) + ") win over the profile text above where they differ: a softer transition setting means no flash, whip, strobe, glitch or punch whatever the profile suggests; a different cut density replaces its pace.")
    lines.append("Shared direction: explicit user constraints win over every profile or dial. Keep each shot useful to the intended story, performance or mood; a new crop alone is not a new story event. Preserve identity, product design and explicitly fixed setting constraints while allowing motivated changes of location and planned state changes. Musical style follows the brief; an accent or drop is a timing fact only when supported by supplied audio measurements. Do not invent musical timing.")
    lines.append("Where an EDIT RHYTHM is given, its shot boundaries and existing internal cuts are fixed. Cut density may guide finer sub-cuts inside shots that have no fixed internal cuts, without adding generations.")
    return chr(10).join(head + lines)
