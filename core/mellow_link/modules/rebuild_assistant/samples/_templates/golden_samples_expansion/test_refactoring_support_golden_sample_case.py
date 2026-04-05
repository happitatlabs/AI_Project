"""샘플별 golden regression test 스텁.

사용 방법:
1. sample 폴더의 input_manifest.json, expected_assertions.yaml을 채운다.
2. 엔진 실행 fixture와 연결한다.
3. deterministic core 비교를 우선 잠근다.
"""

from pathlib import Path
import json
import yaml


def load_case(case_dir: Path):
    manifest = json.loads((case_dir / "input_manifest.json").read_text(encoding="utf-8"))
    expected = yaml.safe_load((case_dir / "expected_assertions.yaml").read_text(encoding="utf-8"))
    return manifest, expected


def test_golden_sample_case_template():
    case_dir = Path(__file__).parent / "sample_xx"
    if not case_dir.exists():
        # 실제 샘플 생성 후 경로를 교체하세요.
        assert True
        return

    manifest, expected = load_case(case_dir)

    # TODO: 실제 엔진 실행 fixture 연결
    result = {
        "primary_judgment": expected["assertions"]["deterministic_core"]["primary_judgment"],
        "recommended_strategy": expected["assertions"]["deterministic_core"]["recommended_strategy"],
    }

    assert result["primary_judgment"] == expected["assertions"]["deterministic_core"]["primary_judgment"]
    assert result["recommended_strategy"] == expected["assertions"]["deterministic_core"]["recommended_strategy"]
