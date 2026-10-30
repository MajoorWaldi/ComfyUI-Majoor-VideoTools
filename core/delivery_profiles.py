"""Explicit SDR delivery contracts; no inferred HDR or OCIO transformation."""
import json
from dataclasses import dataclass
from pathlib import Path

from ..adapters.ffmpeg import run_capture
from .errors import AssemblyError


@dataclass(frozen=True)
class DeliveryProfile:
    name: str
    encoder: str
    codec: str
    pixel_format: str
    working_format: str
    decoded_formats: tuple[str, ...]
    encoder_options: tuple[str, ...]
    alpha: bool = False


PROFILES = {
    "social": DeliveryProfile("social", "libx264", "h264", "yuv420p", "yuv420p", ("yuv420p",),
                              ("-crf", "18", "-preset", "medium")),
    "prores_422_hq": DeliveryProfile("prores_422_hq", "prores_ks", "prores", "yuv422p10le",
                                    "yuv444p10le", ("yuv422p10le",), ("-profile:v", "3")),
    "dnxhr_hqx": DeliveryProfile("dnxhr_hqx", "dnxhd", "dnxhd", "yuv422p10le",
                                "yuv444p10le", ("yuv422p10le",), ("-profile:v", "dnxhr_hqx")),
    "prores_4444": DeliveryProfile("prores_4444", "prores_ks", "prores", "yuva444p10le",
                                  "yuva444p10le", ("yuva444p12le",), ("-profile:v", "4", "-alpha_bits", "16"), True),
}
COLOR_POLICIES = ("require_bt709", "assume_bt709")


def video_stream(path: Path) -> dict:
    data = json.loads(run_capture(["-v", "error", "-select_streams", "v:0", "-show_streams",
                                  "-of", "json", str(path)], "ffprobe"))
    if not data.get("streams"):
        raise AssemblyError(f"{path.name}: no video stream for delivery qualification")
    return data["streams"][0]


def get_profile(name: str, container: str, color_policy: str) -> DeliveryProfile:
    if name not in PROFILES:
        raise AssemblyError(f"Unknown delivery_profile '{name}'. Available: {list(PROFILES)}")
    if color_policy not in COLOR_POLICIES:
        raise AssemblyError(f"Unknown color_policy '{color_policy}'")
    profile = PROFILES[name]
    if name != "social" and container != "mov":
        raise AssemblyError(f"{name} requires output_format=mov; a container is never changed silently")
    return profile


def qualify_inputs(profile, paths, segments, color_policy, width, height):
    if profile.name == "social":
        return []
    encoders = run_capture(["-hide_banner", "-encoders"]).decode(errors="replace")
    if not any(len(row.split()) > 1 and row.split()[1] == profile.encoder for row in encoders.splitlines()):
        raise AssemblyError(f"FFmpeg encoder {profile.encoder} is unavailable for {profile.name}")
    if profile.name == "dnxhr_hqx" and (width < 256 or height < 120):
        raise AssemblyError("DNxHR requires at least 256x120 pixels; no implicit upscale is performed")
    # These legacy effects negotiate 8-bit formats in the current renderer.
    for segment in segments:
        chains = [segment.chain, segment.post, *(layer.chain for layer in segment.layers)]
        if any(token in chain for chain in chains for token in ("eq=", "hue=", "chromashift=", "noise=")):
            raise AssemblyError("This look/transition is not qualified for 10-bit delivery. "
                                "Disable it explicitly or use the social profile.")
    warnings = []
    for path in sorted(paths):
        stream = video_stream(path)
        missing = []
        for key in ("color_space", "color_transfer", "color_primaries"):
            value = stream.get(key, "unknown")
            if value in ("unknown", "unspecified", None):
                missing.append(key)
            elif value != "bt709" and not (key == "color_space" and value == "gbr"):
                raise AssemblyError(f"{path.name}: {key}={value} is incompatible with the SDR BT.709 master. "
                                    "Perform an explicit color-managed conversion first.")
        if missing:
            if color_policy == "require_bt709":
                raise AssemblyError(f"{path.name}: missing {', '.join(missing)}; "
                                    "tag/convert the source or explicitly select assume_bt709")
            warnings.append(f"{path.name}: untagged color explicitly assumed SDR BT.709; not an HDR conversion.")
    return warnings


def output_options(profile):
    options = ["-c:v", profile.encoder, *profile.encoder_options, "-pix_fmt", profile.pixel_format]
    if profile.name != "social":
        options += ["-color_range", "tv", "-colorspace", "bt709", "-color_trc", "bt709",
                    "-color_primaries", "bt709"]
    return options


def validate_delivery(path, profile):
    if profile.name == "social":
        return
    stream = video_stream(path)
    if stream.get("codec_name") != profile.codec or stream.get("pix_fmt") not in profile.decoded_formats:
        raise AssemblyError(f"{profile.name}: encoded codec/pixel format does not match the delivery contract")
    if any(stream.get(key) != "bt709" for key in ("color_space", "color_transfer", "color_primaries")):
        raise AssemblyError(f"{profile.name}: encoded BT.709 metadata is missing")
    # MOV's ProRes nclc color atom does not carry a full/limited-range flag.
    # ProRes uses legal-range YCbCr; qualification must also decode a level ramp.
    prores_legal_range = profile.codec == "prores" and stream.get("color_range") in (None, "unknown")
    if stream.get("color_range") != "tv" and not prores_legal_range:
        raise AssemblyError(f"{profile.name}: encoded signal range is not limited")
