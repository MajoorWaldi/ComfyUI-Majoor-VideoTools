"""FFmpeg/FFprobe subprocess access. Commands are argument lists, never shell strings."""
import os
import shutil
import subprocess
import tempfile
import queue
import threading
import time
from pathlib import Path
from typing import Callable

from ..core.errors import FFmpegError

CREATIONFLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def find_binary(name: str) -> str:
    env = os.environ.get(f"MAJOOR_{name.upper()}")
    found = env if env and Path(env).is_file() else shutil.which(name)
    if not found:
        raise FFmpegError(
            f"'{name}' was not found. Install FFmpeg and add it to PATH, or set the MAJOOR_{name.upper()} environment variable to its full path."
        )
    return found


def run_capture(args: list[str], binary: str = "ffmpeg", timeout: float = 300) -> bytes:
    cmd = [find_binary(binary), *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, shell=False, creationflags=CREATIONFLAGS, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise FFmpegError(f'{binary} exceeded its {timeout:g} second time limit') from error
    if proc.returncode != 0:
        raise FFmpegError(f"{binary} failed ({proc.returncode}): {proc.stderr.decode(errors='replace')[-2000:]}")
    return proc.stdout


def run_ffmpeg(
    args: list[str],
    total_seconds: float | None = None,
    on_progress: Callable[[float], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    timeout: float | None = None,
) -> None:
    """Run ffmpeg to completion, reporting progress (0..1) and honoring cancellation."""
    cmd = [find_binary("ffmpeg"), "-hide_banner", "-nostdin", "-loglevel", "error", "-progress", "pipe:1", "-nostats", *args]
    timeout = timeout if timeout is not None else max(900, (total_seconds or 0) * 10)
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, shell=False, text=True, creationflags=CREATIONFLAGS)
        lines = queue.Queue()
        def read_progress():
            try:
                for line in proc.stdout:
                    lines.put(line)
            finally:
                lines.put(None)
        reader = threading.Thread(target=read_progress, daemon=True)
        reader.start()
        started = time.monotonic()
        try:
            while True:
                if is_cancelled and is_cancelled():
                    raise FFmpegError("Cancelled")
                if time.monotonic() - started > timeout:
                    raise FFmpegError(f'ffmpeg exceeded its {timeout:g} second time limit')
                try:
                    line = lines.get(timeout=.1)
                except queue.Empty:
                    continue
                if line is None:
                    break
                if on_progress and total_seconds and line.startswith("out_time_us="):
                    value = line.split("=", 1)[1].strip()
                    if value.lstrip("-").isdigit():
                        on_progress(min(max(int(value) / 1e6 / total_seconds, 0.0), 1.0))
            code = proc.wait(timeout=max(timeout - (time.monotonic() - started), .1))
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        finally:
            reader.join(timeout=1)
            proc.stdout.close()
        if code != 0:
            err.seek(0)
            raise FFmpegError(f"ffmpeg failed ({code}): {err.read().decode(errors='replace')[-2000:]}")
