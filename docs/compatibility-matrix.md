# Compatibility matrix

Measured on 2026-10-30 on one Windows 11 machine (RTX 4090). Only the combination in the first row was run; other rows are limits taken from the code and `requirements.txt`, not tested results.

| Component | Version in the tested combination | Constraint |
|---|---|---|
| ComfyUI | 0.43.2 | Needs native H3, YuE2, Gemma, FLUX and BiRefNet nodes. Older builds are not tested |
| Majoor VideoTools | 0.1.0 (`pyproject.toml`), `main` at 7e32e8b plus uncommitted work | The Studio refuses to submit when the loaded pack lacks `music_edit_mode` or the dialogue track and asks for a ComfyUI restart |
| HyperKut Studio | working tree, frontend 0.0.0 | `comfy-sdk[pil]>=0.5,<0.6`, `comfy-api-proxy>=0.1.6` |
| ComfyUI Python / torch | Python 3.13.12 / torch 2.10.0+cu130 | The Studio has its own virtual environment; do not share it with ComfyUI |
| Studio dependencies | comfy-sdk 0.5.0, comfy-api-proxy 0.1.6, fastapi 0.162.0, uvicorn 0.54.0, httpx 0.28.1 | Pinned only by the ranges above |
| FFmpeg / ffprobe | 7.1 (gyan.dev full build) | Required on `PATH` |
| Node.js | 22.20 | 22+ for HyperFrames and Tone; not needed to serve a built `frontend/dist` |
| GPU | RTX 4090, 24 GB | Other cards, ROCm and macOS not tested |

Storage backends: `shared_local` (Studio and ComfyUI share the output disk) was run. `remote_artifacts` is covered by unit tests only; transport, VRAM, disk and timing on a real remote worker are not measured.

Update this table at every release and state which rows were actually run. Related: [qualification matrix](qualification-matrix.md), [installation](studio-installation.md), [models](models-and-downloads.md).
