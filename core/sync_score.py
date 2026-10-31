"""How well a list of visual events (text appearing, cuts, flashes) lands on the accents of the music. Measured, for the report of an edit."""
import numpy as np


def sync_score(event_times, accent_times, tolerance=.15) -> dict:
    """Each event is compared with the nearest accent. `within` is the share of events at most `tolerance` seconds from one; `score` is that share in percent."""
    events, accents = np.asarray(event_times, dtype=float), np.asarray(accent_times, dtype=float)
    if not len(events) or not len(accents):
        return {"events": int(len(events)), "mean_offset": None, "within": None, "score": None}
    offsets = np.abs(events[:, None] - accents[None, :]).min(axis=1)
    within = float((offsets <= tolerance).mean())
    return {"events": int(len(events)), "mean_offset": round(float(offsets.mean()), 3), "within": round(within, 3), "score": round(within * 100)}
