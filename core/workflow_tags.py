import json
import os
from pathlib import Path


def workflow_tags(hidden, video, root) -> dict | None:
    """The tags that reopen the graph of this take in ComfyUI: its prompt (API graph) and the workflow of the page when there is one.
    None when turned off, when there is no graph, or when the video already is a file of the project (a stored take handed back)."""
    if os.environ.get("MAJOOR_EMBED_WORKFLOW", "1").strip().lower() in ("0", "false", "no", "off"):
        return None
    source = video.get_stream_source()
    if isinstance(source, str) and Path(source).resolve().is_relative_to(Path(root).resolve()):
        return None
    tags = {}
    if getattr(hidden, "prompt", None) is not None:
        tags["prompt"] = json.dumps(hidden.prompt)
    for key, value in (getattr(hidden, "extra_pnginfo", None) or {}).items():
        tags[key] = json.dumps(value)
    return tags or None
