"""Bridge between ComfyUI VIDEO objects and plain files."""
import contextlib
import hashlib
import io as py_io
import math
import os
import shutil
import uuid
from fractions import Fraction
from pathlib import Path

import folder_paths
import av
import numpy as np
import torch
from comfy_api.latest import AudioInput, VideoFromComponents, VideoFromFile, io

from ..core.errors import MajoorError
from ..core.frame_select import parse_frames
from ..core.media_probe import probe

MajoorShotList = io.Custom("MAJOOR_SHOT_LIST")
MajoorShotMetadata = io.Custom("MAJOOR_SHOT_METADATA")

OUTPUT_SUBFOLDER = "MajoorVideoTools"
VIDEO_COMPONENTS_MEMORY_BUDGET = 512 * 1024 * 1024


def ensure_video_supported(video) -> None:
    if not isinstance(video, (VideoFromFile, VideoFromComponents)):
        raise MajoorError(
            "Video Components can only safely sample file-backed VIDEO or already materialized "
            "tensor VIDEO inputs. This video type cannot be bounded before decoding."
        )


def _check_component_memory(required: int, reason: str) -> None:
    if required > VIDEO_COMPONENTS_MEMORY_BUDGET:
        raise MajoorError(
            f"Video Components needs an estimated {required / (1024 * 1024):.0f} MiB "
            f"({reason}), above its {VIDEO_COMPONENTS_MEMORY_BUDGET // (1024 * 1024)} MiB "
            "memory budget. Select fewer/smaller frames or use a file-backed video."
        )


def _audio_memory_estimate(duration: float, sample_rate: int, channels: int) -> int:
    if duration <= 0 or sample_rate <= 0 or channels <= 0:
        return 0
    return math.ceil(duration * sample_rate * channels * 4) * 2


def _frame_image(frame, image_format: str, align_graph, alpha_channel: bool, time_base):
    float_formats = {
        "gbrpf16le", "gbrpf16be", "gbrapf16le", "gbrapf16be",
        "grayf16le", "grayf16be", "gbrpf32le", "gbrpf32be",
        "gbrapf32le", "gbrapf32be", "grayf32le", "grayf32be",
    }
    if frame.format.name in float_formats:
        byte_order = ">" if frame.format.is_big_endian else "<"
        dtype = np.dtype(f"{byte_order}f{frame.format.components[0].bits // 8}")
        planes = []
        for component in frame.format.components:
            plane = frame.planes[component.plane]
            planes.append(np.ndarray(
                (frame.height, frame.width),
                dtype=dtype,
                buffer=plane,
                strides=(plane.line_size, dtype.itemsize),
            ))
        image = np.stack(planes * 3 if len(planes) == 1 else planes, axis=-1, dtype=np.float32)
    elif image_format in ("gbrpf32le", "gbrapf32le") and frame.width % 32:
        if align_graph[0] is None:
            pad_w = ((frame.width + 31) // 32) * 32
            pad_h = ((frame.height + 31) // 32) * 32
            graph = av.filter.Graph()
            source = graph.add_buffer(
                width=frame.width, height=frame.height,
                format=frame.format.name, time_base=time_base,
            )
            padded = graph.add("pad", f"{pad_w}:{pad_h}:0:0")
            filled = graph.add(
                "fillborders",
                f"left=0:right={pad_w - frame.width}:top=0:bottom={pad_h - frame.height}:mode=smear",
            )
            sink = graph.add("buffersink")
            source.link_to(padded)
            padded.link_to(filled)
            filled.link_to(sink)
            graph.configure()
            align_graph[0] = (graph, source, sink)
        graph, source, sink = align_graph[0]
        source.push(frame)
        image = np.ascontiguousarray(
            sink.pull().to_ndarray(format=image_format)[:frame.height, :frame.width]
        )
    else:
        image = frame.to_ndarray(format=image_format)

    rotation = int(round(frame.rotation // 90)) % 4 if frame.rotation else 0
    if rotation:
        image = np.rot90(image, k=rotation, axes=(0, 1)).copy()
    if image_format in ("rgb24", "rgba"):
        image = image.astype(np.float32) / 255.0
    if alpha_channel:
        image = image[..., :-1]
    return torch.from_numpy(np.ascontiguousarray(image))


def _decode_file_images(video, path: Path, indices: list[int], frame_count: int, width: int, height: int):
    selected = set(indices)
    kept = {}
    actual_count = 0
    image_format = None
    alpha_channel = False
    align_graph = [None]
    start_time, duration = video.get_active_trim_window()

    with av.open(str(path), mode="r") as container:
        video_stream = next((stream for stream in container.streams if stream.type == "video"), None)
        if video_stream is None:
            raise MajoorError(f"Video file '{path.name}' has no video stream.")
        video_stream.thread_type = "AUTO"
        start_pts = int(start_time / video_stream.time_base)
        end_pts = int((start_time + duration) / video_stream.time_base)
        if start_pts:
            container.seek(start_pts, stream=video_stream)

        for packet in container.demux(video_stream):
            try:
                decoded = packet.decode()
            except av.error.InvalidDataError:
                continue
            for frame in decoded:
                if frame.pts is None:
                    raise MajoorError(f"Video file '{path.name}' contains a frame with no timestamp.")
                if frame.pts < start_pts:
                    continue
                if duration and frame.pts >= end_pts:
                    break

                if image_format is None:
                    alpha_channel = any(
                        component.is_alpha for component in frame.format.components
                    ) or frame.format.name == "pal8"
                    if frame.format.name in ("yuvj420p", "yuvj422p", "yuvj444p", "rgb24", "rgba", "pal8"):
                        image_format = "rgba" if alpha_channel else "rgb24"
                    else:
                        image_format = "gbrapf32le" if alpha_channel else "gbrpf32le"

                if actual_count in selected:
                    image = _frame_image(
                        frame, image_format, align_graph, alpha_channel, video_stream.time_base
                    )
                    if tuple(image.shape[:2]) != (height, width):
                        raise MajoorError(
                            "This file-backed video is cropped or transformed in a way that "
                            "cannot be sampled safely without materializing every frame."
                        )
                    kept[actual_count] = image
                actual_count += 1

    if actual_count != frame_count:
        raise MajoorError(
            f"Video frame metadata reported {frame_count} frames, but decoding found "
            f"{actual_count}; refusing to return potentially misindexed frames."
        )
    if len(kept) != len(selected):
        raise MajoorError("One or more requested video frames could not be decoded.")
    if not indices:
        raise MajoorError("The video has no frame.")
    return torch.stack([kept[index] for index in indices])


def _decode_file_audio(video, path: Path, max_bytes: int):
    start_time, duration = video.get_active_trim_window()
    audio_frames = []
    decoded_audio_bytes = 0
    has_first_audio_frame = False
    with av.open(str(path), mode="r") as container:
        video_stream = next((stream for stream in container.streams if stream.type == "video"), None)
        if video_stream is None:
            return None
        audio_stream = next(
            (stream for stream in reversed(container.streams.audio) if stream.codec_context is not None),
            None,
        )
        if audio_stream is None:
            return None
        sample_rate = int(audio_stream.sample_rate or 0)
        channels = int(getattr(audio_stream.layout, "nb_channels", 0) or 0)
        if not sample_rate or not channels:
            raise MajoorError(
                "Audio memory use cannot be estimated for this file; refusing an unbounded decode."
            )
        estimate_duration = duration or float(video.get_duration())
        if estimate_duration <= 0:
            raise MajoorError(
                "Audio duration cannot be estimated for this file; refusing an unbounded decode."
            )
        estimated_bytes = _audio_memory_estimate(estimate_duration, sample_rate, channels)
        if estimated_bytes > max_bytes:
            raise MajoorError("Estimated audio decode exceeds the remaining video memory budget.")
        resampler = av.audio.resampler.AudioResampler(format="fltp")
        start_pts = int(start_time / video_stream.time_base)
        if start_pts:
            container.seek(start_pts, stream=video_stream)

        for packet in container.demux(audio_stream):
            try:
                decoded = packet.decode()
            except av.error.FFmpegError:
                continue
            audio_done = False
            for decoded_frame in decoded:
                for frame in resampler.resample(decoded_frame):
                    if duration and frame.time > start_time + duration:
                        audio_done = True
                        break
                    if not has_first_audio_frame:
                        offset_seconds = start_time - frame.pts * audio_stream.time_base
                        to_skip = max(0, int(offset_seconds * sample_rate))
                        if to_skip < frame.samples:
                            has_first_audio_frame = True
                            expected_bytes = decoded_audio_bytes + (frame.samples - to_skip) * channels * 4
                            if expected_bytes * 2 > max_bytes:
                                raise MajoorError("Decoded audio exceeds the remaining video memory budget.")
                            chunk = frame.to_ndarray()[..., to_skip:]
                            audio_frames.append(chunk)
                            decoded_audio_bytes += chunk.nbytes
                    else:
                        expected_bytes = decoded_audio_bytes + frame.samples * channels * 4
                        if expected_bytes * 2 > max_bytes:
                            raise MajoorError("Decoded audio exceeds the remaining video memory budget.")
                        chunk = frame.to_ndarray()
                        audio_frames.append(chunk)
                        decoded_audio_bytes += chunk.nbytes
                if audio_done:
                    break
            if audio_done:
                break

        if not audio_frames:
            return None
        audio_data = np.concatenate(audio_frames, axis=1)
        if duration:
            audio_data = audio_data[..., :int(duration * sample_rate)]
        if audio_data.nbytes * 2 > max_bytes:
            raise MajoorError("Decoded audio exceeds the remaining video memory budget.")
        return AudioInput({
            "waveform": torch.from_numpy(audio_data).unsqueeze(0),
            "sample_rate": sample_rate,
        })


def sample_video_components(video, frames: str):
    """Decode only selected frames for file videos; bound all materializing fallbacks."""
    ensure_video_supported(video)
    if isinstance(video, VideoFromFile):
        source = video.get_stream_source()
        if not isinstance(source, (str, os.PathLike)):
            raise MajoorError(
                "Video Components cannot safely sample an in-memory encoded video. "
                "Use a file-backed VIDEO or an already materialized tensor video."
            )
        path = Path(source)
        frame_count = int(video.get_frame_count())
        if frame_count <= 0:
            raise MajoorError("The video has no frame.")
        indices = parse_frames(frames, frame_count) if frames.strip() else list(range(frame_count))
        if not indices:
            raise MajoorError("frames selects no frame.")
        width, height = video.get_dimensions()
        selected_bytes = len(indices) * width * height * 48
        with av.open(str(path), mode="r") as container:
            audio_stream = next(
                (stream for stream in reversed(container.streams.audio) if stream.codec_context is not None),
                None,
            )
            audio_bytes = 0
            if audio_stream is not None:
                rate = int(audio_stream.sample_rate or 0)
                channels = int(getattr(audio_stream.layout, "nb_channels", 0) or 0)
                if not rate or not channels:
                    raise MajoorError(
                        "Audio memory use cannot be estimated for this file; refusing an unbounded decode."
                    )
                duration = float(video.get_duration())
                if duration <= 0:
                    raise MajoorError(
                        "Audio duration cannot be estimated for this file; refusing an unbounded decode."
                    )
                audio_bytes = _audio_memory_estimate(duration, rate, channels)
        image_peak_bytes = selected_bytes + width * height * 16
        _check_component_memory(
            image_peak_bytes + audio_bytes,
            "selected frames and audio",
        )

        # Cropped VideoFromFile inputs are materialized only after a conservative
        # full-batch estimate; the stock API applies crop/rotation/color semantics.
        with av.open(str(path), mode="r") as container:
            stream = next((item for item in container.streams if item.type == "video"), None)
            first = next(container.decode(stream), None) if stream is not None else None
            rotated_size = (first.height, first.width) if first and int(round(first.rotation / 90)) % 2 else (
                (first.width, first.height) if first else (0, 0)
            )
        if rotated_size != (width, height):
            fallback_bytes = frame_count * width * height * 48 + len(indices) * width * height * 12 + audio_bytes
            _check_component_memory(fallback_bytes, "cropped video fallback")
            components = video.get_components()
            if components.images.shape[0] != frame_count:
                raise MajoorError("Video frame metadata changed during the bounded crop fallback.")
            images = components.images if indices == list(range(frame_count)) else components.images[indices]
            return images, components.audio, components.frame_rate, frame_count

        images = _decode_file_images(video, path, indices, frame_count, width, height)
        audio_budget = VIDEO_COMPONENTS_MEMORY_BUDGET - image_peak_bytes
        audio = _decode_file_audio(video, path, audio_budget)
        return images, audio, video.get_frame_rate(), frame_count

    if isinstance(video, VideoFromComponents):
        components = video.get_components()
        frame_count = int(components.images.shape[0])
        if frame_count <= 0:
            raise MajoorError("The video has no frame.")
        height, width = components.images.shape[1:3]
        indices = parse_frames(frames, frame_count) if frames.strip() else list(range(frame_count))
        if not indices:
            raise MajoorError("frames selects no frame.")
        channels = int(components.images.shape[3])
        _check_component_memory(
            len(indices) * height * width * channels * components.images.element_size(),
            "selected tensor frames",
        )
        images = components.images if indices == list(range(frame_count)) else components.images[indices]
        return images, components.audio, components.frame_rate, frame_count

    raise MajoorError(
        "Video Components can only safely sample file-backed VIDEO or already materialized "
        "tensor VIDEO inputs. This video type cannot be bounded before decoding."
    )


def video_has_audio(video) -> bool:
    ensure_video_supported(video)
    if isinstance(video, VideoFromComponents):
        return video.get_components().audio is not None
    if not isinstance(video, VideoFromFile):
        raise MajoorError(
            "Audio-stream metadata cannot be bounded for this non-file video implementation."
        )
    source = video.get_stream_source()
    if isinstance(source, (str, os.PathLike)):
        return probe(Path(source), with_packets=False).has_audio
    if isinstance(source, py_io.BytesIO):
        if source.getbuffer().nbytes > VIDEO_COMPONENTS_MEMORY_BUDGET:
            raise MajoorError(
                "The in-memory encoded video exceeds the 512 MiB inspection budget."
            )
        source.seek(0)
        with av.open(source, mode="r") as container:
            return bool(container.streams.audio)
    raise MajoorError("Audio-stream metadata is unavailable for this video source.")


def projects_root(scope=None, worker_root="") -> Path:
    """Prefer the graph-carried runtime location; legacy local graphs keep their root."""
    if worker_root:
        import re
        candidate = Path(worker_root).resolve()
        base = (Path(folder_paths.get_output_directory()) / '_hyperkut_workspaces').resolve()
        if not candidate.is_relative_to(base):
            raise ValueError('Worker project root escapes its workspace')
        parts = candidate.relative_to(base).parts
        if len(parts) != 2 or not re.fullmatch(r'[0-9a-f]{32}', parts[0]) or parts[1] != 'projects':
            raise ValueError('Invalid worker project root')
        return candidate
    if scope is not None and getattr(scope, "storage_root", None) is not None:
        return Path(scope.storage_root).resolve()
    return Path(folder_paths.get_output_directory()) / OUTPUT_SUBFOLDER


def project_media_base(scope, relative="") -> str:
    from ..core.media_locator import project_media_location
    return project_media_location(projects_root(scope), scope.project_id,
                                  Path(folder_paths.get_output_directory()), relative)


@contextlib.contextmanager
def video_file(video):
    """Yield a path holding the video. Untrimmed, uncropped file-backed videos are used in place; anything else is saved first."""
    source = video.get_stream_source()
    if isinstance(source, str) and video.get_active_trim_window() == (0.0, 0.0):
        whole = probe(Path(source), with_packets=False)
        if video.get_dimensions() == (whole.width, whole.height):  # a crop changes the size of the video, not the file
            yield Path(source)
            return
    scratch = projects_root() / "_tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    tmp = scratch / f"{uuid.uuid4().hex}.mp4"
    try:
        video.save_to(str(tmp))
        yield tmp
    finally:
        tmp.unlink(missing_ok=True)


def media_ref(path: Path, kind: str, base: Path) -> dict:
    """Reference to a file under output/input/temp for the frontend widgets.

    Uses 'file'/'folder'/'kind' instead of filename/subfolder/type: ComfyUI registers entries with those keys as assets.
    """
    info = probe(path, with_packets=False)
    folder = path.parent.relative_to(base).as_posix()
    return {
        "file": path.name,
        "folder": "" if folder == "." else folder,
        "kind": kind,
        "width": info.display_size[0],
        "height": info.display_size[1],
        "fps": float(info.fps),
        "duration": float(info.duration),
    }


def preview_ref(video) -> dict:
    """Make a VIDEO viewable through /view. Files already in output/input are referenced, anything else is copied to temp."""
    with video_file(video) as path:
        path = path.resolve()
        scratch = (projects_root() / "_tmp").resolve()  # video_file deletes these on exit, so they must be copied
        for kind, folder in (("output", folder_paths.get_output_directory()), ("input", folder_paths.get_input_directory())):
            base = Path(folder).resolve()
            if path.is_relative_to(base) and not path.is_relative_to(scratch):
                break
        else:
            kind, base = "temp", Path(folder_paths.get_temp_directory()).resolve()
            stat = path.stat()
            key = hashlib.sha256(f"{path}|{stat.st_size}|{stat.st_mtime_ns}".encode()).hexdigest()[:16]
            dest = base / "majoor_compare" / f"{key}{path.suffix.lower()}"
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".partial")
                shutil.copy2(path, tmp)
                tmp.replace(dest)
            path = dest
        return media_ref(path, kind, base)
