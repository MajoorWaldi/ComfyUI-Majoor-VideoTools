import json

import numpy as np
import pytest

from majoor_videotools.core.cut_markers import beat_grid, extend_beats, format_markers, parse_markers, plan_from_markers, preview_mono, waveform_peaks
from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.template import parse_plan
from majoor_videotools.core.timeline_sources import merge_plans, rhythm_text


def test_markers_are_read_in_seconds_timecodes_and_frames():
    assert parse_markers("1.5, 3 0:04.25 1:02 36f 2.5s", 24) == [1.5, 2.5, 3.0, 4.25, 62.0]  # 36f = 1.5 s, equal to the first
    assert parse_markers("", 24) == [] and parse_markers("  \n", 24) == [] and parse_markers("0 0.0", 24) == []
    with pytest.raises(MajoorError, match="Cannot read the marker 'soon'"):
        parse_markers("1.0 soon", 24)
    assert format_markers([3.0, 1.5, 4.25]) == "1.5 3 4.25"
    assert parse_markers(format_markers([0.125, 7.333]), 24) == [0.125, 7.333]


def test_markers_make_shots_and_group_short_cuts_into_sub_cuts():
    plan, info = plan_from_markers([0.25, 0.5, 0.75, 2.0, 2.25, 4.0], 6.0, fps=24, min_shot_seconds=1.0)
    rows = plan["shots"]
    assert [r["duration_frames"] for r in rows] == [48, 48, 48] and info["cuts"] == 7 and info["shots"] == 3
    assert rows[0]["sub_cuts"] == [{"duration_frames": n} for n in (6, 6, 6, 30)] and "sub_cuts" not in rows[2] and not info["warnings"]
    parsed = parse_plan(json.dumps(plan), 24, "16:9", 320)  # a normal Timeline plan
    assert sum(s.frames for s in parsed.shots) == 144
    text = rhythm_text(json.dumps(plan), 24)
    assert text.startswith("EDIT RHYTHM: 3 shots, 7 cuts, 6.00 s")


def test_markers_without_cuts_and_out_of_range_ones():
    plan, info = plan_from_markers([], 4.0, fps=24)
    assert plan["shots"] == [{"duration_frames": 96, "prompt": "", "notes": "markers 0.00-4.00s, 1 cut"}] and info["cuts"] == 1
    plan, info = plan_from_markers([1.0, 9.0, 10.0], 4.0, fps=24, aspect_ratio="9:16")
    assert [r["duration_frames"] for r in plan["shots"]] == [24, 72]  # the markers at 9 s and 10 s are past the end
    assert plan["aspect_ratio"] == "9:16" and any("2 marker(s) after the end" in w for w in info["warnings"])
    plan, info = plan_from_markers([1.0, 1.04, 2.0], 4.0, fps=24, min_shot_seconds=0.2)  # a cut 1 frame after another is merged
    assert info["warnings"] and sum(r["duration_frames"] for r in plan["shots"]) == 96
    with pytest.raises(MajoorError, match="needs a duration"):
        plan_from_markers([1.0], 0.0)


def test_markers_are_a_skeleton_for_the_plan_of_an_llm():
    skeleton, _ = plan_from_markers([0.25, 0.5, 0.75, 2.0], 4.0, fps=24, min_shot_seconds=1.0)
    llm = json.dumps({"shots": [{"prompt": "<Picture 1> a", "zoom": 1.5, "sub_cuts": [{"zoom": 2}, {"flip": True}]}, {"prompt": "<Picture 1> b"}]})
    merged, warnings = merge_plans(json.dumps(skeleton), llm, 24, "16:9", 768)
    assert [r["duration_frames"] for r in merged["shots"]] == [sum(c["duration_frames"] for c in skeleton["shots"][0]["sub_cuts"]), skeleton["shots"][1]["duration_frames"]]
    assert merged["shots"][0]["sub_cuts"][0]["zoom"] == [2.0, 2.0] and merged["shots"][0]["sub_cuts"][1]["flip"] is True and len(warnings) <= 1


def test_waveform_peaks_grid_and_light_copy():
    t = np.arange(22050 * 4) / 22050  # four seconds, loud for the first two
    samples = (np.sin(2 * np.pi * 220 * t) * np.where(t < 2, 1.0, 0.25)).astype(np.float32)
    peaks = waveform_peaks(samples, 100)
    assert len(peaks) == 100 and max(peaks) == 1.0 and peaks[10] > 0.9 and 0.2 < peaks[90] < 0.3
    assert waveform_peaks(np.zeros(10, np.float32), 5) == [0.0] * 5 and waveform_peaks(np.zeros(0, np.float32)) == []
    assert beat_grid(np.array([-0.1, 0.0, 0.5, 1.0, 9.0]), 2.0) == [0.0, 0.5, 1.0]
    light, rate = preview_mono(np.arange(48000 * 2, dtype=np.float32), 48000)
    assert rate == 24000 and len(light) == 48000 and light[0] == pytest.approx(0.5)
    same, rate = preview_mono(np.zeros(100, np.float32), 16000)
    assert rate == 16000 and len(same) == 100


def test_beats_go_on_when_the_music_is_shorter_than_the_edit():
    beats = np.array([0.5, 1.0, 1.5])
    grown = extend_beats(beats, 120.0, 3.2)
    assert grown.tolist() == [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    assert extend_beats(beats, 120.0, 1.6).tolist() == [0.5, 1.0, 1.5] and extend_beats(np.array([]), 120.0, 9).size == 0
