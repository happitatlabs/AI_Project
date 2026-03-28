# Anonymization MVP Status

기준일: 2026-03-25  
상태: 아키텍처 기준 합격, 이후 단계는 기능 품질 보강

## 1. 현재 위치

익명화 MVP는 독립 앱이 아니라 [`mellow_link/services/anonymization`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/services/anonymization) 아래의 공통 보안/전처리 서비스다.

첫 소비자는 [`rebuild_assistant`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant)이며, 공개 제품 흐름에서는 아래 순서를 따른다.

1. 프로젝트 생성
2. 자산 업로드
3. 익명화 전처리
4. `SafeAnalysisBundle` 생성
5. `rebuild_assistant` 분석
6. 결과 패키지 출력

## 2. 고정 규칙

- canonical source는 반드시 익명화 완료본이다.
- 구조 추출은 원본이 아니라 canonical anonymized source 기준으로만 수행한다.
- `rebuild_assistant`는 raw text/direct file path를 입력으로 받지 않고 `SafeAnalysisBundle`만 소비한다.
- original content, original path, mapping 정보는 HTTP 응답, 로그, 예외 메시지, 결과 패키지에 노출하지 않는다.
- storage 물리 경로는 코드 하드코딩이 아니라 [`settings.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/config/settings.py)의 `anonymization_storage_root` 설정으로 관리한다.
- `FULL`은 canonical internal analysis source이며, 외부 반출 허용 여부는 masking level과 별도 정책으로 관리한다.

## 3. 현재 패키지 구조

```text
mellow_link/services/anonymization
├─ __init__.py
├─ schemas.py
├─ service.py
├─ storage.py
├─ tokenizer.py
├─ mapper.py
├─ structure_extractor.py
├─ masking_levels.py
├─ masking_policy.py
├─ bundle_builder.py
└─ export_service.py
```

책임 분리는 다음과 같다.

- `service.py`
  - orchestration facade only
- `storage.py`
  - 저장/경로 해석/접근 제어
- `tokenizer.py`
  - 토큰 분리
- `mapper.py`
  - 식별자 매핑 생성
- `structure_extractor.py`
  - canonical source 기준 구조 추출
- `masking_policy.py`
  - 레벨별 정책 적용
- `bundle_builder.py`
  - `SafeAnalysisBundle` 조립
- `export_service.py`
  - 외부 제공용 public export 생성

## 4. SafeAnalysisBundle 경계

`SafeAnalysisBundle`은 아래 정보만 포함한다.

- `asset_summary`
- `sources`
- `structures`
- `guard`

포함하지 않는 정보:

- original content
- original file path
- mapping content
- mapping path

`asset_summary`는 [`BundleAssetSummary`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/services/anonymization/schemas.py) 타입을 사용하며, 원문 관련 필드가 아예 존재하지 않는다.

## 5. export 정책

public export는 [`PublicExportBundle`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/services/anonymization/schemas.py) 계열 스키마만 사용한다.

- `PublicExportSource`
- `PublicExportStructure`
- `PublicExportBundle`

기본 공개 정책:

- `FULL`: 외부 API 비공개
- `PARTIAL`: 외부 제공 가능
- `FULL_MASKED`: 외부 제공 가능

즉, `masking level`과 `download visibility`는 같은 개념이 아니다.

## 6. 현재 공개 실행선

현재 기본 실행선은 project-scoped 라우트 기준이다.

- [`/projects/create`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/static/projects_create.html)
- [`POST /projects/{id}/run`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/routers/projects.py)

공개 raw rebuild 경로는 차단되어 있다.

- `POST /modules/rebuild_assistant/runs`
  - 403 반환
  - 공개 실행선 아님

모듈 단독 UI도 raw 실행 대신 프로젝트 기반 흐름만 안내한다.

## 7. 남아 있는 compatibility 영역

현재 raw compatibility 흔적은 완전히 제거되지 않았다.

- [`compat.py`](/C:/Users/Hyein/ClaudeAI/AI_Project/mellow_link/modules/rebuild_assistant/compat.py)
  - migration-only
  - private test support only
  - 다음 cleanup phase에서 제거 대상

현재 원칙은 다음과 같다.

- 새 기능은 compatibility 경로를 사용하지 않는다.
- compatibility 경로는 공개 API가 아니다.
- 회귀 테스트와 임시 내부 호환성 외 목적에는 사용하지 않는다.

## 8. 다음 단계

아키텍처 검토 단계는 끝났다. 다음 우선순위는 기능 품질이다.

- tokenizer/mapper 정확도 향상
- 언어별 구조 추출 정밀화
- `PARTIAL`/`FULL_MASKED` 품질 보강
- 자산 간 연결 분석 품질 향상
- 결과 패키지 설명력 향상
