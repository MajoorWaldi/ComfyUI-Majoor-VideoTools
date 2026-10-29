"""Optional local HTML finishing pass. No generated executable code or hosted API."""
import hashlib
import html
import json
import logging
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
from filelock import FileLock
from PIL import Image, ImageDraw

from ..adapters.ffmpeg import CREATIONFLAGS, run_capture, run_ffmpeg
from .audio_quality import assess_loudness, measure_loudness
from .beats import strong_accents
from .delivery_review import review_delivery
from .errors import FFmpegError, MajoorError
from .fingerprints import file_fingerprint, json_fingerprint
from .fx import TEXT_POSITIONS, safe_box
from .hyperframes_layers import prepare_layers
from .layout_review import subject_overlap
from .media_probe import probe
from .motion import needs_mask, parse_layers
from .motion_scenes import readability
from .motion_score import read_score
from .motion_timing import preview_times, shot_layers
from .text_timing import TEXT_TIMING

VERSION = '10'
CLI_VERSION = '0.8.201'
PRESETS = ('editorial', 'minimal', 'energetic')
OPTIONAL_HYPERFRAMES_WARNING = 'optional:hyperframes:unavailable'


def optional_hyperframes_fallback(error, cancelled=None):
    """Return one shared passthrough report for renderer failures, not bad inputs."""
    if isinstance(error, InterruptedError):
        return None
    if isinstance(error, FFmpegError) and 'cancel' in str(error).casefold():
        raise InterruptedError('HyperFrames render cancelled') from error
    if cancelled and cancelled():
        raise InterruptedError('HyperFrames render cancelled') from error
    if isinstance(error, (ValueError, MajoorError)) and not isinstance(error, FFmpegError):
        return None
    if not isinstance(error, (OSError, RuntimeError, subprocess.SubprocessError, FFmpegError)):
        return None

    reason = f'{type(error).__name__}: {error}'.strip()[:2000]
    message = f'Optional HyperFrames finishing unavailable; original video retained. {reason}'
    logging.getLogger(__name__).warning('%s', message)
    return {
        'version': 1,
        'renderer': 'passthrough',
        'status': 'fallback',
        'reused': False,
        'layers': [],
        'warnings': [OPTIONAL_HYPERFRAMES_WARNING],
        'warning_details': [{'code': OPTIONAL_HYPERFRAMES_WARNING, 'message': message}],
        'original_retained': True,
        'reason': reason,
    }


def parse_direction(text: str) -> dict:
    """Plain-language shorthand or a strict structured direction, never HTML/JS."""
    if len(text) > 12000:
        raise ValueError('Motion direction is too long (12000 characters maximum)')
    if text.lstrip().startswith('{'):
        data = json.loads(text)
        if not isinstance(data, dict) or set(data) - {'preset', 'accent', 'reactive', 'title', 'intensity'}:
            raise ValueError('Direction keys: preset, accent, reactive, title, intensity')
    else:
        words = text.strip().casefold()
        preset = words if words in PRESETS else 'minimal' if any(w in words for w in ('minimal', 'sobre', 'discret', 'soft')) else 'energetic' if any(w in words for w in ('energi', 'énergi', 'nerveux', 'bold', 'dynam')) else 'editorial'
        color = re.search(r'#[0-9a-fA-F]{6}\b', text)
        data = {'preset': preset, 'accent': color.group() if color else '#e4c081'}
    defaults = {'reactive': False, 'intensity': 0.18} if data.get('preset') == 'minimal' else {}
    out = {'preset': 'editorial', 'accent': '#e4c081', 'reactive': True, 'title': '', 'intensity': 0.6, **defaults, **data}
    if out['preset'] not in PRESETS or not re.fullmatch(r'#[0-9a-fA-F]{6}', str(out['accent'])):
        raise ValueError('Use preset editorial/minimal/energetic and an accent in #RRGGBB format')
    if not isinstance(out['reactive'], bool) or not isinstance(out['title'], str) or len(out['title']) > 120:
        raise ValueError('reactive must be boolean; title must be text (120 characters maximum)')
    if isinstance(out['intensity'], bool) or not isinstance(out['intensity'], (int, float)) or not math.isfinite(out['intensity']) or not 0 <= out['intensity'] <= 1:
        raise ValueError('intensity must be between 0 and 1')
    return out


def resolve_cues(text: str, timeline: str, duration: float, fps: float) -> list[dict]:
    cues = json.loads(text or '[]')
    rows = json.loads(timeline or '[]')
    if not isinstance(cues, list) or len(cues) > 30 or not isinstance(rows, list):
        raise ValueError('Cues and timeline must be JSON arrays (30 cues maximum)')
    if not any(isinstance(cue, dict) and 'shot_id' in cue for cue in cues):
        rows = []  # absolute/global cues do not rely on a possibly older shot list
    by_id = {}
    for row in rows:
        if not isinstance(row, dict) or not {'id', 'start', 'duration'} <= row.keys():
            raise ValueError('Timeline rows need id, start and duration in final-edit seconds')
        start, length = float(row['start']), float(row['duration'])
        if not all(math.isfinite(x) for x in (start, length)) or start < 0 or length <= 0 or start + length > duration + 1 / fps:
            raise ValueError('Timeline does not fit the final video; provide actual assembled timing')
        if str(row['id']) in by_id:
            raise ValueError('Duplicate shot id in motion timeline')
        by_id[str(row['id'])] = (start, min(start + length, duration))
    result = []
    for cue in cues:
        if not isinstance(cue, dict) or set(cue) - {'shot_id', 'start', 'end', 'text', 'position'}:
            raise ValueError('Cue keys: shot_id, start, end, text, position')
        window = by_id.get(str(cue.get('shot_id'))) if 'shot_id' in cue else (0.0, duration)
        if window is None:
            raise ValueError(f'Unknown shot_id {cue.get("shot_id")!r}; connect the final timeline')
        start = float(cue.get('start', window[0]))
        end = float(cue.get('end', min(window[1], start + 2.4)))
        caption, position = cue.get('text', ''), cue.get('position', 'top')
        if not isinstance(caption, str) or len(caption) > 120 or position not in ('top', 'bottom'):
            raise ValueError('Cue text: 120 characters maximum; position: top or bottom')
        if not math.isfinite(start + end) or start < window[0] or end > window[1] + 1e-6 or end - start < 1 / fps:
            raise ValueError('Cue must stay inside its shot/video and last at least one frame')
        if caption.strip():
            result.append({'start': start, 'end': end, 'text': caption.strip(), 'position': position})
    result.sort(key=lambda c: c['start'])
    if any(a['end'] > b['start'] for a, b in zip(result, result[1:])):
        raise ValueError('Motion titles must not overlap; shorten or move their intervals')
    return result


def runtime_paths() -> tuple[Path, Path, Path]:
    root = Path(os.environ.get('MAJOOR_HYPERFRAMES_RUNTIME', Path(__file__).resolve().parents[1] / 'runtime/hyperframes'))
    node = shutil.which('node')
    cli = root / 'node_modules/hyperframes/bin/hyperframes.mjs'
    gsap = root / 'node_modules/gsap/dist/gsap.min.js'
    if not node or not cli.is_file() or not gsap.is_file():
        raise RuntimeError('HyperFrames is optional. Install Node.js 22+ and run scripts/install_hyperframes.ps1; FFmpeg and local Chrome are required. No automatic download during generation.')
    meta = json.loads((cli.parents[1] / 'package.json').read_text(encoding='utf-8'))
    if meta.get('version') != CLI_VERSION:
        raise RuntimeError(f'This integration requires hyperframes {CLI_VERSION}; rerun its installer')
    return Path(node), cli, gsap


def analyze_audio(source: Path, info) -> dict:
    if not info.has_audio:
        return {'bands': [], 'hits': [], 'audio': False}
    rate = 16000
    raw = run_capture(['-v', 'error', '-i', str(source), '-vn', '-ac', '1', '-ar', str(rate), '-f', 'f32le', '-'])
    samples = np.frombuffer(raw, dtype='<f4')
    if not len(samples) or not np.isfinite(samples).all():
        raise ValueError('Cannot analyze non-finite or empty audio')
    times, strengths = strong_accents(samples, rate)
    chosen = []
    for index in np.argsort(-strengths):
        t = float(times[index])
        if .3 < t < float(info.duration) - .3 and all(abs(t - h) >= .45 for h in chosen):
            chosen.append(t)
    bands = []
    edges = [45, 100, 220, 480, 1000, 2200, 4800, 7900]
    freq = np.fft.rfftfreq(1024, 1 / rate)
    for i in range(round(float(info.duration) * float(info.fps))):
        start = max(0, round(i / float(info.fps) * rate) - 512)
        chunk = samples[start:start + 1024]
        chunk = np.pad(chunk, (0, max(0, 1024 - len(chunk))))
        spectrum = abs(np.fft.rfft(chunk * np.hanning(1024)))
        bands.append([float(spectrum[(freq >= a) & (freq < b)].mean()) for a, b in zip(edges, edges[1:])])
    array = np.array(bands)
    array = np.clip(array / np.maximum(np.percentile(array, 94, axis=0), .001), 0, 1)
    return {'bands': array.round(3).tolist(), 'hits': sorted(chosen),
            'onsets': [float(t) for t, strength in zip(times, strengths) if strength >= .5 and 0 <= t < float(info.duration)], 'audio': True}


def write_composition(project: Path, source: Path, info, direction: dict, cues: list, audio: dict, gsap: Path, layers=None, layer_assets=None) -> None:
    assets = project / 'assets'; assets.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, assets / 'source.mp4')
    shutil.copy2(gsap, assets / 'gsap.min.js')
    shutil.copy2(Path(__file__).resolve().parents[1] / 'web/hyperframes_layers.js', assets / 'hyperframes_layers.js')
    width, height = info.display_size
    duration, fps = float(info.duration), float(info.fps)
    cards = []
    for i, cue in enumerate(cues):
        letters = ''.join('<span>' + html.escape(c) + '</span>' for c in cue['text'])
        cards.append(f'<div id="title{i}" class="clip title {cue["position"]}" data-start="{cue["start"]}" data-duration="{cue["end"]-cue["start"]}" data-track-index="1"><div class="panel"><div class="words">{letters}</div><div class="rule"></div></div></div>')
    scene = Path(__file__).resolve().parents[1] / 'web/hyperframes_scene.html'
    config = {'duration': duration, 'fps': fps, 'cues': cues, 'audio': audio, 'layers': layers or [], 'layer_assets': layer_assets or {},
              'text_timing': TEXT_TIMING, 'safe_boxes': {name: safe_box(width,height,pos[0]) for name,pos in TEXT_POSITIONS.items()}, **direction}
    # Script JSON cannot terminate the script tag, including user-supplied captions.
    encoded = json.dumps(config, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    body = scene.read_text(encoding='utf-8').replace('__CONFIG__', encoded).replace('__CARDS__', ''.join(cards)).replace('__WIDTH__', str(width)).replace('__HEIGHT__', str(height)).replace('__ACCENT__', direction['accent']).replace('__DURATION__', str(duration))
    (project / 'compositions').mkdir(exist_ok=True)
    (project / 'compositions/motion.html').write_text(body, encoding='utf-8')
    root = f'''<!doctype html><html><head><meta charset="utf-8"><script src="assets/gsap.min.js"></script><script src="assets/hyperframes_layers.js"></script><style>html,body{{margin:0;background:#080808;overflow:hidden}}#main{{position:relative;width:{width}px;height:{height}px}}#source,#motion{{position:absolute;inset:0;width:100%;height:100%}}#source{{object-fit:contain;z-index:1}}#motion{{z-index:2}}</style></head><body><div id="main" data-composition-id="main" data-start="0" data-duration="{duration}" data-width="{width}" data-height="{height}" data-fps="{fps}"><video id="source" class="clip" src="assets/source.mp4" data-start="0" data-duration="{duration}" data-track-index="0" muted playsinline></video><div id="motion" class="clip" data-composition-id="motion" data-composition-src="compositions/motion.html" data-start="0" data-duration="{duration}" data-track-index="1" data-track-kind="graphics" data-width="{width}" data-height="{height}"></div></div><script>const clock={{t:0}};const tl=gsap.timeline({{paused:true}});tl.to(clock,{{t:{duration},duration:{duration},ease:'none'}});window.__timelines=window.__timelines||{{}};window.__timelines.main=tl;</script></body></html>'''
    if (layer_assets or {}).get('footage') and 'frame_paths' not in (layer_assets or {}):
        root = re.sub(r'<video id="source".*?</video>', '', root)  # canvas uses exact decoded source frames
    (project / 'index.html').write_text(root, encoding='utf-8')
    (project / 'direction.json').write_text(json.dumps(config, indent=2), encoding='utf-8')


def _render_command(cmd, project, log, cancelled, progress, timeout=900, completed=None):
    env = {**os.environ, 'HYPERFRAMES_NO_TELEMETRY': '1', 'DO_NOT_TRACK': '1'}
    start = time.monotonic()
    complete_since = None
    recovered_shutdown = False
    with log.open('wb') as stream:
        process = subprocess.Popen(cmd, cwd=project, env=env, stdout=stream, stderr=subprocess.STDOUT, shell=False, creationflags=CREATIONFLAGS)
        try:
            while process.poll() is None:
                if cancelled and cancelled():
                    raise InterruptedError('HyperFrames render cancelled')
                if completed is not None:
                    with log.open('rb') as reader:
                        reader.seek(max(0, log.stat().st_size - 65536))
                        tail = reader.read().decode(errors='replace')
                    # The CLI may retain an open handle after encoding is complete.
                    # A log alone never authorizes success: validate the artifact too.
                    marked = 'Render complete' in tail and '"message":"artifact validated"' in tail
                    if marked:
                        complete_since = complete_since or time.monotonic()
                        if time.monotonic() - complete_since >= 5:
                            completed()
                            if cancelled and cancelled():
                                raise InterruptedError('HyperFrames render cancelled')
                            recovered_shutdown = True
                            break
                if time.monotonic() - start > timeout:
                    raise TimeoutError(f'HyperFrames render exceeded {timeout:g} seconds; original video retained')
                if progress:
                    progress(min(.9, .2 + (time.monotonic() - start) / timeout * .7))
                time.sleep(.2)
        finally:
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATIONFLAGS)
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
        if process.returncode and not recovered_shutdown:
            raise RuntimeError('HyperFrames failed; original video retained. ' + log.read_text(errors='replace')[-1800:])
    return recovered_shutdown


def validate_silent_render(path, info, cancelled=None):
    actual = probe(path, with_packets=False)
    fps, duration = float(info.fps), float(info.duration)
    if (actual.display_size != info.display_size or abs(float(actual.fps) - fps) > .001
            or actual.frame_count != round(duration * fps)
            or abs(float(actual.duration) - duration) > 1 / fps + .01):
        raise RuntimeError('HyperFrames completed file failed frame count, timing or dimensions validation')
    # Read every video frame, including the tail: reject truncated/corrupt artifacts.
    run_ffmpeg(['-v', 'error', '-xerror', '-i', str(path), '-map', '0:v:0', '-an', '-f', 'null', '-'],
               duration, None, cancelled, timeout=120)


def capture_previews(node, cli, project, info, layers, cues, timeline, cancelled=None, *, masks=None):
    """Render real composition stills before encoding; validate decoding, not aesthetics."""
    times = preview_times(layers, cues, timeline, float(info.duration), float(info.fps))
    folder = project / 'previews'
    folder.mkdir(exist_ok=True)
    for old in folder.glob('*.png'):
        old.unlink()
    _render_command([str(node), str(cli), 'snapshot', str(project.resolve()), '--at',
                     ','.join(f'{t:.6f}' for t in times), '--output', str(folder.resolve()),
                     '--keep', '--no-end'], project, project / 'preview.log', cancelled, None, timeout=180)
    paths = sorted(folder.glob('*.png'))
    if len(paths) != len(times):
        raise RuntimeError('HyperFrames preview capture incomplete; full render was not started')
    tiles = []
    for path in paths:
        with Image.open(path) as image:
            image.load()
            if image.size != info.display_size:
                raise RuntimeError('HyperFrames preview dimensions differ; full render was not started')
            thumb = image.convert('RGB')
            thumb.thumbnail((384, 240))
            tile = Image.new('RGB', (384, 266), '#111111')
            tile.paste(thumb, ((384 - thumb.width) // 2, 0))
            ImageDraw.Draw(tile).text((8, 244), path.stem, fill='white')
            tiles.append(tile)
    sheet = Image.new('RGB', (384 * min(4, len(tiles)), 266 * math.ceil(len(tiles) / 4)), '#111111')
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % 4) * 384, (i // 4) * 266))
    contact = folder / 'contact.jpg'
    sheet.save(contact, quality=90)
    report = {'times': times, 'images': [str(path) for path in paths], 'contact_sheet': str(contact),
              'technical_check': 'passed', 'semantic_review': 'not_automated'}
    script = Path(__file__).resolve().parents[1] / 'scripts/review_hyperframes_layout.mjs'
    try:
        if cancelled and cancelled(): raise InterruptedError('Layout review cancelled')
        result = subprocess.run([str(node),str(script),str(project.resolve()),json.dumps(times)],
                                capture_output=True,timeout=45,creationflags=CREATIONFLAGS)
        if result.returncode: raise RuntimeError(result.stderr.decode(errors='replace')[-200:])
        layout = json.loads((folder/'layout.json').read_text(encoding='utf-8'))
        warnings=[]
        for sample in layout['samples']:
            visible=[row for row in sample['canvas'] if row.get('alpha',0)>.1]
            for i,row in enumerate(visible):
                if row['effective_font_px']<18: warnings.append({'time':sample['time'],'kind':'small_effective_text','layer':i})
                a,b,c,d=row['rect'];l,t,r,bt=row['safe_box']
                if a<l-1 or b<t-1 or c>r+1 or d>bt+1: warnings.append({'time':sample['time'],'kind':'outside_safe_box','layer':i})
                for other in visible[:i]:
                    x,y,z,w=other['rect']
                    if min(c,z)>max(a,x) and min(d,w)>max(b,y): warnings.append({'time':sample['time'],'kind':'text_overlap','layer':i})
        subject = subject_overlap(layout['samples'], masks, info.display_size, float(info.duration))
        report['layout']={'status':'measured','report':str(folder/'layout.json'),'warnings':warnings,
                          'subject_overlap':subject,'contrast':'not_evaluated'}
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
        report['layout']={'status':'not_evaluated','reason':str(error)[:200]}
    (folder / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def render_hyperframes(source: Path, output_root: Path, direction_text='', cues_text='[]', timeline='[]', *, layers_text='[]', masks=None, cancelled=None, progress=None) -> tuple[Path, dict]:
    info = probe(source, with_packets=False)
    duration, fps = float(info.duration), float(info.fps)
    if not 0 < duration <= 180 or not 1 <= fps <= 60:
        raise ValueError('HyperFrames finishing supports up to 180 seconds and 60 fps')
    raw_layers, _ = shot_layers(layers_text, timeline, duration, fps)
    layers = parse_layers(json.dumps(raw_layers), duration)
    if needs_mask(layers) and masks is None:
        raise ValueError('These layers require a subject mask (BiRefNet or equivalent)')
    direction = parse_direction(direction_text)
    cues = resolve_cues(cues_text, timeline, duration, fps)
    if direction['title'] and not cues:
        cues = resolve_cues(json.dumps([{'text': direction['title'], 'start': min(.25, duration * .1), 'end': min(2.65, duration)}]), '[]', duration, fps)
    node, cli, gsap = runtime_paths()
    template = Path(__file__).resolve().parents[1] / 'web/hyperframes_scene.html'
    mask_fp = ''
    if needs_mask(layers):
        mask_fp = hashlib.sha256(np.ascontiguousarray(masks, dtype=np.float32).tobytes()).hexdigest()
    driver = template.with_name('hyperframes_layers.js')
    score_rows = json.loads(layers_text or '[]')
    score_rows = score_rows.get('layers', []) if isinstance(score_rows, dict) else score_rows
    shared_score = read_score(source, score_rows, duration, fps)
    key = json_fingerprint([VERSION, shared_score, CLI_VERSION, file_fingerprint(template), file_fingerprint(driver), file_fingerprint(gsap), file_fingerprint(source), direction, cues, layers_text, timeline, mask_fp])[:20]
    project = output_root / 'hyperframes' / key
    project.mkdir(parents=True, exist_ok=True)
    result = project / 'motion.mp4'
    with FileLock(str(project) + '.lock', timeout=120):
        if cancelled and cancelled():
            raise InterruptedError('HyperFrames render cancelled')
        if result.is_file():
            report = json.loads((project / 'report.json').read_text(encoding='utf-8'))
            return result, {**report, 'original': str(source), 'reused': True}
        configured = json.loads(layers_text or '[]')
        configured = configured.get('layers', []) if isinstance(configured, dict) else configured
        sync_requested = any(isinstance(row, dict) and row.get('sync') == 'onset' for row in configured)
        audio = analyze_audio(source, info) if direction['reactive'] or sync_requested else {'bands': [], 'hits': [], 'audio': info.has_audio}
        if shared_score:
            resolved, alignment = shared_score['layers'], shared_score['alignment']
        else:
            resolved, alignment = shot_layers(layers_text, timeline, duration, fps, audio.get('onsets', audio['hits']))
        layers = parse_layers(json.dumps(resolved), duration)
        layout_review=readability(layers,*info.display_size,duration)
        layer_assets = prepare_layers(project, source, info, layers, masks, cancelled)
        display_audio = audio if direction['reactive'] else {'bands': [], 'hits': [], 'audio': audio['audio']}
        write_composition(project, source, info, direction, cues, display_audio, gsap, layers, layer_assets)
        silent = project / 'render.partial.mp4'
        staged = project / 'motion.partial.mp4'
        try:
            previews = capture_previews(node, cli, project, info, layers, cues, timeline, cancelled, masks=masks)
            silent.unlink(missing_ok=True)
            recovered_shutdown = _render_command([str(node), str(cli), 'render', str(project.resolve()), '--quality', 'looks', '--fps', str(info.fps), '--workers', '1', '--output', str(silent.resolve()), '--strict'], project, project / 'render.log', cancelled, progress,
                completed=lambda: validate_silent_render(silent, info, cancelled))
            # Preserve the final mix bit-for-bit where its codec supports MP4.
            run_ffmpeg(['-y', '-i', str(silent), '-i', str(source), '-map', '0:v:0', '-map', '1:a:0?', '-c', 'copy', '-t', str(duration), '-movflags', '+faststart', str(staged)], duration, None, cancelled)
            actual = probe(staged, with_packets=False)
            if abs(float(actual.duration) - duration) > 1 / fps + .01 or actual.display_size != info.display_size or actual.has_audio != info.has_audio:
                raise RuntimeError('HyperFrames output failed duration, dimensions or audio validation')
            report = {'reused': False, 'layers': layers, 'mask_used': needs_mask(layers), 'renderer': 'hyperframes', 'preset': direction['preset'], 'direction': direction, 'cues': cues, 'audio_reactive': bool(audio['audio'] and direction['reactive']), 'hits': len(audio['hits']), 'project': str(project), 'original': str(source), 'limits': 'Bounded presets; plain brief selects a preset and #RRGGBB accent. Use JSON for precise control. No automatic tracking or semantic prompt generation.'}
            report.update(score_source='assembly_measured_music' if shared_score else 'final_mix_fallback', score_events=shared_score['events'] if shared_score else [], alignment=alignment, previews=previews, recovered_shutdown=recovered_shutdown, readability=layout_review)
            delivered_audio = measure_loudness(staged)
            report['delivered_audio'] = {'measurement': delivered_audio, 'assessment': assess_loudness(delivered_audio),
                                         'scope': 'decoded final remux; assessment is advisory for unnormalized input'}
            try:
                report['delivery_review'] = review_delivery(staged, source)
            except Exception as error:
                report['delivery_review'] = {'status': 'not_evaluated', 'reason': str(error)[:200]}
            (project / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            staged.replace(result)
        finally:
            silent.unlink(missing_ok=True)
            staged.unlink(missing_ok=True)
        if progress:
            progress(1.0)
        return result, report
