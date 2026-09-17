$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskTools = Join-Path $taskRoot '.tools'
$taskArchive = Join-Path $taskTools 'ffmpeg-release-essentials.zip'
New-Item -ItemType Directory -Force -Path $taskTools | Out-Null
$taskBase = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
Write-Host 'Downloading FFmpeg Windows essentials from the distributor linked by ffmpeg.org...'
Invoke-WebRequest -Uri $taskBase -OutFile $taskArchive -UseBasicParsing
$taskExpected = ((Invoke-WebRequest -Uri ($taskBase + '.sha256') -UseBasicParsing).Content.Trim() -split '\s+')[0]
$taskActual = (Get-FileHash -LiteralPath $taskArchive -Algorithm SHA256).Hash
if ($taskActual -ne $taskExpected) { throw 'FFmpeg checksum mismatch. Archive was not extracted.' }
Expand-Archive -LiteralPath $taskArchive -DestinationPath $taskTools -Force
$taskFFmpeg = Get-ChildItem -LiteralPath $taskTools -Filter ffmpeg.exe -Recurse | Select-Object -First 1
if (-not $taskFFmpeg) { throw 'FFmpeg executable not found in archive.' }
Write-Host ('Media tools ready in ' + $taskFFmpeg.DirectoryName)
