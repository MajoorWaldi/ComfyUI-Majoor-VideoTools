"""Measure decoded true peak with FFmpeg's oversampled EBU R128 analyzer."""
import re
import math
import shutil
import subprocess
import time
from pathlib import Path

from ..adapters.ffmpeg import CREATIONFLAGS,find_binary
from .errors import MediaError


def _run_audio(command, *, timeout, is_cancelled=None):
    """Bound and cancel audio subprocesses without leaking an encoder process."""
    if is_cancelled and is_cancelled():
        raise InterruptedError("Audio processing cancelled")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=CREATIONFLAGS, shell=False)
    started = time.monotonic()
    try:
        while True:
            if is_cancelled and is_cancelled():
                raise InterruptedError("Audio processing cancelled")
            if time.monotonic() - started >= timeout:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                stdout, stderr = process.communicate(timeout=.1)
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        process.kill()
        process.communicate()
        raise


def assess_loudness(measured: dict, target_lufs: float = -14.0, ceiling_dbtp: float = -1.5, tolerance_lu: float = 1.0) -> dict:
    """Qualify the decoded delivery, not merely the requested gain."""
    value, peak = measured['integrated_lufs'], measured['true_peak_dbtp']
    if value is None or value < -60:
        return {'status': 'not_evaluated', 'reason': 'silent_or_no_audio', 'target_lufs': target_lufs, 'ceiling_dbtp': ceiling_dbtp}
    target_ok = abs(value - target_lufs) <= tolerance_lu
    peak_ok = peak is not None and peak <= ceiling_dbtp
    return {'status': 'passed' if target_ok and peak_ok else 'warning', 'target_lufs': target_lufs,
            'ceiling_dbtp': ceiling_dbtp, 'tolerance_lu': tolerance_lu, 'within_target': target_ok,
            'within_ceiling': peak_ok, 'integrated_lufs': value, 'true_peak_dbtp': peak}


def measure_true_peak(path:Path) -> dict:
    result=subprocess.run([find_binary('ffmpeg'),'-hide_banner','-nostdin','-i',str(path),'-vn','-af','ebur128=peak=true','-f','null','-'],capture_output=True,creationflags=CREATIONFLAGS,timeout=180)
    if result.returncode:
        raise MediaError(f'True peak measurement failed: {result.stderr.decode(errors="replace")[-500:]}')
    text=result.stderr.decode(errors='replace')
    matches=re.findall(r'True peak:\s*Peak:\s*([-+\d.]+|-inf)\s*dBFS',text)
    if not matches:raise MediaError('True peak measurement returned no summary')
    peak=None if matches[-1]=='-inf' else float(matches[-1])
    return {'method':'ffmpeg-ebur128-true-peak','true_peak_dbtp':peak,'silent':peak is None,'ceiling_dbtp':-1.0,'within_ceiling':peak is None or peak<=-1.0}


def measure_loudness(path: Path, is_cancelled=None) -> dict:
    """The integrated loudness (LUFS, ITU-R BS.1770 with gating) and the true peak (dBTP) of the audio of a file, measured by FFmpeg's ebur128 analyzer. None for a silent or absent audio."""
    result = _run_audio([find_binary('ffmpeg'), '-hide_banner', '-nostdin', '-i', str(path), '-vn', '-af', 'ebur128=peak=true', '-f', 'null', '-'], timeout=300, is_cancelled=is_cancelled)
    if result.returncode:
        if b'does not contain any stream' in result.stderr:  # a file with no audio
            return {'integrated_lufs': None, 'true_peak_dbtp': None}
        raise MediaError(f'Loudness measurement failed: {result.stderr.decode(errors="replace")[-500:]}')
    text = result.stderr.decode(errors='replace')
    summary = text[text.rfind('Summary:'):] if 'Summary:' in text else text
    integrated = re.findall(r'\bI:\s*([-+\d.]+|-inf)\s*LUFS', summary)
    peak = re.findall(r'True peak:\s*Peak:\s*([-+\d.]+|-inf)\s*dBFS', summary)
    value = lambda found: None if not found or found[-1] == '-inf' else float(found[-1])
    return {'integrated_lufs': value(integrated), 'true_peak_dbtp': value(peak)}


def normalize_loudness(path: Path, out: Path, target_lufs: float = -14.0, ceiling_dbtp: float = -1.5, max_gain_db: float = 18.0, is_cancelled=None, audio_codec="aac") -> dict:
    """The audio of `path` brought to `target_lufs` integrated loudness, with a limiter below `ceiling_dbtp`; the picture is copied. A file with no audio (or below -60 LUFS), or already within half a LU, is copied as it is.
    Returns what was measured before and after and the gain that was applied (dB)."""
    if not all(math.isfinite(v) for v in (target_lufs, ceiling_dbtp, max_gain_db)) or max_gain_db < 0 or not -60 <= target_lufs <= -5 or not -12 <= ceiling_dbtp <= 0:
        raise ValueError('Invalid loudness target, ceiling or gain limit')
    if audio_codec not in ("aac", "pcm_s24le"):
        raise ValueError("Unsupported loudness output audio codec")
    before = measure_loudness(path, is_cancelled)
    if before['integrated_lufs'] is None or before['integrated_lufs'] < -60.0:  # silence, or too quiet to be a mix: raising it would only raise the noise
        shutil.copy2(path, out)
        return {'before': before, 'after': before, 'gain_db': 0.0, 'applied': False, 'assessment': assess_loudness(before, target_lufs, ceiling_dbtp)}
    gain = max(-max_gain_db, min(max_gain_db, target_lufs - before['integrated_lufs']))
    if abs(gain) < 0.5 and (before['true_peak_dbtp'] is None or before['true_peak_dbtp'] <= ceiling_dbtp):
        shutil.copy2(path, out)
        return {'before': before, 'after': before, 'gain_db': 0.0, 'applied': False, 'assessment': assess_loudness(before, target_lufs, ceiling_dbtp)}
    limit = 10 ** ((ceiling_dbtp - 0.5) / 20)  # the limiter works on sample peaks: half a dB under the ceiling for the overshoot between samples
    command = [find_binary('ffmpeg'), '-y', '-hide_banner', '-nostdin', '-loglevel', 'error', '-i', str(path), '-map', '0:v?', '-map', '0:a', '-c:v', 'copy', '-af', f'volume={gain:.2f}dB,alimiter=limit={limit:.4f}:level=disabled',
               '-c:a', audio_codec, *(['-b:a', '256k'] if audio_codec == 'aac' else []), '-movflags', '+faststart', str(out)]
    result = _run_audio(command, timeout=600, is_cancelled=is_cancelled)
    if result.returncode:
        raise MediaError(f'Loudness normalization failed: {result.stderr.decode(errors="replace")[-500:]}')
    after = measure_loudness(out, is_cancelled)
    # Sample limiting alone does not guarantee decoded AAC true peak. One bounded
    # correction favours headroom over forcing a dynamic track to the LUFS target.
    peak_correction = 0.0
    if after['true_peak_dbtp'] is not None and after['true_peak_dbtp'] > ceiling_dbtp:
        peak_correction = ceiling_dbtp - after['true_peak_dbtp'] - .5
        corrected = out.with_name(out.stem + '.peak-safe' + out.suffix)
        try:
            repair = command.copy()
            repair[repair.index(str(path))] = str(out)
            repair[repair.index('-af') + 1] = f'volume={peak_correction:.2f}dB'
            repair[-1] = str(corrected)
            result = _run_audio(repair, timeout=600, is_cancelled=is_cancelled)
            if result.returncode:
                raise MediaError('Decoded true-peak correction failed')
            corrected.replace(out)
            after = measure_loudness(out, is_cancelled)
        finally:
            corrected.unlink(missing_ok=True)
    assessment = assess_loudness(after, target_lufs, ceiling_dbtp)
    if not assessment.get('within_ceiling', True):
        raise MediaError('Normalized audio still exceeds the decoded true-peak ceiling')
    return {'before': before, 'after': after, 'gain_db': round(gain, 2), 'peak_correction_db': round(peak_correction, 2),
            'applied': True, 'assessment': assessment}
