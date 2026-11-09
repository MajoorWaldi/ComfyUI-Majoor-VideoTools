"""Give the Creative recipes (Text, Music) a video model choice: the H3 sub-graphs of a shot block stay, and a Generate Shot (API) branch is added beside them.

Per shot block: Generator Is (H3?) drives three lazy switches per take (images, audio, fps) that feed the take's Create Video, so only the chosen
model runs. The controls get a VIDEO MODEL node (Generator Select, Set GENERATOR); Create Timeline reads it, so the plan follows the model.
The block of Remix is a replacement of a subject in a video, which an API model does not do the same way: it is left as it is.

    python scripts/add_generator_router.py            # rewrites recipes/ and workflows/ (same bytes)

Idempotent: a recipe that already holds a Generate Shot (API) node is skipped."""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMIX = "SECATOR Remix"  # a Remix replaces the subject of a source video: Seedance does it in edit mode, so its block gets the router in another form
FILES = ("SECATOR Creative Text", "SECATOR Creative Music", REMIX)
H3 = "e8d64e56-82fd-4a7a-b144-51025f6ba7be"
CTRL, BLOCK, TIMELINE_NODE = "0", "SHOT_", "MajoorCreateTimeline"
GENSHOT_SIZE, IS_SIZE, SELECT_SIZE, SWITCH_SIZE = (330, 450), (270, 60), (400, 82), (340, 110)
GAP = 40


class Recipe:
    def __init__(self, data: dict):
        self.d = data
        self.nodes = {n["id"]: n for n in data["nodes"]}
        self.links = {l[0]: l for l in data["links"]}
        self.next_node = max(max(self.nodes), data["last_node_id"]) + 1  # last_node_id of the files is not always the highest id
        self.next_link = max(max(self.links), data["last_link_id"]) + 1

    # -- nodes and links ------------------------------------------------------------------------------------------
    def add(self, node: dict) -> dict:
        node["id"] = self.next_node
        self.next_node += 1
        node.setdefault("flags", {})
        node.setdefault("order", 0)
        node.setdefault("mode", 0)
        self.d["nodes"].append(node)
        self.nodes[node["id"]] = node
        return node

    def link(self, src: dict, slot: int, dst: dict, input_name: str) -> int:
        target = next((i for i, inp in enumerate(dst["inputs"]) if inp["name"] == input_name), None)
        if target is None:
            raise SystemExit(f"node {dst['id']} ({dst['type']}) has no input {input_name}")
        old = dst["inputs"][target].get("link")
        if old is not None:
            self.unlink(old)
        lid = self.next_link
        self.next_link += 1
        kind = src["outputs"][slot]["type"]
        record = [lid, src["id"], slot, dst["id"], target, kind]
        self.d["links"].append(record)
        self.links[lid] = record
        src["outputs"][slot].setdefault("links", None)
        src["outputs"][slot]["links"] = (src["outputs"][slot]["links"] or []) + [lid]
        dst["inputs"][target]["link"] = lid
        return lid

    def unlink(self, lid: int) -> None:
        record = self.links.pop(lid)
        self.d["links"].remove(record)
        src, dst = self.nodes[record[1]], self.nodes[record[3]]
        src["outputs"][record[2]]["links"] = [x for x in src["outputs"][record[2]]["links"] if x != lid] or None
        if dst["inputs"][record[4]].get("link") == lid:
            dst["inputs"][record[4]]["link"] = None

    def source(self, node: dict, input_name: str):
        """(node, slot) that feeds an input, or None."""
        inp = next((i for i in node["inputs"] if i["name"] == input_name), None)
        if not inp or inp.get("link") is None:
            return None
        record = self.links[inp["link"]]
        return self.nodes[record[1]], record[2]

    # -- layout ----------------------------------------------------------------------------------------------------
    def group(self, title_start: str) -> dict:
        return next(g for g in self.d["groups"] if g["title"].startswith(title_start))

    def rects(self, group: dict):
        x0, y0, w, h = group["bounding"]
        for n in self.d["nodes"]:
            x, y = n["pos"]
            if x0 <= x <= x0 + w and y0 <= y <= y0 + h:
                sx, sy = (260, 30) if (n.get("flags") or {}).get("collapsed") else (n["size"][0], max(n["size"][1] + 320, 760 if n["type"] == TIMELINE_NODE else 0))  # the frontend sizes a node taller than the file says
                yield x, y - 30, x + sx, y + sy

    def free_spot(self, group: dict, w: int, h: int, near: tuple[int, int]):
        x0, y0, gw, gh = group["bounding"]
        taken = list(self.rects(group))
        spots = sorted(((x, y) for y in range(int(y0) + 40, int(y0 + gh), 20) for x in range(int(x0) + 20, int(x0 + gw), 20)), key=lambda p: (p[0] - near[0]) ** 2 + (p[1] - near[1]) ** 2)
        for x, y in spots:
            if x + w > x0 + gw - 20 or y + h > y0 + gh - 20:
                continue
            if all(x + w + GAP <= a or x >= c + GAP or y + h + GAP <= b or y - 30 >= d + GAP for a, b, c, d in taken):
                return x, y
        raise SystemExit(f"no free place of {w}x{h} in {group['title']}")


def get_node(r: Recipe, name: str, type_: str, pos) -> dict:
    return r.add({"type": "GetNode", "pos": list(pos), "size": [210, 34], "flags": {"collapsed": True}, "inputs": [],
                  "outputs": [{"name": type_, "type": type_, "links": None}], "properties": {"Node name for S&R": "GetNode", "aux_id": "kijai/ComfyUI-KJNodes"},
                  "widgets_values": [name], "title": f"Get_{name}", "color": "#2a363b", "bgcolor": "#3f5159"})


def switch(r: Recipe, kind: str, title: str, pos) -> dict:
    return r.add({"type": "ComfySwitchNode", "pos": list(pos), "size": list(SWITCH_SIZE),
                  "inputs": [{"name": "switch", "type": "BOOLEAN", "link": None, "widget": {"name": "switch"}},
                             {"name": "on_false", "type": kind, "link": None}, {"name": "on_true", "type": kind, "link": None}],
                  "outputs": [{"name": "output", "type": kind, "links": None}], "properties": {"Node name for S&R": "ComfySwitchNode"},
                  "widgets_values": [False], "title": title})


def gen_shot(r: Recipe, title: str, pos, aspect: str, seed: int, remix: bool = False) -> dict:
    images = [{"name": f"image_{i}", "type": "IMAGE", "shape": 7, "link": None} for i in range(1, 10)]
    return r.add({"type": "MajoorGenerateShot", "pos": list(pos), "size": list(GENSHOT_SIZE),
                  "inputs": [{"name": "generator", "type": "STRING", "link": None}, {"name": "prompt", "type": "STRING", "link": None}, {"name": "seconds", "type": "FLOAT", "link": None},
                             *images, {"name": "reference_frames", "type": "IMAGE", "shape": 7, "link": None}, {"name": "reference_audio", "type": "AUDIO", "shape": 7, "link": None},
                             {"name": "aspect_ratio", "type": "COMBO", "widget": {"name": "aspect_ratio"}, "link": None},
                             {"name": "resolution", "type": "COMBO", "widget": {"name": "resolution"}, "link": None},
                             {"name": "generate_audio", "type": "BOOLEAN", "widget": {"name": "generate_audio"}, "link": None},
                             {"name": "seed", "type": "INT", "widget": {"name": "seed"}, "link": None},
                             {"name": "reference_fps", "type": "FLOAT", "shape": 7, "widget": {"name": "reference_fps"}, "link": None},
                             {"name": "task", "type": "COMBO", "shape": 7, "widget": {"name": "task"}, "link": None}, {"name": "source_video", "type": "VIDEO", "shape": 7, "link": None}],
                  "outputs": [{"name": "images", "type": "IMAGE", "links": None}, {"name": "audio", "type": "AUDIO", "links": None}, {"name": "fps", "type": "FLOAT", "links": None}],
                  "properties": {"Node name for S&R": "MajoorGenerateShot"}, "widgets_values": [aspect, "720p", True, seed, "randomize", 24, "edit" if remix else "reference"],
                  "widgets_values_named": {"aspect_ratio": aspect, "resolution": "720p", "generate_audio": True, "seed": seed, "control_after_generate": "randomize", "reference_fps": 24, "task": "edit" if remix else "reference"},
                  "title": title, "color": "#432", "bgcolor": "#653"})


NOTE_GUIDE = ("**Video model** (VIDEO MODEL in the controls): `minimax_h3` generates the takes locally with H3; `seedance_2_5`, `wan_3_0`, `ltx_2_5_fast` and `ltx_2_5_pro` "
              "call the Comfy API (sign in; each take spends credits, so keep RETRY BAD TAKES off while you try). The plan, the length asked and the take follow the choice and only the "
              "chosen branch runs. The API branch of a shot block (**Generate Shot (API)**) has its own aspect ratio and resolution: set them like CREATE TIMELINE (LTX makes 16:9 and 9:16 only; "
              "Seedance needs a reference picture or video, so keep one REF on). The prompt writer still writes the H3 prompt format for now.\n")
NOTE_GUIDE_REMIX = ("**Video model** (VIDEO MODEL in the controls): `minimax_h3` replaces the subject locally with H3 and its pose map. `seedance_2_5` calls the Comfy API in **edit** mode: Seedance changes the source shot "
                    "and the pictures say who replaces whom; the take keeps the length and the format of the source. Keep H3 for a shot shorter than about two seconds, for POSE ONLY, and when a reference video must give the motion. "
                    "Each take spends credits (sign in), so keep the retry off while you try; only the chosen branch runs.\n")
NOTE_DEPS = "- API video models (Seedance 2.5, Wan 3.0, LTX 2.5): a signed-in Comfy account with credits (the partner nodes of ComfyUI); nothing to download.\n"
NOTE_WIRING = "| `GENERATOR` | STRING | VIDEO MODEL (Generator Select) | CREATE TIMELINE, and the Generator Is and Generate Shot (API) nodes of each shot |\n"


def patch_notes(r: Recipe, remix: bool = False) -> None:
    for n in r.d["nodes"]:
        if n["type"] != "MarkdownNote":
            continue
        text, title = n["widgets_values"][0], n.get("title", "")
        if title == "GUIDE":
            marker = "Optional loaders are bypassed"
            if marker in text:
                n["widgets_values"][0] = text.replace(marker, (NOTE_GUIDE_REMIX if remix else NOTE_GUIDE) + marker, 1)
                n["size"][1] += 130  # the notes under it are pushed down by push_notes_down
        elif title.startswith("DEPENDENCIES") and "### System\n\n" in text:
            n["widgets_values"][0] = text.replace("### System\n\n", "### System\n\n" + NOTE_DEPS, 1)
            n["size"][1] += 50
        elif title.startswith("WIRING") and "|---|---|---|---|\n" in text:
            n["widgets_values"][0] = text.replace("|---|---|---|---|\n", "|---|---|---|---|\n" + (NOTE_WIRING.replace("CREATE TIMELINE, and the ", "") if remix else NOTE_WIRING), 1)


def push_notes_down(r: Recipe, before: dict) -> None:
    """A note that grew pushes the notes under it (the column left of the sections) down by the same amount."""
    notes = sorted((n for n in r.d["nodes"] if n["type"] == "MarkdownNote" and n["pos"][0] < 0), key=lambda n: n["pos"][1])
    shift = 0
    for n in notes:
        n["pos"][1] += shift
        shift += n["size"][1] - before[n["id"]]


def write_like(path: Path, data: dict) -> None:
    """Write a recipe the way its file was kept, in recipes/ and in workflows/ (the same bytes): the frontend's indented JSON with CRLF and no final newline, or the compact JSON of the Remix."""
    original = path.read_bytes().decode("utf-8")
    if original.startswith('{"'):
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ("\n" if original.endswith("\n") else "")
    else:
        text = json.dumps(data, ensure_ascii=False, indent=2).replace("\n", "\r\n")
    for folder in ("recipes", "workflows"):
        (ROOT / folder / path.name).write_bytes(text.encode("utf-8"))


def patch(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    r = Recipe(data)
    if any(n["type"] == "MajoorGenerateShot" for n in data["nodes"]):
        return False
    h3 = sorted((n for n in data["nodes"] if n["type"] == H3), key=lambda n: n["id"])
    if len(h3) != 2:
        raise SystemExit(f"{path.name}: expected two H3 instances (take and retry), found {len(h3)}")
    remix = path.stem == REMIX
    timeline = next((n for n in data["nodes"] if n["type"] == TIMELINE_NODE), None)  # a Remix has no plan to make: its shots are cut from the source
    if timeline is None and not remix:
        raise SystemExit(f"{path.name}: no Create Timeline")
    aspect = next((v for v in (timeline["widgets_values"] if timeline else []) if v in ("16:9", "9:16", "1:1")), "9:16")
    ctrl, block = r.group("0"), next(g for g in data["groups"] if g["title"].startswith(BLOCK))

    # controls: the choice, one Set for every reader
    sx, sy = r.free_spot(ctrl, *SELECT_SIZE, (4900, 600))
    select = r.add({"type": "MajoorGeneratorSelect", "pos": [sx, sy], "size": list(SELECT_SIZE),
                    "inputs": [{"name": "generator", "type": "COMBO", "widget": {"name": "generator"}, "link": None}],
                    "outputs": [{"name": "generator", "type": "STRING", "links": None}], "properties": {"Node name for S&R": "MajoorGeneratorSelect"},
                    "widgets_values": ["minimax_h3"], "widgets_values_named": {"generator": "minimax_h3"}, "title": "VIDEO MODEL (H3 local, or an API model)", "color": "#323", "bgcolor": "#535"})
    px, py = r.free_spot(ctrl, 210, 34, (5390, 430))
    setter = r.add({"type": "SetNode", "pos": [px, py], "size": [210, 34], "flags": {"collapsed": True}, "inputs": [{"name": "STRING", "type": "STRING", "link": None}],
                    "outputs": [{"name": "STRING", "type": "STRING", "links": None}], "properties": {"Node name for S&R": "SetNode", "previousName": "GENERATOR", "aux_id": "kijai/ComfyUI-KJNodes"},
                    "widgets_values": ["GENERATOR"], "title": "Set_GENERATOR"})
    r.link(select, 0, setter, "STRING")

    if timeline is not None:  # the plan follows the model
        tx, ty = r.free_spot(r.group("4"), 210, 34, (timeline["pos"][0], timeline["pos"][1] + timeline["size"][1] + 60))
        plan_get = get_node(r, "GENERATOR", "STRING", (tx, ty))
        timeline["inputs"].append({"name": "generator", "type": "STRING", "link": None, "shape": 7})
        r.link(plan_get, 0, timeline, "generator")

    # the shot block
    x0, y0, gw, gh = block["bounding"]
    composite = (310 + 2 * (GENSHOT_SIZE[0] + GAP) + 2 * (SWITCH_SIZE[0] + GAP), 3 * (SWITCH_SIZE[1] + 50) + 60)  # what the branch takes: a column, two Generate Shot, two columns of switches
    gx, gy = r.free_spot(block, *composite, (max(n["pos"][0] for n in h3) + 600, y0 + 780))
    shot_get = get_node(r, "GENERATOR", "STRING", (gx, gy))
    is_h3 = r.add({"type": "MajoorGeneratorIs", "pos": [gx, gy + 70], "size": list(IS_SIZE),
                   "inputs": [{"name": "generator", "type": "STRING", "link": None}, {"name": "is", "type": "COMBO", "widget": {"name": "is"}, "link": None}],
                   "outputs": [{"name": "selected", "type": "BOOLEAN", "links": None}], "properties": {"Node name for S&R": "MajoorGeneratorIs"},
                   "widgets_values": ["minimax_h3"], "widgets_values_named": {"is": "minimax_h3"}, "title": "H3 MODEL? (else the API branch)"})
    r.link(shot_get, 0, is_h3, "generator")
    fx, fy = gx, gy + 70 + IS_SIZE[1] + 70
    h3_fps = r.add({"type": "PrimitiveFloat", "pos": [fx, fy], "size": [270, 60], "inputs": [], "outputs": [{"name": "FLOAT", "type": "FLOAT", "links": None}],
                    "properties": {"Node name for S&R": "PrimitiveFloat"}, "widgets_values": [24.0], "title": "H3 fps"})

    colx = gx + 310
    rng = random.Random(7)
    for k, (h3_node, label) in enumerate(zip(h3, ("API · generates the shot", "API · again with another seed"))):
        gen = gen_shot(r, label, (colx + k * (GENSHOT_SIZE[0] + GAP), gy), aspect, rng.randrange(1, 2**31), remix)
        r.link(shot_get, 0, gen, "generator")
        if remix:  # the video that is changed is the shot of the source; the pictures are who replaces whom (the references of the pose map and of the reference video stay with H3)
            feeds = {"prompt": "value", "seconds": "value_1", "source_video": "video", **{f"image_{i + 1}": f"ref_images.ref_image_{i}" for i in range(5)}}
        else:
            feeds = {"prompt": "value", "seconds": "value_1", "reference_frames": "ref_videos.ref_video_0", "reference_audio": "ref_audios.ref_audio_0",
                     **{f"image_{i + 1}": f"ref_images.ref_image_{i}" for i in range(6)}}
        for mine, theirs in feeds.items():
            found = r.source(h3_node, theirs)
            if found:
                r.link(found[0], found[1], gen, mine)
        take = next(r.nodes[r.links[l][3]] for l in h3_node["outputs"][1]["links"] if r.nodes[r.links[l][3]]["type"] == "CreateVideo")
        sw_x = colx + 2 * (GENSHOT_SIZE[0] + GAP) + (k * (SWITCH_SIZE[0] + GAP) if False else 0)
        stacked = [("IMAGE", "images", 1, 0, "images"), ("AUDIO", "audio", 0, 1, "audio"), ("FLOAT", "fps", None, 2, "fps")]
        for j, (kind, name, h3_slot, gen_slot, take_input) in enumerate(stacked):
            sw = switch(r, kind, f"{label.split(' · ')[1].upper()} · {name}", (sw_x + k * (SWITCH_SIZE[0] + GAP), gy + j * (SWITCH_SIZE[1] + 50)))
            r.link(is_h3, 0, sw, "switch")
            r.link(gen, gen_slot, sw, "on_false")
            r.link(h3_node, h3_slot, sw, "on_true") if h3_slot is not None else r.link(h3_fps, 0, sw, "on_true")
            if take_input == "fps":
                take["inputs"].append({"name": "fps", "type": "FLOAT", "link": None, "widget": {"name": "fps"}})
            r.link(sw, 0, take, take_input)

    sizes = {n['id']: n['size'][1] for n in r.d['nodes'] if n['type'] == 'MarkdownNote'}
    patch_notes(r, remix)
    push_notes_down(r, sizes)
    data["last_node_id"], data["last_link_id"] = r.next_node - 1, r.next_link - 1
    write_like(path, data)
    return True


if __name__ == "__main__":
    for name in FILES:
        done = patch(ROOT / "recipes" / f"{name}.json")
        print(f"{name}: {'router added' if done else 'already has it'}")
    sys.exit(0)
