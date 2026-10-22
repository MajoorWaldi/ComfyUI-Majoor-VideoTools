"""Every node of the pack run on real media (a 3-scene clip, a generated take, a click track): Scene Detect, Create Timeline (json, music, video, none), Select / Apply Shot Metadata,
Shot Assemble (music, order, fps, effects), Cut Markers, Audio Rhythm, Music Brief, Edit Skills, Edit Mode, the previews and their refusals. Needs ffmpeg.
Everything is written under a temporary output folder.

    ComfyUI/.venv/Scripts/python.exe custom_nodes/ComfyUI-Majoor-VideoTools/tests/comfy/check_nodes.py
"""
import json
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import _boot  # noqa: E402
import comfy.utils  # noqa: E402
import folder_paths  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
from comfy_api.latest import InputImpl  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="mvt_audit_"))
for sub in ("input", "output", "temp"):
    (TMP / sub).mkdir()
folder_paths.get_output_directory = lambda: str(TMP / "output")
folder_paths.get_input_directory = lambda: str(TMP / "input")
folder_paths.get_temp_directory = lambda: str(TMP / "temp")


class _Bar:
    def __init__(self, *a, **k): pass
    def update_absolute(self, *a, **k): pass
    def update(self, *a, **k): pass


comfy.utils.ProgressBar = _Bar

from MVT.nodes.apply_shot_metadata import MajoorApplyShotMetadata as Apply  # noqa: E402
from MVT.nodes.audio_rhythm import MajoorAudioRhythm as Rhythm  # noqa: E402
from MVT.nodes.compare_video import MajoorCompareVideo as Compare  # noqa: E402
from MVT.nodes.create_timeline import MajoorCreateTimeline as Timeline  # noqa: E402
from MVT.nodes.cut_markers import MajoorCutMarkers as Markers  # noqa: E402
from MVT.nodes.edit_mode import MajoorEditMode as Mode  # noqa: E402
from MVT.nodes.edit_skills import MajoorEditSkills as Skills  # noqa: E402
from MVT.nodes.select_frames import MajoorSelectEveryNFrames as EveryN  # noqa: E402
from MVT.nodes.music_brief import MajoorMusicBrief as Brief  # noqa: E402
from MVT.nodes.preview_video import MajoorPreviewVideo as Preview  # noqa: E402
from MVT.nodes.scene_detect_split import MajoorSceneDetectSplit as Detect  # noqa: E402
from MVT.nodes.select_shot import MajoorSelectShot as Select  # noqa: E402
from MVT.nodes.shot_assemble import MajoorShotAssemble as Assemble  # noqa: E402
from MVT.core.errors import MajoorError  # noqa: E402


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


IN = TMP / "input"
ffmpeg("-f", "lavfi", "-i", "color=c=red:s=320x240:r=24:d=2", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=24:d=2", "-f", "lavfi", "-i", "smptebars=s=320x240:r=24:d=2", "-f", "lavfi", "-i", "sine=f=440:d=6:r=48000",
       "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-g", "12", "-pix_fmt", "yuv420p", "-c:a", "aac", str(IN / "scenes.mp4"))
ffmpeg("-f", "lavfi", "-i", "testsrc=s=160x120:r=30:d=3", "-f", "lavfi", "-i", "sine=f=880:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(IN / "gen.mp4"))
ffmpeg("-f", "lavfi", "-i", "testsrc=s=321x241:r=24:d=1", "-c:v", "libx264", "-pix_fmt", "yuv444p", str(IN / "odd.mp4"))
scenes = InputImpl.VideoFromFile(str(IN / "scenes.mp4"))
gen = InputImpl.VideoFromFile(str(IN / "gen.mp4"))

rate = 22050
click = np.zeros(int(rate * 6), np.float32)
for t in np.arange(0, 5.9, 0.5):
    i = int(t * rate)
    click[i:i + 800] += (np.random.default_rng(1).standard_normal(800) * np.exp(-np.arange(800) / 150)).astype(np.float32) * 0.8
music = {"waveform": torch.from_numpy(np.stack([click, click]))[None], "sample_rate": rate}

results = []


def check(name, fn):
    refused = "refused" in name  # a name with "refused" must raise a clear error
    t = time.time()
    try:
        out = fn()
    except Exception as e:  # noqa: BLE001
        if refused and isinstance(e, (MajoorError, ValueError)):
            results.append((name, "ok", str(e)))
            print(f"ok   {name:58s} {type(e).__name__}: {str(e)[:100]}")
            return None
        results.append((name, "FAIL", repr(e)))
        print(f"FAIL {name:58s} {type(e).__name__}: {str(e)[:200]}")
        traceback.print_exc(limit=3)
        return None
    if refused:
        results.append((name, "FAIL", "not refused"))
        print(f"FAIL {name:58s} not refused")
        return out
    results.append((name, "ok", out))
    print(f"ok   {name:58s} {str(out)[:110]} ({time.time() - t:.2f}s)")
    return out


def args(o):
    return o.args if hasattr(o, "args") else o


# --- select every n frames
check("Select Every N Frames: 16 of 240 reach the end", lambda: (lambda r: (tuple(r[0].shape), r[1].split(", ")[0], r[1].split(", ")[-1]))(args(EveryN.execute(images=torch.rand(240, 8, 8, 3), every_n=2, max_frames=16, spread_to_end=True))))
check("Select Every N Frames: refused on an empty batch (refused)", lambda: EveryN.execute(images=torch.rand(0, 8, 8, 3), every_n=2, max_frames=16, spread_to_end=True))

# --- edit skills: pictures and videos in one batch, announced in the message
def _skills_videos():
    out = args(Skills.execute(skill="h3_shot_prompt_from_plan", overlays_splits=True, text_overlays=True, reference_mode=True, genre="all", duration=0.0, fps=0.0, aspect_ratio="auto", n_pictures=1,
                              text_allowed="", brief="", extra_instructions="", profile="none", cut_density="auto", transition_intensity="auto", creative_freedom="auto", reference_fidelity="auto",
                              narrative_coherence="auto", rhythm_text="SHOT_001", images=torch.rand(2, 64, 64, 3), video_1=torch.rand(8, 32, 48, 3), video_2=torch.rand(4, 96, 64, 3)))
    return tuple(out[3].shape), "<Video 2> = images 11 to 14" in out[1]


check("Edit Skills: 2 pictures + 8 + 4 frames in one batch, announced", _skills_videos)
check("Edit Skills: no image gives no batch", lambda: args(Skills.execute(skill="h3_shot_prompt_from_plan", overlays_splits=True, text_overlays=True, reference_mode=True, genre="all", duration=0.0, fps=0.0, aspect_ratio="auto", n_pictures=1,
                                                                           text_allowed="", brief="", extra_instructions="", profile="none", cut_density="auto", transition_intensity="auto", creative_freedom="auto", reference_fidelity="auto",
                                                                           narrative_coherence="auto"))[3])

# --- preview / compare
check("Preview Video: a file of the input folder", lambda: args(Preview.execute(video=scenes)) or "ui ok")
check("Preview ref of a cropped video is the crop", lambda: (lambda r: (r["width"], r["height"]))(__import__("MVT.adapters.comfy_video", fromlist=["x"]).preview_ref(scenes.as_cropped(0, 0, 100, 80))))
check("Preview ref of a trimmed video", lambda: (lambda r: round(r["duration"], 2))(__import__("MVT.adapters.comfy_video", fromlist=["x"]).preview_ref(scenes.as_trimmed(1.0, 2.0))))
check("Preview Video: images batch with odd size", lambda: Preview.execute(images=torch.rand(8, 241, 321, 3), fps=24.0) and "ok")
check("Preview Video: both video and images refused", lambda: Preview.execute(video=scenes, images=torch.rand(2, 16, 16, 3)))

# --- scene detect
shots = check("Scene Detect: 3 scenes", lambda: args(Detect.execute(video=scenes, detection_mode="adaptive", sensitivity=0.5, min_shot_frames=6))[0])
check("   shots found", lambda: [(s.shot_id, s.start_frame, s.end_frame_exclusive) for s in shots.shots])
check("Scene Detect: shot_count", lambda: args(Detect.execute(video=scenes, detection_mode="adaptive", sensitivity=0.5, min_shot_frames=6))[3])
rhythm = check("Scene Detect: rhythm_text and skeleton_json", lambda: (lambda r: (r[0].splitlines()[0], len(json.loads(r[1])["shots"])))(args(Detect.execute(video=scenes, detection_mode="adaptive", sensitivity=0.5, min_shot_frames=6))[1:]))
cropped = scenes.as_cropped(10, 10, 100, 80)
c_shots = check("Scene Detect: a cropped video", lambda: args(Detect.execute(video=cropped, detection_mode="adaptive", sensitivity=0.5, min_shot_frames=6))[0])
check("   source size of the cropped video", lambda: (c_shots.source.width, c_shots.source.height))
trimmed = scenes.as_trimmed(1.0, 3.0)
t_shots = check("Scene Detect: a trimmed video", lambda: args(Detect.execute(video=trimmed, detection_mode="adaptive", sensitivity=0.5, min_shot_frames=6))[0])
check("   frames of the trimmed video", lambda: t_shots.source.frame_count)
check("Scene Detect: manual cuts", lambda: len(args(Detect.execute(video=scenes, detection_mode="manual", sensitivity=0.5, min_shot_frames=6, cut_points="24 60"))[0].shots))
check("Scene Detect: manual cut outside refused", lambda: Detect.execute(video=scenes, detection_mode="manual", sensitivity=0.5, min_shot_frames=6, cut_points="9999"))

# --- timeline
plan = json.dumps({"fps": 24, "shots": [{"duration": 1.0, "prompt": "a"}, {"duration": 1.5, "prompt": "b", "sub_cuts": [{"duration": 0.5}, {"duration": 1.0, "zoom": 1.5}]}, {"duration": 1.0, "prompt": "c"}]})


def timeline(source, **kw):
    base = dict(source=source, fps=0.0, aspect_ratio="auto", resolution=256, generation_profile="minimax_h3")
    return args(Timeline.execute(**base, **kw))


check("Create Timeline: shot_count", lambda: timeline({"source": "json", "plan_json": plan, "cut_snap": "off", "bpm": 0.0}, preview_thumbnails=False, card_text=False)[3])
tl = check("Create Timeline: json", lambda: timeline({"source": "json", "plan_json": plan, "cut_snap": "off", "bpm": 0.0}, preview_thumbnails=False, card_text=False))
check("   rhythm text", lambda: tl[2].split("\n")[0])
tm = check("Create Timeline: music", lambda: timeline({"source": "music", "cut_every": "bar", "shots": 0, "duration": 0.0, "bpm": 0.0, "beats_per_bar": 4, "downbeat": 0}, music=music, preview_thumbnails=False, card_text=False))
check("   music plan", lambda: tm[2].split("\n")[0])
check("Create Timeline: music without music refused", lambda: timeline({"source": "music", "cut_every": "bar", "shots": 0, "duration": 0.0, "bpm": 0.0, "beats_per_bar": 4, "downbeat": 0}))
tv = check("Create Timeline: video", lambda: timeline({"source": "video", "detection_mode": "adaptive", "sensitivity": 0.5, "min_cut_seconds": 0.1, "min_shot_seconds": 1.0, "cut_snap": "off"}, video=scenes, preview_thumbnails=False, card_text=False))
check("   video plan", lambda: tv[2].split("\n")[0])
check("Create Timeline: none", lambda: timeline({"source": "none"}, preview_thumbnails=False)[1] == "")
check("Create Timeline: skeleton + plan", lambda: timeline({"source": "json", "plan_json": plan, "cut_snap": "off", "bpm": 0.0}, skeleton_json=tm[1], preview_thumbnails=False, card_text=False)[2].split("\n")[0])
check("Create Timeline: bad json refused with the text", lambda: timeline({"source": "json", "plan_json": "{nope", "cut_snap": "off", "bpm": 0.0}))

# --- select / apply / assemble
shot_list = tl[0]
sel = check("Select Shot: SHOT_002", lambda: args(Select.execute(shot_list=shot_list, shot_id="SHOT_002", take="active", frame_sampling="first_middle_last", sample_count=3, preview_resolution=128)))
check("   outputs", lambda: (tuple(sel[1].shape), sel[3], sel[5], round(sel[6], 2)))
check("Select Shot: every_n reaches the last frame", lambda: (lambda s: (tuple(s[1].shape), len(s[1])))(args(Select.execute(shot_list=shot_list, shot_id="SHOT_002", take="active", frame_sampling="every_n", sample_count=5, preview_resolution=128, every_n=4, spread_to_end=True))))
check("Select Shot: unknown shot refused", lambda: Select.execute(shot_list=shot_list, shot_id="SHOT_099", take="active", frame_sampling="first", sample_count=1, preview_resolution=128))
check("Select Shot: unknown revision refused", lambda: Select.execute(shot_list=shot_list, shot_id="SHOT_001", take="revision_id", frame_sampling="first", sample_count=1, preview_resolution=128, revision_id="take_9"))
current = shot_list
for sid in ("SHOT_001", "SHOT_002", "SHOT_003"):
    s = args(Select.execute(shot_list=shot_list, shot_id=sid, take="active", frame_sampling="first", sample_count=1, preview_resolution=128))
    current = check(f"Apply Shot Metadata: {sid}", lambda s=s, current=current: args(Apply.execute(shot_list=current, metadata=s[2], video=gen, activate_new_take=True, duration_policy="inherit_target"))[0])
asm = check("Shot Assemble: default", lambda: Assemble.execute(shot_list=current, assembly_mode="original_order", missing_shot_policy="error", duration_policy="trim_or_pad_last_frame", fps_policy="source", audio_policy="mute", output_format="mp4", video_codec="h264", output_name="audit"))
check("   assembled length", lambda: (lambda v: (v.get_duration(), v.get_frame_count() if hasattr(v, "get_frame_count") else None))(args(asm)[0]))
check("Shot Assemble: with music and sfx", lambda: Assemble.execute(shot_list=current, assembly_mode="original_order", missing_shot_policy="error", duration_policy="trim_or_pad_last_frame", fps_policy="source", audio_policy="mute", output_format="mp4", video_codec="h264", output_name="audit_music", music=music, sfx=music, music_volume=0.5, sfx_volume=0.5, music_fade=1.0) and "ok")
check("Shot Assemble: manual order", lambda: Assemble.execute(shot_list=current, assembly_mode="manual_order", manual_order="SHOT_003, SHOT_001, SHOT_002", missing_shot_policy="error", duration_policy="trim_or_pad_last_frame", fps_policy="source", audio_policy="mute", output_format="mp4", video_codec="h264", output_name="audit_order") and "ok")
check("Shot Assemble: manual order with a missing shot refused", lambda: Assemble.execute(shot_list=current, assembly_mode="manual_order", manual_order="SHOT_003", missing_shot_policy="error", duration_policy="trim_or_pad_last_frame", fps_policy="source", audio_policy="mute", output_format="mp4", video_codec="h264", output_name="x"))
check("Shot Assemble: hostile output name", lambda: Assemble.execute(shot_list=current, assembly_mode="original_order", missing_shot_policy="error", duration_policy="trim_or_pad_last_frame", fps_policy="source", audio_policy="mute", output_format="mp4", video_codec="h264", output_name="../../evil") and sorted(p.name for p in (TMP / "output").rglob("evil*")))
check("Shot Assemble: mov, fixed fps, retime", lambda: Assemble.execute(shot_list=current, assembly_mode="original_order", missing_shot_policy="error", duration_policy="retime_to_target", fps_policy="fixed", output_fps=30.0, audio_policy="shot_audio", output_format="mov", video_codec="h264", output_name="audit_mov") and "ok")
check("Shot Assemble: effects off", lambda: Assemble.execute(shot_list=current, assembly_mode="original_order", missing_shot_policy="error", duration_policy="trim_or_pad_last_frame", fps_policy="source", audio_policy="mute", output_format="mp4", video_codec="h264", output_name="audit_fx", effects=False, sub_cuts=False) and "ok")
check("Shot Assemble: the template alone refused", lambda: Assemble.execute(shot_list=shot_list, assembly_mode="original_order", missing_shot_policy="error", duration_policy="trim_or_pad_last_frame", fps_policy="source", audio_policy="mute", output_format="mp4", video_codec="h264", output_name="x"))

# --- cut markers
check("Cut Markers: video and music", lambda: args(Markers.execute(markers="1 2", min_shot_seconds=0.5, fps=0.0, aspect_ratio="auto", duration=0.0, bpm=0.0, beats_per_bar=4, downbeat=0, video=scenes, music=music))[0][:60])
check("Cut Markers: shot_count", lambda: args(Markers.execute(markers="1 2", min_shot_seconds=0.5, fps=0.0, aspect_ratio="auto", duration=0.0, bpm=0.0, beats_per_bar=4, downbeat=0, video=scenes, music=music))[2])
check("Cut Markers: nothing connected refused", lambda: Markers.execute(markers="", min_shot_seconds=1.0, fps=0.0, aspect_ratio="auto", duration=0.0, bpm=0.0, beats_per_bar=4, downbeat=0))
check("Cut Markers: a marker after the end", lambda: args(Markers.execute(markers="99", min_shot_seconds=0.5, fps=0.0, aspect_ratio="auto", duration=6.0, bpm=0.0, beats_per_bar=4, downbeat=0, music=music))[0][:60])

# --- audio rhythm, music brief, edit skills, edit mode
plan_text = tm[1]
check("Audio Rhythm: with music", lambda: args(Rhythm.execute(plan_json=plan_text, fps=0.0, sensitivity=0.5, music=music))[0].count("audio:"))
check("Audio Rhythm: stereo float music clipping", lambda: args(Rhythm.execute(plan_json=plan_text, fps=0.0, sensitivity=1.0, music={"waveform": music["waveform"] * 5, "sample_rate": rate}))[0].count("audio:"))
check("Audio Rhythm: mono 8-bit-ish tiny music", lambda: args(Rhythm.execute(plan_json=plan_text, fps=0.0, sensitivity=0.5, music={"waveform": music["waveform"][:, :1, :2000], "sample_rate": rate}))[0].count("audio:"))
check("Audio Rhythm: no music", lambda: args(Rhythm.execute(plan_json=plan_text, fps=0.0, sensitivity=0.5))[0].count("audio:"))
check("Audio Rhythm: empty plan", lambda: args(Rhythm.execute(plan_json="", fps=0.0, sensitivity=0.5, music=music)))
check("Audio Rhythm: bad plan refused", lambda: Rhythm.execute(plan_json="[]", fps=0.0, sensitivity=0.5, music=music))
check("Music Brief: fenced JSON", lambda: args(Brief.execute(brief_json='```json\n{"bpm": 120, "duration": 8, "music_prompt": "lofi", "sfx": []}\n```', bpm=0.0, duration=0.0, steady_beat=True))[:3])
check("Music Brief: bad JSON refused", lambda: Brief.execute(brief_json="no", bpm=0.0, duration=0.0, steady_beat=True))
check("Edit Mode: executes to nothing", lambda: args(Mode.execute(mode="image_to_edit")))
check("Edit Skills: every prompt skill", lambda: [len(args(Skills.execute(skill=s, overlays_splits=True, text_overlays=True, reference_mode=True, genre="all", duration=0.0, fps=0.0, aspect_ratio="auto", n_pictures=1, text_allowed="", brief="b", extra_instructions="", profile="none", cut_density="auto", transition_intensity="auto", creative_freedom="auto", reference_fidelity="auto", narrative_coherence="auto"))[0].split()) for s in ("timeline_planner", "dynamic_edit_skill", "h3_shot_prompt_from_plan", "music_brief_from_plan", "remix_planner", "remix_shot_analyzer", "remix_edit_director")])
check("Edit Skills: images batch counts the pictures", lambda: args(Skills.execute(skill="timeline_planner", overlays_splits=True, text_overlays=True, reference_mode=True, genre="all", duration=0.0, fps=0.0, aspect_ratio="auto", n_pictures=1, text_allowed="", brief="b", extra_instructions="", profile="none", cut_density="auto", transition_intensity="auto", creative_freedom="auto", reference_fidelity="auto", narrative_coherence="auto", images=torch.rand(3, 8, 8, 3)))[1].count("<Picture"))

failed = [r for r in results if r[1] == "FAIL"]
print(chr(10) + "==== summary:", len(results) - len(failed), "ok,", len(failed), "failed")
sys.exit(1 if failed else 0)
