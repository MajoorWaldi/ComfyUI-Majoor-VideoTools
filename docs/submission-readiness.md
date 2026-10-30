# Release checklist

For the node pack and its separate HyperKut Studio beta:

- [ ] Publish matching source versions, workflow files and license notices.
- [ ] Verify a clean installation against pinned node/model revisions.
- [ ] Validate retained-take assembly, manual montage and requested optional runtimes.
- [ ] Check model, dependency and media permissions, including territory-specific restrictions.
- [ ] Include only explicitly authorized portable inputs and public demo assets.
- [ ] Document hardware, output limits and model-backed verification separately from scripted tests.

The Studio is a local single-user application. An opt-in authenticated jury mode exists, but public TLS deployment, per-user authorization and complete storage/compute quotas remain unqualified. Finishing is experimental and disabled by default.

[Installation](studio-installation.md) · [Roadmap](../ROADMAP.md) · [License scope](../LICENSES.md) · [Official contest requirements](https://comfy.org/open-source-higgsfield)


## Audit correction qualification

Source changes and runtime results are tracked in [PR #5 checklist](AUDIT_CORRECTIFS_CODEX_2026-10-30.md). The engine suite passed 616 tests (2 skipped), Studio backend 425 (7 skipped), frontend 129 plus build; targeted admission/benchmark and real CPU ComfyUI/browser/media checks are recorded separately. These local runs do not close all 18 gates.

**Publication decision: NO-GO.** A user-supplied H3 authorization excerpt confirms conditional use permission; the original request is needed to verify its scope. Exact weight revisions, complete fresh model-backed installation, SMB, remaining resolved-graph/FX qualification, real TLS deployment and human narrative review are not established. No model generation, public access, commit, push or release was performed. [Qualification matrix](qualification-matrix.md), [local security boundary](local-security-boundary.md), [audio contract](audio-policy-contract.md), and [dated license gates](license-verification-2026-10-30.md) distinguish PASS, skips and remaining work.
