"""Small native YuE2 adapter; no inference, network or optional dependencies here."""
import re
import warnings

from .errors import MajoorError
from .vendor.yue2.instrumentalize import convert_score

WORDLESS = '[Chorus]\nOh oh\nAh ah\nOh oh\nAh ah'


def music_style(prompt: str, bpm: int = 120, key: str = 'C major', lyrics: str = '') -> tuple[str, str, bool]:
    if not prompt.strip():
        raise MajoorError('YuE2 needs a musical direction')
    text = prompt.strip()
    quiet = bool(re.search(r'\b(?:no\s+(?:vocals?|voices?|singing|rap)|without\s+(?:vocals?|voices?|singing)|sans\s+(?:voix|chant|paroles))\b',text,re.I))
    vocals = bool(re.search(r'\b(?:vocals?|vocalises?|singing|sung|rapper|rapping|rap|chanting|chants?|chops?|choir|voix|chant|chante|choral)\b',text,re.I))
    instrumental = quiet or not (lyrics.strip() or vocals)
    words = '[Instrumental]' if instrumental else (lyrics.strip() or WORDLESS)
    # Keep musical metadata explicit in YuE2's style field (there are no separate native BPM/key inputs).
    metadata = (f' Tempo: {bpm} BPM.' if bpm > 0 else '') + (f' Key: {key}.' if key.strip() else '')
    return text + metadata, words, instrumental


def music_score(abc: str, instrumental: bool) -> tuple[str, dict]:
    if not abc.strip():
        raise MajoorError('YuE2 did not produce a composition plan')
    if not instrumental:
        return abc, {'instrumental': False, 'converted': False}
    recovery = {}
    try:
        converted, report = convert_score(abc, overlap='vocal', keep_chords=True)
    except (ValueError, KeyError, IndexError, ZeroDivisionError) as error:
        # The native token generator can stop inside the final Ins line. Never
        # invent its missing notes/barline or relax the strict score parser.
        lines = abc.splitlines()
        starts = [i for i, line in enumerate(lines) if line == 'V: Vocal']
        ins = [i for i, line in enumerate(lines) if line == 'V: Ins']
        final_ins_cut = (
            re.fullmatch(r'group [0-9]+, Ins: music line must end with a plain barline', str(error))
            and len(starts) > 1 and ins and starts[-1] < ins[-1]
            and ins[-1] == len(lines) - 2
            and lines[-1].strip() and not lines[-1].endswith(('|', '|]'))
        )
        if not final_ins_cut:
            raise MajoorError(f'YuE2 instrumental score preparation failed: {error}') from error
        prefix = lines[:starts[-1]]
        while prefix and prefix[-1].startswith('% '):
            prefix.pop()
        try:
            converted, report = convert_score('\n'.join(prefix) + '\n', overlap='vocal', keep_chords=True)
        except (ValueError, KeyError, IndexError, ZeroDivisionError):
            raise MajoorError(f'YuE2 instrumental score preparation failed: {error}') from error
        recovery = {'discarded_incomplete_final_group': True,
                    'score_warning': 'Token-limited ABC: incomplete final voice pair discarded; preceding groups validated.'}
        warnings.warn(recovery['score_warning'], RuntimeWarning, stacklevel=2)
    return converted, {'instrumental': True, 'converted': True, **report, **recovery}
