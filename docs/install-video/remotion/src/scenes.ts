export type Step = {
  cwd?: string;
  cmd: string;
  out?: {t: string; kind?: 'ok' | 'dim' | 'warn'}[];
  note: string;
};

export type TerminalScene = {
  id: string;
  step: string;
  title: string;
  shell: string;
  steps: Step[];
};

export const FPS = 30;

export const scenes: TerminalScene[] = [
  {
    id: 'pack',
    step: 'STEP 1',
    title: 'Put the pack in ComfyUI',
    shell: 'PowerShell',
    steps: [
      {
        cmd: 'cd "ComfyUI\\custom_nodes"',
        note: 'Every custom node lives in ComfyUI/custom_nodes.',
      },
      {
        cmd: 'git clone https://github.com/MajoorWaldi/ComfyUI-Majoor-VideoTools',
        out: [{t: "Cloning into 'ComfyUI-Majoor-VideoTools'...", kind: 'dim'}, {t: 'done.', kind: 'ok'}],
        note: 'The pack: Majoor VideoTools, the nodes and graphs the Studio drives.',
      },
      {
        cmd: '..\\..\\python_embeded\\python.exe -m pip install -r ComfyUI-Majoor-VideoTools\\requirements.txt',
        out: [{t: 'Successfully installed scenedetect filelock numpy Pillow opencv-python', kind: 'ok'}],
        note: "Use ComfyUI's own Python, not the system one.",
      },
      {
        cmd: 'git clone https://github.com/Fannovel16/comfyui_controlnet_aux',
        out: [{t: "Cloning into 'comfyui_controlnet_aux'...", kind: 'dim'}, {t: 'done.', kind: 'ok'}],
        note: 'The one extra custom node the Studio graphs ask for.',
      },
    ],
  },
  {
    id: 'finishing',
    step: 'STEP 2',
    title: 'Install the finishing tools',
    shell: 'PowerShell',
    steps: [
      {
        cmd: 'cd ComfyUI-Majoor-VideoTools',
        note: 'Run both installers from the pack root.',
      },
      {
        cmd: 'powershell -ExecutionPolicy Bypass -File .\\scripts\\install_hyperframes.ps1',
        out: [{t: 'hyperframes@0.8.201', kind: 'ok'}, {t: 'gsap@3.15.0', kind: 'ok'}],
        note: 'HyperFrames draws the titles, graphics and kinetic lyrics.',
      },
      {
        cmd: 'powershell -ExecutionPolicy Bypass -File .\\scripts\\install_tone.ps1',
        out: [{t: 'tone@15.1.22', kind: 'ok'}, {t: '30 sound cues synthesized', kind: 'ok'}],
        note: 'Tone builds the sound-effect bank once. No sample pack is downloaded.',
      },
    ],
  },
  {
    id: 'studio',
    step: 'STEP 4',
    title: 'Set up the Studio',
    shell: 'PowerShell',
    steps: [
      {
        cmd: 'git clone https://github.com/MajoorWaldi/HyperKut-Studio "HyperKut Studio"',
        out: [{t: "Cloning into 'HyperKut Studio'...", kind: 'dim'}, {t: 'done.', kind: 'ok'}],
        note: 'The Studio is its own repository, next to the pack modules.',
      },
      {
        cmd: 'cd "HyperKut Studio"; python -m venv .venv',
        note: 'Its Python environment is separate from the engine.',
      },
      {
        cmd: '.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt',
        out: [{t: 'Successfully installed fastapi uvicorn httpx pydantic comfy-sdk ...', kind: 'ok'}],
        note: 'Never mix these packages into ComfyUI.',
      },
      {
        cwd: 'frontend',
        cmd: 'npm ci',
        out: [{t: 'added 312 packages', kind: 'dim'}],
        note: 'Node.js 22 or newer.',
      },
      {
        cwd: 'frontend',
        cmd: 'npm run build',
        out: [{t: 'dist/index.html  built', kind: 'ok'}],
        note: 'The interface is served from frontend/dist.',
      },
    ],
  },
  {
    id: 'start',
    step: 'STEP 5',
    title: 'Start and open',
    shell: 'PowerShell',
    steps: [
      {
        cwd: 'ComfyUI_windows_portable',
        cmd: '.\\run_nvidia_gpu.bat',
        out: [{t: 'Starting server ... To see the GUI go to: http://127.0.0.1:8188', kind: 'ok'}],
        note: 'ComfyUI first, and leave it running.',
      },
      {
        cwd: 'HyperKut Studio',
        cmd: '.\\scripts\\run_studio.ps1',
        out: [
          {t: 'ComfyUI   http://127.0.0.1:8188   healthy', kind: 'ok'},
          {t: 'Studio    http://127.0.0.1:8090   ready', kind: 'ok'},
        ],
        note: 'It finds a free port by itself if one is taken.',
      },
    ],
  },
];

const CPS = 34; // typing speed, characters per second
export const typeFrames = (s: string) => Math.ceil((s.length / CPS) * FPS);

export const stepFrames = (s: Step) => {
  const out = s.out?.length ?? 0;
  return 8 + typeFrames(s.cmd) + 10 + out * 9 + 22;
};

export const sceneFrames = (scene: TerminalScene) => 12 + scene.steps.reduce((n, s) => n + stepFrames(s), 0) + 30;
