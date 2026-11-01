"""Shot sizes decided from the content of the edit, not from a fixed alternation.

No model: a few readable rules over what is already measured. For each shot of one character, in order:

* the first shot of the edit establishes the place: wide when it lasts long enough to be read, else medium;
* the last shot of a character's part settles: medium, unless it is short or energetic;
* a short shot (under a second) is a close-up, an energetic one (chorus, drop) goes closer still when it is short;
* a long shot that is not energetic opens up: wide, or medium when the character just appeared;
* otherwise medium and close-up alternate;
* the same size never comes three times in a row.

`energy` is optional, 0..1 per shot (loudness around the shot); without it the rules use duration and position only."""
SIZES = ("wide", "medium", "close_up", "extreme_close_up")
SHORT, LONG, ESTABLISH = 1.0, 3.5, 1.5
HIGH_ENERGY = .66


def _closer(size: str) -> str:
    return SIZES[min(SIZES.index(size) + 1, len(SIZES) - 1)]


def _wider(size: str) -> str:
    return SIZES[max(SIZES.index(size) - 1, 0)]


def choose_sizes(shots, *, first_of_edit: str | None = None) -> dict[str, str]:
    """{shot_id: size} for the shots of one character. Each shot is {"id", "duration" (seconds), "energy" (0..1 or None)}, in time order.

    `first_of_edit` is the id of the shot that opens the whole edit, when it belongs to this character."""
    result, history = {}, []
    for i, shot in enumerate(shots):
        duration, energy = float(shot["duration"]), shot.get("energy")
        energetic = duration < SHORT or (energy is not None and energy >= HIGH_ENERGY)
        last = i == len(shots) - 1 and len(shots) > 1 and not energetic  # a fast closing shot stays close
        if shot["id"] == first_of_edit:
            size = "wide" if duration >= ESTABLISH else "medium"
        elif last:
            size = "medium"
        elif duration < SHORT:
            size = "extreme_close_up" if energy is not None and energy >= HIGH_ENERGY else "close_up"
        elif duration >= LONG and (energy is None or energy < HIGH_ENERGY):
            size = "medium" if i == 0 else "wide"
        elif energy is not None and energy >= HIGH_ENERGY:
            size = "close_up"
        else:
            size = "medium" if not history or history[-1] != "medium" else "close_up"
        if len(history) >= 2 and history[-1] == history[-2] == size:  # never three of a kind
            size = _closer(size) if size != SIZES[-1] else _wider(size)
        history.append(size)
        result[shot["id"]] = size
    return result
