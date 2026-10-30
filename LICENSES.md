# Code, model and media licenses

Reviewed 2026-10-26. This inventory identifies applicable sources; it grants no additional rights. The existing [MIT LICENSE](LICENSE) for the author's code is unchanged. Open-source application code, downloadable model weights, commercial output rights and competition eligibility are separate matters.

## Application and dependencies

| Component | License / terms | Scope |
|---|---|---|
| Majoor VideoTools original code | MIT | This pack's original code and templates |
| HyperKut Studio original code | MIT | The separately versioned Studio; its own LICENSE applies |
| HyperFrames 0.8.201 | Apache-2.0 | External video renderer |
| Tone.js 15.1.22 | MIT | External synthesis library |
| puppeteer-core 25.16.0 | Apache-2.0 | Browser automation; **not MIT** |
| GSAP 3.15.0 | GreenSock Standard “no charge” license | Separate terms; do not label MIT, Apache or unrestricted open source |
| Vendored YuE2 instrumental helpers | MIT | Only the files and notice in core/vendor/yue2 |
| ComfyUI | GPL-3.0 | Separately installed engine |
| comfyui_controlnet_aux | Apache-2.0 in installed LICENSE.txt | Pose preprocessing code; weights keep their own terms |
| KJNodes / Easy-Use | GPL-3.0 in installed LICENSE files | Visual workflow dependencies; not required by exported Studio API graphs |
| FFmpeg, browser, fonts, codecs and other dependencies | Their own licenses / build terms | Not relicensed by this project |

See [third-party notices](THIRD_PARTY_NOTICES.md). The GSAP publisher announces free commercial use, but its actual standard terms remain authoritative. The official Standard License and FAQ were reviewed on 2026-10-28. They permit AI-generated code and niche visual tools that do not directly compete with Webflow; they restrict certain competing animation builders. HyperKut is a video-only tool, so no automatic paid-license requirement was identified, but this is an interpretation rather than written product-specific approval. See the official GSAP Standard License and FAQ for its permitted-use scope. Runtime packages are obtained by explicit installers rather than bundled as this project's MIT source.

## Model weights

No model weights are included in the source distribution. A local installation or quantization does not remove upstream terms. Verify the exact checkpoint provider as well as its base model.

| Model / role | Upstream terms and authoritative source |
|---|---|
| MiniMax H3, associated VAEs / ControlNet / derivatives | [H3 Community License](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE); separate authorization may apply |
| YuE2-3B and audio VAE | [CC BY-NC 4.0 plus individual-creator permission](https://github.com/multimodal-art-projection/YuE/blob/main/MODEL_LICENSE); [Comfy checkpoint](https://huggingface.co/Comfy-Org/YuE2) |
| Gemma 4 | [Apache-2.0](https://huggingface.co/Comfy-Org/gemma-4) |
| FLUX.2 klein 4B | [Apache-2.0](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B); do not generalize to every FLUX variant |
| Qwen3 4B | [Apache-2.0](https://huggingface.co/Qwen/Qwen3-4B) |
| Qwen3-VL used by H3 | Apache-2.0 for the base encoder, identified in the H3 license; verify the packaged H3 checkpoint too |
| BiRefNet | [MIT](https://huggingface.co/ZhengPeng7/BiRefNet) |
| DWPose / YOLOX | [DWPose](https://github.com/IDEA-Research/DWPose) / [YOLOX Apache-2.0](https://github.com/Megvii-BaseDetection/YOLOX/blob/main/LICENSE); checkpoint conversion/provenance must be recorded separately |

Configured checkpoint names and folders: [model inventory](docs/models-and-downloads.md). ACE-Step and MMAudio are not model generators in the maintained Studio API path. Their mere presence in a shared ComfyUI installation does not make them part of this inventory.

### H3: territory and authorization

The Community License excludes the EU, UK, South Korea and US. Section V.4 also addresses outputs. A suitable authorization must be established for use in an excluded territory; none is established by this documentation. [Comfy's official licensing page](https://comfy.org/minimax/license/) distinguishes local authorization from rights included with Comfy Cloud. A competition bonus does not grant a personal license. This Studio currently uses local H3, not a Cloud entitlement.

### YuE2: individual creators versus companies

The additional permission allows individuals acting in a personal creative capacity to generate and monetize outputs under its conditions. It does not authorize companies' commercial use of the weights or commercial resale of weights. The base CC BY-NC terms still apply outside the permission. Do not describe every output as automatically noncommercial, or claim the weights are universally commercially permissive. YuE2 is the active music generator; no replacement is implied.

## Redistribution and user media

Keep this project's LICENSE, upstream notices and the existing vendored-helper LICENSE. Installing dependencies is different from distributing their binaries: a packaged installer/image must separately meet every included component's requirements, including GPL dependencies and the actual FFmpeg build. This file is an inventory, not a complete transitive SBOM or a substitute for those license texts.

Video, music, likenesses, voices, fonts and user samples require their own rights. The synthesized Tone palette contains no downloaded third-party sound recordings and does not grant rights to unrelated media. No output is automatically made MIT by this repository's LICENSE.

Competition-specific publication and authorization questions are tracked in [Studio readiness](docs/submission-readiness.md). Clearing documentation does not establish permission, publish either repository or submit an entry.


Primary H3, YuE2 and GSAP texts were re-read on 2026-10-30. See the [dated verification and remaining gates](docs/license-verification-2026-10-30.md). This does not establish a missing personal authorization or a deployment right.
