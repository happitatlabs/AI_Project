from __future__ import annotations

from typing import Any

from .decision_engine import DecisionEngine
from .diagnosis_engine import DiagnosisEngine
from .improvement_planner import ImprovementPlanner
from .input_assembler import InputAssembler
from .policies import load_engine_policy_bundle
from .result_packager import ResultPackager
from .runtime_contracts import build_stage_control, enter_stage
from .structure_analyzer import StructureAnalyzer
from .validation_engine import ValidationEngine


class RefactoringSupportEngineFacade:
    def __init__(self, legacy_service: Any) -> None:
        self.legacy_service = legacy_service
        self.policy_bundle = load_engine_policy_bundle()
        self.input_assembler = InputAssembler()
        self.structure_analyzer = StructureAnalyzer()
        self.diagnosis_engine = DiagnosisEngine(policy_bundle=self.policy_bundle)
        self.decision_engine = DecisionEngine(policy_bundle=self.policy_bundle)
        self.validation_engine = ValidationEngine()
        self.improvement_planner = ImprovementPlanner()
        self.result_packager = ResultPackager()

    def build_result(self, prepared: Any):
        stage_control = getattr(prepared, "stage_control", None) or build_stage_control(
            str(getattr(prepared, "goal", "") or "")
        )
        prepared.stage_control = stage_control

        enter_stage(stage_control, "analysis")
        analysis_input = self.input_assembler.assemble(prepared, stage_control=stage_control)
        structure = self.structure_analyzer.analyze(analysis_input, stage_control=stage_control)

        enter_stage(stage_control, "diagnosis")
        diagnosis = self.diagnosis_engine.run(
            prepared,
            structure,
            self.legacy_service,
            stage_control=stage_control,
        )

        enter_stage(stage_control, "decision")
        decisions = self.decision_engine.run(
            prepared,
            structure,
            diagnosis,
            self.legacy_service,
            stage_control=stage_control,
        )
        validation_result = self.validation_engine.validate_decision(
            prepared=prepared,
            diagnosis=diagnosis,
            decisions=decisions,
            stage_control=stage_control,
        )
        if validation_result["status"] == "fail":
            enter_stage(stage_control, "decision")
            decisions = self.decision_engine.run(
                prepared,
                structure,
                diagnosis,
                self.legacy_service,
                stage_control=stage_control,
                retry_hint=str(validation_result.get("retry_hint") or ""),
            )
            validation_result = self.validation_engine.validate_decision(
                prepared=prepared,
                diagnosis=diagnosis,
                decisions=decisions,
                stage_control=stage_control,
            )
            if validation_result["status"] == "fail":
                failure_types = ", ".join(validation_result.get("failure_types") or [])
                raise ValueError(f"validation failed after single retry: {failure_types or 'unknown_failure'}")

        enter_stage(stage_control, "planning")
        improvement = self.improvement_planner.run(
            prepared,
            structure,
            diagnosis,
            decisions,
            stage_control=stage_control,
        )
        return self.result_packager.package(
            prepared,
            structure,
            diagnosis,
            decisions,
            improvement,
            self.legacy_service,
            stage_control=stage_control,
            validation_result=validation_result,
        )
