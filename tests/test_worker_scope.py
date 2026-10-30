from dataclasses import replace
from pathlib import Path

import pytest

from majoor_videotools.core.models import Source, Revision, Shot, ShotList, Detection
from majoor_videotools.core.project import load_shot_list, fork_shot_list
from majoor_videotools.core.paths import ProjectStore
from majoor_videotools.core.revisions import make_metadata, check_lineage
from majoor_videotools.core.errors import ManifestError


def collection():
    source=Source('sources/input.mp4','sha256:test',64,64,24,1,'CFR',24,1.,False)
    revision=Revision('original','sources/input.mp4',1.,'original')
    shot=Shot('SHOT_001',0,0,24,None,None,1.,'sources/input.mp4','original',(revision,))
    return ShotList('p_12345678',source,Detection('fixture',0.,1,'test'),(shot,))


def test_runtime_root_is_never_serialized_or_accepted_from_manifest(tmp_path):
    shot_list=replace(collection(),storage_root=tmp_path)
    encoded=shot_list.to_dict()
    assert 'storage_root' not in encoded
    encoded['storage_root']='C:/malicious/path'
    assert ShotList.from_dict(encoded).storage_root is None
    assert shot_list.with_shot(shot_list.shots[0]).storage_root==tmp_path


def test_load_and_metadata_retain_explicit_worker_root(tmp_path):
    original=collection()
    ProjectStore(tmp_path,original.project_id).write_json('manifest.json',original.to_dict())
    loaded=load_shot_list(tmp_path,original.project_id)
    metadata=make_metadata(loaded,loaded.shots[0],loaded.shots[0].active)
    assert loaded.storage_root==tmp_path.resolve()==metadata.storage_root
    assert check_lineage(loaded,metadata)==loaded.shots[0]
    other=replace(loaded,storage_root=tmp_path/'other-worker')
    with pytest.raises(ManifestError,match='workspace'):
        check_lineage(other,metadata)


def test_fork_retains_worker_root(tmp_path):
    original=replace(collection(),storage_root=tmp_path)
    source=ProjectStore(tmp_path,original.project_id)
    source.write_json('manifest.json',original.to_dict())
    source.resolve('sources/input.mp4').write_bytes(b'synthetic')
    fork=fork_shot_list(tmp_path,original,'p_87654321')
    assert fork.storage_root==tmp_path.resolve()
    assert fork_shot_list(tmp_path,original,'p_87654321').storage_root==tmp_path.resolve()


def test_real_take_stays_inside_one_worker(fixtures,tmp_path):
    from majoor_videotools.core.scene_detection import detect_scenes
    from majoor_videotools.core.revisions import apply_revision
    first_root=tmp_path/'worker-a'
    second_root=tmp_path/'worker-b'
    first=detect_scenes(fixtures['one'],first_root,'manual',.5,1,thumbnails=False)
    second=detect_scenes(fixtures['one'],second_root,'manual',.5,1,thumbnails=False)
    assert first.project_id==second.project_id
    shot=first.shots[0]
    metadata=make_metadata(first,shot,shot.active)
    with pytest.raises(ManifestError,match='destination'):
        apply_revision(first,second_root,metadata,fixtures['gen'])
    modified=apply_revision(first,first_root,metadata,fixtures['gen'])
    assert modified.storage_root==first_root.resolve()
    assert load_shot_list(second_root,second.project_id).shots[0].active_revision_id=='original'
    assert load_shot_list(first_root,first.project_id).shots[0].active_revision_id!='original'
