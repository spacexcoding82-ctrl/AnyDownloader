$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskFFmpeg = Get-ChildItem -LiteralPath (Join-Path $taskRoot '.tools') -Filter ffmpeg.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($taskFFmpeg) { $env:FFMPEG_LOCATION = $taskFFmpeg.DirectoryName }
if (-not (Test-Path -LiteralPath 'frontend\dist\client\index.html')) { throw 'Build the frontend first: cd frontend; npm ci; npm run build' }
& '.\.venv\Scripts\python.exe' -m backend.serve
