param(
    [switch]$CheckReport
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot "runtime-data"
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"

function Write-Step {
    param(
        [string]$Message
    )
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail-Step {
    param(
        [string]$StepName,
        [string]$Message
    )
    Write-Host ""
    Write-Host "[FAIL] $StepName" -ForegroundColor Red
    Write-Host $Message -ForegroundColor Yellow
    exit 1
}

function Invoke-ComposeStep {
    param(
        [string]$StepName,
        [string[]]$Command
    )

    Write-Step $StepName
    Write-Host ("docker " + ($Command -join " ")) -ForegroundColor DarkGray
    & docker @Command
    if ($LASTEXITCODE -ne 0) {
        Fail-Step $StepName "docker 명령이 실패했습니다. exit_code=$LASTEXITCODE"
    }
}

function Invoke-ComposeStepCapture {
    param(
        [string]$StepName,
        [string[]]$Command
    )

    Write-Step $StepName
    Write-Host ("docker " + ($Command -join " ")) -ForegroundColor DarkGray
    $output = & docker @Command 2>&1
    $exitCode = $LASTEXITCODE
    if ($output) {
        $output | ForEach-Object { Write-Host $_ }
    }
    if ($exitCode -ne 0) {
        Fail-Step $StepName "docker 명령이 실패했습니다. exit_code=$exitCode"
    }
    return ($output -join [Environment]::NewLine)
}

function Get-InspectSummaryValue {
    param(
        [string]$Text,
        [string]$FieldName
    )

    $pattern = "(?m)^- " + [regex]::Escape($FieldName) + ": (.+)$"
    $match = [regex]::Match($Text, $pattern)
    if ($match.Success) {
        return $match.Groups[1].Value.Trim()
    }
    return "unknown"
}

function Ensure-RuntimeData {
    Write-Step "runtime-data 초기화"

    $runtimeDirs = @(
        "reports",
        "archive",
        "history",
        "logs",
        "generated_skills"
    )

    $jsonFiles = @{
        "agent_state.json" = "{}"
        "pending_approvals.json" = "[]"
    }

    if (-not (Test-Path $RuntimeRoot)) {
        New-Item -ItemType Directory -Path $RuntimeRoot | Out-Null
    }

    foreach ($dir in $runtimeDirs) {
        $path = Join-Path $RuntimeRoot $dir
        if (-not (Test-Path $path)) {
            New-Item -ItemType Directory -Path $path | Out-Null
        }
    }

    foreach ($file in $jsonFiles.Keys) {
        $path = Join-Path $RuntimeRoot $file
        if (-not (Test-Path $path)) {
            Set-Content -Path $path -Value $jsonFiles[$file] -Encoding UTF8
            continue
        }

        try {
            $raw = Get-Content -Path $path -Raw -ErrorAction Stop
            if ([string]::IsNullOrWhiteSpace($raw)) {
                Set-Content -Path $path -Value $jsonFiles[$file] -Encoding UTF8
            } else {
                $null = $raw | ConvertFrom-Json -ErrorAction Stop
            }
        } catch {
            Fail-Step "runtime-data 초기화" "$file 이(가) 유효한 JSON이 아닙니다: $($_.Exception.Message)"
        }
    }

    $logPath = Join-Path $RuntimeRoot "agent.log"
    if (-not (Test-Path $logPath)) {
        Set-Content -Path $logPath -Value "" -Encoding UTF8
    }

    Write-Host "runtime-data 준비 완료: $RuntimeRoot" -ForegroundColor Green
}

function Assert-ComposeExists {
    if (-not (Test-Path $ComposeFile)) {
        Fail-Step "사전 확인" "docker-compose.yml 을 찾을 수 없습니다: $ComposeFile"
    }
}

function Assert-DockerAvailable {
    Write-Step "docker 환경 확인"
    & docker compose version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Fail-Step "docker 환경 확인" "docker compose 를 사용할 수 없습니다."
    }
    Write-Host "docker compose 사용 가능" -ForegroundColor Green
}

function Invoke-ReviewShowIfAvailable {
    $approvalPath = Join-Path $RuntimeRoot "pending_approvals.json"
    $entries = @()

    try {
        $entries = Get-Content -Path $approvalPath -Raw | ConvertFrom-Json
    } catch {
        Fail-Step "review_pending show 검사" "pending_approvals.json 읽기 실패: $($_.Exception.Message)"
    }

    if ($null -eq $entries) {
        $entries = @()
    }
    if ($entries -isnot [System.Collections.IEnumerable] -or $entries -is [string]) {
        $entries = @($entries)
    }

    if ($entries.Count -lt 1) {
        Write-Step "review_pending.py show 0"
        Write-Host "pending approval 항목이 없어 show 0 검증은 건너뜁니다." -ForegroundColor Yellow
        return
    }

    Invoke-ComposeStep "review_pending.py show 0 실행" @("compose", "run", "--rm", "agent-review", "review_pending.py", "show", "0")
}

Assert-ComposeExists
Assert-DockerAvailable
Ensure-RuntimeData

Invoke-ComposeStep "agent-test 실행" @("compose", "run", "--rm", "agent-test")
$inspectOutput = Invoke-ComposeStepCapture "inspect_storage.py 실행" @("compose", "run", "--rm", "agent-review")
Invoke-ComposeStep "review_pending.py list 실행" @("compose", "run", "--rm", "agent-review", "review_pending.py", "list")
Invoke-ReviewShowIfAvailable

if ($CheckReport) {
    Invoke-ComposeStep "agent-report 실행" @("compose", "run", "--rm", "agent-report")
}

Write-Host ""
Write-Host "[OK] Docker 1차 검증 완료" -ForegroundColor Green
Write-Host "검증 대상:" -ForegroundColor Cyan
Write-Host "- agent-test"
Write-Host "- inspect_storage.py"
Write-Host "- review_pending.py list"
if ($CheckReport) {
    Write-Host "- agent-report"
}
# baseline 요약 필드 의미:
# - baseline_status: 현재 risk delta 비교 기준선이 있는지/신선한지 상태
# - baseline_reason: baseline_status가 그렇게 판정된 이유 (예: fresh_snapshot, initial_scan)
# - high_risk_delta: baseline 대비 HIGH risk 경로 수 증감
# - new_high_risk_paths: baseline 이후 새로 HIGH로 잡힌 경로 목록
$baselineStatus = Get-InspectSummaryValue -Text $inspectOutput -FieldName 'baseline_status'
$highRiskDelta = Get-InspectSummaryValue -Text $inspectOutput -FieldName 'high_risk_delta'
Write-Host "Baseline 요약:" -ForegroundColor Cyan
Write-Host "- baseline_status: $baselineStatus"
Write-Host "- baseline_reason: $(Get-InspectSummaryValue -Text $inspectOutput -FieldName 'baseline_reason')"
Write-Host "- high_risk_delta: $highRiskDelta"
Write-Host "- new_high_risk_paths: $(Get-InspectSummaryValue -Text $inspectOutput -FieldName 'new_high_risk_paths')"
if ($baselineStatus -eq "missing") {
    Write-Host "NEXT: create baseline"
} elseif ([int]$highRiskDelta -ne 0) {
    Write-Host "NEXT: review changed high-risk paths"
} else {
    Write-Host "NEXT: continue monitoring"
}
