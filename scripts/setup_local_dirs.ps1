$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "root: $root"

@(
  "logs",
  "models",
  "audio_outputs"
) | ForEach-Object {
  $p = Join-Path $root $_
  if (-not (Test-Path $p)) {
    New-Item -ItemType Directory -Path $p | Out-Null
    Write-Host "created: $p"
  }
}

$envExample = Join-Path $root ".env.example"
$envFile = Join-Path $root ".env"
if ((Test-Path $envExample) -and (-not (Test-Path $envFile))) {
  Copy-Item $envExample $envFile
  Write-Host "created: $envFile (from .env.example)"
}

Write-Host "done"
