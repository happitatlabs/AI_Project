from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from mellow_link.services.project_results.archive import persist_project_result_archive


class _RecordingLogger:
    def __init__(self) -> None:
        self.warnings: list[tuple[object, ...]] = []

    def warning(self, *args: object) -> None:
        self.warnings.append(args)


@pytest.mark.asyncio
async def test_project_result_archive_uses_deterministic_paths_and_reopenable_docx(
    tmp_path: Path,
):
    project = SimpleNamespace(id="proj_pilot_delivery")
    generated_path = tmp_path / "generated.docx"
    generated = Document()
    generated.add_heading("현대화 판단 보고서", level=1)
    generated.add_paragraph("프로젝트 결과 보관 검증")
    generated.save(generated_path)
    logger = _RecordingLogger()

    async def generate_docx(*args, **kwargs):
        return generated_path, "pilot-result.docx"

    result = await persist_project_result_archive(
        project,
        run_id="run_pilot_delivery",
        db=object(),
        archive_root=tmp_path / "archive",
        logger=logger,
        get_run_snapshot_fn=lambda *args, **kwargs: {"status": "completed"},
        get_run_events_fn=lambda *args, **kwargs: [{"type": "run_finished"}],
        extract_structured_result_fn=lambda events: {"status": "completed"},
        build_assets_payload_fn=lambda *args, **kwargs: [],
        build_result_package_fn=lambda *args, **kwargs: {},
        extract_polish_bundle_fn=lambda *args, **kwargs: None,
        result_package_markdown_fn=lambda *args, **kwargs: "# 현대화 판단 보고서\n",
        generate_result_package_docx_fn=generate_docx,
        result_package={"provenance": {"run_id": "run_pilot_delivery"}},
    )

    expected_dir = tmp_path / "archive" / "proj_pilot_delivery" / "run_pilot_delivery"
    expected_markdown = expected_dir / "result.md"
    expected_docx = expected_dir / "result.docx"

    assert result == {
        "markdown_path": str(expected_markdown),
        "docx_path": str(expected_docx),
    }
    assert expected_markdown.read_text(encoding="utf-8") == "# 현대화 판단 보고서\n"
    assert expected_docx.is_file()
    reopened = Document(expected_docx)
    assert reopened.paragraphs[0].text == "현대화 판단 보고서"
    assert logger.warnings == []
