$ErrorActionPreference='Stop'
$pack=Split-Path $PSScriptRoot -Parent
$runtime=Join-Path $pack 'runtime\tonejs'
if(-not(Get-Command node -ErrorAction SilentlyContinue)){throw 'Node.js 22+ is required'}
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
npm.cmd install --prefix $runtime --save-exact tone@15.1.22 puppeteer-core@25.16.0 --no-audit --no-fund
if($LASTEXITCODE -ne 0){throw 'Tone.js installation failed'}
node (Join-Path $PSScriptRoot 'render_tone_bank.mjs')
if($LASTEXITCODE -ne 0){throw 'Tone.js offline sound rendering failed'}
Write-Host 'Tone.js ready: 30 local synthesized cues, including stereo transitions. Restart ComfyUI.'
