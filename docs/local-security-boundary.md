# Local security boundary and deployment qualification

Supported baseline: one trusted operator, local ComfyUI, local Studio. A workspace ID is storage scoping, not authentication. File path validation does not provide user authorization.

## Static route inventory

| Pack route | Purpose | Boundary |
|---|---|---|
| GET /majoor/video_info | Probe annotated input/output/temp media | Resolver canonicalizes the file and checks configured roots; not arbitrary remote URLs. |
| GET /majoor/recipes and /majoor/modes | Workflow metadata | ComfyUI server access boundary. |
| POST /majoor/deploy_shots | Transform a submitted workflow | Treat body as untrusted data; no arbitrary shell execution should be introduced. |
| GET /majoor/skills and POST /majoor/skills/compose | Local prompt/skill composition | Not a model-license or access-control boundary. |
| GET /view (ComfyUI) | Serve media | Output-relative URL; relies on ComfyUI access controls. |

Studio routes and SDK transport are a separate application and must be qualified separately. A ComfyUI /view path can expose files to anyone authorized to that server; an isolated worker folder does not create private per-user media permissions.

## Implemented Studio admission, not a public deployment

The separate Studio backend defaults to `HYPERKUT_ACCESS_MODE=local` and refuses non-loopback HTTP/WebSocket clients. New `jury` admission requires an explicit dedicated `HYPERKUT_WORKSPACE` and `HYPERKUT_OUTPUT_DIR`, non-wildcard `HYPERKUT_ALLOWED_HOSTS`, `HYPERKUT_ACCESS_USERNAME`, and a password of at least 24 characters in `HYPERKUT_ACCESS_PASSWORD`. Secrets are excluded from settings repr; do not put real passwords in source, shell transcripts or public logs. Existing SECATOR environment fallbacks remain.

Jury mode requires HTTPS at the ASGI boundary and constant-time Basic credential comparison for frontend, API, static files and media; remote restart is forbidden. Admission is outermost so early route/restart responses cannot bypass it. A correctly configured TLS reverse proxy and its trusted-forwarded-header policy are operator responsibilities. Keep ComfyUI/proxy ports private: this Studio middleware does not secure native ComfyUI routes.

Limits include 16 MiB non-upload request bodies, the existing per-upload limit plus a bounded multipart envelope, minimum free disk (default 256 MiB), and a serialized persistent-upload budget (default 20 GiB). `HYPERKUT_MAX_WORKSPACE_MB` / `Settings.max_workspace_bytes` currently limits **uploads only**, despite its name; generated takes/exports, model storage and GPU time require separate OS/queue quotas. `HYPERKUT_MIN_FREE_DISK_MB` sets the free-space threshold. Partial uploads are removed on failure/cancellation.

This is one shared jury account with one dedicated workspace, not per-user project authorization. Unit/API tests pass for remote refusal, TLS/auth across routes, malformed credentials, body limits, quota cleanup and cross-origin upload refusal. No public listener, certificate, tunnel or real jury deployment was opened or qualified.

## Required before jury/public exposure

- [ ] Deploy and qualify the implemented authentication over real TLS; keep native ComfyUI and proxy APIs private.
- [ ] Verify permitted hosts/origins, browser sessions, upload limits and CSRF behavior.
- [ ] Use a dedicated workspace with only authorized presets/references; do not expose personal library projects.
- [ ] Apply queue/run and disk quotas, expiry and a cancellation path.
- [ ] Test ../, encoded traversal, symlink/reparse escape, forged project/workspace IDs and cross-user reads.
- [ ] Test malformed/large JSON, large media, subprocess timeout and shutdown cleanup.
- [ ] Establish required H3 authorization and downstream terms/safeguards for the actual deployment territory.

Local file locators reject traversal/encoded aliases and canonical symlink escapes. They explicitly refuse external-output roots that need artifact transfer. These measures are not proof of multi-user isolation. No firewall change, tunnel or public endpoint is automatically installed/opened by these corrections.
