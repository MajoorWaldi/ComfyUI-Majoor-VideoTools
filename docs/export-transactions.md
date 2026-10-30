# Export transactions, cache and recovery

Assembly cache version 5 uses the actual source/take/layer/text file fingerprints, renderer source fingerprints, graph, audio bytes and options. Historical exports are kept; they are not overwritten by a new cache version.

## Concurrency contract

- A FileLock in `cache/export_locks/` is named by the canonical final export path. Workers sharing that filesystem use the same lock.
- Cache probe, encoding, media validation, normalization, final replacement and score/delivery sidecars happen under the export lock. Different output keys use different locks.
- Lock acquisition polls at 100 ms, checks cancellation, and times out after 120 s with a controlled error. Timeout is not a corrupt-export success; retry when the other worker finishes.
- Filter scripts, partial videos and leveled files use per-invocation UUIDs in the same project/volume. A worker cleans only its own incomplete media. Unique filter logs remain for diagnosis.
- SFX WAV and text PNG caches are published via temporary file + rename. Readers cannot see a half-written cache entry.
- Cancellation is checked before final publication. A crash after video publication but before sidecars is repaired by the next verified cache hit. Sidecars are independently atomic; this is recovery, not a multi-file filesystem transaction.
- `optional-audio.json` is a latest-completed-export advisory report. It includes the associated export and plan fingerprint; it is not a historical per-job journal.

SMB correctness depends on FileLock/OS filesystem lock support and same-volume rename semantics. Local Windows tests execute same-key processes, simultaneous different-key encoders, cancellation during a running encode, a fresh recovery process, and lock timeout/cancellation. Cross-host SMB and abrupt process-kill recovery remain unqualified. Assembly normalization and its loudness measurements poll cancellation, terminate their subprocess and retain bounded timeouts.

## Durable audio / delivery v2

Supplied music is copied, by SHA-256, into `sources/audio/<digest>.<extension>`, with an atomic `sources/audio/index.json` under the project lock. Delivery sidecars contain a project-relative `media_ref`, asset hash, available WAV duration/rate/channel metadata, audio policy and renderer build. Deleted temporary input paths are no longer the asset identity. Rights remain `user_supplied_not_verified`; a hash does not grant permission. Version 1 delivery readers remain accepted, while new writes are version 2.

Legacy `cache/audio` assets are retained, not automatically migrated or garbage-collected. Tests remove the temporary WAV and read the persistent index in a new process. The experimental Studio snapshot includes and verifies registered persistent audio, but its source is Git-ignored in that separate repository: a normal pack/Studio commit does not distribute that transport. Full released ZIP portability remains unqualified.

## Regenerable-cache retention

Assembly enters a cache-use lease before maintenance. Defaults: 10 GiB regenerable budget, 30 days maximum age and 256 MiB minimum free space. Only known PNG/WAV/MP4 intermediates in `cache/text`, `cache/render_sources`, `cache/timeline`, and `cache/sfx_*.wav` are candidates. A one-hour grace period protects recent previews. Manifest/editor/audio-index references are protected; sources, takes, exports, persistent/legacy audio and unknown files are never retention candidates.

A short project maintenance lock serializes lease admission and collection; per-render OS locks keep active leases visible without serializing separate exports. Any active lease prevents deletion. A stale lease file whose OS lock has been released does not block maintenance. Insufficient free space fails explicitly; deletion errors produce warnings. This is bounded cache maintenance, not a whole-project storage quota or an assurance that every future encode fits the disk.

## Other caches

HyperFrames checks build metadata, output fingerprint, streams, dimensions and duration before reusing media. Missing/corrupt reports invalidate the cache. Reports are written atomically. Source/template/driver/GSAP/mask/timing inputs remain in its key. Final score sidecars are removed when the current export has no shared score. Invalid advisory delivery metadata returns not_evaluated rather than a false pass.

After an interrupted operation, retry the same request to probe/recover; do not delete arbitrary partial files belonging to another worker. Retention and corruption regressions pass; long-running disk pressure and cross-host filesystem behavior still need qualification.
