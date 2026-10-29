"""Camera looks: the camera, the lens and the aperture of the whole edit, one choice of Edit Mode. The planner writes them into every shot and the prompt enhancer into the brief (creative mode)."""
CAMERAS = {
    "digital_cinema": "shot on a modular 8K digital cinema camera with a premium modern prime lens at 35 mm, f/4: clean, sharp, neutral colors",
    "film_70mm": "shot on a grand-format 70 mm film camera with a warm cinema prime lens at 50 mm, f/2.8: fine grain, deep colors, soft highlight roll-off",
    "film_16mm": "shot on a classic 16 mm film camera with a vintage prime lens at 25 mm, f/2: visible grain, soft contrast, slightly faded colors",
    "anamorphic": "shot on a full-frame cinema camera with a classic anamorphic lens at 40 mm, f/2.8: a wide cinemascope frame, oval bokeh, horizontal flares",
    "vintage_70s": "shot with a 1970s cinema prime lens at 35 mm, f/2: soft halation around the highlights, a warm cast, a gentle vignette",
    "portrait_bokeh": "shot with a swirl-bokeh portrait lens at 85 mm, f/1.4: a razor-thin focus on the eyes, a creamy swirling background",
    "macro_detail": "shot with an extreme macro lens at 100 mm, f/4: textures and details fill the frame, a shallow focus",
    "ultra_wide": "shot with an ultra-wide 14 mm lens at f/8: everything in focus, a strong perspective, a low camera",
}
NONE = "none"


def camera_text(look: str) -> str:
    """The instruction for the planner and the enhancer, empty for 'none' or a look that does not exist."""
    phrase = CAMERAS.get(look, "")
    return f"CAMERA LOOK: {phrase}. Say it in the camera and lens words of every prompt, never as a text on the screen." if phrase else ""
