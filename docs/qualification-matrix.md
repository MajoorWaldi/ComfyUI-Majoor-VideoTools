# Qualification evidence — PR #5

Date: 2026-10-30. **Local runtime qualification executed; release remains NO-GO.** The results below supersede the earlier preparation-only NOT RUN record. No model generation, public deployment or blanket closure of G0-G17 is claimed.

## Executed evidence

| Ticket | Evidence and result | Still open |
|---|---|---|
| G0 | H3 license re-read; user-supplied email excerpt confirms specific conditional H3/H3 Works use permission | Original request needed to verify France/jury/hosting scope; email not independently authenticated; exact weight revisions and final-payload rights NOT VERIFIED |
| G1 | PASS: two-process same-key reuse, actual simultaneous encoders for distinct keys, cancellation of running FFmpeg then recovery by another process, lock timeout/cancel | Cross-host SMB and abrupt OS-kill recovery NOT RUN |
| G2 | PASS: locator regressions; Chromium HTTP 206 and real metadata/image decoding for sources, thumbnails, persistent audio and two exports in classic and isolated roots; retained takes/music also resolve | All comparison/dialogue UI paths and complete Studio browser traversal NOT RUN |
| G3 | PASS: decoded reorder/duplicate/trim/slip/source-master/music/dialogue regressions; procedural tones and locked music measured | Speed-ramp take audio remains intentionally silent; real speech review NOT RUN |
| G4 | PASS: regression suite, fractional fps, slip/sub-cuts/self overlays, capacity refusal/padding | Exhaustive overlays/splits/alternate takes/ramp combinations not certified |
| G5 | PASS: environment/workflow inventory; fresh local clone plus current changes, Python 3.11 clean dependency environment: 115 targeted tests | Not a fresh complete ComfyUI/Studio/model installation; model pins and GPU Remix/Text/Music with 1-5 refs NOT RUN |
| G6 | PASS: actual workflow wiring and missing-wire mutations | Full GPU workflows NOT RUN |
| G7 | PASS: NaN, infinity, bool, overflow and normal-value regressions in engine suite | Production model-backed projects not certified |
| G8 | PASS: temporary WAV removal, fresh-process persistent index read; experimental snapshot carries verified persistent audio | Old cache/audio not automatically migrated; snapshot code is Git-ignored in the separate Studio repository, not a released transport |
| G9 | PASS: unchanged detection preserves saved takes/edits; incompatible bounds refused without overwrite | Automatic migration deliberately not implemented |
| G10 | PASS: CFR/fractional, 90/270 rotation, nonzero video PTS, first of two audio tracks, decoded +250 ms delayed audio | VFR/audio-leading/full color/format corpus not certified |
| G11 | PASS in Chromium: actual playback, seek to 0.5 s, buffered media, explicit autoplay refusal, duplicate/undo/redo, close releases src/pauses media, five reopen cycles in isolated root | Graph/node removal, stressed network buffering and pixel/FX parity NOT RUN; editor is raw-take preview |
| G12 | PASS: corruption/asset changes, bounded regenerable-cache retention, free-space refusal, active/crashed lease regression | Long-running disk pressure, abrupt process kill and SMB NOT RUN |
| G13 | PASS: explicit ProRes HQ, DNxHR HQX and ProRes 4444 alpha; decoded >512-level ramp, max error <5, alpha >240 levels, BT.709 tags | Every overlay/split/text/finishing chain not certified; HDR/OCIO unsupported; legacy 8-bit effects rejected |
| G14 | PASS: pure rational compiler, legacy/manual adapters, deterministic portable hashes, incremental occurrence tests | FX/duration resolution still occurs in assembler; frontend does not consume one resolved graph for its entire lifecycle |
| G15 | PASS: authorized procedural 6 s / 144-frame benchmark, cut errors [0,0,0], tone order 880/440/660/880 Hz, music 220 Hz throughout | Model/narrative benchmark and human identity/continuity/text/music review NOT RUN |
| G16 | PASS: local fail-closed admission, jury TLS/auth checks, body/upload quotas, partial-file cleanup, external-origin refusal | No public TLS deployment; one shared jury account, not per-user ACLs; quota is uploads only, not total generated output/GPU |
| G17 | Evidence/contracts updated; no commit, push or publication | NO-GO pending rights, remaining development and external qualification |

## Commands and measured runs

Use the actual ComfyUI interpreter, not an unrelated system Python:

```powershell
$py = '..\..\.venv\Scripts\python.exe'
& $py -m pytest tests\integration -q --tb=short
node --test tests\web\*.mjs
& $py tests\comfy\check_nodes.py
& $py tests\comfy\check_timeline_edit.py
& $py scripts\benchmark_editorial.py --output-dir <private-benchmark-directory>
```

- Engine integration suite: **616 passed, 2 skipped**, 232.62 s; a subsequent benchmark regression is recorded separately rather than added to this historical suite total.
- Distinct/same-key export transaction tests: **8 passed**.
- Separate Studio backend suite: **425 passed, 7 skipped**; after moving admission outside all route middleware: **10 access tests passed**. Its test-only SDK/async dependencies were isolated, not installed into the shared ComfyUI environment.
- Studio frontend: **129 tests / 24 files passed**; TypeScript/Vite production build passed.
- Pack web tests: **8 test files passed**. The word_renderer helper is not a standalone test.
- Actual node integration script: **79 OK / 0 failed**; Timeline Edit script passed. Merely collecting check_*.py is not this evidence.
- Isolated CPU/offline ComfyUI v0.43.0 on loopback: actual /prompt submission, history, 72-frame montage with/without music, saved document and second-run cache reuse passed. No GPU/model generation.
- Chromium: 14 source/thumb/audio/export URLs across two roots returned 206 and decoded; retained takes/music also returned 206; player lifecycle checks above passed. Stream-aborted events on explicit media cleanup are expected, not missing-file failures.
- Procedural benchmark report: 6.0 s, 144 frames, observed cuts 36/72/108; graph fingerprint `ed336fdac6d75a2b18c333b3a0283ab471547ae66ca22f963dd823ff33b9ffb6`. Output SHA-256 `1b02c568ab21ea44bd28755bcced5bfb87c00027b522702608fad9487d0d6434` for this environment; codec versions can change encoded bytes.

Environment: Windows, ComfyUI v0.43.0, ComfyUI Python 3.13.12, FFmpeg 7.1, Node 22.20.0. The independent clean dependency run used Python 3.11.0. Skips are not passes. Existing optional-runtime tests do not establish full external runtime/GPU qualification.

The initial system-Python run failed collection because Pillow was absent; the existing ComfyUI interpreter resolved that mismatch. Rotation fixtures were corrected. A real decoded-audio regression (+250 ms source audio advanced to zero) was reproduced, fixed with timestamp-aware resampling and rerun successfully. The benchmark's initial fixture-construction errors were corrected before its PASS.

scripts/collect_qualification.py was executed for environment/workflow inventory. --models-root explicitly enables model hashing; no model hashing/download/inference was performed. Store inventories privately because they can contain local paths. The fresh-clone evidence uses base commit e4bb61a74e0a65865d2a5a4484199fd8c25a19b5 plus the current working-tree overlay; it does not pin a finished release.

A conditional H3 authorization email excerpt was subsequently supplied; its referenced original request is still needed to verify scope. No SMB share or GPU qualification window was supplied. Human narrative review remains NOT RUN. The Studio is a distinct repository; experimental Git-ignored snapshot changes must not be presented as published pack functionality.
