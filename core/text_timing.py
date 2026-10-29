"""Reading hold shared by legacy overlays and unified finishing advisories."""

TEXT_TIMING = {'word_stagger': .09, 'exit_ratio': .5, 'minimum_exit': .1}


def reading_seconds(content: str) -> float:
    return 1.0 + .25 * max(len(content.split()) - 3, 0)


def reading_budget(content: str, entrance: float = 0, exit: float = 0) -> float:
    """Animation time is additional to the fully readable hold."""
    return max(0, entrance) + reading_seconds(content) + max(0, exit)


def animated_reading_budget(content, animation='none', entrance=.25, out='none', repeat=1):
    count = max(1, int(repeat))
    entry = max(0, entrance) if animation != 'none' else 0
    if animation == 'words':
        entry += max(0, len(content.split()) * count - 1) * TEXT_TIMING['word_stagger']
    exit = max(TEXT_TIMING['minimum_exit'], entrance * TEXT_TIMING['exit_ratio']) if out == 'fade' else 0
    return reading_budget(' '.join([content] * count), entry, exit)
