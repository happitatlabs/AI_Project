"""
evaluator.py — 행동 결과 평가 시스템

역할:
- 각 행동의 실행 결과를 점수(score)로 평가
- 성공/실패/개선 여부를 기록
- 누적 통계를 통한 에이전트 성능 추적
"""

from datetime import datetime


class Evaluator:
    @staticmethod
    def _merge_meta(action: dict, result: dict, previous_state: dict) -> dict:
        meta = dict(result.get("meta", {}))
        action_source = meta.get("action_source") or action.get("action_source")
        if not action_source:
            action_source = "fallback" if action.get("source") == "cooldown_fallback" else "normal"
        state_diff = meta.get("state_diff", {})
        state_snapshot = result.get("state_snapshot", {})
        if not state_diff and (state_snapshot or previous_state):
            prev_files = set(previous_state.get("decision_files", previous_state.get("files", [])))
            curr_files = set(state_snapshot.get("decision_files", state_snapshot.get("files", [])))
            state_diff = {
                "decision_changed": curr_files != prev_files,
                "external_changed": curr_files != prev_files,
                "self_artifact_changed": False,
            }
        work_type = (
            meta.get("work_type")
            or action.get("skill_name")
            or action.get("fallback_kind")
            or action.get("type")
        )
        merged = {
            "action_source": action_source,
            "is_normal_skill": meta.get("is_normal_skill", action.get("type") == "skill" and action_source in {"normal", "cooldown_reopen"}),
            "output_created": meta.get("output_created", bool(result.get("report_file") or result.get("created_file"))),
            "new_insight": meta.get("new_insight", False),
            "specific_findings": meta.get("specific_findings", False),
            "decision_changed": meta.get("decision_changed", state_diff.get("decision_changed", False)),
            "self_artifact_changed": meta.get("self_artifact_changed", state_diff.get("self_artifact_changed", False)),
            "external_changed": meta.get("external_changed", state_diff.get("external_changed", False)),
            "is_skip_or_noop": meta.get("is_skip_or_noop", bool(result.get("report_skipped")) or action.get("type") in {"noop", "wait"}),
            "work_type": work_type,
            "work_type_changed": meta.get("work_type_changed", True),
            "recent_fallback_count": meta.get("recent_fallback_count", 0),
        }
        return merged

    @staticmethod
    def _grade_for_score(score: int) -> tuple[str, str]:
        if score >= 85:
            return "high-value success", "success"
        if score >= 70:
            return "useful success", "success"
        if score >= 55:
            return "low-value success", "partial"
        if score >= 40:
            return "weak / near-noop", "partial"
        return "fail or invalid", "failure"

    def evaluate(self, action: dict, result: dict, previous_state: dict) -> dict:
        """
        행동과 그 결과를 평가하여 점수를 매긴다.

        반환 구조:
        {
            "score": 0~100,
            "status": "success" | "failure" | "partial",
            "improvement": bool,
            "reason": str,
            "metrics": dict
        }
        """
        reasons: list[str] = []
        metrics = {}
        meta = self._merge_meta(action, result, previous_state)

        if result.get("success"):
            score = 35 if meta["is_skip_or_noop"] else 50
            reasons.append("실행 성공" if not meta["is_skip_or_noop"] else "실행은 되었으나 skip/noop 성격")
        else:
            reasons.append(f"실행 실패: {result.get('error', 'unknown')}")
            return {
                "score": 20,
                "status": "failure",
                "grade": "fail or invalid",
                "improvement": False,
                "reason": "; ".join(reasons),
                "reasons": reasons,
                "metrics": metrics,
                "evaluated_at": datetime.now().isoformat(),
            }

        output = result.get("output", "")
        if output:
            score += 10
            reasons.append("출력 생성됨")
        metrics["output_length"] = len(output)

        elapsed = result.get("elapsed_seconds", 999)
        if elapsed < 1.0:
            score += 5
            reasons.append("빠른 실행")
        elif elapsed < 5.0:
            score += 3
            reasons.append("적절한 실행 속도")
        metrics["elapsed_seconds"] = elapsed

        if meta["external_changed"]:
            score += 10
            reasons.append("외부 상태 변화 반영")
        if meta["new_insight"]:
            score += 10
            reasons.append("새 인사이트 포함")
        if meta["specific_findings"]:
            score += 5
            reasons.append("구체 경로/파일 단위 관찰 포함")
        if meta["is_normal_skill"]:
            score += 5
            reasons.append("정상 스킬 실행")
        if meta["work_type_changed"]:
            score += 5
            reasons.append("최근과 다른 작업 유형 수행")

        if meta["self_artifact_changed"] and not meta["external_changed"]:
            score -= 15
            reasons.append("self artifact 변화만 감지")
        if meta["is_skip_or_noop"]:
            score -= 15
            reasons.append("skip/no-op 결과")
        if meta["action_source"] == "fallback" and meta["recent_fallback_count"] >= 2:
            score -= 10
            reasons.append("fallback 연속 실행")
        if meta["output_created"] and not meta["external_changed"] and not meta["new_insight"]:
            score -= 10
            reasons.append("외부 변화/새 인사이트 없이 출력만 생성")

        score = max(0, min(score, 100))
        grade, status = self._grade_for_score(score)
        improvement = score >= 70

        metrics.update({
            "decision_changed": meta["decision_changed"],
            "self_artifact_changed": meta["self_artifact_changed"],
            "external_changed": meta["external_changed"],
            "action_source": meta["action_source"],
            "work_type": meta["work_type"],
        })

        return {
            "score": score,
            "status": status,
            "grade": grade,
            "improvement": improvement,
            "reason": "; ".join(reasons),
            "reasons": reasons,
            "metrics": metrics,
            "evaluated_at": datetime.now().isoformat(),
        }

    def compute_trend(self, history: list[dict], window: int = 5) -> dict:
        """최근 히스토리에서 점수 추세를 계산."""
        recent = history[-window:] if history else []
        scores = [
            h.get("evaluation", {}).get("score", 0)
            for h in recent
            if "evaluation" in h
        ]

        if not scores:
            return {"trend": "no_data", "avg_score": 0, "samples": 0}

        avg = sum(scores) / len(scores)

        if len(scores) >= 2:
            first_half = sum(scores[: len(scores) // 2]) / max(len(scores) // 2, 1)
            second_half = sum(scores[len(scores) // 2 :]) / max(len(scores) - len(scores) // 2, 1)
            if second_half > first_half + 5:
                trend = "improving"
            elif second_half < first_half - 5:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient"

        return {
            "trend": trend,
            "avg_score": round(avg, 1),
            "samples": len(scores),
            "recent_scores": scores,
        }
