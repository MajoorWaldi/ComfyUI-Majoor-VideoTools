"""Deploy one block of nodes per shot from a recipe.

A recipe is a normal ComfyUI workflow (as saved by the frontend) that holds ONE shot block: a group around a Select Shot node and
everything that processes that shot (analysis, generation, Apply Shot Metadata, compare...). The block talks to the rest of the
graph through KJNodes Set/Get nodes, so cloning it is mechanical: every `SHOT_001` in the block becomes the id of the new shot,
the Apply Shot Metadata nodes are chained one after the other, and the last one feeds Shot Assemble.

Everything here works on the serialized workflow (JSON in, JSON out), so it runs and is tested without ComfyUI."""
import copy
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .errors import MajoorError

SELECT = "MajoorSelectShot"
APPLY = "MajoorApplyShotMetadata"
ASSEMBLE = "MajoorShotAssemble"
SAVE = "SaveVideo"
DEPLOYER = "MajoorDeployShots"
GET, SET = "GetNode", "SetNode"
SWITCH = "ComfySwitchNode"
UI_CACHE = ("majoor_ui", "majoor_compare", "majoor_assembly", "majoor_deploy")  # frontend caches that go stale in a copy
SHOT_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
RECIPES = Path(__file__).resolve().parents[1] / "recipes"
GAP = 60.0


# ---- recipes -----------------------------------------------------------------------------------------------------

def list_recipes() -> list[str]:
    return sorted(p.stem for p in RECIPES.glob("*.json")) if RECIPES.is_dir() else []


def recipe_info(name: str) -> dict:
    """What a recipe says about itself in extra.majoor_recipe: {"kind": "plan" | "video", "priority": number, "title": text}."""
    return ((load_recipe(name).get("extra") or {}).get("majoor_recipe")) or {}


def pick_recipe(name: str, has_plan: bool) -> str:
    """'auto' takes the recipe for shots that come with a plan (Create Timeline: kind "plan") or for shots cut from a video (Scene Detect: kind "video");
    the highest priority wins. A recipe without a kind is a plan recipe when its name ends with _plan."""
    if name != "auto":
        return name
    kind = "plan" if has_plan else "video"
    found = []
    for recipe in list_recipes():
        info = recipe_info(recipe)
        if (info.get("kind") or ("plan" if recipe.endswith("_plan") else "video")) == kind:
            found.append((-float(info.get("priority", 0)), recipe))
    if not found:
        raise MajoorError(f"No {kind} recipe in the recipes folder (set extra.majoor_recipe.kind in the workflow, or end the name with _plan for a plan recipe). Available: {list_recipes()}")
    return sorted(found)[0][1]


def load_recipe(name: str) -> dict:
    if not re.fullmatch(r"[\w .()&-]+", name or ""):
        raise MajoorError(f"Invalid recipe name {name!r}")
    path = RECIPES / f"{name}.json"
    if not path.is_file():
        raise MajoorError(f"Unknown recipe '{name}'. Available: {list_recipes()}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise MajoorError(f"Recipe '{name}' is not valid JSON: {e}") from e


# ---- reading a workflow --------------------------------------------------------------------------------------------

def _widget(node: dict, name: str, default=None):
    named = node.get("widgets_values_named")
    if isinstance(named, dict) and name in named:
        return named[name]
    return default


def _set_widget(node: dict, name: str, value) -> None:
    """Keep widgets_values and widgets_values_named in step."""
    named = node.get("widgets_values_named")
    if isinstance(named, dict) and name in named:
        position = list(named).index(name)
        named[name] = value
        values = node.get("widgets_values")
        if isinstance(values, list) and position < len(values):
            values[position] = value


def _subgraph_closure(workflow: dict, node_types: set[str]) -> dict[str, dict]:
    available = {d["id"]: d for d in workflow.get("definitions", {}).get("subgraphs", [])}
    found: dict[str, dict] = {}
    todo = [t for t in node_types if t in available]
    while todo:
        sid = todo.pop()
        if sid in found:
            continue
        found[sid] = available[sid]
        todo += [n["type"] for n in available[sid].get("nodes", []) if n.get("type") in available]
    return found


def _name(node: dict) -> str:
    return str((node.get("widgets_values") or [""])[0]) if node["type"] in (GET, SET) else ""


def _has_token(text: str, token: str) -> bool:
    return re.search(re.escape(token) + r"(?!\d)", text) is not None


def _shot_number(shot_id: str) -> int:
    found = re.search(r"(\d+)\s*$", shot_id)
    return int(found.group(1)) if found else 10**9


def _node_box(node: dict) -> list[float]:
    x, y = node["pos"][:2]
    w, h = node.get("size", [0, 0])[:2]
    return [x, y, x + w, y + h]


def _block_token(workflow: dict, select: dict, nodes: dict[int, dict], links: list[list]) -> str:
    """The name the Set/Get nodes of a block carry (SHOT_001 in SHOT_001_META). Usually the shot_id of its Select Shot; when the Select Shot was left on
    another shot, the shortest name among the Set nodes it feeds directly."""
    shot_id = str(_widget(select, "shot_id", "") or (select.get("widgets_values") or [""])[0])
    if any(n["type"] in (GET, SET) and shot_id and _has_token(_name(n), shot_id) for n in workflow["nodes"]):
        return shot_id
    fed = [_name(nodes[l[3]]) for l in links if l[1] == select["id"] and nodes.get(l[3]) is not None and nodes[l[3]]["type"] == SET]
    fed = [n for n in fed if n]
    return min(fed, key=len) if fed else shot_id


@dataclass
class Block:
    """Everything that processes one shot: its Select Shot, the Set/Get nodes named after it, and whatever is wired to them."""
    shot_id: str
    node_ids: set[int]  # ids in the workflow it was read from
    nodes: list[dict]  # copies, plus a copy of each shared Get node the block reads from
    links: list[list]
    defs: dict[str, dict]  # subgraph definitions the block needs, by id
    groups: list[dict]  # the groups around the Select Shot, the outer one first
    box: list[float]  # x, y, width, height of the block on the canvas
    warnings: list[str] = field(default_factory=list)
    shared_nodes: dict[int, dict] = field(default_factory=dict)  # nodes outside the block that feed it, copied once for all the shots
    shared_links: list[list] = field(default_factory=list)
    list_inputs: list[list] = field(default_factory=list)  # [node id, input slot] of the inputs that read the shot list (Create Timeline, Scene Detect...)


def _groups_of(workflow: dict, node: dict) -> list[dict]:
    """Every group around a node (a group can sit in a group), the biggest first."""
    cx, cy = node["pos"][0] + node.get("size", [0, 0])[0] / 2, node["pos"][1] + 10
    found = [g for g in workflow.get("groups", []) if g["bounding"][0] <= cx <= g["bounding"][0] + g["bounding"][2] and g["bounding"][1] <= cy <= g["bounding"][1] + g["bounding"][3]]
    return sorted(found, key=lambda g: -g["bounding"][2] * g["bounding"][3])


def collect_block(workflow: dict, select: dict) -> Block:
    nodes = {n["id"]: n for n in workflow["nodes"]}
    shot_id = _block_token(workflow, select, nodes, workflow["links"])
    by_node: dict[int, list[list]] = {}
    for link in workflow["links"]:
        by_node.setdefault(link[1], []).append(link)
        by_node.setdefault(link[3], []).append(link)

    def is_chain(link: list) -> bool:
        """The shot list passed from one Apply Shot Metadata to the next: it belongs to no single shot."""
        start, end = nodes.get(link[1]), nodes.get(link[3])
        return link[5] == "MAJOOR_SHOT_LIST" and start is not None and start["type"] == APPLY

    # the block is what is downstream of its Select Shot and of the Set/Get nodes named after the shot
    members = {select["id"]}
    members |= {n["id"] for n in workflow["nodes"] if n["type"] in (GET, SET) and shot_id and _has_token(_name(n), shot_id)}
    todo = list(members)
    while todo:
        for link in by_node.get(todo.pop(), []):
            target = nodes.get(link[3])
            if link[1] not in members or target is None or link[3] in members or is_chain(link):
                continue
            if target["type"] in (ASSEMBLE, SAVE, DEPLOYER) or (target["type"] in (GET, SET) and not _has_token(_name(target), shot_id)):
                continue
            members.add(link[3])
            todo.append(link[3])

    copies = [copy.deepcopy(nodes[i]) for i in sorted(members)]
    links = [list(l) for l in workflow["links"] if l[1] in members and l[3] in members and not is_chain(l)]
    warnings = []
    next_node = max(nodes) + 1
    next_link = max([l[0] for l in workflow["links"]] or [0]) + 1
    twins: dict[int, dict] = {}
    shared_nodes: dict[int, dict] = {}
    shared_links: list[list] = []  # [origin id, origin slot, target id, target slot, type]: inputs fed by a node shared by all shots
    list_inputs: list[list] = []
    link_by_id = {lk[0]: lk for lk in workflow["links"]}

    def real_origin(link: list):
        """The node a link really comes from: Reroute nodes are only wires."""
        origin, slot = nodes.get(link[1]), link[2]
        for _ in range(32):
            if origin is None or origin["type"] != "Reroute":
                break
            feeding = (origin.get("inputs") or [{}])[0].get("link")
            origin, slot = (nodes.get(link_by_id[feeding][1]), link_by_id[feeding][2]) if feeding in link_by_id else (None, 0)
        return origin, slot

    for l in workflow["links"]:
        if l[3] not in members or l[1] in members or is_chain(l):
            continue
        target_input = nodes[l[3]]["inputs"][l[4]]
        if l[5] == "MAJOOR_SHOT_LIST" or target_input.get("type") == "MAJOOR_SHOT_LIST":  # wired straight to the source in the target graph
            next(c for c in copies if c["id"] == l[3])["inputs"][l[4]]["link"] = None
            list_inputs.append([l[3], l[4]])
            continue
        origin, l_slot = real_origin(l)
        if origin is None:
            warnings.append(f"{shot_id}: an input of #{l[3]} comes from a Reroute that leads nowhere; not reproduced")
            continue
        l = [l[0], origin["id"], l_slot, l[3], l[4], l[5]]
        if origin["type"] == GET:  # every block gets its own copy of the Get nodes it reads through
            if l[1] not in twins:
                twin = copy.deepcopy(origin)
                twin["id"], twin["outputs"][0]["links"] = next_node, []
                twin["pos"] = [nodes[l[3]]["pos"][0] - 240, nodes[l[3]]["pos"][1]]
                twins[l[1]] = twin
                copies.append(twin)
                next_node += 1
            twin = twins[l[1]]
            next(c for c in copies if c["id"] == l[3])["inputs"][l[4]]["link"] = next_link  # the input now reads from the copy
            links.append([next_link, twin["id"], l[2], l[3], l[4], l[5]])
            twin["outputs"][0]["links"].append(next_link)
            next_link += 1
        elif origin["type"] in (SET, ASSEMBLE, SAVE, DEPLOYER):
            continue
        else:  # a real node (an edit request, a number...) shared by all the shots: copied once, linked from every block
            shared_nodes.setdefault(l[1], copy.deepcopy(origin))
            shared_links.append([l[1], l[2], l[3], l[4], l[5]])

    groups = _groups_of(workflow, select)
    boxes = [_node_box(n) for n in copies]
    for group in groups:
        gx, gy, gw, gh = group["bounding"]
        boxes.append([gx, gy, gx + gw, gy + gh])
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    defs = _subgraph_closure(workflow, {n["type"] for n in copies})
    return Block(shot_id, members, copies, links, defs, copy.deepcopy(groups), [x0, y0, x1 - x0, y1 - y0], warnings, shared_nodes, shared_links, list_inputs)


def find_blocks(workflow: dict) -> list[Block]:
    return [collect_block(workflow, n) for n in workflow.get("nodes", []) if n["type"] == SELECT]


def template_block(recipe: dict) -> Block:
    blocks = find_blocks(recipe)
    if not blocks:
        raise MajoorError("The recipe has no shot block: it needs a Select Shot node with the Set/Get nodes of its shot (SHOT_001_META, SHOT_001_GENERATED...).")
    block = min(blocks, key=lambda b: _shot_number(b.shot_id))
    if not SHOT_ID.fullmatch(block.shot_id):
        raise MajoorError(f"The Select Shot of the recipe has no usable shot_id ({block.shot_id!r}).")
    return block


# ---- cloning -------------------------------------------------------------------------------------------------------

class Alloc:
    def __init__(self, workflow: dict):
        self.node = max([workflow.get("last_node_id", 0), *(n["id"] for n in workflow.get("nodes", []))] or [0])
        self.link = max([workflow.get("last_link_id", 0), *(l[0] for l in workflow.get("links", []))] or [0])
        self.group = max([0, *(g.get("id", 0) for g in workflow.get("groups", []))])

    def next_node(self) -> int:
        self.node += 1
        return self.node

    def next_link(self) -> int:
        self.link += 1
        return self.link

    def next_group(self) -> int:
        self.group += 1
        return self.group


def _strip_ui(node: dict) -> None:
    props = node.get("properties")
    if isinstance(props, dict):
        for key in UI_CACHE:
            props.pop(key, None)


@dataclass
class Clone:
    shot_id: str
    nodes: list[dict]
    links: list[list]
    groups: list[dict]
    defs: list[dict]
    apply: dict | None
    select: dict
    shared_links: list[list]  # [origin id in the block's workflow, origin slot, new target id, target slot, type]
    list_inputs: list[list]  # [new node id, input slot] of the inputs that read the shot list


def clone_block(block: Block, shot_id: str, index: int, origin: tuple[float, float], alloc: Alloc, stamp: dict) -> Clone:
    """A copy of the block for one shot: names substituted, ids fresh, subgraph definitions copied under new ids."""
    payload = {"nodes": block.nodes, "groups": block.groups, "defs": list(block.defs.values())}
    for node in payload["nodes"]:
        _strip_ui(node)
    text = json.dumps(payload)
    for old in sorted(block.defs):  # every subgraph definition of the copy gets its own id: Set/Get names inside them are per shot
        text = text.replace(old, str(uuid.uuid4()))
    text = re.sub(re.escape(block.shot_id) + r"(?!\d)", shot_id, text)
    data = json.loads(text)

    gx, gy = block.box[:2]
    ox, oy = origin
    renumber = {n["id"]: alloc.next_node() for n in data["nodes"]}
    link_ids = {l[0]: alloc.next_link() for l in block.links}
    nodes = []
    for node in data["nodes"]:
        node["id"] = renumber[node["id"]]
        node["pos"] = [node["pos"][0] - gx + ox, node["pos"][1] - gy + oy]
        for slot in node.get("inputs", []):
            slot["link"] = link_ids.get(slot.get("link"))  # links to outside the block are dropped
        for slot in node.get("outputs", []):
            slot["links"] = [link_ids[i] for i in slot.get("links") or [] if i in link_ids] or None
        node.setdefault("properties", {})["majoor_deploy"] = dict(stamp, shot=shot_id)
        nodes.append(node)
    links = [[link_ids[l[0]], renumber[l[1]], l[2], renumber[l[3]], l[4], l[5]] for l in block.links]

    groups = data["groups"]
    for group in groups:
        group["id"] = alloc.next_group()
        group["bounding"] = [group["bounding"][0] - gx + ox, group["bounding"][1] - gy + oy, *group["bounding"][2:]]
        if not _has_token(group.get("title", ""), shot_id):
            group["title"] = f"{group.get('title', '')} {shot_id}".strip()
    select = next(n for n in nodes if n["type"] == SELECT)
    _set_widget(select, "shot_id", shot_id)
    _set_widget(select, "index", index)
    for node in nodes:  # the same seed for every shot would make them move alike
        seed = (node.get("widgets_values_named") or {}).get("noise_seed")
        if isinstance(seed, int) and not isinstance(seed, bool):
            _set_widget(node, "noise_seed", seed + index - 1)
    apply = next((n for n in nodes if n["type"] == APPLY), None)
    shared = [[l[0], l[1], renumber[l[2]], l[3], l[4]] for l in block.shared_links]
    listed = [[renumber[i], slot] for i, slot in block.list_inputs]
    return Clone(shot_id, nodes, links, groups, data["defs"], apply, select, shared, listed)


# ---- editing the target graph --------------------------------------------------------------------------------------

def _gives_same(node: dict, template_node: dict, slots: set[int]) -> bool:
    """The node has, in each output slot the blocks read, the type that the recipe's shared node has there (an LLM answer in place of a typed text)."""
    outs, wanted = node.get("outputs") or [], template_node.get("outputs") or []
    return bool(slots) and all(s < len(outs) and s < len(wanted) and outs[s].get("type") == wanted[s].get("type") for s in slots)


def _link_index(workflow: dict) -> dict[int, list]:
    return {l[0]: l for l in workflow["links"]}


def _drop_links(workflow: dict, doomed: set[int]) -> None:
    if not doomed:
        return
    workflow["links"] = [l for l in workflow["links"] if l[0] not in doomed]
    for node in workflow["nodes"]:
        for slot in node.get("inputs", []):
            if slot.get("link") in doomed:
                slot["link"] = None
        for slot in node.get("outputs", []):
            if slot.get("links"):
                slot["links"] = [i for i in slot["links"] if i not in doomed] or None


def remove_nodes(workflow: dict, node_ids: set[int]) -> None:
    touching = {l[0] for l in workflow["links"] if l[1] in node_ids or l[3] in node_ids}
    workflow["nodes"] = [n for n in workflow["nodes"] if n["id"] not in node_ids]
    _drop_links(workflow, touching)


def _prune_defs(workflow: dict) -> None:
    """Remove subgraph definitions nothing uses any more."""
    defs = workflow.get("definitions", {}).get("subgraphs")
    if not defs:
        return
    used, todo = set(), [n["type"] for n in workflow["nodes"]]
    by_id = {d["id"]: d for d in defs}
    while todo:
        t = todo.pop()
        if t in by_id and t not in used:
            used.add(t)
            todo += [n["type"] for n in by_id[t].get("nodes", [])]
    workflow["definitions"]["subgraphs"] = [d for d in defs if d["id"] in used]


def _connect(workflow: dict, alloc: Alloc, origin: dict, origin_slot: int, target: dict, target_slot: int, kind: str) -> None:
    """Link origin -> target, replacing whatever fed that input."""
    slot = target["inputs"][target_slot]
    if slot.get("link") is not None:
        _drop_links(workflow, {slot["link"]})
    lid = alloc.next_link()
    workflow["links"].append([lid, origin["id"], origin_slot, target["id"], target_slot, kind])
    slot["link"] = lid
    out = origin["outputs"][origin_slot]
    out["links"] = [*(out.get("links") or []), lid]


def _input_slot(node: dict, name: str) -> int:
    for i, slot in enumerate(node.get("inputs", [])):
        if slot["name"] == name:
            return i
    raise MajoorError(f"{node['type']} #{node['id']} has no input '{name}'")


def _defined_names(nodes: list[dict], defs: list[dict]) -> tuple[set[str], set[str]]:
    sets, gets = set(), set()
    for node in [*nodes, *(n for d in defs for n in d.get("nodes", []))]:
        if node["type"] in (GET, SET) and node.get("widgets_values"):
            (sets if node["type"] == SET else gets).add(str(node["widgets_values"][0]))
    return sets, gets


FIRST_PICTURE = {"REF1": "REF", "REF": "REF1"}  # the first reference picture is named REF in the older recipes and graphs, REF1 in the newer ones


def _follow_first_picture(clones, root_sets: set[str]) -> list[str]:
    """A block reads REF1 and the graph sets REF (or the other way round): the Get nodes of the blocks follow the Set node that exists, so that the first picture is not silently lost."""
    available = root_sets | _defined_names([n for c in clones for n in c.nodes], [d for c in clones for d in c.defs])[0]
    renamed: list[str] = []
    for node in [n for c in clones for n in c.nodes] + [n for c in clones for d in c.defs for n in d.get("nodes", [])]:
        name = _name(node) if node["type"] == GET else ""
        alias = FIRST_PICTURE.get(name)
        if alias and name not in available and alias in available:
            node["widgets_values"][0] = alias
            if "widgets_values_named" in node:
                node["widgets_values_named"] = {"Constant": alias}
            if node.get("title") == f"Get_{name}":
                node["title"] = f"Get_{alias}"
            renamed.append(f"{name} -> {alias}")
    return sorted(set(renamed))


@dataclass
class Report:
    created: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    nodes_added: int = 0

    def to_dict(self) -> dict:
        return {"created": self.created, "replaced": self.replaced, "warnings": self.warnings, "nodes_added": self.nodes_added}


def _finale(recipe: dict, template: Block) -> list[dict]:
    """The nodes after the shot blocks in the recipe (Shot Assemble, Save Video...): not part of the template block."""
    nodes = [n for n in recipe["nodes"] if n["type"] in (ASSEMBLE, SAVE) and n["id"] not in template.node_ids]
    return copy.deepcopy(nodes)


def _stamp(node: dict) -> dict:
    return (node.get("properties") or {}).get("majoor_deploy") or {}


def deploy(recipe: dict, workflow: dict, shot_ids: list[str], *, anchor_id: int | None = None, columns: int = 1, include_finale: bool = True,
           replace_existing: bool = True) -> tuple[dict, Report]:
    """Return a copy of `workflow` with one block per shot id, chained and assembled. `workflow` is not modified."""
    if not shot_ids:
        raise MajoorError("No shot to deploy: run Scene Detect & Split (or Create Timeline) once so the shots are known.")
    bad = [s for s in shot_ids if not SHOT_ID.fullmatch(str(s))]
    if bad or len(set(shot_ids)) != len(shot_ids):
        raise MajoorError(f"Shot ids must be unique and use letters, digits, _ and - only: {bad or shot_ids}")
    wf = copy.deepcopy(workflow)
    wf.setdefault("nodes", [])
    wf.setdefault("links", [])
    wf.setdefault("groups", [])
    wf.setdefault("definitions", {}).setdefault("subgraphs", [])
    report = Report()
    template = template_block(recipe)
    report.warnings += template.warnings

    anchor = next((n for n in wf["nodes"] if n["id"] == anchor_id), None)
    previous = (anchor or {}).get("properties", {}).get("majoor_deploy")
    if previous:  # a previous deployment is replaced as a whole
        remove_nodes(wf, set(previous.get("nodes", [])))
        wf["groups"] = [g for g in wf["groups"] if g.get("id") not in set(previous.get("groups", []))]

    # blocks of the same shots built by hand: replaced by the recipe's block
    wanted = set(shot_ids)
    for block in find_blocks(wf):
        if block.shot_id in wanted and block.shot_id not in report.replaced:
            if not replace_existing:
                raise MajoorError(f"The graph already has a block for {block.shot_id}. Delete it, or enable replace_existing.")
            report.replaced.append(block.shot_id)
            remove_nodes(wf, block.node_ids)
            gone = {g.get("id") for g in block.groups}
            wf["groups"] = [g for g in wf["groups"] if g.get("id") not in gone]
    stale = {n["id"] for n in wf["nodes"] if _stamp(n) and n["type"] != DEPLOYER and _stamp(n).get("shot") != "shared"}
    if stale:  # leftovers of a deployment whose record was lost (after the blocks above, which are read whole)
        remove_nodes(wf, stale)
    _prune_defs(wf)

    alloc = Alloc(wf)
    bx, by, bw, bh = template.box
    if anchor:
        origin = (anchor["pos"][0], anchor["pos"][1] + anchor.get("size", [0, 200])[1] + 100)
    else:
        origin = (bx, by)
    stamp = {"recipe": template.shot_id}
    clones: list[Clone] = []
    cols = max(int(columns), 1)
    for i, shot_id in enumerate(shot_ids):
        spot = (origin[0] + (i % cols) * (bw + GAP), origin[1] + (i // cols) * (bh + GAP))
        clones.append(clone_block(template, shot_id, i + 1, spot, alloc, stamp))
        report.created.append(shot_id)

    # Apply Shot Metadata nodes form a chain: the first starts from the shot list, each next one from the previous
    chained: list[Clone] = [c for c in clones if c.apply is not None]
    for prev, cur in zip(chained, chained[1:]):
        slot = _input_slot(cur.apply, "shot_list")
        before = cur.apply["inputs"][slot].get("link")
        if before is not None:
            feeder_id = next((l[1] for l in cur.links if l[0] == before), None)
            _drop_links_in_clone(cur, before)
            cur.apply["inputs"][slot]["link"] = None
            feeder = next((n for n in cur.nodes if n["id"] == feeder_id), None)
            if feeder is not None and feeder["type"] == GET and not any(l[1] == feeder["id"] for l in cur.links):
                cur.nodes.remove(feeder)  # a Get node that only served this input
    if not chained:
        report.warnings.append("The recipe's block has no Apply Shot Metadata: generated shots will not be put back into the shot list.")

    for c in clones:
        wf["nodes"].extend(c.nodes)
        wf["links"].extend(c.links)
        wf["groups"].extend(c.groups)
        wf["definitions"]["subgraphs"].extend(c.defs)
        report.nodes_added += len(c.nodes)
    for prev, cur in zip(chained, chained[1:]):
        _connect(wf, alloc, prev.apply, 0, cur.apply, _input_slot(cur.apply, "shot_list"), "MAJOOR_SHOT_LIST")

    # nodes shared by all the shots (the edit request...): reused when the graph already has one, copied once otherwise
    shared: dict[int, dict] = {}
    for n, (oid, template_node) in enumerate(template.shared_nodes.items()):
        slots = {slot for origin_id, slot, *_ in template.shared_links if origin_id == oid}
        found = next((x for x in wf["nodes"] if x.get("title") == template_node.get("title") and x["id"] not in {y["id"] for c in clones for y in c.nodes}
                      and (x["type"] == template_node["type"] or _gives_same(x, template_node, slots))), None)
        if found is None:
            found = copy.deepcopy(template_node)
            _strip_ui(found)
            found["id"] = alloc.next_node()
            found["pos"] = [origin[0] - found.get("size", [400, 200])[0] - 100, origin[1] + n * (found.get("size", [400, 200])[1] + GAP)]
            found["inputs"] = [dict(i, link=None) for i in found.get("inputs", [])]
            found["outputs"] = [dict(o, links=None) for o in found.get("outputs", [])]
            found.setdefault("properties", {})["majoor_deploy"] = dict(stamp, shot="shared")
            wf["nodes"].append(found)
            report.nodes_added += 1
        shared[oid] = found
    by_id = {x["id"]: x for x in wf["nodes"]}
    for c in clones:
        for oid, oslot, tid, tslot, kind in c.shared_links:
            _connect(wf, alloc, shared[oid], oslot, by_id[tid], tslot, kind)

    # the blocks read the shot list straight from Create Timeline / Scene Detect & Split, not through Get nodes
    source = shot_list_source(wf, anchor)
    by_id = {x["id"]: x for x in wf["nodes"]}
    first_apply = chained[0] if chained else None
    unlinked = 0
    for c in clones:
        for tid, tslot in c.list_inputs:
            target = by_id[tid]
            if target["type"] == APPLY and c is not first_apply:
                continue  # chained to the previous Apply instead
            if source is None:
                unlinked += 1
                continue
            dp_slot = source[1]
            _connect(wf, alloc, source[0], dp_slot, target, tslot, "MAJOOR_SHOT_LIST")
    if unlinked:
        report.warnings.append("No Create Timeline or Scene Detect & Split found to read the shot list from: connect the shot_list of Deploy Shots to one, then press Create shots again.")

    # Shot Assemble (and Save Video) after the last Apply
    created_ids = {n["id"] for c in clones for n in c.nodes}
    last = chained[-1].apply if chained else None
    assemble = next((n for n in wf["nodes"] if n["type"] == ASSEMBLE), None)
    if last is not None and assemble is not None:
        _connect(wf, alloc, last, 0, assemble, _input_slot(assemble, "shot_list"), "MAJOOR_SHOT_LIST")
    elif last is not None and include_finale:
        finale = _finale(recipe, template)
        ids = {}
        fx = origin[0] + cols * (bw + GAP)
        top = min((n["pos"][1] for n in finale), default=0)
        left = min((n["pos"][0] for n in finale), default=0)
        for n in finale:
            _strip_ui(n)
            ids[n["id"]] = alloc.next_node()
        for n in finale:
            old = n["id"]
            n["id"] = ids[old]
            n["pos"] = [n["pos"][0] - left + fx, n["pos"][1] - top + origin[1]]
            n.setdefault("properties", {})["majoor_deploy"] = dict(stamp, shot="finale")
            for slot in n.get("inputs", []):
                slot["link"] = None
            for slot in n.get("outputs", []):
                slot["links"] = None
        for lid, o, os_, t, ts, kind in recipe["links"]:  # keep the links between the finale nodes (Assemble -> Save Video)
            if o in ids and t in ids:
                _connect_ids(finale, alloc, wf, ids[o], os_, ids[t], ts, kind)
        wf["nodes"].extend(finale)
        report.nodes_added += len(finale)
        created_ids |= {n["id"] for n in finale}
        assemble = next((n for n in finale if n["type"] == ASSEMBLE), None)
        if assemble is None:
            report.warnings.append("The recipe has no Shot Assemble: nothing was added after the shots.")
        else:
            _connect(wf, alloc, last, 0, assemble, _input_slot(assemble, "shot_list"), "MAJOOR_SHOT_LIST")
    elif last is not None:
        report.warnings.append("No Shot Assemble in the graph: connect the last Apply Shot Metadata to one.")

    # names the blocks read from the rest of the graph must be set somewhere
    root_sets = {str(n["widgets_values"][0]) for n in wf["nodes"] if n["type"] == SET and n.get("widgets_values")}
    for names in _follow_first_picture(clones, root_sets):
        report.warnings.append(f"The first reference picture is read as {names.split(' -> ')[1]} (the Set node of the graph) instead of {names.split(' -> ')[0]}.")
    block_sets, block_gets = _defined_names([n for c in clones for n in c.nodes], [d for c in clones for d in c.defs])
    missing = sorted(block_gets - block_sets - root_sets)
    if missing:
        report.warnings.append(f"No Set node for: {', '.join(missing)}. Add them (the recipe file has them) or the Get nodes will fail."
                               + (" Without REF or REF1 the first reference picture reaches neither H3 nor the LLM." if {"REF", "REF1"} & set(missing) else ""))

    if anchor:
        anchor.setdefault("properties", {})["majoor_deploy"] = {
            "recipe": template.shot_id,
            "nodes": sorted(created_ids),
            "groups": [g["id"] for c in clones for g in c.groups],
            "shots": shot_ids,
            "warnings": report.warnings,
        }
    wf["last_node_id"], wf["last_link_id"] = alloc.node, alloc.link
    _prune_defs(wf)
    known = set(check_workflow(workflow))  # what was already wrong in the graph is not ours to refuse over
    problems = [p for p in check_workflow(wf) if p not in known]
    if problems:
        raise MajoorError("The deployment would break the graph, nothing was changed: " + "; ".join(problems[:5]))
    return wf, report


def _check_subgraph(d: dict) -> list[str]:
    """The same checks inside one subgraph definition (its links are dicts, its inputs and outputs are the nodes -10 and -20)."""
    name = d.get("name") or d.get("id")
    problems = []
    nodes = {}
    for n in d.get("nodes", []):
        if n["id"] in nodes:
            problems.append(f"{name}: duplicate node id {n['id']}")
        nodes[n["id"]] = n
    links = {}
    for l in d.get("links", []):
        if l["id"] in links:
            problems.append(f"{name}: duplicate link id {l['id']}")
        links[l["id"]] = l
        for end, key, slot_key, field in ((l["origin_id"], "origin_id", "origin_slot", "outputs"), (l["target_id"], "target_id", "target_slot", "inputs")):
            if end in (-10, -20):
                continue
            node = nodes.get(end)
            if node is None:
                problems.append(f"{name}: link {l['id']} joins a missing node {end}")
            elif l[slot_key] >= len(node.get(field, [])):
                problems.append(f"{name}: link {l['id']} uses a missing slot of node {end}")
        target = nodes.get(l["target_id"])
        if target is not None and l["target_slot"] < len(target.get("inputs", [])) and target["inputs"][l["target_slot"]].get("link") != l["id"]:
            problems.append(f"{name}: link {l['id']} is not recorded on its target")
    for n in nodes.values():
        for slot in n.get("inputs", []):
            if slot.get("link") is not None and slot["link"] not in links:
                problems.append(f"{name}: node {n['id']} input '{slot['name']}' points at missing link {slot['link']}")
    for field in ("inputs", "outputs"):
        for io in d.get(field, []):
            for lid in io.get("linkIds") or []:
                if lid not in links:
                    problems.append(f"{name}: {field[:-1]} '{io['name']}' lists missing link {lid}")
    return problems


def check_workflow(wf: dict) -> list[str]:
    """Structural problems of a serialized workflow: duplicate ids, links to missing nodes or slots, inputs that disagree with the link table."""
    problems = []
    nodes = {}
    for n in wf["nodes"]:
        if n["id"] in nodes:
            problems.append(f"duplicate node id {n['id']}")
        nodes[n["id"]] = n
    links = {}
    for l in wf["links"]:
        if l[0] in links:
            problems.append(f"duplicate link id {l[0]}")
        links[l[0]] = l
        o, t = nodes.get(l[1]), nodes.get(l[3])
        if o is None or t is None:
            problems.append(f"link {l[0]} joins a missing node ({l[1]} -> {l[3]})")
            continue
        if l[2] >= len(o.get("outputs", [])) or l[4] >= len(t.get("inputs", [])):
            problems.append(f"link {l[0]} uses a missing slot")
        elif t["inputs"][l[4]].get("link") != l[0] or l[0] not in (o["outputs"][l[2]].get("links") or []):
            problems.append(f"link {l[0]} is not recorded on its nodes")
    for n in wf["nodes"]:
        for slot in n.get("inputs", []):
            if slot.get("link") is not None and slot["link"] not in links:
                problems.append(f"node {n['id']} input '{slot['name']}' points at missing link {slot['link']}")
    ids = [g.get("id") for g in wf.get("groups", [])]
    if len(set(ids)) != len(ids):
        problems.append("duplicate group ids")
    for d in wf.get("definitions", {}).get("subgraphs", []):
        problems += _check_subgraph(d)
    defs = {d["id"] for d in wf.get("definitions", {}).get("subgraphs", [])}
    for n in wf["nodes"]:
        if UUID.fullmatch(str(n["type"])) and n["type"] not in defs:
            problems.append(f"node {n['id']} uses a missing subgraph definition")
    return problems


LIST_SOURCES = ("MajoorCreateTimeline", "MajoorSceneDetectSplit")


def _follow_wire(wf: dict, node: dict, slot: int) -> tuple[dict, int]:
    """Through Reroute nodes, KJNodes Get/Set pairs and a switch (the input its own `switch` widget selects), to the node that really makes the value."""
    by_id = {n["id"]: n for n in wf["nodes"]}
    links = {l[0]: l for l in wf["links"]}
    for _ in range(64):
        if node["type"] == GET:
            name = _name(node)
            node = next((n for n in wf["nodes"] if n["type"] == SET and _name(n) == name), None)
            if node is None:
                break
            feeding = (node.get("inputs") or [{}])[0].get("link")
        elif node["type"] == "Reroute":
            feeding = (node.get("inputs") or [{}])[0].get("link")
        elif node["type"] == SWITCH:
            chosen = "on_true" if (node.get("widgets_values") or [False])[0] else "on_false"
            feeding = next((i.get("link") for i in node.get("inputs") or [] if i["name"] == chosen), None)
        else:
            break
        if feeding not in links:
            break
        node, slot = by_id[links[feeding][1]], links[feeding][2]
    return node, slot


def shot_list_source(wf: dict, anchor: dict | None) -> tuple[dict, int] | None:
    """The node the shot blocks read the shot list from: what feeds the Deploy Shots node, else what feeds a Set 'SHOT_LIST', else the only Create Timeline /
    Scene Detect & Split of the graph. Returns (node, output slot)."""
    by_id = {n["id"]: n for n in wf["nodes"]}
    links = {l[0]: l for l in wf["links"]}

    def from_input(node: dict, index: int):
        feeding = (node.get("inputs") or [{}] * (index + 1))[index].get("link")
        if feeding in links:
            origin, slot = _follow_wire(wf, by_id[links[feeding][1]], links[feeding][2])
            return (origin, slot) if origin["type"] in LIST_SOURCES else None
        return None

    if anchor is not None:
        for i, slot in enumerate(anchor.get("inputs", [])):
            if slot["name"] == "shot_list":
                found = from_input(anchor, i)
                if found:
                    return found
    for n in wf["nodes"]:
        if n["type"] == SET and _name(n) == "SHOT_LIST" and not _stamp(n):
            found = from_input(n, 0)
            if found:
                return found
    candidates = [n for n in wf["nodes"] if n["type"] in LIST_SOURCES]
    return (candidates[0], 0) if len(candidates) == 1 else None


def _drop_links_in_clone(clone: Clone, link_id: int) -> None:
    clone.links = [l for l in clone.links if l[0] != link_id]
    for node in clone.nodes:
        for slot in node.get("outputs", []):
            if slot.get("links"):
                slot["links"] = [i for i in slot["links"] if i != link_id] or None


def _connect_ids(nodes: list[dict], alloc: Alloc, wf: dict, origin_id: int, origin_slot: int, target_id: int, target_slot: int, kind: str) -> None:
    origin = next(n for n in nodes if n["id"] == origin_id)
    target = next(n for n in nodes if n["id"] == target_id)
    lid = alloc.next_link()
    wf["links"].append([lid, origin_id, origin_slot, target_id, target_slot, kind])
    target["inputs"][target_slot]["link"] = lid
    origin["outputs"][origin_slot]["links"] = [*(origin["outputs"][origin_slot].get("links") or []), lid]
