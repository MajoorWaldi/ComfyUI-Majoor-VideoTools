# Get Video Components Advanced

The node returns the input `VIDEO` unchanged, total frame count, metadata, selected `IMAGE` frames, the full `AUDIO` track, and the indices corresponding to the returned images. Frame selection syntax and ordering are shared with **Load Video Advanced**.

Uncropped file-backed ComfyUI videos are decoded as a stream: unselected frames are not converted to image tensors, and audio is decoded separately. The node caps its estimated temporary and output allocation at 512 MiB. If selected frames plus audio would exceed that limit, it fails with an actionable error instead of attempting an unbounded allocation.

Already-materialized tensor videos are supported within the same selected-image budget. A cropped file video uses ComfyUI's component decoder only when a conservative estimate for materializing the full video remains within budget; this preserves ComfyUI's crop/color handling but decodes the full batch and audio together. Other non-file video implementations fail explicitly because their decode allocation cannot be bounded through the public video interface. Use a file-backed video or an already-materialized tensor video for those cases.

With **load_images** disabled, the node returns an empty `IMAGE` batch and no `AUDIO`; it still reports metadata and whether the file contains an audio stream.
