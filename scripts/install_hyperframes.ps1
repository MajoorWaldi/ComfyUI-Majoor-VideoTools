$ErrorActionPreference = 'Stop'
$runtimeRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'runtime\hyperframes'
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22 or newer first.' }
$nodeMajor = [int]((node --version).TrimStart('v').Split('.')[0])
if ($nodeMajor -lt 22) { throw 'Node.js 22 or newer is required.' }
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
npm.cmd install --prefix $runtimeRoot --save-exact hyperframes@0.8.201 gsap@3.15.0 lottie-web@5.12.2 --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Optional HyperFrames dependencies could not be installed.' }
Write-Host "HyperFrames installed in $runtimeRoot. FFmpeg and local Chrome must be available. Restart ComfyUI to register the new node."
