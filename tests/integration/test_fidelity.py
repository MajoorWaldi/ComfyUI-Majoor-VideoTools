import json
from pathlib import Path


def test_remix_regeneration_uses_original_source_instead_of_previous_generated_take():
    root=Path(__file__).resolve().parents[2]
    prompt=json.loads((root/'HyperKut Studio/workflows/remix/shot.api.json').read_text(encoding='utf-8'))
    select=next(n for n in prompt.values() if n['class_type']=='MajoorSelectShot')
    assert select['inputs']['take']=='original'
    for path in ('workflows/SECATOR Remix.json','recipes/SECATOR Remix.json'):
        graph=json.loads((root/path).read_text(encoding='utf-8'))
        node=next(n for n in graph['nodes'] if n['type']=='MajoorSelectShot')
        assert node['widgets_values'][1]=='original'
