from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_COSTING_REPLACEMENTS = {
    "원가체계": "현행 구조",
    "원가 계산": "업무 기준 검토",
    "원가계산": "업무 기준 검토",
    "배부기준": "판단 기준",
    "배부 기준": "판단 기준",
    "제조경비": "운영 비용",
    "제조 경비": "운영 비용",
    "표준원가": "기준 정보",
}

_DEMO_REPLACEMENTS = {
    "sample_a_legacy_order_review": "주문관리 현대화 검토 사례",
    "sample_a": "주문관리 현대화 검토 사례",
    "sample_b_consulting_ppt_review": "업무 프로세스 현대화 검토 사례",
    "sample_b": "업무 프로세스 현대화 검토 사례",
    "si company": "고객사 A",
    "SI Company": "고객사 A",
    "Si Company": "고객사 A",
}

_GENERIC_NOT_SUPPORTED = (
    "전체 시스템 자동 전환",
    "자동 코드 치환",
    "운영 배포",
    "실행 성공 보장",
)


def build_docx_polish_report(
    pkg: dict[str, Any], *, surface_mode: str = "internal"
) -> str:
    """Return polished Markdown that the document renderer can turn into a DOCX report."""
    is_external = surface_mode == "external"
    ctx = _ReportContext(pkg=pkg, is_external=is_external)

    lines: list[str] = [
        "# 현대화 판단 보고서",
        f"프로젝트: {ctx.project_name}",
        f"고객사: {ctx.client_name}",
        "",
        "## 1. 1페이지 요약",
    ]
    lines.extend(_executive_summary_lines(ctx))
    lines.extend(
        [
            "",
            "## 2. 분석 범위와 입력 자료",
            f"- 분석 목표: {ctx.clean(ctx.project.get('goal') or '업로드 자료 기준 현대화 검토')}",
            "- 결과 성격: 고객/상사 검토용 초안이며, 운영 배포나 자동 전환을 보장하지 않습니다.",
            "",
        ]
    )
    lines.extend(_asset_table_lines(ctx))
    lines.extend(
        [
            "",
            "## 3. 현행 구조/업무 흐름 요약",
        ]
    )
    lines.extend(
        _bullet_lines(
            ctx.current_structure,
            "현행 구조와 업무 흐름은 추가 입력 자료 확인 후 보강해야 합니다.",
            limit=5,
        )
    )
    lines.extend(["", "## 4. 핵심 문제"])
    lines.extend(
        _bullet_lines(
            ctx.issue_lines,
            "핵심 문제는 입력 근거가 보강된 뒤 확정해야 합니다.",
            limit=5,
        )
    )
    lines.extend(["", "## 5. 개선 선택지"])
    lines.extend(_option_table_lines(ctx))
    lines.extend(["", "## 6. 권장안"])
    lines.extend(_recommendation_lines(ctx))
    lines.extend(["", "## 7. 리스크와 검토 필요 사항"])
    lines.extend(_risk_table_lines(ctx))
    lines.extend(["", "## 8. 단계별 실행 준비 계획"])
    lines.append(
        "- 이 섹션은 실행 자동화가 아니라 파일럿 이후 사람이 검토할 실행 준비 계획입니다."
    )
    lines.append("")
    lines.extend(_execution_table_lines(ctx))

    if is_external:
        lines.extend(
            [
                "",
                "## 9. 산출물 기준",
                f"- 생성 기준 시각: {ctx.provenance.get('generated_at') or '-'}",
                "- 상세 추적 정보와 입력 파일명은 내부 검토본에서 확인합니다.",
            ]
        )
    else:
        lines.extend(_internal_provenance_lines(ctx))

    lines.extend(["", "## 파일럿 범위와 제외 항목", "- 비지원 범위"])
    for item in _GENERIC_NOT_SUPPORTED:
        lines.append(f"  - {item}")

    return "\n".join(lines).strip() + "\n"


class _ReportContext:
    def __init__(self, *, pkg: dict[str, Any], is_external: bool) -> None:
        self.pkg = pkg
        self.is_external = is_external
        self.project = (
            pkg.get("project") if isinstance(pkg.get("project"), dict) else {}
        )
        self.provenance = (
            pkg.get("provenance") if isinstance(pkg.get("provenance"), dict) else {}
        )
        self.display = (
            pkg.get("display") if isinstance(pkg.get("display"), dict) else {}
        )
        self.display_sections = (
            self.display.get("sections")
            if isinstance(self.display.get("sections"), dict)
            else {}
        )
        self.diagnosis = (
            pkg.get("diagnosis") if isinstance(pkg.get("diagnosis"), dict) else {}
        )
        self.design = pkg.get("design") if isinstance(pkg.get("design"), dict) else {}
        self.structure_comparison = (
            pkg.get("structure_comparison")
            if isinstance(pkg.get("structure_comparison"), dict)
            else {}
        )
        self.assets = _as_list(self.provenance.get("input_assets") or pkg.get("assets"))
        self.external_sensitive_values = (
            _external_sensitive_values(pkg, self.assets) if is_external else ()
        )
        self.raw_text = _flatten_text(pkg)
        self.has_costing_anchor = bool(
            re.search(
                r"회계|전표|GL|손익|재무|결산|accounting|ledger",
                self.raw_text,
                flags=re.IGNORECASE,
            )
        )
        self.has_order_anchor = bool(
            re.search(
                r"주문|결제|배송|상태|order|payment|delivery",
                self.raw_text,
                flags=re.IGNORECASE,
            )
        )
        self.project_name = self.clean(
            _display_name(self.project.get("project_name") or "현대화 검토")
        )
        self.client_name = self.clean(
            _display_name(self.project.get("client_name") or "고객사")
        )
        self.analysis_items = _clean_items(
            _as_list(
                pkg.get("analysis_summary") or self.diagnosis.get("analysis_summary")
            ),
            self,
        )
        self.current_structure = _clean_items(
            _coerce_items(
                self.structure_comparison.get("current_structure")
                or self.structure_comparison.get("before")
            ),
            self,
        )
        if not self.current_structure:
            self.current_structure = self.analysis_items
        self.issue_lines = _clean_items(
            _issue_items(pkg.get("decision_items")) or self.analysis_items, self
        )
        self.design_options = _design_options(self)
        self.recommended_option = _recommended_option(self)
        self.risks = _clean_items(_risk_items(self), self)
        self.missing_context = _as_list(
            _section(self, "risks").get("missing_context_details")
            or self.diagnosis.get("missing_context_details")
        )
        self.execution_plan = _as_list(
            _section(self, "execution_plan").get("items") or pkg.get("execution_plan")
        )

    def clean(self, value: Any, *, max_chars: int | None = None) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if self.is_external:
            text = _redact_external_text(text, self.external_sensitive_values)
        text = _display_name(text)
        if self.has_order_anchor:
            text = text.replace("청구 조정 기능", "상태 보정 로직").replace(
                "청구 조정", "상태 보정"
            )
        if not self.has_costing_anchor:
            for source, target in _COSTING_REPLACEMENTS.items():
                text = text.replace(source, target)
        text = re.sub(r"\s+", " ", text).strip()
        if max_chars and len(text) > max_chars:
            text = _compress_text(text, max_chars=max_chars)
        return text


def _executive_summary_lines(ctx: _ReportContext) -> list[str]:
    hero = ctx.display.get("hero") if isinstance(ctx.display.get("hero"), dict) else {}
    summary = (
        ctx.pkg.get("executive_summary")
        if isinstance(ctx.pkg.get("executive_summary"), dict)
        else {}
    )
    conclusion = ctx.clean(
        ctx.pkg.get("core_conclusion")
        or hero.get("headline")
        or summary.get("core_message")
        or "제공 자료 기준의 현대화 검토 초안입니다.",
        max_chars=150,
    )
    problems = _dedupe(ctx.issue_lines or ctx.analysis_items, limit=3)
    risks = _dedupe(ctx.risks, limit=2)
    recommendation = _recommendation_sentence(ctx)
    next_actions = _next_actions(ctx)
    return [
        f"- 한 줄 결론: {conclusion}",
        f"- 핵심 문제: {_join_values(problems[:3], fallback='핵심 문제는 추가 자료 확인 후 확정')}",
        f"- 권장안: {recommendation}",
        f"- 주요 리스크: {_join_values(risks[:2], fallback='추가 자료 부족에 따른 판단 제한')}",
        f"- 다음 행동: {_join_values(next_actions[:2], fallback='파일럿 범위와 제외 범위 합의')}",
    ]


def _asset_table_lines(ctx: _ReportContext) -> list[str]:
    if ctx.is_external:
        rows = _external_asset_rows(ctx)
        return _markdown_table(
            ["유형", "설명"], rows or [["자료", "업로드 자료 기준으로 분석했습니다."]]
        )
    rows: list[list[str]] = []
    for asset in ctx.assets:
        if not isinstance(asset, dict):
            continue
        name = ctx.clean(
            asset.get("name")
            or asset.get("original_filename")
            or asset.get("filename")
            or "-"
        )
        size = str(asset.get("size") or asset.get("file_size") or "-")
        rows.append([_asset_type(name), name, size])
    return _markdown_table(
        ["유형", "파일명", "크기"], rows or [["자료", "입력 자산 정보 없음", "-"]]
    )


def _option_table_lines(ctx: _ReportContext) -> list[str]:
    rows: list[list[str]] = []
    for index, option in enumerate(ctx.design_options[:4], start=1):
        if not isinstance(option, dict):
            continue
        label = ctx.clean(
            option.get("name") or option.get("title") or f"선택지 {index}"
        )
        description = ctx.clean(
            option.get("description")
            or option.get("structure_summary")
            or option.get("summary")
            or option.get("approach")
            or "개선 선택지",
            max_chars=90,
        )
        pros = _join_short(
            option.get("pros") or option.get("benefits") or option.get("advantages"),
            ctx,
            fallback="적용 범위 조정 가능",
        )
        cons = _join_short(
            option.get("cons") or option.get("risks") or option.get("tradeoffs"),
            ctx,
            fallback="추가 검토 필요",
        )
        rows.append([label, description, pros, cons])
    if not rows:
        rows.append(
            [
                "A",
                "현행 구조를 유지하며 필요한 보완만 검토",
                "빠르게 검토 가능",
                "구조 개선 효과 제한",
            ]
        )
        rows.append(
            [
                "B",
                "핵심 흐름을 기준으로 부분 개선",
                "리스크를 통제하며 개선 가능",
                "범위 합의 필요",
            ]
        )
    return _markdown_table(["선택지", "설명", "장점", "단점"], rows)


def _recommendation_lines(ctx: _ReportContext) -> list[str]:
    sentence = _recommendation_sentence(ctx)
    reason = ""
    if isinstance(ctx.recommended_option, dict):
        reason = ctx.clean(
            ctx.recommended_option.get("selection_reason")
            or ctx.recommended_option.get("reason")
            or "",
            max_chars=180,
        )
    basis = _dedupe([reason] + ctx.issue_lines + ctx.risks, limit=2)
    lines = [f"- 권장안: {sentence}"]
    if basis:
        lines.append(f"- 선택 및 권장 근거: {' '.join(basis)}")
    return lines


def _risk_table_lines(ctx: _ReportContext) -> list[str]:
    rows: list[list[str]] = []
    for risk in ctx.risks[:5]:
        rows.append(
            [risk, "일정/범위 판단 지연 가능", "추가 자료 확인 후 범위와 우선순위 확정"]
        )
    for item in ctx.missing_context[:3]:
        if isinstance(item, dict):
            material = ctx.clean(item.get("required_material") or "추가 자료")
            reason = ctx.clean(
                item.get("reason") or "판단 근거 보강 필요", max_chars=80
            )
            rows.append([f"{material} 부족", reason, "고객사 확인 자료 요청"])
    return _markdown_table(
        ["리스크", "영향", "대응"],
        rows or [["추가 자료 부족", "판단 정확도 제한", "자료 수집 후 재검토"]],
    )


def _execution_table_lines(ctx: _ReportContext) -> list[str]:
    rows: list[list[str]] = []
    for index, item in enumerate(ctx.execution_plan[:5], start=1):
        if not isinstance(item, dict):
            continue
        phase = ctx.clean(
            item.get("week_label")
            or item.get("phase")
            or item.get("title")
            or f"{index}단계"
        )
        tasks = _join_short(
            item.get("tasks") or item.get("action") or item.get("decision"),
            ctx,
            fallback="검토 작업 확정",
        )
        note = _join_short(
            item.get("deliverables") or item.get("priority_reason"),
            ctx,
            fallback="담당자와 범위 확인",
        )
        rows.append([phase, tasks, note])
    if not rows:
        rows = [
            ["1단계", "입력 자료와 업무 범위 확인", "누락 자료 식별"],
            ["2단계", "개선 선택지와 리스크 검토", "고객사 의사결정 기준 정리"],
            ["3단계", "파일럿 실행 범위 확정", "산출물과 제외 범위 합의"],
        ]
    return _markdown_table(["단계", "작업", "비고"], rows)


def _internal_provenance_lines(ctx: _ReportContext) -> list[str]:
    lines = [
        "",
        "## 9. 분석 근거와 provenance",
        f"- run_id: {ctx.provenance.get('run_id') or '-'}",
        f"- 생성 시각: {ctx.provenance.get('generated_at') or '-'}",
        f"- Run 상태: {ctx.provenance.get('run_status') or '-'}",
        f"- 앱 버전: {ctx.provenance.get('app_version') or '-'}",
        f"- 모듈 버전: {ctx.provenance.get('module_version') or '-'}",
        f"- 템플릿 키: {ctx.provenance.get('template_key') or '-'}",
        "- 입력 자산 상세와 검증 필요 항목은 위 표와 리스크 섹션을 기준으로 검토합니다.",
    ]
    questions = _clean_items(_as_list(ctx.pkg.get("report_questions")), ctx)
    if questions:
        lines.append("- 검증 질문")
        lines.extend(f"  - {item}" for item in questions[:5])
    return lines


def _markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    safe_headers = [_escape_cell(header) for header in headers]
    lines = [
        "| " + " | ".join(safe_headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        padded = list(row[: len(headers)]) + [""] * max(0, len(headers) - len(row))
        lines.append("| " + " | ".join(_escape_cell(cell) for cell in padded) + " |")
    return lines


def _bullet_lines(items: list[str], empty: str, *, limit: int) -> list[str]:
    cleaned = _dedupe(items, limit=limit)
    if not cleaned:
        return [f"- {empty}"]
    return [f"- {item}" for item in cleaned]


def _display_name(text: Any) -> str:
    result = str(text or "").strip()
    for source, target in _DEMO_REPLACEMENTS.items():
        result = result.replace(source, target)
    return result


def _clean_items(items: Iterable[Any], ctx: _ReportContext) -> list[str]:
    return _dedupe(
        [ctx.clean(item, max_chars=180) for item in items if str(item or "").strip()]
    )


def _coerce_items(value: Any) -> list[Any]:
    if isinstance(value, str):
        return [value]
    return _as_list(value)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _section(ctx: _ReportContext, key: str) -> dict[str, Any]:
    section = (
        ctx.display_sections.get(key) if isinstance(ctx.display_sections, dict) else {}
    )
    return section if isinstance(section, dict) else {}


def _issue_items(value: Any) -> list[str]:
    items: list[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            text = item.get("statement") or item.get("item") or item.get("description")
            if text:
                if re.match(
                    r"^\s*(선택\s*이유|선택\s*근거|권장\s*이유|권장\s*근거)\s*[:：-]",
                    str(text),
                ):
                    continue
                items.append(str(text))
        elif str(item or "").strip():
            items.append(str(item))
    return items


def _design_options(ctx: _ReportContext) -> list[Any]:
    display_items = _as_list(_section(ctx, "design_options").get("items"))
    return display_items or _as_list(
        ctx.pkg.get("design_options") or ctx.design.get("design_options")
    )


def _recommended_option(ctx: _ReportContext) -> dict[str, Any] | None:
    option = ctx.pkg.get("recommended_option")
    if isinstance(option, dict):
        return option
    option = (
        ctx.design.get("recommended_option") if isinstance(ctx.design, dict) else None
    )
    return option if isinstance(option, dict) else None


def _risk_items(ctx: _ReportContext) -> list[Any]:
    return _as_list(
        _section(ctx, "risks").get("items")
        or ctx.pkg.get("risks")
        or ctx.diagnosis.get("risks")
    )


def _recommendation_sentence(ctx: _ReportContext) -> str:
    if isinstance(ctx.recommended_option, dict):
        name = ctx.clean(
            ctx.recommended_option.get("name")
            or ctx.recommended_option.get("title")
            or "권장 선택지",
            max_chars=80,
        )
        reason = ctx.clean(
            ctx.recommended_option.get("summary")
            or ctx.recommended_option.get("description")
            or "",
            max_chars=120,
        )
        if reason and reason != name:
            return f"{name}을 우선 검토합니다. {reason}"
        return f"{name}을 우선 검토합니다."
    return "핵심 업무 흐름을 기준으로 부분 개선 범위를 우선 확정합니다."


def _next_actions(ctx: _ReportContext) -> list[str]:
    actions: list[str] = []
    for item in ctx.execution_plan:
        if isinstance(item, dict):
            text = item.get("action") or item.get("decision") or item.get("title")
            if text:
                actions.append(ctx.clean(text, max_chars=90))
    if not actions:
        actions = [
            "입력 자료 누락 여부를 확인합니다.",
            "파일럿 범위와 제외 범위를 고객사와 합의합니다.",
        ]
    return _dedupe(actions, limit=2)


def _external_asset_rows(ctx: _ReportContext) -> list[list[str]]:
    seen: set[str] = set()
    rows: list[list[str]] = []
    for asset in ctx.assets:
        if not isinstance(asset, dict):
            continue
        name = str(
            asset.get("name")
            or asset.get("original_filename")
            or asset.get("filename")
            or ""
        )
        asset_type = _asset_type(name)
        if asset_type in seen:
            continue
        seen.add(asset_type)
        rows.append([asset_type, _external_asset_description(asset_type)])
    return rows


def _asset_type(name: str) -> str:
    suffix = name.lower()
    if suffix.endswith((".sql", ".ddl")):
        return "SQL"
    if suffix.endswith((".java", ".kt", ".cs", ".js", ".ts", ".py")):
        return "코드"
    if suffix.endswith((".ppt", ".pptx")):
        return "PPT"
    if suffix.endswith((".doc", ".docx", ".pdf", ".md", ".txt")):
        return "문서"
    return "자료"


def _external_asset_description(asset_type: str) -> str:
    return {
        "SQL": "조회/상태 변경 등 데이터 흐름 확인 자료",
        "코드": "서비스 흐름과 업무 규칙 확인 자료",
        "PPT": "업무/현대화 검토용 컨설팅 자료",
        "문서": "업무 구조와 판단 기준 확인 자료",
    }.get(asset_type, "현행 구조와 업무 흐름 확인 자료")


def _external_sensitive_values(
    pkg: dict[str, Any], assets: list[Any]
) -> tuple[str, ...]:
    values = set(_collect_internal_values(pkg))
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        for key in ("name", "original_filename", "filename", "path"):
            value = str(asset.get(key) or "").strip()
            if value:
                values.add(value)
    return tuple(
        sorted((value for value in values if len(value) >= 3), key=len, reverse=True)
    )


def _collect_internal_values(value: Any, *, key: str = "") -> list[str]:
    if isinstance(value, dict):
        collected: list[str] = []
        for child_key, child_value in value.items():
            collected.extend(
                _collect_internal_values(child_value, key=str(child_key).lower())
            )
        return collected
    if isinstance(value, (list, tuple)):
        collected = []
        for item in value:
            collected.extend(_collect_internal_values(item, key=key))
        return collected
    sensitive_key = (
        key == "id"
        or key.endswith("_id")
        or any(token in key for token in ("path", "filename", "raw_content"))
    )
    text = str(value or "").strip()
    return [text] if sensitive_key and text else []


def _redact_external_text(text: str, sensitive_values: tuple[str, ...]) -> str:
    redacted = text
    for value in sensitive_values:
        redacted = redacted.replace(value, "내부 정보 제거")
    return re.sub(
        r"\b(?:run|proj|asset|safe[_-]?bundle|temp(?:_file)?)[_-][A-Za-z0-9][A-Za-z0-9_.-]*\b",
        "내부 정보 제거",
        redacted,
        flags=re.IGNORECASE,
    )


def _join_short(value: Any, ctx: _ReportContext, *, fallback: str) -> str:
    if isinstance(value, str):
        return ctx.clean(value, max_chars=90) or fallback
    items = _clean_items(_as_list(value), ctx)
    return " / ".join(items[:2]) if items else fallback


def _join_values(items: Iterable[str], *, fallback: str) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    return " / ".join(values) if values else fallback


def _dedupe(items: Iterable[str], *, limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = re.sub(r"\s+", " ", str(item or "").strip())
        if not text:
            continue
        key = _semantic_key(text)
        if key in seen:
            continue
        if any(
            _token_overlap(key, _semantic_key(existing)) >= 0.78 for existing in result
        ):
            continue
        seen.add(key)
        result.append(text)
        if limit and len(result) >= limit:
            break
    return result


def _semantic_key(text: str) -> str:
    text = re.sub(
        r"^(선택\s*이유|선택\s*근거|권장\s*이유|권장\s*근거)\s*[:：-]\s*", "", text
    )
    text = re.sub(r"[^\w가-힣]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _token_overlap(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def _compress_text(text: str, *, max_chars: int) -> str:
    sentences = [
        part.strip() for part in re.split(r"(?<=[.!?。])\s+", text) if part.strip()
    ]
    compressed = sentences[0] if sentences else text
    if len(compressed) > max_chars:
        compressed = compressed[: max_chars - 1].rstrip(" ,.;:") + "..."
    return compressed


def _escape_cell(value: Any) -> str:
    text = str(value or "").strip().replace("|", "/")
    return re.sub(r"\s+", " ", text)


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return str(value or "")
