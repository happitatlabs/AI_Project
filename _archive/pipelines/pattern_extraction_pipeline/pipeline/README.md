# Pattern Extraction Pipeline

익명화된 SQL 자산에서 실무 패턴을 추출해 추천 엔진이 사용할 학습 재료로 저장하는 최소 실행 골격입니다.

## 구성 단계

1. `input_loader`: SQL 입력 로드
2. `normalizer`: SQL 포맷 정리
3. `pattern_extractor`: 패턴 추출 및 evidence 수집
4. `pattern_serializer`: 결과 JSON 저장
5. `training_bundle_builder`: 결과를 bundle로 묶기

## 결과 스키마

```json
{
  "source_id": "string",
  "normalized_sql": "string",
  "patterns": [
    {
      "type": "string",
      "description": "string",
      "evidence": ["string"]
    }
  ]
}
```

## 실행 방법

프로젝트 루트에서:

```powershell
python pattern_extraction_pipeline/pipeline/main.py
```

또는 `pipeline` 디렉터리에서:

```powershell
python main.py
```

실행 후 `pipeline/output/` 아래에 패턴 결과 JSON과 training bundle JSON이 생성됩니다.
