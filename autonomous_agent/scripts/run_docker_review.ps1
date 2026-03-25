param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot "runtime-data"
$RuntimeDirs = @("reports", "archive", "history", "logs", "generated_skills")
$RuntimeFiles = @("agent_state.json", "pending_approvals.json", "agent.log")

if (-not (Test-Path $RuntimeRoot)) {
    New-Item -ItemType Directory -Path $RuntimeRoot | Out-Null
}

foreach ($dir in $RuntimeDirs) {
    $path = Join-Path $RuntimeRoot $dir
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path | Out-Null
    }
}

foreach ($file in $RuntimeFiles) {
    $path = Join-Path $RuntimeRoot $file
    if (-not (Test-Path $path)) {
        Set-Content -Path $path -Value "" -Encoding UTF8
    }
}

if (-not $CommandArgs -or $CommandArgs.Count -eq 0) {
    $CommandArgs = @("inspect_storage.py")
}

docker compose run --rm agent-review @CommandArgs
