"""Pure shared validation for declarative motion and sound-event rows."""

EVENT_ROLE_PRIORITY = {"action": 4, "reveal": 3, "narrative": 2, "decoration": 1}
EVENT_ROLES = frozenset(EVENT_ROLE_PRIORITY)
SOUND_EFFECTS = frozenset({
    "shutter", "impact", "swell", "whoosh", "hit", "glitch", "sub_drop", "riser",
    "reverse", "downlifter", "click", "pop", "tick", "sparkle", "tape_stop",
    "stutter", "ui_click_soft", "ui_click_crisp", "notification_soft",
    "notification_confirm", "notification_alert", "metal_tick", "metal_chime",
    "glass_ping", "stereo_whoosh_lr", "stereo_whoosh_rl", "stereo_sweep",
    "logo_soft", "logo_bold", "logo_sparkle",
})


def validate_motion_rows(rows):
    """Validate fields shared by the engine and Studio before any rendering work."""
    if not isinstance(rows, (list, tuple)) or len(rows) > 120:
        raise ValueError("Motion layers must contain at most 120 objects")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("Motion layers must be objects")
        role = row.get("event_role", "decoration")
        if not isinstance(role, str) or role not in EVENT_ROLES:
            raise ValueError("Motion event_role must be action, reveal, narrative or decoration")
        sound = row.get("sfx")
        if sound not in (None, "") and (not isinstance(sound, str) or sound not in SOUND_EFFECTS):
            raise ValueError(f"Unknown motion sound effect in layer {index}")
    return rows
