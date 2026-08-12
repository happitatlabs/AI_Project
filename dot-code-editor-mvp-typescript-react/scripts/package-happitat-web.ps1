$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$OutputRoot = Join-Path $ProjectRoot "web-output"
$ArchivePath = Join-Path $OutputRoot "dot-code-editor-happitat-web.zip"

Set-Location $ProjectRoot
npm run build:happitat

if (-not (Test-Path $OutputRoot)) {
  New-Item -ItemType Directory -Path $OutputRoot | Out-Null
}

if (Test-Path $ArchivePath) {
  Remove-Item -LiteralPath $ArchivePath -Force
}

Compress-Archive -Path (Join-Path $ProjectRoot "dist\*") -DestinationPath $ArchivePath -Force
Write-Host "Web package created: $ArchivePath"
