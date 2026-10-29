# Configured model files and provenance

Inventory of maintained Studio API templates, 2026-10-26. Filenames are loader settings, not a promise that every upstream branch exposes the exact quantization. Use the provider's file listing and matching license; record the exact revision before redistribution. Model terms: [LICENSES.md](../LICENSES.md).

| Role | Configured file | ComfyUI/models folder | Source / status |
|---|---|---|---|
| Vision planning | gemma4_12b_int8_convrot.safetensors | text_encoders | [Comfy-Org/gemma-4](https://huggingface.co/Comfy-Org/gemma-4) |
| Audio-aware planning | gemma4_e4b_it_fp8_scaled.safetensors | text_encoders | Same Gemma repository |
| H3 model | minimax_h3_ref2va_pruned_int8_convrot.safetensors | diffusion_models | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) |
| H3 encoder | qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors | text_encoders | Same H3 repository; packaged encoder terms also apply |
| H3 video VAE | minimax_h3_video_vae_int8_convrot.safetensors | vae | Same H3 repository |
| H3 audio VAE | minimax_h3_audio_vae_fp32.safetensors | vae | Same H3 repository |
| H3 pose patch | minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors | model_patches | Same H3 repository; only when pose branch is needed |
| H3 turbo LoRA | minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors | loras | Configured local filename; exact provider/revision remains to be pinned; do not silently substitute a 4-step version |
| Music | yue2_3b_int8_convrot.safetensors | checkpoints | [Comfy-Org/YuE2](https://huggingface.co/Comfy-Org/YuE2), combined model/encoder/VAE |
| Location plates | flux-2-klein-4b-fp8.safetensors | diffusion_models | [BFL](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8), optional plate branch |
| Plate encoder | qwen_3_4b.safetensors | text_encoders | [Comfy-Org/flux2-klein](https://huggingface.co/Comfy-Org/flux2-klein), split_files |
| Plate VAE | flux2-vae.safetensors | vae | Same FLUX repository; its component terms apply |
| Subject mask | birefnet.safetensors | model loader's mask folder | [BiRefNet](https://huggingface.co/ZhengPeng7/BiRefNet); follow the installed native loader's directory mapping |
| Pose / detection | dw-ll_ucoco_384_bs5.torchscript.pt; yolox_l.onnx | controlnet_aux managed location | [DWPose](https://github.com/IDEA-Research/DWPose) / [YOLOX](https://github.com/Megvii-BaseDetection/YOLOX); record converted checkpoint provider |

Some branches are lazy and some upstream loaders download files on first use. Install and provision resources explicitly before offline use. Do not interpret an optional preset switch as permission to remove a shared model. No weights are bundled here, and no blanket rights to all quantizations or derivative checkpoints are asserted.
