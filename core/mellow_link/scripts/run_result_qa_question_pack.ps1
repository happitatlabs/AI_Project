param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [Parameter(Mandatory = $true)]
    [string]$Token,

    [string]$BaseUrl = "http://127.0.0.1:8000",

    [string]$QuestionPackPath = "",

    [string]$SampleName = "",

    [switch]$SkipExplanation,

    [switch]$SkipQa
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-True {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Condition,

        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Normalize-Json {
    param(
        [Parameter(Mandatory = $true)]
        $Value
    )

    return ($Value | ConvertTo-Json -Depth 30 -Compress)
}

function Invoke-ApiGet {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [Parameter(Mandatory = $true)]
        [hashtable]$Headers
    )

    return Invoke-RestMethod -Method Get -Uri $Uri -Headers $Headers -ContentType "application/json"
}

function Invoke-ApiPost {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [Parameter(Mandatory = $true)]
        [hashtable]$Headers,

        [Parameter(Mandatory = $true)]
        $Body
    )

    $jsonBody = $Body | ConvertTo-Json -Depth 30 -Compress
    return Invoke-RestMethod -Method Post -Uri $Uri -Headers $Headers -ContentType "application/json" -Body $jsonBody
}

function Get-SummaryCard {
    param(
        [Parameter(Mandatory = $true)]
        $Response,

        [Parameter(Mandatory = $true)]
        [string]$CardKey
    )

    return @($Response.summary_cards | Where-Object { $_.card_key -eq $CardKey })[0]
}

function Resolve-QuestionPackPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProvidedPath
    )

    if ($ProvidedPath) {
        return (Resolve-Path -LiteralPath $ProvidedPath).Path
    }

    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $repoRoot = Split-Path -Parent $scriptDir
    $defaultPath = Join-Path $repoRoot "modules\rebuild_assistant\samples\_templates\phase3_qa_question_pack.json"
    return (Resolve-Path -LiteralPath $defaultPath).Path
}

$resolvedPackPath = Resolve-QuestionPackPath -ProvidedPath $QuestionPackPath
$questionPack = Get-Content -Raw -Path $resolvedPackPath | ConvertFrom-Json -Depth 30

$headers = @{
    "Authorization" = "Bearer $Token"
    "Accept" = "application/json"
}

$resultUri = "$BaseUrl/projects/$ProjectId/result?format=json"
$resultPackage = Invoke-ApiGet -Uri $resultUri -Headers $headers
$authoritativePayload = $resultPackage.authoritative_payload
$topDecision = $null
$topStage = $null

if ($authoritativePayload.decision_summary -and $authoritativePayload.decision_summary.decisions) {
    $topDecision = @($authoritativePayload.decision_summary.decisions)[0]
}
if ($authoritativePayload.improvement_plan_bundle -and $authoritativePayload.improvement_plan_bundle.execution_stages) {
    $topStage = @($authoritativePayload.improvement_plan_bundle.execution_stages)[0]
}

Write-Host "ProjectId: $ProjectId" -ForegroundColor Cyan
Write-Host "Question pack: $resolvedPackPath" -ForegroundColor Cyan
Write-Host "Recommended strategy: $($authoritativePayload.decision_summary.recommended_strategy)" -ForegroundColor Cyan

if (-not $SkipExplanation) {
    Write-Host ""
    Write-Host "[Explanation Audience Invariance]" -ForegroundColor Yellow

    $explanations = @{}
    foreach ($audience in @("developer", "manager", "client")) {
        $uri = "$BaseUrl/projects/$ProjectId/result/explanation?audience=$audience"
        $response = Invoke-ApiGet -Uri $uri -Headers $headers
        $explanations[$audience] = $response
        Write-Host ("- audience={0} summary_cards={1} section_views={2}" -f $audience, @($response.summary_cards).Count, @($response.section_views).Count)
        Assert-True -Condition (-not [bool]$response.provenance.delivery_mode_applied) -Message "delivery_mode_applied must stay false in first Phase 3 implementation"
    }

    foreach ($cardKey in @("strategy", "priority", "execution", "scope")) {
        $developerCard = Get-SummaryCard -Response $explanations["developer"] -CardKey $CardKey
        $managerCard = Get-SummaryCard -Response $explanations["manager"] -CardKey $CardKey
        $clientCard = Get-SummaryCard -Response $explanations["client"] -CardKey $CardKey
        Assert-True -Condition ((Normalize-Json $developerCard.citations) -eq (Normalize-Json $managerCard.citations)) -Message "Explanation citations drifted for card '$CardKey' between developer and manager"
        Assert-True -Condition ((Normalize-Json $managerCard.citations) -eq (Normalize-Json $clientCard.citations)) -Message "Explanation citations drifted for card '$CardKey' between manager and client"
    }

    if ($topDecision) {
        $priorityScore = [string]$topDecision.priority_score
        foreach ($audience in @("developer", "manager", "client")) {
            $card = Get-SummaryCard -Response $explanations[$audience] -CardKey "priority"
            Assert-True -Condition ($card.body -like "*$priorityScore*") -Message "Explanation priority card for '$audience' does not contain top priority score $priorityScore"
        }
    }

    if ($topStage) {
        $stageTitle = [string]$topStage.title
        foreach ($audience in @("developer", "manager", "client")) {
            $card = Get-SummaryCard -Response $explanations[$audience] -CardKey "execution"
            Assert-True -Condition ($card.body -like "*$stageTitle*") -Message "Explanation execution card for '$audience' does not contain top stage title '$stageTitle'"
        }
    }
}

if (-not $SkipQa) {
    Write-Host ""
    Write-Host "[Q&A Audience Invariance]" -ForegroundColor Yellow

    foreach ($check in @($questionPack.common_audience_invariance_checks)) {
        Write-Host ("- check={0}" -f $check.id)
        $responses = @{}
        foreach ($audience in @($check.audiences)) {
            $responses[$audience] = Invoke-ApiPost -Uri "$BaseUrl/projects/$ProjectId/result/qa" -Headers $headers -Body @{
                question = $check.question
                audience = $audience
            }
            Write-Host ("  audience={0} mode={1} citations={2} sections={3}" -f $audience, $responses[$audience].answer_mode, @($responses[$audience].citations).Count, (Normalize-Json $responses[$audience].referenced_sections))
        }

        Assert-True -Condition ((Normalize-Json $responses["developer"].citations) -eq (Normalize-Json $responses["manager"].citations)) -Message "Q&A citations drifted for check '$($check.id)' between developer and manager"
        Assert-True -Condition ((Normalize-Json $responses["manager"].citations) -eq (Normalize-Json $responses["client"].citations)) -Message "Q&A citations drifted for check '$($check.id)' between manager and client"
        Assert-True -Condition ((Normalize-Json $responses["developer"].referenced_sections) -eq (Normalize-Json $responses["manager"].referenced_sections)) -Message "Q&A referenced_sections drifted for check '$($check.id)' between developer and manager"
        Assert-True -Condition ((Normalize-Json $responses["manager"].referenced_sections) -eq (Normalize-Json $responses["client"].referenced_sections)) -Message "Q&A referenced_sections drifted for check '$($check.id)' between manager and client"

        if ($check.id -eq "priority-invariance" -and $topDecision) {
            $priorityScore = [string]$topDecision.priority_score
            foreach ($audience in @("developer", "manager", "client")) {
                Assert-True -Condition ($responses[$audience].answer -like "*$priorityScore*") -Message "Q&A priority answer for '$audience' does not contain top priority score $priorityScore"
            }
        }

        if ($check.id -eq "execution-invariance" -and $topStage) {
            $stageTitle = [string]$topStage.title
            foreach ($audience in @("developer", "manager", "client")) {
                Assert-True -Condition ($responses[$audience].answer -like "*$stageTitle*") -Message "Q&A execution answer for '$audience' does not contain top stage title '$stageTitle'"
            }
        }
    }

    if ($SampleName) {
        Write-Host ""
        Write-Host "[Sample-Specific Questions]" -ForegroundColor Yellow
        $sampleConfig = @($questionPack.sample_question_sets | Where-Object { $_.sample_name -eq $SampleName })[0]
        Assert-True -Condition ([bool]$sampleConfig) -Message "SampleName '$SampleName' was not found in question pack"

        foreach ($item in @($sampleConfig.questions)) {
            $response = Invoke-ApiPost -Uri "$BaseUrl/projects/$ProjectId/result/qa" -Headers $headers -Body @{
                question = $item.question
                audience = $item.audience
            }
            $expectInsufficient = [bool]$item.expect_insufficient_grounding
            Write-Host ("- id={0} audience={1} sections={2} citations={3} insufficient={4}" -f $item.id, $item.audience, (Normalize-Json $response.referenced_sections), @($response.citations).Count, $response.insufficient_grounding)
            Assert-True -Condition ((Normalize-Json $response.referenced_sections) -eq (Normalize-Json $item.expected_referenced_sections)) -Message "Referenced sections mismatch for sample question '$($item.id)'"
            Assert-True -Condition ([bool]$response.insufficient_grounding -eq $expectInsufficient) -Message "insufficient_grounding mismatch for sample question '$($item.id)'"
            if ([bool]$item.expect_citations) {
                Assert-True -Condition (@($response.citations).Count -gt 0) -Message "Expected citations for sample question '$($item.id)'"
            } else {
                Assert-True -Condition (@($response.citations).Count -eq 0) -Message "Did not expect citations for sample question '$($item.id)'"
            }
        }
    }
}

Write-Host ""
Write-Host "Smoke check passed." -ForegroundColor Green
