from __future__ import annotations

import asyncio
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from mellow_link.modules.rebuild_assistant.postprocess.consulting_contract import (
    build_consulting_min_contract,
)
from mellow_link.modules.rebuild_assistant.postprocess.consulting_deck import (
    build_consulting_deck,
)
from mellow_link.modules.rebuild_assistant.postprocess.schemas import ConsultingMinContract
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.llm_service import LLMService
from mellow_link.tests.refactoring_support_test_utils import (
    load_expected_assertions,
    load_expansion_sample_case,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "consulting_flow_compare"
FLOW_LABELS = {
    "A": "input -> LLM -> consulting_min_contract -> consulting_deck",
    "B": "input -> consulting_min_contract -> LLM -> consulting_deck",
    "C": "input -> SLM structure -> LLM reasoning -> SLM contract -> deck",
}
SAMPLES = (
    "02_access_control_workflow",
    "04_db_heavy_query_filter",
    "05_legacy_tangled_mixed",
)
REPEATS = 3
MAX_RAW_DIGEST_CHARS = 9000
ACTION_TOKENS = (
    "분리",
    "정리",
    "구조화",
    "설계",
    "확정",
    "구성",
    "검토",
    "반영",
    "정렬",
    "보완",
    "유지",
    "수립",
    "개선",
)
PLACEHOLDER_SNIPPETS = (
    "충분하지 않습니다",
    "추가 확인",
    "추가 분석",
    "확정 전입니다",
)


@dataclass
class RunBundle:
    flow: str
    case_name: str
    run_index: int
    contract: dict[str, list[str]]
    deck: dict[str, Any]
    raw_output: dict[str, Any]
    domain_accuracy: float
    controllability: float
    output_quality: float


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_가-힣]+", _normalized_text(value).lower())


def _token_f1(lhs: list[str], rhs: list[str]) -> float:
    if not lhs and not rhs:
        return 1.0
    if not lhs or not rhs:
        return 0.0
    lhs_counts: dict[str, int] = {}
    rhs_counts: dict[str, int] = {}
    for token in lhs:
        lhs_counts[token] = lhs_counts.get(token, 0) + 1
    for token in rhs:
        rhs_counts[token] = rhs_counts.get(token, 0) + 1
    overlap = 0
    for token, count in lhs_counts.items():
        overlap += min(count, rhs_counts.get(token, 0))
    precision = overlap / max(1, len(lhs))
    recall = overlap / max(1, len(rhs))
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _extract_json_object(text: str) -> dict[str, Any]:
    normalized = _normalized_text(text)
    if not normalized:
        return {}
    try:
        parsed = json.loads(normalized)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _contract_to_dict(contract: ConsultingMinContract) -> dict[str, list[str]]:
    data = contract.model_dump()
    return {
        key: [_normalized_text(item) for item in value if _normalized_text(item)]
        for key, value in data.items()
    }


def _normalize_contract_payload(payload: dict[str, Any]) -> ConsultingMinContract:
    normalized = {}
    for field in ("as_is", "process_flow", "rules", "risks", "gap", "actions"):
        value = payload.get(field) if isinstance(payload, dict) else None
        if isinstance(value, str):
            normalized[field] = [_normalized_text(value)] if _normalized_text(value) else []
        elif isinstance(value, list):
            normalized[field] = [_normalized_text(item) for item in value if _normalized_text(item)]
        else:
            normalized[field] = []
    return ConsultingMinContract(**normalized)


def _normalize_source_payload(payload: dict[str, Any]) -> dict[str, Any]:
    def string_list(value: Any) -> list[str]:
        if isinstance(value, str):
            return [_normalized_text(value)] if _normalized_text(value) else []
        if isinstance(value, list):
            return [_normalized_text(item) for item in value if _normalized_text(item)]
        return []

    def object_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    normalized = {
        "analysis_summary": string_list(payload.get("analysis_summary")),
        "risks": string_list(payload.get("risks")),
        "recommended_directions": string_list(payload.get("recommended_directions")),
        "grounded_business_rules": [],
        "decision_items": [],
        "execution_plan": [],
        "missing_context_details": [],
    }
    for item in object_list(payload.get("grounded_business_rules"))[:6]:
        title = _normalized_text(item.get("title"))
        description = _normalized_text(item.get("description"))
        if title or description:
            normalized["grounded_business_rules"].append({"title": title, "description": description})
    for item in object_list(payload.get("decision_items"))[:6]:
        statement = _normalized_text(item.get("statement"))
        rationale = _normalized_text(item.get("rationale"))
        if statement or rationale:
            normalized["decision_items"].append({"statement": statement, "rationale": rationale})
    for item in object_list(payload.get("execution_plan"))[:6]:
        week_label = _normalized_text(item.get("week_label"))
        goal = _normalized_text(item.get("goal"))
        if week_label or goal:
            normalized["execution_plan"].append({"week_label": week_label, "goal": goal})
    for item in object_list(payload.get("missing_context_details"))[:6]:
        required_material = _normalized_text(item.get("required_material"))
        reason = _normalized_text(item.get("reason"))
        if required_material or reason:
            normalized["missing_context_details"].append(
                {"required_material": required_material, "reason": reason}
            )
    return normalized


def _flatten_contract(contract: dict[str, list[str]]) -> set[str]:
    flattened: set[str] = set()
    for section, items in contract.items():
        for item in items:
            normalized = _normalized_text(item)
            if normalized:
                flattened.add(f"{section}:{normalized.lower()}")
    return flattened


def _jaccard_similarity(lhs: set[str], rhs: set[str]) -> float:
    if not lhs and not rhs:
        return 1.0
    if not lhs or not rhs:
        return 0.0
    return len(lhs & rhs) / len(lhs | rhs)


def _domain_accuracy_score(
    contract: dict[str, list[str]],
    reference_contract: dict[str, list[str]],
) -> float:
    section_scores = []
    for section in ("as_is", "process_flow", "rules", "risks", "gap", "actions"):
        lhs_tokens = _tokenize(" ".join(contract.get(section, [])))
        rhs_tokens = _tokenize(" ".join(reference_contract.get(section, [])))
        section_scores.append(_token_f1(lhs_tokens, rhs_tokens))
    return round(100 * mean(section_scores), 1)


def _controllability_score(contract: dict[str, list[str]], deck: dict[str, Any]) -> float:
    score = 0.0
    required_sections = ("as_is", "process_flow", "rules", "risks", "gap", "actions")
    if all(section in contract for section in required_sections):
        score += 20
    if all(isinstance(contract.get(section), list) for section in required_sections):
        score += 20
    within_limits = all(0 < len(contract.get(section, [])) <= 6 for section in required_sections)
    if within_limits:
        score += 20
    all_items = [item for section in required_sections for item in contract.get(section, [])]
    normalized_unique = {_normalized_text(item).lower() for item in all_items if _normalized_text(item)}
    unique_ratio = len(normalized_unique) / max(1, len(all_items))
    score += 20 * unique_ratio
    placeholder_hits = 0
    for chapter in deck.get("chapters", []):
        for section in chapter.get("sections", []):
            if section.get("uses_placeholder"):
                placeholder_hits += 1
    score += max(0.0, 20 - 5 * placeholder_hits)
    return round(min(score, 100.0), 1)


def _output_quality_score(contract: dict[str, list[str]]) -> float:
    required_sections = ("as_is", "process_flow", "rules", "risks", "gap", "actions")
    coverage = sum(1 for section in required_sections if contract.get(section)) / len(required_sections)
    items = [item for section in required_sections for item in contract.get(section, [])]
    if not items:
        return 0.0
    good_length_ratio = sum(18 <= len(item) <= 140 for item in items) / len(items)
    action_items = contract.get("actions", []) + contract.get("process_flow", [])
    actionable_ratio = 0.0
    if action_items:
        actionable_ratio = sum(
            bool(re.search(r"\d+주차", item)) or any(token in item for token in ACTION_TOKENS)
            for item in action_items
        ) / len(action_items)
    unique_ratio = len({_normalized_text(item).lower() for item in items}) / len(items)
    score = 35 * coverage + 25 * good_length_ratio + 25 * actionable_ratio + 15 * unique_ratio
    return round(min(score, 100.0), 1)


def _build_input_digest(case: dict[str, Any]) -> str:
    chunks = [
        f"goal: {_normalized_text(case['goal'])}",
    ]
    constraints = case.get("constraints") or []
    if constraints:
        chunks.append("constraints:")
        for item in constraints:
            chunks.append(f"- {_normalized_text(item)}")
    chunks.append("assets:")
    remaining = MAX_RAW_DIGEST_CHARS
    for spec in case["asset_specs"]:
        name = spec["name"]
        content = spec["content"]
        header = f"\n### {name}\n"
        body_budget = max(200, min(2000, remaining - len(header)))
        excerpt = content[:body_budget]
        chunks.append(header + excerpt)
        remaining -= len(header) + len(excerpt)
        if remaining <= 400:
            break
    return "\n".join(chunks)


def _build_structured_digest(result: Any, expected_assertions: dict[str, Any]) -> dict[str, Any]:
    decision_summary = result.decision_summary if isinstance(result.decision_summary, dict) else {}
    decisions = decision_summary.get("decisions", []) if isinstance(decision_summary, dict) else []
    top_decision = decisions[0] if decisions else {}
    execution_plan = [item.model_dump() for item in result.execution_plan[:5]]
    design_options = [item.model_dump() for item in result.design_options[:2]]
    return {
        "primary_judgment": result.primary_judgment,
        "template_judgment": result.template_judgment,
        "narrative_axis": result.narrative_axis,
        "report_purpose": result.report_purpose,
        "analysis_summary": list(result.analysis_summary[:6]),
        "grounded_business_rules": [item.model_dump() for item in result.grounded_business_rules[:6]],
        "retained_contracts": [item.model_dump() for item in result.retained_contracts[:6]],
        "risks": list(result.risks[:6]),
        "execution_plan": execution_plan,
        "design_options": design_options,
        "recommended_option": result.recommended_option.model_dump() if result.recommended_option else {},
        "top_decision": top_decision,
        "expected_assertions": expected_assertions.get("assertions", {}).get("deterministic_core", {}),
    }


def _flow_a_prompt(raw_digest: str) -> str:
    return (
        "아래 입력 자산만 근거로 컨설팅 초안 source JSON을 만들어라.\n"
        "추측을 최소화하고, 근거가 약하면 비워라.\n"
        "반드시 JSON object만 반환하라.\n"
        "허용 키:\n"
        "- analysis_summary: string[]\n"
        "- grounded_business_rules: {title, description}[]\n"
        "- risks: string[]\n"
        "- decision_items: {statement, rationale}[]\n"
        "- execution_plan: {week_label, goal}[]\n"
        "- recommended_directions: string[]\n"
        "- missing_context_details: {required_material, reason}[]\n"
        "규칙:\n"
        "- 각 배열은 최대 6개.\n"
        "- 한국어로 쓴다.\n"
        "- 입력에 없는 고유명사, 숫자, 조직명을 새로 만들지 마라.\n"
        "- 보고서식이 아니라 machine-readable JSON만 출력한다.\n\n"
        f"{raw_digest}"
    )


def _flow_b_prompt(contract: dict[str, list[str]]) -> str:
    contract_json = json.dumps(contract, ensure_ascii=False, indent=2)
    return (
        "아래 consulting_min_contract JSON을 더 읽기 좋고 컨설팅 친화적으로 다듬어라.\n"
        "하지만 사실관계와 도메인 축은 유지해야 한다.\n"
        "반드시 같은 스키마의 JSON object만 반환하라.\n"
        "허용 키는 as_is, process_flow, rules, risks, gap, actions 뿐이다.\n"
        "규칙:\n"
        "- 각 배열은 1~6개 유지.\n"
        "- 중복 문장을 제거한다.\n"
        "- 입력에 없는 새 도메인 축이나 새 고유명사를 추가하지 마라.\n"
        "- 한국어로 쓴다.\n\n"
        f"{contract_json}"
    )


def _flow_c_reasoning_prompt(structured_digest: dict[str, Any]) -> str:
    return (
        "아래 구조화된 분석 결과를 읽고 reasoning memo를 4개 bullet로 요약하라.\n"
        "bullet 제목은 focus, why, risk, next 로 고정한다.\n"
        "새 사실은 추가하지 마라.\n"
        "반드시 JSON object만 반환하라. 키는 focus, why, risk, next.\n\n"
        f"{json.dumps(structured_digest, ensure_ascii=False, indent=2)}"
    )


async def _llm_json(
    llm: LLMService,
    *,
    prompt: str,
    system_prompt: str,
    context_id: str,
    temperature: float = 0.2,
    max_tokens: int = 900,
    mode: str = "fast",
) -> tuple[dict[str, Any], str]:
    result = await llm.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        mode=mode,
        context_id=context_id,
        auto_unload=False,
        request_timeout_seconds=180,
        options={"temperature": temperature, "num_predict": max_tokens, "num_ctx": 4096},
    )
    raw_text = result.content or ""
    if not raw_text.strip() and mode != "fast":
        fallback = await llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            mode="fast",
            context_id=f"{context_id}:fallback-fast",
            auto_unload=False,
            request_timeout_seconds=180,
            options={"temperature": temperature, "num_predict": max_tokens, "num_ctx": 4096},
        )
        raw_text = fallback.content or ""
    return _extract_json_object(raw_text), raw_text


def _build_deck(contract: ConsultingMinContract, case_name: str) -> dict[str, Any]:
    return build_consulting_deck(
        contract,
        project_name=f"experiment:{case_name}",
        client_name="flow-compare",
        surface_mode="internal",
    )


def _summarize_flow_case(runs: list[RunBundle]) -> dict[str, Any]:
    contracts = [_flatten_contract(run.contract) for run in runs]
    pairwise = []
    for left_index in range(len(contracts)):
        for right_index in range(left_index + 1, len(contracts)):
            pairwise.append(_jaccard_similarity(contracts[left_index], contracts[right_index]))
    consistency = 100.0 if not pairwise else round(100 * mean(pairwise), 1)
    return {
        "domain_accuracy": round(mean(run.domain_accuracy for run in runs), 1),
        "consistency": consistency,
        "controllability": round(mean(run.controllability for run in runs), 1),
        "output_quality": round(mean(run.output_quality for run in runs), 1),
        "sample_output": runs[0].contract,
    }


async def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    service = RebuildAssistantService()
    llm = LLMService(timeout=180.0)
    await llm.connect()

    raw_results: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "samples": {},
        "flows": FLOW_LABELS,
        "repeats": REPEATS,
        "scoring_basis": {
            "domain_accuracy": "deterministic baseline contract token-F1",
            "consistency": "pairwise Jaccard similarity over normalized contract items",
            "controllability": "schema compliance, item limit compliance, placeholder avoidance, duplication ratio",
            "output_quality": "coverage, length fitness, actionability, uniqueness",
        },
    }
    aggregated: dict[str, list[dict[str, Any]]] = {"A": [], "B": [], "C": []}

    try:
        for case_name in SAMPLES:
            case = load_expansion_sample_case(case_name)
            expected_assertions = load_expected_assertions(case_name)
            prepared = service.prepare_safe_bundle_input(
                goal=case["goal"],
                safe_bundle=case["safe_bundle"],
                constraints=case["constraints"],
            )
            result = service.build_result(prepared)
            baseline_contract_model = build_consulting_min_contract(result.model_dump(mode="json"))
            baseline_contract = _contract_to_dict(baseline_contract_model)
            baseline_deck = _build_deck(baseline_contract_model, case_name)
            raw_digest = _build_input_digest(case)
            structured_digest = _build_structured_digest(result, expected_assertions)

            sample_runs: dict[str, list[RunBundle]] = {"A": [], "B": [], "C": []}

            for run_index in range(1, REPEATS + 1):
                flow_a_payload, flow_a_raw = await _llm_json(
                    llm,
                    prompt=_flow_a_prompt(raw_digest),
                    system_prompt=(
                        "You are a strict consulting-analysis extractor. "
                        "Return machine-readable JSON only. Do not invent unsupported facts."
                    ),
                    context_id=f"flow-a:{case_name}:{run_index}",
                    temperature=0.2,
                    max_tokens=900,
                )
                flow_a_source = _normalize_source_payload(flow_a_payload)
                flow_a_contract_model = build_consulting_min_contract(flow_a_source)
                flow_a_contract = _contract_to_dict(flow_a_contract_model)
                flow_a_deck = _build_deck(flow_a_contract_model, case_name)
                sample_runs["A"].append(
                    RunBundle(
                        flow="A",
                        case_name=case_name,
                        run_index=run_index,
                        contract=flow_a_contract,
                        deck=flow_a_deck,
                        raw_output={"response_text": flow_a_raw, "source_payload": flow_a_source},
                        domain_accuracy=_domain_accuracy_score(flow_a_contract, baseline_contract),
                        controllability=_controllability_score(flow_a_contract, flow_a_deck),
                        output_quality=_output_quality_score(flow_a_contract),
                    )
                )

                flow_b_payload, flow_b_raw = await _llm_json(
                    llm,
                    prompt=_flow_b_prompt(baseline_contract),
                    system_prompt=(
                        "You rewrite a consulting_min_contract without changing factual anchors. "
                        "Return JSON only."
                    ),
                    context_id=f"flow-b:{case_name}:{run_index}",
                    temperature=0.1,
                    max_tokens=1400,
                )
                flow_b_contract_model = _normalize_contract_payload(flow_b_payload)
                flow_b_contract = _contract_to_dict(flow_b_contract_model)
                flow_b_deck = _build_deck(flow_b_contract_model, case_name)
                sample_runs["B"].append(
                    RunBundle(
                        flow="B",
                        case_name=case_name,
                        run_index=run_index,
                        contract=flow_b_contract,
                        deck=flow_b_deck,
                        raw_output={"response_text": flow_b_raw, "contract_payload": flow_b_payload},
                        domain_accuracy=_domain_accuracy_score(flow_b_contract, baseline_contract),
                        controllability=_controllability_score(flow_b_contract, flow_b_deck),
                        output_quality=_output_quality_score(flow_b_contract),
                    )
                )

            flow_c_reasoning_payload, flow_c_reasoning_raw = await _llm_json(
                llm,
                prompt=_flow_c_reasoning_prompt(structured_digest),
                system_prompt=(
                    "You read a structured deterministic result and write a short reasoning memo. "
                    "Do not change facts. Return JSON only."
                ),
                context_id=f"flow-c:{case_name}:reasoning",
                temperature=0.1,
                max_tokens=300,
            )
            sample_runs["C"].append(
                RunBundle(
                    flow="C",
                    case_name=case_name,
                    run_index=1,
                    contract=baseline_contract,
                    deck=baseline_deck,
                    raw_output={
                        "reasoning_payload": flow_c_reasoning_payload,
                        "response_text": flow_c_reasoning_raw,
                        "structured_digest": structured_digest,
                    },
                    domain_accuracy=100.0,
                    controllability=_controllability_score(baseline_contract, baseline_deck),
                    output_quality=_output_quality_score(baseline_contract),
                )
            )

            sample_summary = {
                "expected_deterministic_core": expected_assertions.get("assertions", {}).get("deterministic_core", {}),
                "baseline_contract": baseline_contract,
                "scores": {},
                "runs": {},
            }

            for flow in ("A", "B", "C"):
                summary = _summarize_flow_case(sample_runs[flow])
                sample_summary["scores"][flow] = summary
                sample_summary["runs"][flow] = [
                    {
                        "run_index": run.run_index,
                        "contract": run.contract,
                        "domain_accuracy": run.domain_accuracy,
                        "controllability": run.controllability,
                        "output_quality": run.output_quality,
                        "raw_output": run.raw_output,
                    }
                    for run in sample_runs[flow]
                ]
                aggregated[flow].append(summary)

            raw_results["samples"][case_name] = sample_summary

    finally:
        await llm.disconnect()

    flow_summary = {}
    for flow in ("A", "B", "C"):
        items = aggregated[flow]
        flow_summary[flow] = {
            "flow": FLOW_LABELS[flow],
            "domain_accuracy": round(mean(item["domain_accuracy"] for item in items), 1),
            "consistency": round(mean(item["consistency"] for item in items), 1),
            "controllability": round(mean(item["controllability"] for item in items), 1),
            "output_quality": round(mean(item["output_quality"] for item in items), 1),
        }
    raw_results["flow_summary"] = flow_summary

    json_path = ARTIFACT_DIR / f"consulting_flow_compare_{timestamp}.json"
    json_path.write_text(json.dumps(raw_results, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Consulting Flow Comparison",
        "",
        f"- generated_at_utc: {raw_results['generated_at_utc']}",
        f"- json: {json_path}",
        "",
        "## Aggregate Scores",
        "",
        "| Flow | domain accuracy | consistency | controllability | output quality |",
        "|---|---:|---:|---:|---:|",
    ]
    for flow in ("A", "B", "C"):
        item = flow_summary[flow]
        lines.append(
            f"| {flow} | {item['domain_accuracy']} | {item['consistency']} | "
            f"{item['controllability']} | {item['output_quality']} |"
        )
    lines.append("")
    lines.append("## Per Sample")
    lines.append("")
    for case_name in SAMPLES:
        lines.append(f"### {case_name}")
        lines.append("")
        lines.append("| Flow | domain accuracy | consistency | controllability | output quality |")
        lines.append("|---|---:|---:|---:|---:|")
        for flow in ("A", "B", "C"):
            item = raw_results["samples"][case_name]["scores"][flow]
            lines.append(
                f"| {flow} | {item['domain_accuracy']} | {item['consistency']} | "
                f"{item['controllability']} | {item['output_quality']} |"
            )
        lines.append("")
    markdown_path = ARTIFACT_DIR / f"consulting_flow_compare_{timestamp}.md"
    markdown_path.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"json": str(json_path), "markdown": str(markdown_path), "flow_summary": flow_summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
