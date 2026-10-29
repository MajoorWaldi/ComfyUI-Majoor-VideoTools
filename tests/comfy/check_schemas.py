"""Every node of the pack builds its schema (a node that fails there takes the whole pack down at startup), and Edit Skills composes its profile."""
import asyncio

import _boot

extension = asyncio.run(_boot.pack.comfy_entrypoint())
nodes = asyncio.run(extension.get_node_list())
ids = [node.define_schema().node_id for node in nodes]
assert len(ids) == len(set(ids)), "duplicate node ids"
print(len(ids), "schemas ok:", ", ".join(ids))

from MVT.nodes.edit_skills import _build  # noqa: E402

_, planner, _ = _build("timeline_planner", True, True, True, "all", 0, 0, "auto", 1, "", "", "viral_aura_farming", {"cut_density": "low"})
_, music, _ = _build("music_brief_from_plan", True, True, True, "all", 0, 0, "auto", 1, "", "", "viral_aura_farming", {})
assert "Viral / Aura Farming" in planner and "Cut density: low," in planner and "EDITING PROFILE" not in music
_, minimax, _ = _build("music_brief_minimax3", True, True, True, "all", 0, 0, "auto", 1, "", "", "beauty_premium", {})
assert "MUSIC DIRECTION OF THE PROFILE" in minimax and "soft contemporary instrumental" in minimax and "EDITING PROFILE" not in minimax
print("edit skills ok")
