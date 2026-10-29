"""Focused CPU-only checks for sampled video-component decoding.

Run with the ComfyUI Python interpreter:
    python custom_nodes/ComfyUI-Majoor-VideoTools/tests/comfy/check_video_component_sampling.py
"""
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import torch

import _boot  # noqa: F401
from comfy_api.latest import InputImpl, VideoComponents
from MVT.adapters import comfy_video
from MVT.core.errors import MajoorError
from MVT.nodes.get_video_components import MajoorGetVideoComponentsAdvanced


class _Frame:
    width = 4
    height = 2
    rotation = 0
    format = SimpleNamespace(
        name="rgb24",
        components=[SimpleNamespace(is_alpha=False)],
    )

    def __init__(self, value):
        self.pts = value
        self.value = value

    def to_ndarray(self, format):
        assert format == "rgb24"
        return np.full((self.height, self.width, 3), self.value, dtype=np.uint8)


class _Packet:
    stream = SimpleNamespace(type="video")

    def __init__(self, value):
        self.value = value

    def decode(self):
        return [_Frame(self.value)]


class _AudioFrame:
    time = 0.0
    pts = 0
    samples = 4

    def to_ndarray(self):
        return np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)


class _AudioPacket:
    stream = SimpleNamespace(type="audio")

    def decode(self):
        return [_AudioFrame()]


class _Streams:
    def __init__(self, video, audio):
        self.video = [video]
        self.audio = [audio]

    def __iter__(self):
        return iter([*self.video, *self.audio])


class _Container:
    def __init__(self):
        self.video_stream = SimpleNamespace(
            type="video",
            time_base=Fraction(1, 24),
            average_rate=Fraction(24),
        )
        self.audio_stream = SimpleNamespace(
            type="audio",
            codec_context=object(),
            sample_rate=8000,
            layout=SimpleNamespace(nb_channels=1),
            time_base=Fraction(1, 8000),
        )
        self.streams = _Streams(self.video_stream, self.audio_stream)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def decode(self, _stream):
        return iter([_Frame(0)])

    def demux(self, stream):
        if stream.type == "audio":
            return iter([_AudioPacket()])
        return (_Packet(value) for value in range(5))


class _Resampler:
    def __init__(self, **_kwargs):
        pass

    def resample(self, frame):
        return [frame]


def main():
    video = InputImpl.VideoFromFile("synthetic.mp4")
    video.get_stream_source = lambda: "synthetic.mp4"
    video.get_frame_count = lambda: 5
    video.get_dimensions = lambda: (4, 2)
    video.get_active_trim_window = lambda: (0.0, 0.0)
    video.get_duration = lambda: 5 / 24
    video.get_frame_rate = lambda: Fraction(24)
    video.get_components = lambda: (_ for _ in ()).throw(AssertionError("full decode invoked"))

    original_open = comfy_video.av.open
    original_resampler = comfy_video.av.audio.resampler.AudioResampler
    comfy_video.av.open = lambda *_args, **_kwargs: _Container()
    comfy_video.av.audio.resampler.AudioResampler = _Resampler
    try:
        images, audio, rate, count = comfy_video.sample_video_components(video, "3, 1, 3")
        assert tuple(images.shape) == (3, 2, 4, 3)
        assert np.allclose(images[:, 0, 0, 0].numpy(), [3 / 255, 1 / 255, 3 / 255])
        assert audio["sample_rate"] == 8000
        assert tuple(audio["waveform"].shape) == (1, 1, 4)
        assert rate == 24 and count == 5
        result = MajoorGetVideoComponentsAdvanced.execute(video, "3, 1")
        args = result.args if hasattr(result, "args") else result
        assert args[0] is video and tuple(args[6].shape) == (2, 2, 4, 3)
        assert args[7]["sample_rate"] == 8000 and args[8] == "3, 1" and args[9] is True

        original_budget = comfy_video.VIDEO_COMPONENTS_MEMORY_BUDGET
        comfy_video.VIDEO_COMPONENTS_MEMORY_BUDGET = 1
        try:
            try:
                comfy_video.sample_video_components(video, "0")
            except MajoorError as error:
                assert "memory budget" in str(error)
            else:
                raise AssertionError("oversized allocation was not refused")
        finally:
            comfy_video.VIDEO_COMPONENTS_MEMORY_BUDGET = original_budget

        try:
            comfy_video.sample_video_components(object(), "")
        except MajoorError as error:
            assert "cannot be bounded" in str(error)
        else:
            raise AssertionError("unsupported non-file video was not refused")

        materialized = InputImpl.VideoFromComponents(
            VideoComponents(
                images=torch.arange(4 * 2 * 4 * 3, dtype=torch.float32).reshape(4, 2, 4, 3),
                frame_rate=Fraction(24),
            )
        )
        tensor_images, tensor_audio, tensor_rate, tensor_count = comfy_video.sample_video_components(
            materialized, "2, 0"
        )
        assert torch.equal(tensor_images, materialized.get_components().images[[2, 0]])
        assert tensor_audio is None and tensor_rate == 24 and tensor_count == 4
    finally:
        comfy_video.av.open = original_open
        comfy_video.av.audio.resampler.AudioResampler = original_resampler


if __name__ == "__main__":
    main()
    print("ok   selected file frames preserve requested order; unsupported videos fail closed")
