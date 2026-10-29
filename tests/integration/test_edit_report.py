"""The report of a finished edit: contact sheet, first frame, black stretches, cuts against the music."""
import json
import subprocess

import numpy as np
from PIL import Image

from majoor_videotools.core.beats import write_wav
from majoor_videotools.core.edit_report import REVIEW_CHECKLIST, contact_sheet, cut_times, edit_report, first_frame, black_stretches, sync_report


def video(path, black_first=0.0):
    """6 s at 24 fps: black for `black_first` seconds (if any), then a test picture."""
    graph = "testsrc2=s=128x224:d=6:r=24[v]" if not black_first else "color=c=black:s=128x224:d=%s:r=24[a];testsrc2=s=128x224:d=%s:r=24[b];[a][b]concat=n=2:v=1:a=0[v]" % (black_first, 6 - black_first)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-filter_complex", graph, "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def manifest(shots):
    return {"source": {"fps_num": 24, "fps_den": 1}, "shots": [{"target_duration_seconds": d, "plan": {"fx": {"sub_cuts": [{"frames": f} for f in subs]} if subs else {}}} for d, subs in shots]}


def test_the_cuts_of_an_edit_are_the_shot_starts_and_the_cuts_inside_the_shots():
    assert cut_times(manifest([(2.0, None), (2.0, [12, 12, 24]), (2.0, None)])) == [2.0, 2.5, 3.0, 4.0]


def test_a_black_first_frame_and_a_black_stretch_are_reported(tmp_path):
    ok = video(tmp_path / "ok.mp4")
    dark = video(tmp_path / "dark.mp4", black_first=1.5)
    assert first_frame(ok)["ok"] is True and first_frame(dark)["ok"] is False
    assert black_stretches(ok) == []
    stretch = black_stretches(dark)
    assert len(stretch) == 1 and stretch[0]["start"] < 0.1 and 1.4 <= stretch[0]["end"] <= 1.6


def test_the_cuts_are_measured_against_the_attacks_of_the_music():
    accents, strength = np.array([1.0, 2.0, 3.0, 4.0]), np.array([1.0, 0.9, 0.2, 1.0])  # the one at 3 s is weak: it is not an attack to cut on
    report = sync_report([1.02, 2.5, 3.0, 4.2], accents, strength)
    assert report["attacks"] == 3 and report["distances_ms"] == [20, 500, 1000, 200]
    assert report["within_50ms"] == 1 and report["within_100ms"] == 1 and report["median_ms"] == 350
    assert sync_report([1.0], np.zeros(0), np.zeros(0))["within_50ms"] is None


def test_a_contact_sheet_tiles_the_frames_with_their_times(tmp_path):
    sheets = contact_sheet(video(tmp_path / "v.mp4"), [0.5, 1.5, 2.5, 3.5, 4.5], tmp_path / "sheets", columns=2, rows=2, tile_width=100)
    assert [p.name for p in sheets] == ["sheet-1.png", "sheet-2.png"]
    assert Image.open(sheets[0]).size[0] == 200 and Image.open(sheets[1]).size[0] == 200


def test_the_report_of_an_edit_is_written_with_its_sheets(tmp_path):
    project = tmp_path / "p_abc"
    (project / "music").mkdir(parents=True)
    json.dump(manifest([(2.0, None), (2.0, [12, 36]), (2.0, None)]), open(project / "manifest.json", "w"))
    clicks = np.zeros(22050 * 6, dtype=np.float32)
    for k in range(6):
        clicks[int(k * 22050):int(k * 22050) + 300] = np.hanning(300)
    write_wav(project / "music" / "retained.wav", np.stack([clicks, clicks], axis=1), 22050)
    out = edit_report(project, video(tmp_path / "v.mp4"))
    assert out["cuts"] == [2.0, 2.5, 4.0] and out["first_frame"]["ok"] and out["sync"]["cuts"] == 3 and out["sheets"] == ["sheet-1.png"]
    assert (project / "exports" / "edit_report.json").is_file() and (project / "exports" / "sheet-1.png").is_file() and out["checklist"] == REVIEW_CHECKLIST
