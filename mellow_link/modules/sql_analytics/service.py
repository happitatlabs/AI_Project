from __future__ import annotations

import sys
from pathlib import Path

_SQL_ENGINE_ROOT = Path(__file__).resolve().parents[2] / "sql_ai_decision_engine"
if str(_SQL_ENGINE_ROOT) not in sys.path:
    sys.path.append(str(_SQL_ENGINE_ROOT))

from app.schemas.request import AnalyzeRequest
from app.services.analysis_pipeline import AnalysisPipeline


class SQLAnalyticsService:
    def __init__(self) -> None:
        self._pipeline = AnalysisPipeline()

    def analyze(self, question: str, input_type: str = "natural_language") -> dict:
        req = AnalyzeRequest(question=question, input_type=input_type)
        return self._pipeline.run(req)
