# Installing local graphics and sound finishing

Current instructions: 2026-10-26. These commands document the existing installers; a clean-machine installation remains to be validated separately. Run them once, explicitly, from the **VideoTools pack root**. They are not Studio-venv Python packages.

## Requirements and scope

| Capability | What is required |
|---|---|
| Serve an already built Studio | Studio Python dependencies; no Node server for frontend assets |
| Build frontend/dist | Node.js 22+ and npm in Studio/frontend |
| Render graphics, titles or shared motion layers | HyperFrames runtime, Node.js 22+, FFmpeg/ffprobe and a compatible local browser |
| Build the 30-sound palette | Tone.js runtime, Node.js 22+ and local Chrome/Edge |
| Mix an already generated Tone bank | Existing Python/FFmpeg assembler; no browser launched for each assembly |

Animated design is **experimental and disabled by default in the Studio**. Install HyperFrames when you enable graphics. Graphics are optional at the application level, not automatically bypassed whenever a legacy node is present: disabling animated decoration does not disable separately requested text/layers. Any remaining layer request still needs the shared renderer. Basic typography does not require BiRefNet; subject-dependent layers do.

## Windows / PowerShell

Open PowerShell in `ComfyUI/custom_nodes/ComfyUI-Majoor-VideoTools` and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_hyperframes.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\install_tone.ps1
```

HyperFrames installs `hyperframes@0.8.201` and `gsap@3.15.0` in `runtime/hyperframes`. Tone installs `tone@15.1.22` and `puppeteer-core@25.16.0` in `runtime/tonejs`, then synthesizes 30 mono/stereo WAV cues in `runtime/tonejs/bank`. It does not download a sample pack. Preserve upstream notices: [licenses](../LICENSES.md).

The installers need network access for npm. HyperFrames may additionally provision fonts/browser resources; provision and validate those before promising fully offline rendering. No npm installation is initiated by a generation request. The Tone palette builder requires a locally installed Chrome/Edge (or MAJOOR_CHROME); its puppeteer-core dependency does not bundle a browser.

For a custom Tone browser/runtime, set these in the shell used for installation and in the ComfyUI launcher as appropriate:

```powershell
$env:MAJOOR_CHROME = 'C:\path\to\chrome.exe'
$env:MAJOOR_TONE_RUNTIME = 'C:\path\to\tone-runtime'
```

The provided Tone installer installs to the standard pack runtime. If you choose a custom runtime, provision its pinned dependencies there and run `node scripts/render_tone_bank.mjs` with MAJOOR_TONE_RUNTIME pointing to it. Setting the variable alone does not relocate an existing bank. HyperFrames supports MAJOOR_HYPERFRAMES_RUNTIME for an already provisioned runtime containing node_modules. Consult each engine for browser-specific settings; MAJOOR_CHROME here is the Tone bank builder's setting.

After updating engine code or installed runtimes, restart ComfyUI **when no job is running**. Rebuild the frontend only if its source changed; restart the Studio if its backend changed. Documentation changes alone require neither.

## Controls, absence and failures

- Studio animated design and explicit graphic layers use the unified HyperFrames compositor. Missing required graphics dependencies produce an explicit error.
- **Sound effects / Bruitages** selects the existing single SFX bus. An installed Tone bank is loaded locally; user WAVs override matching types and retain stereo. Musical notifications/signatures are explicit cues, not added on every cut.
- Without a Tone bank, six historical procedural sounds remain available. An invalid installed bank is an error, not silent acceptance.
- **Sound design** is a different existing control: it retains/mixes the sound of generated takes. It is not the Tone installer or music generator.
- Music added-track volume defaults to zero; this does not mean that source-master audio is muted.

Windows is the currently documented/validated integration environment. The supplied PowerShell helpers are Windows-oriented. Cross-platform setup and a fresh-clone reproduction are pending work, not claims made by this guide. Do not delete shared models or node packages to simplify an installation.
