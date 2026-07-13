from __future__ import annotations

import zipfile
from pathlib import Path

SAMPLES_DIR = (
    Path(__file__).resolve().parents[1] / "modules" / "rebuild_assistant" / "samples"
)
PILOT_DIR = SAMPLES_DIR / "pilot_demo"
SAMPLE_A_DIR = PILOT_DIR / "sample_a_legacy_order_review"
SAMPLE_B_DIR = PILOT_DIR / "sample_b_consulting_ppt_review"

EXPECTED_OUTLINE_SECTIONS = [
    "## 1. 1페이지 요약",
    "## 2. 분석 범위와 입력 자료",
    "## 3. 현행 구조/업무 흐름 요약",
    "## 4. 핵심 문제",
    "## 5. 개선 선택지",
    "## 6. 권장안",
    "## 7. 리스크와 검토 필요 사항",
    "## 8. 단계별 실행 준비 계획",
    "## 9. 분석 근거와 provenance",
]

SAMPLE_B_FORBIDDEN_TERMS = [
    "원가",
    "회계",
    "제조 원가",
    "원가계산",
    "배부기준",
    "배부 기준",
    "재료비",
    "노무비",
    "제조경비",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_pptx_xml_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        chunks = []
        for name in archive.namelist():
            if name.endswith(".xml"):
                chunks.append(archive.read(name).decode("utf-8", errors="ignore"))
        return "\n".join(chunks)


def test_pilot_demo_sample_paths_and_required_documents_exist():
    assert PILOT_DIR.is_dir()
    assert SAMPLE_A_DIR.is_dir()
    assert SAMPLE_B_DIR.is_dir()

    for sample_dir in (SAMPLE_A_DIR, SAMPLE_B_DIR):
        assert (sample_dir / "README.md").is_file()
        assert (sample_dir / "expected_report_outline.md").is_file()


def test_expected_report_outlines_use_fixed_section_structure():
    for sample_dir in (SAMPLE_A_DIR, SAMPLE_B_DIR):
        outline = _read_text(sample_dir / "expected_report_outline.md")
        assert outline.startswith("# 기대 보고서 개요")
        for section in EXPECTED_OUTLINE_SECTIONS:
            assert section in outline


def test_sample_a_contains_legacy_order_code_sql_and_schema_assets():
    assert (SAMPLE_A_DIR / "business_overview.md").is_file()
    assert (SAMPLE_A_DIR / "schema.sql").is_file()

    sql_files = sorted((SAMPLE_A_DIR / "sql").glob("*.sql"))
    code_files = sorted((SAMPLE_A_DIR / "code").glob("*.java"))

    assert len(sql_files) >= 3
    assert len(code_files) >= 1

    schema = _read_text(SAMPLE_A_DIR / "schema.sql")
    assert schema.count("CREATE TABLE") == 5
    assert "FOREIGN KEY" in schema
    assert "LEGACY_ORDER" in schema
    assert "There is no dedicated order status history table" in schema

    repository = _read_text(SAMPLE_A_DIR / "code" / "OrderRepository.java")
    for sql_file in sql_files:
        assert f"sql/{sql_file.name}" in repository


def test_sample_b_contains_slide_markdown_and_pptx_assets():
    slides_path = SAMPLE_B_DIR / "slides.md"
    pptx_path = SAMPLE_B_DIR / "sample_b_consulting_ppt_review.pptx"

    assert slides_path.is_file()
    assert pptx_path.is_file()

    slides = _read_text(slides_path)
    assert slides.count("\n## ") == 12
    assert "## 1. 표지" in slides
    assert "## 10. 단계별 추진 계획" in slides

    with zipfile.ZipFile(pptx_path) as archive:
        slide_xml_files = [
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        ]
    assert len(slide_xml_files) == 12


def test_sample_b_forbidden_domain_terms_are_absent_from_input_materials():
    text_chunks = []
    for path in SAMPLE_B_DIR.glob("*.md"):
        text_chunks.append(_read_text(path))
    text_chunks.append(
        _read_pptx_xml_text(SAMPLE_B_DIR / "sample_b_consulting_ppt_review.pptx")
    )
    combined = "\n".join(text_chunks)

    for term in SAMPLE_B_FORBIDDEN_TERMS:
        assert term not in combined
