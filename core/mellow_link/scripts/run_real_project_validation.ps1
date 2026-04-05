param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [Parameter(Mandatory = $true)]
    [string]$Token,

    [string]$BaseUrl = "http://127.0.0.1:8000",

    [string]$OutputPath = "",

    [switch]$RunQaSmoke
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ScriptRoot = Split-Path -Parent $PSCommandPath

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

function Resolve-OutputPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectId,
        [string]$ProvidedPath
    )

    if ($ProvidedPath) {
        return $ProvidedPath
    }

    $repoRoot = Split-Path -Parent $ScriptRoot
    $outputDir = Join-Path $repoRoot "docs\validation_runs"
    if (-not (Test-Path -LiteralPath $outputDir)) {
        New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
    }
    $dateTag = Get-Date -Format "yyyy-MM-dd"
    return (Join-Path $outputDir "$dateTag-$ProjectId-validation.md")
}

function Join-Lines {
    param(
        [object[]]$Items,

        [string]$Prefix = "- "
    )

    $filtered = @(@($Items) | Where-Object { $_ -and $_.ToString().Trim() })
    if (-not $filtered.Count) {
        return "-"
    }
    return ($filtered | ForEach-Object { "$Prefix$_" }) -join "`r`n"
}

function Build-DecisionLines {
    param(
        [Parameter(Mandatory = $true)]
        $Decisions
    )

    $lines = @()
    foreach ($decision in @($Decisions | Select-Object -First 3)) {
        $decisionId = [string]($decision.decision_id)
        $decisionType = [string]($decision.decision_type)
        $priority = [string]($decision.priority_score)
        $rationale = [string]($decision.rationale)
        $lines += "- $decisionId | type=$decisionType | priority=$priority | rationale=$rationale"
    }
    if (-not $lines.Count) {
        return "-"
    }
    return $lines -join "`r`n"
}

function Get-FirstItem {
    param(
        $Items
    )

    $normalized = @($Items)
    if ($normalized.Count -gt 0) {
        return $normalized[0]
    }
    return $null
}

function Build-ChecklistBlock {
    return @"
### 1. 구조 판단 타당성
- [ ] structural_judgment가 실제 프로젝트 구조 문제와 일치한다.
- [ ] recommended_strategy가 실무적으로 수용 가능하다.
- [ ] top decision 1~3개가 실제 개선 우선순위와 크게 어긋나지 않는다.

### 2. 근거 연결 타당성
- [ ] decision -> issue -> evidence -> score_breakdown 연결이 납득 가능하다.
- [ ] score_breakdown.final_score가 과도하거나 과소하지 않다.
- [ ] explainability가 score와 같은 판단을 설명한다.

### 3. 실행 가능성
- [ ] top execution_stage가 실제 착수 가능하다.
- [ ] 첫 단계 task가 모호하지 않다.
- [ ] risk / verification checkpoint 누락이 없다.

### 4. taxonomy 분리 타당성
- [ ] narrative_axis가 설명 보조로만 동작한다.
- [ ] narrative_axis가 구조 판단을 오염시키지 않는다.
- [ ] primary_judgment 없이도 reviewer가 결과를 이해할 수 있다.

### 5. explanation / Q&A 품질
- [ ] audience가 달라도 fact / score / citation이 바뀌지 않는다.
- [ ] Q&A가 grounding 부족 시 억지로 답하지 않는다.
- [ ] explanation surface가 structural_judgment를 중심으로 보여준다.
"@
}

function Resolve-StructuralJudgment {
    param(
        [Parameter(Mandatory = $true)]
        $ProjectResult,

        [Parameter(Mandatory = $true)]
        $ExplanationResult
    )

    $explanationValue = [string]($ExplanationResult.taxonomy_view.core_judgment.structural_judgment)
    if ($explanationValue.Trim()) {
        return @{ value = $explanationValue.Trim(); source = "explanation.taxonomy_view" }
    }

    $resultValue = [string]($ProjectResult.structural_judgment)
    if ($resultValue.Trim()) {
        return @{ value = $resultValue.Trim(); source = "result.structural_judgment" }
    }

    $decisionSummary = $ProjectResult.authoritative_payload.decision_summary
    $decisions = @($decisionSummary.decisions)
    $topDecision = Get-FirstItem -Items $decisions
    $recommendedStrategy = [string]($decisionSummary.recommended_strategy)
    $topDecisionType = if ($null -ne $topDecision) { [string]$topDecision.decision_type } else { "" }

    if (-not $decisions.Count) {
        return @{ value = "observation_only"; source = "decision_summary_fallback" }
    }
    if ($recommendedStrategy -eq "마이그레이션 고려" -or $topDecisionType -eq "migration_consideration") {
        return @{ value = "migration_consideration"; source = "decision_summary_fallback" }
    }
    if ($recommendedStrategy -eq "재설계 우선" -or $topDecisionType -eq "redesign") {
        return @{ value = "redesign"; source = "decision_summary_fallback" }
    }
    return @{ value = "refactor"; source = "decision_summary_fallback" }
}

function Resolve-NarrativeAxis {
    param(
        [Parameter(Mandatory = $true)]
        $ProjectResult,

        [Parameter(Mandatory = $true)]
        $ExplanationResult
    )

    $explanationValue = [string]($ExplanationResult.taxonomy_view.explanation_context.narrative_axis)
    if ($explanationValue.Trim()) {
        return @{ value = $explanationValue.Trim(); source = "explanation.taxonomy_view" }
    }

    foreach ($candidate in @(
            [string]$ProjectResult.narrative_axis,
            [string]$ProjectResult.template_judgment,
            [string]$ProjectResult.primary_judgment
        )) {
        if ($candidate.Trim()) {
            return @{ value = $candidate.Trim(); source = "result_fallback" }
        }
    }

    return @{ value = "-"; source = "unavailable" }
}

function Resolve-SyntheticSignal {
    param(
        [Parameter(Mandatory = $true)]
        $ProjectResult
    )

    $extensions = $null
    if ($null -ne $ProjectResult.PSObject.Properties["extensions"]) {
        $extensions = $ProjectResult.extensions
    }
    if ($null -ne $extensions -and $null -ne $extensions.decision_governance) {
        $raw = $extensions.decision_governance.synthetic_signal_detected
        if ($null -ne $raw) {
            return @{
                value = [bool]$raw
                source = "result.extensions.decision_governance"
                packager_guard_applied = [bool]$extensions.decision_governance.packager_guard_applied
            }
        }
    }

    $decisionSummary = $ProjectResult.authoritative_payload.decision_summary
    $decisions = @($decisionSummary.decisions)
    if (-not $decisions.Count) {
        return @{
            value = $false
            source = "decision_summary_inference"
            packager_guard_applied = $false
        }
    }

    $diagnosisIssues = @($ProjectResult.authoritative_payload.diagnosis_report.issues)
    $synthetic = $false
    foreach ($decision in $decisions) {
        $decisionType = [string]$decision.decision_type
        $issueIds = @($decision.issue_ids)
        $evidenceIds = @($decision.evidence_ids)
        if (($decisionType -eq "migration_consideration" -and $issueIds.Count -eq 0 -and $evidenceIds.Count -eq 0) `
            -or ($decisionType -eq "migration_consideration" -and $diagnosisIssues.Count -eq 0)) {
            $synthetic = $true
            break
        }
    }

    return @{
        value = [bool]$synthetic
        source = "decision_summary_inference"
        packager_guard_applied = $false
    }
}

function Resolve-ReviewDiffMarkdown {
    param(
        [Parameter(Mandatory = $true)]
        $ProjectResult,

        [Parameter(Mandatory = $true)]
        $ResolvedSyntheticSignal
    )

    $extensions = $null
    if ($null -ne $ProjectResult.PSObject.Properties["extensions"]) {
        $extensions = $ProjectResult.extensions
    }
    if ($null -ne $extensions -and $null -ne $extensions.review_diff -and $null -ne $extensions.review_diff.markdown) {
        $value = [string]$extensions.review_diff.markdown
        if ($value.Trim()) {
            return $value.Trim()
        }
    }
    return (Build-ReviewDiffMarkdownFallback -ProjectResult $ProjectResult -ResolvedSyntheticSignal $ResolvedSyntheticSignal)
}

function Build-ReviewDiffMarkdownFallback {
    param(
        [Parameter(Mandatory = $true)]
        $ProjectResult,

        [Parameter(Mandatory = $true)]
        $ResolvedSyntheticSignal
    )

    $structure = $ProjectResult.authoritative_payload.structure_snapshot
    $diagnosis = $ProjectResult.authoritative_payload.diagnosis_report
    $decisionSummary = $ProjectResult.authoritative_payload.decision_summary
    $appendix = $ProjectResult.authoritative_payload.appendix

    $components = @($structure.components)
    $dependencies = @($structure.dependencies)
    $issues = @($diagnosis.issues)
    $evidenceIndex = @($appendix.evidence_index)
    $decisions = @($decisionSummary.decisions)

    $componentAliasMap = @{}
    $componentIndex = 1
    foreach ($component in $components) {
        $componentAliasMap[[string]$component.component_id] = "Component{0:D2}" -f $componentIndex
        $componentIndex += 1
    }

    $componentLines = @()
    foreach ($component in $components | Select-Object -First 8) {
        $responsibilities = @($component.responsibility_families) -join ", "
        if (-not $responsibilities) {
            $responsibilities = "-"
        }
        $componentLines += "- {0} [{1}] responsibilities={2}" -f $componentAliasMap[[string]$component.component_id], ([string]$component.layer), $responsibilities
    }
    if (-not $componentLines.Count) {
        $componentLines += "- component summary unavailable"
    }

    $dependencyLines = @()
    foreach ($dependency in $dependencies | Select-Object -First 8) {
        $fromAlias = $componentAliasMap[[string]$dependency.from_component]
        if (-not $fromAlias) {
            $fromAlias = "ComponentX"
        }
        $toAlias = $componentAliasMap[[string]$dependency.to_component]
        if (-not $toAlias) {
            $toAlias = "ComponentY"
        }
        $dependencyLines += "  - {0} -> {1} ({2})" -f $fromAlias, $toAlias, ([string]$dependency.dependency_type)
    }
    if (-not $dependencyLines.Count) {
        $dependencyLines += "  - dependency summary unavailable"
    }

    $fingerprintGroups = $evidenceIndex | Group-Object fingerprint | Where-Object { $_.Count -ge 2 } | Select-Object -First 5
    $evidenceLines = @()
    $fingerprintIndex = 1
    foreach ($group in $fingerprintGroups) {
        $evidenceLines += "- RuleFragment{0:D2}:" -f $fingerprintIndex
        foreach ($item in @($group.Group) | Select-Object -First 5) {
            $evidenceLines += "  - {0}:{1}" -f ([string]$item.asset_name), ([string]$item.locator)
        }
        $fingerprintIndex += 1
    }
    if (-not $evidenceLines.Count) {
        $leakIssues = @($issues | Where-Object { $_.detector_id -match 'leak|scatter|coupling|boundary|duplicate' } | Select-Object -First 5)
        foreach ($issue in $leakIssues) {
            $evidenceLines += "- detector={0} issue_id={1}" -f ([string]$issue.detector_id), ([string]$issue.issue_id)
        }
    }
    if (-not $evidenceLines.Count) {
        $evidenceLines += "- evidence summary unavailable"
    }

    $decisionLines = @()
    if ($decisions.Count) {
        $decisionLines += "- allowed:"
        foreach ($decision in $decisions | Select-Object -First 5) {
            $decisionLines += "  - {0} ({1}) priority={2} issue_count={3} evidence_count={4}" -f ([string]$decision.decision_type), ([string]$decision.decision_id), ([string]$decision.priority_score), (@($decision.issue_ids).Count), (@($decision.evidence_ids).Count)
        }
    }
    else {
        $decisionLines += "- allowed: none"
    }

    if ($ResolvedSyntheticSignal.value) {
        $decisionLines += "- blocked:"
        $decisionLines += "  - migration_consideration"
        $decisionLines += "- block reason:"
        $decisionLines += "  - no asset-derived migration evidence"
        $decisionLines += "  - issue_ids = []"
        $decisionLines += "  - evidence_ids = []"
        $decisionLines += "  - goal wording only (contamination)"
    }
    else {
        $decisionLines += "- blocked: none"
    }
    $decisionLines += "- synthetic_signal_detected: $($ResolvedSyntheticSignal.value)"

    return @"
## Structural Evidence Diff

### Structural View
$(($componentLines + @('- dependency_flows:') + $dependencyLines) -join "`r`n")

### Evidence View
$(($evidenceLines) -join "`r`n")

### Decision View
$(($decisionLines) -join "`r`n")
"@.Trim()
}

function Build-MarkdownReport {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectId,

        [Parameter(Mandatory = $true)]
        $ProjectResult,

        [Parameter(Mandatory = $true)]
        $ExplanationResult,

        [Parameter(Mandatory = $true)]
        $ResolvedStructuralJudgment,

        [Parameter(Mandatory = $true)]
        $ResolvedNarrativeAxis,

        [Parameter(Mandatory = $true)]
        $ResolvedSyntheticSignal,

        [Parameter(Mandatory = $true)]
        [string]$QaSummary,

        [string]$ReviewDiffMarkdown = ""
    )

    $project = $ProjectResult.project
    $authoritative = $ProjectResult.authoritative_payload
    $decisionSummary = $authoritative.decision_summary
    $diagnosisReport = $authoritative.diagnosis_report
    $improvement = $authoritative.improvement_plan_bundle
    $topDecision = Get-FirstItem -Items $decisionSummary.decisions
    $topStage = Get-FirstItem -Items $improvement.execution_stages
    $topIssue = Get-FirstItem -Items $diagnosisReport.issues
    $taxonomyView = $ExplanationResult.taxonomy_view
    $recommendedOptionName = if ($null -ne $ProjectResult.recommended_option) { [string]$ProjectResult.recommended_option.name } else { "-" }

    $topScore = if ($null -ne $topDecision) { [string]$topDecision.priority_score } else { "-" }
    $topDecisionType = if ($null -ne $topDecision) { [string]$topDecision.decision_type } else { "-" }
    $topStageTitle = if ($null -ne $topStage) { [string]$topStage.title } else { "-" }
    $topIssueSummary = if ($null -ne $topIssue) { [string]$topIssue.summary } else { "-" }
    $topIssueDetectors = @($diagnosisReport.issues | Select-Object -First 5 | ForEach-Object { [string]$_.detector_id })
    $reviewDiffSection = ""
    if ($ReviewDiffMarkdown.Trim()) {
        $reviewDiffSection = "## Review Diff`r`n$ReviewDiffMarkdown"
    }

    return @"
# Real Project Validation Record

기준 문서: refactoring_support_engine.md  
project_id: $ProjectId

## 기본 정보
- project_name: $($project.project_name)
- client_name: $($project.client_name)
- review_date: $(Get-Date -Format "yyyy-MM-dd")
- reviewer: [작성 필요]
- project_type: [refactor-centered | redesign-centered]

## Core Judgment
- structural_judgment: $($ResolvedStructuralJudgment.value)
- structural_judgment_source: $($ResolvedStructuralJudgment.source)
- recommended_strategy: $($taxonomyView.core_judgment.recommended_strategy)
- top_decision_type: $($taxonomyView.core_judgment.top_decision_type)
- top_priority_score: $topScore
- narrative_axis: $($ResolvedNarrativeAxis.value)
- narrative_axis_source: $($ResolvedNarrativeAxis.source)

## Top Evidence Snapshot
- top_issue_summary: $topIssueSummary
- top_issue_detectors:
$(Join-Lines -Items $topIssueDetectors)
- score_breakdown:
  - severity_component: $($taxonomyView.evidence_view.score_breakdown.severity_component)
  - blast_radius_component: $($taxonomyView.evidence_view.score_breakdown.blast_radius_component)
  - effort_component: $($taxonomyView.evidence_view.score_breakdown.effort_component)
  - confidence_bonus: $($taxonomyView.evidence_view.score_breakdown.confidence_bonus)
  - detector_weight: $($taxonomyView.evidence_view.score_breakdown.detector_weight)
  - hotspot_bonus: $($taxonomyView.evidence_view.score_breakdown.hotspot_bonus)
  - multi_slice_bonus: $($taxonomyView.evidence_view.score_breakdown.multi_slice_bonus)
  - redesign_bonus: $($taxonomyView.evidence_view.score_breakdown.redesign_bonus)
  - final_score: $($taxonomyView.evidence_view.score_breakdown.final_score)

## Execution Snapshot
- top_execution_stage: $topStageTitle
- execution_stage_count: $(@($improvement.execution_stages).Count)
- recommended_option: $recommendedOptionName

## Decision Summary Snapshot
$(Build-DecisionLines -Decisions $decisionSummary.decisions)

## Reviewer Verdict
- reviewer_verdict: [valid | partially_valid | invalid]
- taxonomy_confusion: [none | minor | major]
- correction_required: [yes | no]

## Validation Checklist
$(Build-ChecklistBlock)

## Q&A Smoke Summary
$QaSummary

$reviewDiffSection

## Enforcement Record
- synthetic_signal_detected: $($ResolvedSyntheticSignal.value)
- synthetic_signal_source: $($ResolvedSyntheticSignal.source)
- ResultPackager 2차 검증 확인: $(if ($ResolvedSyntheticSignal.packager_guard_applied) { "applied" } else { "not_detected" })
- Validation 기록 완료 여부: yes

## Notes
- taxonomy_confusion_notes:
- correction_notes:
- product_surface_change_needed:
- core_engine_change_needed: [yes | no]
"@
}

$headers = @{
    "Authorization" = "Bearer $Token"
    "Accept" = "application/json"
}

$resultUri = "$BaseUrl/projects/$ProjectId/result?format=json"
$explanationUri = "$BaseUrl/projects/$ProjectId/result/explanation?audience=manager"

$resultPackage = Invoke-ApiGet -Uri $resultUri -Headers $headers
$explanation = Invoke-ApiGet -Uri $explanationUri -Headers $headers
$resolvedStructuralJudgment = Resolve-StructuralJudgment -ProjectResult $resultPackage -ExplanationResult $explanation
$resolvedNarrativeAxis = Resolve-NarrativeAxis -ProjectResult $resultPackage -ExplanationResult $explanation
$resolvedSyntheticSignal = Resolve-SyntheticSignal -ProjectResult $resultPackage
$reviewDiffMarkdown = Resolve-ReviewDiffMarkdown -ProjectResult $resultPackage -ResolvedSyntheticSignal $resolvedSyntheticSignal

Assert-True -Condition ([bool]$explanation.taxonomy_view.core_judgment.recommended_strategy) -Message "taxonomy_view.core_judgment.recommended_strategy is required"
Assert-True -Condition ([bool]$resolvedStructuralJudgment.value) -Message "resolved structural_judgment is required"
Assert-True -Condition ([bool]$resolvedNarrativeAxis.value) -Message "resolved narrative_axis is required"

$qaSummary = "- skipped"
if ($RunQaSmoke) {
    $qaQuestions = @(
        "왜 이게 권장 전략이야?",
        "왜 이게 우선순위가 높아?",
        "첫 단계에서 정확히 뭘 해야 해?"
    )
    $qaLines = @()
    foreach ($question in $qaQuestions) {
        $response = Invoke-ApiPost -Uri "$BaseUrl/projects/$ProjectId/result/qa" -Headers $headers -Body @{
            question = $question
            audience = "manager"
        }
        $qaLines += "- question: $question"
        $qaLines += "  - insufficient_grounding: $($response.insufficient_grounding)"
        $qaLines += "  - referenced_sections: $((@($response.referenced_sections) -join ', '))"
        $qaLines += "  - citation_count: $(@($response.citations).Count)"
    }
    $qaSummary = $qaLines -join "`r`n"
}

$resolvedOutputPath = Resolve-OutputPath -ProjectId $ProjectId -ProvidedPath $OutputPath
$report = Build-MarkdownReport -ProjectId $ProjectId -ProjectResult $resultPackage -ExplanationResult $explanation -ResolvedStructuralJudgment $resolvedStructuralJudgment -ResolvedNarrativeAxis $resolvedNarrativeAxis -ResolvedSyntheticSignal $resolvedSyntheticSignal -QaSummary $qaSummary -ReviewDiffMarkdown $reviewDiffMarkdown
Set-Content -LiteralPath $resolvedOutputPath -Value $report -Encoding UTF8

Write-Host "Validation record written:" -ForegroundColor Cyan
Write-Host $resolvedOutputPath -ForegroundColor Green
