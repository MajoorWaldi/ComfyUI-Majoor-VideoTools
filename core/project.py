"""Read a project back from its folder: the shot list of its manifest, with every take that was registered since."""
from pathlib import Path
import dataclasses
import os
import shutil

from .errors import MajoorError
from .models import ShotList
from .paths import ProjectStore
from .scene_detection import persist_manifest


def load_shot_list(root: Path, project_id: str) -> ShotList:
    manifest = ProjectStore(root, project_id).read_json("manifest.json")
    if manifest is None:
        raise MajoorError(f"Project {project_id} has no manifest in {root}: run Create Timeline (or Scene Detect) first")
    return dataclasses.replace(ShotList.from_dict(manifest), storage_root=Path(root).resolve())


def fork_shot_list(root: Path, shot_list: ShotList, project_id: str) -> ShotList:
    """Give a caller its own editable collection; immutable media may share disk blocks."""
    if project_id == shot_list.project_id:
        return shot_list
    source = ProjectStore(root, shot_list.project_id)
    target = ProjectStore(root, project_id)
    with source.lock(), target.lock():
        existing = target.read_json('manifest.json')
        if existing:
            return dataclasses.replace(ShotList.from_dict(existing), storage_root=Path(root).resolve())
        refs = {shot_list.source.uri}
        refs.update(s.thumbnail_ref for s in shot_list.shots if s.thumbnail_ref)
        refs.update(r.media_ref for s in shot_list.shots for r in s.revisions)
        # Music is used by subsequent standalone assembly prompts.
        refs.update(source.rel(p) for p in (source.dir/'sources').rglob('*') if p.is_file())
        for ref in refs:
            src, dst = source.resolve(ref), target.resolve(ref)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
        result = dataclasses.replace(shot_list, project_id=project_id, storage_root=Path(root).resolve())
        persist_manifest(target, result)
        return result
