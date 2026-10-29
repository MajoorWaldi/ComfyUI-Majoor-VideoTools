from majoor_videotools.core.hyperframes_layers import prepare_layers
from majoor_videotools.core.media_probe import probe
from majoor_videotools.core.motion import parse_layers
import json


def test_short_effect_extracts_only_active_frames_with_exact_mapping(tmp_path, fixtures):
    info = probe(fixtures['gen'], with_packets=False)
    rows = parse_layers(json.dumps([{'type':'effect','kind':'grain','start':1,'end':2}]), float(info.duration))
    assets = prepare_layers(tmp_path, fixtures['gen'], info, rows)
    paths = assets['frame_paths']
    assert paths[0] is None and paths[30] is not None and paths[60] is None
    assert sum(p is not None for p in paths) == 30
    assert len(list((tmp_path/'assets/frames').glob('*.png'))) == 30
