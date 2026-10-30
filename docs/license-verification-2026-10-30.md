# License source review — 2026-10-30

Scope: primary-source text review and assessment of a user-supplied authorization excerpt, not independent email authentication or legal clearance. Existing original-code MIT licensing is unchanged.

| Component | Authoritative text reviewed | Finding / release gate |
|---|---|---|
| H3 / derivatives | [MiniMax H3 license](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) | Community terms exclude EU, UK, Korea and US. A user-supplied email excerpt confirms specific permission to use H3 and H3 Works, conditional on the original request's commitments and representations. That request is not yet available to verify France/jury/hosting scope. Hosted access also carries downstream terms/safeguard obligations. |
| YuE2 weights / VAE | [YuE MODEL_LICENSE](https://github.com/multimodal-art-projection/YuE/blob/main/MODEL_LICENSE) | CC BY-NC 4.0 plus specific individual-creator permission. That permission covers individuals monetizing outputs under its conditions; it is not blanket commercial weight use by companies or sale of weights. |
| GSAP | [Standard License + FAQ](https://gsap.com/community/standard-license/) | Free commercial permitted uses; restrictions target competing visual animation builders. AI-authored code and non-competing niche tools are discussed separately. HyperKut's applicability remains a documented interpretation, not written product-specific approval. |

Exact quantizations, provider revisions and model SHA-256 still need a release inventory. The existing [model list](models-and-downloads.md) records configured filenames and known unpinned files; it does not establish rights to derivatives. [License scope](../LICENSES.md) and [third-party notices](../THIRD_PARTY_NOTICES.md) remain authoritative within this project.

## Media

The author has confirmed ownership/redistribution permission for the two supplied preset music tracks and generated portraits. The silver.muse source is credited in the Studio media documentation; attribution alone is not permission to redistribute a third-party reference. Check every packaged original source and preview, fonts and narration authorization against the actual release payload. Do not extend one asset's permission to unrelated material.

## Gate status

- [x] Re-read the three primary model/runtime terms above on 2026-10-30.
- [x] Keep code, weights, runtime and media rights distinct.
- [x] Read the user-supplied written authorization excerpt on 2026-10-30: specific H3/H3 Works use permission is stated, conditional on the original request.
- [ ] Inspect the original request and match its commitments to the intended territory, local use, jury access, hosting and any distribution. The excerpt alone does not specify these; sender, headers and email date were not independently verified.
- [ ] Pin/check every included checkpoint revision and upstream notice.
- [ ] Product-specific GSAP clarification if the planned UI crosses into a competing visual builder.
- [ ] Review the final distributed media/runtime payload and make a release go/no-go decision.

No license application, external message or public release was sent by this patch.

### Individual use is not a territorial exception

The H3 license was checked again during runtime qualification. Definition 9 covers natural and legal persons. Section IV.1 requires separate prior written authorization above USD 20 million in yearly commercial-product/service revenue; that threshold does not override the territorial limits. Definitions 3/5 and section V.4 exclude the EU, UK, Korea and US from the community grant, including use of outputs. Being an individual, working locally or entering a competition does not itself remove that exclusion. API/app services have separate terms that must be checked for their particular use. This describes the community grant, not the scope of the separate conditional permission supplied afterward. That permission must be assessed together with the original request; it must not be extended to all users of the MIT-licensed pack. No personal email content or headers are reproduced here.
