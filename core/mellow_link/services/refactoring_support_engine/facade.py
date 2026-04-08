from __future__ import annotations

from typing import Any

from .decision_engine import DecisionEngine
from .diagnosis_engine import DiagnosisEngine
from .improvement_planner import ImprovementPlanner
from .input_assembler import InputAssembler
from .policies import load_engine_policy_bundle
from .result_packager import ResultPackager
from .structure_analyzer import StructureAnalyzer


class RefactoringSupportEngineFacade:
    def __init__(self, legacy_service: Any) -> None:
        self.legacy_service = legacy_service
        self.policy_bundle = load_engine_policy_bundle()
        self.input_assembler = InputAssembler()
        self.structure_analyzer = StructureAnalyzer()
        self.diagnosis_engine = DiagnosisEngine(policy_bundle=self.policy_bundle)
        self.decision_engine = DecisionEngine(policy_bundle=self.policy_bundle)
        self.improvement_planner = ImprovementPlanner()
        self.result_packager = ResultPackager()

    def build_result(self, prepared: Any):
        analysis_input = self.input_assembler.assemble(prepared)
        structure = self.structure_analyzer.analyze(analysis_input)
        diagnosis = self.diagnosis_engine.run(prepared, structure, self.legacy_service)
        decisions = self.decision_engine.run(prepared, structure, diagnosis)
        improvement = self.improvement_planner.run(prepared, structure, diagnosis, decisions)
        return self.result_packager.package(prepared, structure, diagnosis, decisions, improvement, self.legacy_service)
