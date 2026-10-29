"""The text stays in the safe area, the sound effects lead into the cuts and the cuts go to the attacks of the music."""
import numpy as np
from PIL import Image

from majoor_videotools.core.beats import accent_strength, strong_accents
from majoor_videotools.core.fx import TEXT_POSITIONS, render_text, safe_box, text_overlay_filters
from majoor_videotools.core.sfx import LEAD, cue_sound, plan_cues, render_track
from majoor_videotools.core.template import snap_boundaries

W, H = 608, 1056


def spec(content, position="bottom", size=0.1, **extra):
    return {"content": content, "position": position, "size": size, "color": "white", "repeat": 1, "rotate": 0.0, **extra}


def test_text_stays_inside_the_safe_box_cut_in_lines_and_made_smaller(tmp_path):
    for content, position in (("NEW DROP", "bottom"), ("THE FRAGRANCE OF A NEW ERA", "bottom"), ("SHOP NOW", "bottom_right"), ("A VERY LONG PRODUCT HEADLINE TEXT", "center"), ("SUPERCALIFRAGILISTICEXPIALIDOCIOUS", "top")):
        left, top, right, bottom = safe_box(W, H, TEXT_POSITIONS[position][0])
        box = Image.open(render_text(spec(content, position), W, H, tmp_path)).getchannel("A").getbbox()
        assert box[0] >= left - 4 and box[1] >= top - 4 and box[2] <= right + 4 and box[3] <= bottom + 4, (content, box, (left, top, right, bottom))
    assert H - safe_box(W, H)[3] >= H * 0.2 and H - safe_box(W, H)[3] <= H * 0.3  # the bottom of a vertical video is left to the caption of the app
    assert safe_box(W, H, 1.0)[2] < safe_box(W, H, 0.5)[2]  # and the right side to its buttons


def test_a_text_has_an_outline_and_the_look_asked_for(tmp_path):
    plain = Image.open(render_text(spec("HELLO", stroke=False), W, H, tmp_path)).convert("RGBA")
    outlined = Image.open(render_text(spec("HELLO", stroke=True), W, H, tmp_path)).convert("RGBA")
    def dark(im):
        pixels = np.asarray(im).astype(int)
        return int(((pixels[..., 3] > 200) & (pixels[..., :3].sum(axis=2) < 120)).sum())

    assert dark(outlined) > 200 and dark(plain) == 0  # white letters on any picture: they carry a black edge
    assert render_text(spec("HELLO", font="serif"), W, H, tmp_path) != render_text(spec("HELLO", font="impact"), W, H, tmp_path)


def test_a_text_appears_and_leaves_at_its_time_inside_the_cut_that_holds_it():
    stream, placing = text_overlay_filters({"animation": "slide_up", "start": 0.5, "end": 2.0, "content": "NEW DROP"}, 0.0, 2.67, H)
    assert "fade=t=in:st=0.500:d=0.350" in stream and "fade=t=out:st=1.850:d=0.180" in stream and "between(t,0.500,2.030)" in placing and "pow(" in placing
    stream, placing = text_overlay_filters({"animation": "fade", "content": "NEW DROP"}, 1.0, 2.67, H)  # a later cut of the shot: the text is already there
    assert "fade=t=in" not in stream and "fade=t=out:st=1.490:d=0.180" in stream and "between(t,0.000,1.670)" in placing
    assert text_overlay_filters({"animation": "none", "content": "NEW DROP"}, 0.0, 2.0, H)[0] == ""


def test_a_text_stays_long_enough_to_be_read():
    from majoor_videotools.core.fx import reading_seconds

    assert reading_seconds("NEW DROP") == 1.0 and reading_seconds("ONE TWO THREE") == 1.0
    assert reading_seconds("ONE TWO THREE FOUR FIVE") == 1.5 and reading_seconds("") == 1.0
    _, placing = text_overlay_filters({"animation": "fade", "start": 0.5, "end": 0.8, "content": "NEW DROP"}, 0.0, 3.0, H)
    assert "between(t,0.500,2.030)" in placing  # asked for 0.3 s, shown for entrance + readable hold + exit
    _, placing = text_overlay_filters({"animation": "fade", "start": 2.0, "end": 2.2, "content": "NEW DROP"}, 0.0, 2.5, H)
    assert "between(t,2.000,2.500)" in placing  # as long as the shot allows


def test_whooshes_lead_into_the_cut_and_hits_only_land_on_attacks():
    track = render_track([(2.0, "whoosh"), (5.0, "swell")], 8.0)
    rate = 48000
    for cut, kind in ((2.0, "whoosh"), (5.0, "swell")):
        window = np.abs(track[int((cut - 1) * rate):int((cut + 1) * rate)]).sum(axis=1)
        assert abs((window.argmax() / rate - 1) ) < 0.08, kind  # the weight of the sound is on the cut, not after it
    assert LEAD["whoosh"] > 0 and cue_sound("hit").shape[0] > 0
    attacks = np.array([1.0, 3.5])
    kept = plan_cues([(0.95, "hit"), (2.0, "hit"), (3.55, "hit"), (3.6, "whoosh")], attacks)
    assert kept == [(1.0, "hit"), (3.6, "whoosh")]  # a hit goes onto the attack, none where the music has none, and a whoosh beside a hit takes its place
    assert plan_cues([(0.0, "hit"), (0.1, "impact"), (0.2, "whoosh")]) == [(0.1, "impact")]
    assert plan_cues([(1.0, "hit"), (2.0, "hit")]) == [(1.0, "hit"), (2.0, "hit")]


def click_track(path_rate, seconds, bpm, strong_every=2, weak=0.02):
    rate = path_rate
    samples = np.zeros(int(rate * seconds), dtype=np.float32)
    period = 60.0 / bpm
    for k in range(int(seconds / period)):
        start = int(k * period * rate)
        samples[start:start + 400] += np.hanning(400).astype(np.float32) * (1.0 if k % strong_every == 0 else weak)
    return samples


def test_a_cut_goes_to_the_attack_that_the_music_has_not_to_an_empty_half_beat():
    rate, fps = 22050, 24
    samples = click_track(rate, 8, 120)  # a beat every 12 frames, a strong kick on every second beat
    times, strength = strong_accents(samples, rate)
    assert len(times) == 7 and np.allclose(times, np.arange(1, 8, 1.0), atol=0.05)  # the kick at 0 s has nothing before it to rise from
    grid = [round(k * 0.25 * fps) for k in range(1, 31)]  # every half beat
    accents = accent_strength(grid, times, strength, fps)
    assert accents[24] > 0.5 and accents[12] == 0.0  # a kick on the beat at 1 s, nothing at 0.5 s
    plain = snap_boundaries([30, 30, 30], grid, [], ["a", "b", "c"], "half beat", 6)
    with_accents = snap_boundaries([30, 30, 30], grid, [], ["a", "b", "c"], "half beat", 6, accents)
    assert plain[0] == 30 and with_accents[0] == 24 and abs(with_accents[0] - 30) <= 6  # the cut planned at 1.25 s goes to the kick at 1.0 s


def test_a_high_cut_density_gets_its_burst_when_the_planner_wrote_none():
    import json

    from majoor_videotools.core.timeline_sources import ensure_burst

    shots = [{"id": "SHOT_00%d" % i, "duration": d, "prompt": p} for i, (d, p) in enumerate([(2.0, "macro droplet"), (2.5, "silhouette"), (3.0, "close-up of the cap texture"), (2.5, "full bottle"), (5.0, "hero hold")], 1)]
    plan = json.dumps({"shots": shots})
    burst = json.loads(ensure_burst(plan, "high"))["shots"]
    picked = [s for s in burst if s.get("sub_cuts")]
    assert 1 <= len(picked) <= 3 and burst[0].get('sub_cuts') is None and burst[-1].get('sub_cuts') is None
    cuts = next(s for s in picked if s['id']=='SHOT_003')["sub_cuts"]
    assert len(cuts) == 5 and sum(c["duration"] for c in cuts) == 3.0 and all(c["duration"] < 0.2 for c in cuts[:4])
    assert len(json.loads(ensure_burst(plan, "medium"))["shots"][2]["sub_cuts"]) == 3
    for density in ("auto", "low"):
        assert ensure_burst(plan, density) == plan
    written = json.dumps({"shots": [{**shots[0]}, {**shots[1], "sub_cuts": [{"duration": 1.0}, {"duration": 1.5}]}, *shots[2:]]})
    enriched=json.loads(ensure_burst(written,"high"))['shots']
    assert enriched[1]['sub_cuts']==json.loads(written)['shots'][1]['sub_cuts']  # existing editorial choices stay
    assert enriched[2].get('sub_cuts')  # slow existing cuts do not disable high density elsewhere
    assert ensure_burst("not json", "high") == "not json"


def test_the_words_the_user_asked_for_are_on_the_last_shot_when_the_planner_left_them_out():
    import json

    from majoor_videotools.core.timeline_sources import ensure_text

    plan = json.dumps({"shots": [{"duration": 2, "prompt": "a"}, {"duration": 3, "prompt": "b"}]})
    added = json.loads(ensure_text(plan, " NEW DROP "))["shots"]
    assert "text" not in added[0] and added[1]["text"]["content"] == "NEW DROP" and added[1]["text"]["position"] == "center"
    assert ensure_text(plan, "") == plan and ensure_text("not json", "NEW DROP") == "not json"
    written = json.dumps({"shots": [{"duration": 2, "prompt": "a", "text": {"content": "OTHER"}}, {"duration": 3, "prompt": "b"}]})
    assert ensure_text(written, "NEW DROP") == written  # a text that the planner wrote stays
