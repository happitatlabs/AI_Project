from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.anonymization import (
    AnonymizationAsset,
    AnonymizationRunRequest,
    AnonymizationService,
)
from mellow_link.services.rag_service import extract_text_from_file
from mellow_link.services.refactoring_support_engine.analysis_context_builder import AnalysisContextBuilder

SAMPLES_ROOT = (
    Path(__file__).resolve().parents[1]
    / "modules"
    / "rebuild_assistant"
    / "samples"
    / "08_consulting_output_reference"
    / "assets"
)
REPORT_PATH = Path(__file__).resolve().parent / "output" / "ppt_regression_report.json"
PPT_EXTENSIONS = {".ppt", ".pptx"}
DOMAIN_POLLUTION_TERMS = (
    ("product_domain_pollution", "product 기능", "product"),
    ("save_validation_pollution", "저장 전 검증", "저장 전 검증"),
    ("parameter_validation_pollution", "파라미터 검증", "파라미터 검증"),
    ("api_validation_pollution", "api validation", "api validation"),
    ("sql_parameter_pollution", "sql 파라미터", "sql 파라미터"),
)
SENSITIVE_LABEL_PATTERN = re.compile(
    r"^\s*-\s*(?:고객사|고객명|기관명|기관|회사명|회사|수행사|담당자|작성자|프로젝트명|사업명|계약명)\s*[:：]\s*(?P<value>.+?)\s*$"
)
GENERIC_SENSITIVE_VALUES = {"-", "[NO_EXTRACTABLE_TEXT]"}


@dataclass(frozen=True)
class ExpectedDomainProfile:
    profile_id: str
    keywords: tuple[str, ...]
    min_result_hits: int = 2


OO_MILK_PROFILE = ExpectedDomainProfile(
    profile_id="oo_milk_costing",
    keywords=("원가", "배부", "재료비", "노무비", "제조경비", "손익"),
    min_result_hits=2,
)
BPR_ISMP_PROFILE = ExpectedDomainProfile(
    profile_id="bpr_ismp",
    keywords=("업무프로세스", "통합재무", "인적자원", "기금", "이행계획", "변화관리", "요구사항"),
    min_result_hits=2,
)
WATERWORKS_PROFILE = ExpectedDomainProfile(
    profile_id="waterworks_proposal",
    keywords=("수용가", "민원", "요금", "자재", "자산", "예산", "회계"),
    min_result_hits=2,
)
MARITIME_PROFILE = ExpectedDomainProfile(
    profile_id="maritime_biz",
    keywords=("선박", "영업", "운항", "장비", "재무", "총무", "협력업체"),
    min_result_hits=2,
)
GENERIC_CONSULTING_PROFILE = ExpectedDomainProfile(
    profile_id="generic_consulting",
    keywords=("업무", "현행", "개선", "구조", "계획", "요구사항", "방향"),
    min_result_hits=1,
)
EXPECTED_DOMAIN_PROFILE_RULES: tuple[tuple[tuple[str, ...], ExpectedDomainProfile], ...] = (
    (("부산우유", "원가계산컨설팅", "원가계산"), OO_MILK_PROFILE),
    (("차세대경영정보", "bprismp"), BPR_ISMP_PROFILE),
    (("상수도제안", "상수도"), WATERWORKS_PROFILE),
    (("광역정보", "해운", "위동"), MARITIME_PROFILE),
)


def _ppt_files() -> list[Path]:
    return sorted(path for path in SAMPLES_ROOT.rglob("*") if path.is_file() and path.suffix.lower() in PPT_EXTENSIONS)


def _expected_domain_profile(path: Path) -> ExpectedDomainProfile:
    haystack = f"{path.as_posix()} {path.name}".lower()
    for markers, profile in EXPECTED_DOMAIN_PROFILE_RULES:
        if any(marker.lower() in haystack for marker in markers):
            return profile
    return GENERIC_CONSULTING_PROFILE


def _extract_sensitive_values(sml_text: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for raw_line in str(sml_text or "").splitlines():
        match = SENSITIVE_LABEL_PATTERN.match(raw_line)
        if not match:
            continue
        value = re.sub(r"\s+", " ", str(match.group("value") or "").strip()).strip(" -")
        if not value or value.upper() in GENERIC_SENSITIVE_VALUES or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _result_text(result) -> str:
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False)


def _safe_bundle_text(safe_bundle) -> str:
    return "\n\n".join(str(source.content or "") for source in list(safe_bundle.sources or []))


def _review_text(review_report) -> str:
    if review_report is None:
        return ""
    return json.dumps(review_report.model_dump(mode="json"), ensure_ascii=False)


def _count_non_empty_lines(text: str) -> int:
    return len([line for line in str(text or "").splitlines() if line.strip()])


def _low_conf_warning_count(review_report) -> int:
    if review_report is None:
        return 0
    return sum(
        1
        for item in list(review_report.label_less_warnings or [])
        if str(getattr(item, "entity_type_guess", "") or "").strip() == "low_conf_term"
    )


def _parse_slide(locator: str) -> int | None:
    match = re.search(r"slide\s+(?P<slide>\d+)", str(locator or ""), re.IGNORECASE)
    if not match:
        return None
    return int(match.group("slide"))


def _person_overflow_reason(item) -> str:
    preview = str(getattr(item, "masked_preview", "") or "")
    locator = str(getattr(item, "locator", "") or "")
    lowered = preview.lower()
    if "|" in preview and re.search(r"\b(?:REQ|FR|NFR|IF|DB|SEC|TEST|PM|SFR|TER|SER|PMR|PSR)(?:-[A-Z])?-\d{2,3}\b", preview, re.IGNORECASE):
        return "table_requirement_line"
    if "tables" in locator.lower():
        return "table_line"
    if any(term in lowered for term in ("요구사항", "요건", "테스트", "보안", "이행계획", "추진조직")):
        return "requirement_statement"
    if re.match(r"^\s*-\s*(?:\d+(?:\.\d+)+|\d+[\.\)]|[ivxlcm]+[\.\)])", preview, re.IGNORECASE):
        return "numbered_heading_line"
    return "structured_content_line"


def _build_person_overflow_examples(review_report, *, limit: int = 10) -> list[dict[str, object]]:
    if review_report is None:
        return []
    examples: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for item in list(getattr(review_report, "label_less_risks", []) or []):
        if str(getattr(item, "entity_type_guess", "") or "") != "person_name":
            continue
        locator = str(getattr(item, "locator", "") or "")
        preview = str(getattr(item, "masked_preview", "") or "")
        dedupe_key = (locator, preview)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        examples.append(
            {
                "candidate": "[PERSON_CANDIDATE]",
                "slide": _parse_slide(locator),
                "reason": _person_overflow_reason(item),
                "locator": locator,
                "safe_snippet": preview[:240],
            }
        )
        if len(examples) >= limit:
            break
    return examples


def _run_single_file_regression(path: Path) -> dict[str, object]:
    domain_profile = _expected_domain_profile(path)
    entry: dict[str, object] = {
        "file": path.name,
        "relative_path": path.relative_to(SAMPLES_ROOT).as_posix(),
        "status": "ok",
        "issues": [],
        "warnings": [],
        "diagnostics": {},
    }
    try:
        original_bytes = path.read_bytes()
        sml_text = extract_text_from_file(path, original_bytes)
        entry["diagnostics"]["sml_text_length"] = len(sml_text or "")
        entry["diagnostics"]["expected_domain_profile"] = domain_profile.profile_id
        entry["diagnostics"]["expected_keywords"] = list(domain_profile.keywords)
        if not sml_text.strip():
            entry["issues"].append("sml_generation_failed")
            entry["status"] = "fail"
            return entry

        anonymization_result = AnonymizationService().run_anonymization_pipeline(
            AnonymizationRunRequest(
                project_id=f"ppt_batch_{path.stem}",
                assets=[
                    AnonymizationAsset(
                        asset_id=path.stem,
                        name=path.name,
                        temp_file_id=f"temp_{path.stem}",
                        kind_hint="presentation",
                        content_text=sml_text,
                        original_bytes=original_bytes,
                    )
                ],
            )
        )
        safe_bundle = anonymization_result.safe_bundle
        review_report = anonymization_result.review_report
        safe_bundle_text = _safe_bundle_text(safe_bundle)
        review_text = _review_text(review_report)
        safe_source_count = len(list(safe_bundle.sources or []))
        risk_person_count = safe_bundle_text.count("[RISK_PERSON_CANDIDATE]")
        line_count = max(1, _count_non_empty_lines(sml_text))
        low_conf_count = _low_conf_warning_count(review_report)
        low_conf_ratio = low_conf_count / line_count

        entry["diagnostics"].update(
            {
                "safe_source_count": safe_source_count,
                "risk_person_candidate_count": risk_person_count,
                "low_conf_warning_count": low_conf_count,
                "low_conf_ratio": round(low_conf_ratio, 4),
            }
        )
        if safe_source_count < 1:
            entry["issues"].append("safe_source_missing")

        analysis_context = AnalysisContextBuilder().build(
            project_id=f"ppt_batch_{path.stem}",
            run_id=f"run_{path.stem}",
            safe_bundle=safe_bundle,
            goal="",
            constraints=[],
        )
        service = RebuildAssistantService()
        prepared = service.prepare_analysis_context_input(analysis_context=analysis_context)
        result = service.build_result(prepared)
        result_text = _result_text(result)
        summary = prepared.question_guard_summary

        entry["diagnostics"].update(
            {
                "uploaded_asset_count": getattr(summary, "uploaded_asset_count", 0),
                "has_pptx_asset": bool(getattr(summary, "has_pptx_asset", False)),
                "guard_input_source_count": getattr(summary, "guard_input_source_count", 0),
                "guard_input_total_chars": getattr(summary, "guard_input_total_chars", 0),
                "source_question_candidate_count": getattr(summary, "source_question_candidate_count", 0),
                "question_guard_summary": summary.model_dump() if hasattr(summary, "model_dump") else {},
            }
        )

        if getattr(summary, "guard_input_source_count", 0) < 1:
            entry["issues"].append("guard_input_missing")
        if getattr(summary, "source_question_candidate_count", 0) < 1:
            entry["issues"].append("question_candidate_missing")
            no_candidate_reasons = list(getattr(summary, "no_candidate_reasons", []) or [])
            entry["diagnostics"]["no_candidate_reasons"] = no_candidate_reasons
            if not no_candidate_reasons:
                entry["issues"].append("no_candidate_reason_missing")

        source_lower = sml_text.lower()
        result_lower = result_text.lower()
        for issue_code, result_term, source_term in DOMAIN_POLLUTION_TERMS:
            if result_term in result_lower and source_term not in source_lower:
                entry["issues"].append(issue_code)

        result_domain_hits = [term for term in domain_profile.keywords if term in result_text]
        entry["diagnostics"]["result_domain_terms"] = result_domain_hits
        if len(set(result_domain_hits)) < domain_profile.min_result_hits:
            entry["issues"].append("expected_domain_signal_missing")

        for raw_value in _extract_sensitive_values(sml_text):
            if raw_value in safe_bundle_text or raw_value in review_text or raw_value in result_text:
                entry["issues"].append(f"raw_sensitive_leak:{raw_value}")

        if risk_person_count > 100:
            entry["issues"].append("risk_person_candidate_overflow")
            entry["diagnostics"]["person_candidate_overflow_examples"] = _build_person_overflow_examples(review_report)
        if low_conf_ratio > 0.30:
            entry["warnings"].append("low_conf_ratio_high")

    except Exception as exc:  # pragma: no cover - regression harness should report unexpected exceptions
        entry["issues"].append(f"exception:{type(exc).__name__}")
        entry["diagnostics"]["exception_message"] = str(exc)

    if entry["issues"]:
        entry["status"] = "fail"
    elif entry["warnings"]:
        entry["status"] = "warn"
    else:
        entry["status"] = "ok"
    return entry


def _write_report(entries: list[dict[str, object]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "sample_root": str(SAMPLES_ROOT),
        "report_count": len(entries),
        "reports": entries,
    }
    REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_entry(entry: dict[str, object]) -> None:
    problems = list(entry.get("issues") or []) + list(entry.get("warnings") or [])
    detail = ""
    if problems:
        detail = " - " + ", ".join(str(item) for item in problems[:4])
    print(f"[{str(entry['status']).upper()}] {entry['file']}{detail}")


def test_ppt_batch_regression():
    files = _ppt_files()
    assert files, f"no ppt/pptx files found under {SAMPLES_ROOT}"

    entries = [_run_single_file_regression(path) for path in files]
    for entry in entries:
        _print_entry(entry)
    _write_report(entries)

    failures = [entry for entry in entries if entry["status"] == "fail"]
    if failures:
        failure_names = ", ".join(str(item["file"]) for item in failures[:10])
        pytest.fail(
            f"{len(failures)} PPT regression failure(s) detected. report={REPORT_PATH}. files={failure_names}"
        )
