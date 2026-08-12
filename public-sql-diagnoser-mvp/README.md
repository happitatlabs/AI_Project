# SQL Explainer MVP

SQL Explainer는 레거시 시스템 분석을 돕기 위한 룰 기반 SQL 설명기입니다. 사용자가 SQL 하나를 입력하면 테이블, JOIN, 조건, 집계, CTE, 윈도우 함수, CASE 문 등을 구조화해 추출하고, 신규 개발자가 이해하기 쉬운 한국어 설명과 복사 가능한 보고서를 생성합니다.

기본 분석은 AI 없이 동작합니다. AI 기능은 선택적으로 호출하는 설명 보강 레이어이며, 기존 룰 기반 분석 결과를 대체하지 않습니다.

## 주요 기능

- SQL 입력 및 즉시 분석
- 단건 SQL / 다건 SQL 분석 모드
- 테이블 중심 자산 지도 생성
- 시스템 의존성 지도와 영향도 분석
- 보고서 / 문서화 산출물 생성
- 리스크 / 개선 포인트 탐지
- 사용 테이블과 alias 추출
- JOIN 관계 및 WHERE 기반 관계 조건 추정
- CTE 처리 흐름과 단계별 필터 분석
- WHERE / HAVING 조건 분석
- GROUP BY 기준과 집계 지표 분석
- 윈도우 함수 분석
- CASE WHEN 분류 기준 분석
- 서브쿼리 탐지
- UNION / EXCEPT / INTERSECT 계열 SET 연산 탐지
- INSERT INTO SELECT 배치성 SQL 판별
- 업무 목적 추론
- 분석 신뢰도와 warnings 출력
- 복사 가능한 분석 보고서 생성
- 예제 SQL 프리셋 제공
- 선택형 AI 설명 보강
- 단건 AI 문서 초안 생성
- 다건 AI 문서 초안 생성
- CSV / JSON 기반 데이터 인사이트 계산
- 선택형 AI 데이터 인사이트 해석

## 분석 가능한 SQL 요소

- 테이블: 일반 테이블, schema.table, quoted identifier 일부 지원
- JOIN: INNER / LEFT / RIGHT / FULL JOIN 및 WHERE 기반 관계 조건
- CTE: WITH 절 이름, 의존 관계, 단계별 역할
- WHERE: 최종 SELECT 및 CTE 내부 조건
- HAVING: GROUP BY 이후 집계 결과 필터
- GROUP BY: 집계 기준 컬럼
- 집계 함수: COUNT, SUM, AVG, MIN, MAX
- 윈도우 함수: SUM/AVG/LAG/RANK/ROW_NUMBER 등 OVER 절 기반 함수
- CASE 문: CASE WHEN 조건과 라벨
- 서브쿼리: EXISTS, IN, scalar subquery, derived table 탐지
- SET 연산: UNION, UNION ALL, EXCEPT, INTERSECT
- INSERT INTO SELECT: 조회 결과 적재/배치성 SQL

## 데이터 인사이트 계산 계층

`데이터 인사이트` 모드는 SQL 구조 분석과 별도로, CSV 또는 JSON 행 데이터를 브라우저에서 기계식으로 계산하는 기능입니다. 목적은 숫자는 프로그램이 계산하고, AI는 검증 가능한 계산 결과의 의미만 해석하도록 역할을 분리하는 것입니다.

처리 흐름은 다음과 같습니다.

```text
CSV / JSON 원본 행 데이터
-> 브라우저 내 기계식 계산
-> 검증 가능한 계산 결과와 인사이트 후보
-> 선택 실행 AI 해석
-> 사실 / 해석 / 확인 필요 사항 / 제안 보고서
```

사용자는 숫자 지표 컬럼을 선택하고, 필요하면 시간 컬럼과 그룹 컬럼을 선택합니다. 프로그램은 다음을 직접 계산합니다.

- 계산 대상 건수, 합계, 평균, 최대값, 최소값
- 기간별 값과 이전 기간 대비 증감률
- 그룹별 합계, 전체 비중, 그룹 평균 대비 차이
- IQR 또는 Z-score 기반 이상치 후보
- 변화폭, 지속성, 그룹 차이, 이상치 여부를 근거로 한 중요도 후보

`ComputedAnalysisResult`에는 계약 버전과 계산 기준도 포함됩니다. 계산 기준에는 입력/계산/제외 행 수, 기간 범위와 단위, 그룹 비교 기준, IQR·Z-score 임계값, 반복 주기 미평가 여부가 기록됩니다. 따라서 AI는 계산 방법을 바꾸거나, 반복 주기·계절성처럼 계산하지 않은 내용을 단정할 수 없습니다.

AI는 원본 행 데이터를 받지 않습니다. `/api/ai-data-insights`에는 원본 행이 없는 `ComputedAnalysisResult`만 전달되고, 서버는 `rows` 필드 또는 유효하지 않은 계산 계약을 포함한 요청을 거부합니다. AI provider로는 마스킹된 범주 정보, 계산된 수치, 근거 ID, 계산 기준, 후보 우선순위만 전송합니다. AI는 후보를 선택해 해석·확인 필요 사항·제안만 작성하며, 표시되는 사실과 숫자는 프로그램이 계산한 결과를 사용합니다.

데이터 분석 Markdown 보고서는 다음 순서로 생성됩니다.

- 분석 개요와 데이터 범위
- 계산 기준과 핵심 지표
- 중요도 상위 3개 이내의 주요 인사이트
- 기계식 추세·비교·이상치 근거
- 결론과 주의 사항

입력 데이터는 최대 20,000행까지 계산합니다. 현재 시간 추세는 `YYYY-MM`, `YYYY-MM-DD` 등 일반적인 날짜/월 형식에 한정되며, 중첩 JSON, 복잡한 날짜 형식, 통계적 인과 검증은 지원 범위가 아닙니다.

## 다건 SQL 분석

다건 SQL 모드는 여러 SQL을 붙여넣고 한 번에 분석하는 기능입니다. 세미콜론(`;`)을 기준으로 SQL을 분리하되, 문자열 리터럴이나 주석 안의 세미콜론은 분리 기준으로 사용하지 않도록 방어합니다.

다건 분석 결과:

- SQL별 분석 요약
- 테이블별 사용 횟수
- 반복 JOIN 관계
- 반복 WHERE / HAVING 조건 패턴
- 핵심 테이블 후보
- 테이블별 사용 SQL, JOIN 대상, 주요 조건, 업무 추정
- 시스템 지도: 테이블 관계, SQL 의존성, CTE 흐름, 적재 흐름
- 선택 노드 기준 상위 의존 / 하위 영향 분석
- Markdown 보고서 다운로드
- PDF 저장용 인쇄 보고서
- Excel용 테이블 사용 현황 CSV 다운로드
- Notion / Confluence 붙여넣기용 문서 생성
- 다건 AI 설명 보강
- 다건 AI 문서 초안 생성
- AI 설명 보강 결과 포함 옵션
- SQL 리스크 finding 탐지
- 리스크 findings CSV 다운로드
- 업무 목적 분포
- 다건 분석 Markdown 보고서

이 기능은 여러 SQL을 개별 설명하는 데서 끝나지 않고, 레거시 시스템의 테이블 사용 패턴과 반복 관계를 찾기 위한 기반입니다.

## 테이블 중심 자산 지도

테이블 자산 지도는 SQL 목록을 테이블 기준으로 재구성합니다. 레거시 시스템을 볼 때 “어떤 SQL이 있나”보다 “어떤 테이블이 핵심이고 어디에 연결되나”를 먼저 파악하기 위한 Phase 3 기능입니다.

현재 제공 항목:

- 테이블 목록 자동 생성
- 테이블별 사용 SQL 보기
- 테이블별 JOIN 대상 보기
- 테이블별 주요 WHERE / HAVING 조건 보기
- 테이블별 업무 추정 표시
- 핵심 테이블 후보 표시
- INSERT INTO 대상 테이블 표시

핵심 테이블 후보는 사용 SQL 수, JOIN 대상 수, 조건 반복, 업무 목적 다양성, INSERT 대상 여부 등을 점수화해 추정합니다. 이 점수는 설계 검토를 돕는 힌트이며 실제 업무 중요도를 단정하지 않습니다.

## 시스템 의존성 지도

시스템 지도는 여러 SQL 분석 결과를 노드와 엣지 구조로 재구성합니다. 화면에서는 보기 모드를 바꿔 관계를 좁혀 볼 수 있습니다.

지원 보기:

- 전체 지도: SQL, 테이블, CTE, View, Procedure 후보 간 주요 연결
- 테이블 관계: JOIN과 적재 흐름 중심의 테이블 간 연결
- SQL 의존성: SQL이 읽는 테이블과 쓰는 테이블
- CTE 흐름: CTE 단계와 CTE 의존 관계
- 적재 흐름: INSERT INTO SELECT와 View 정의 기반 변환 흐름

선택한 노드에 대해서는 다음을 표시합니다.

- 관련 SQL
- 중요도와 분석 신뢰도
- 상위 의존 관계
- 하위 영향 관계
- 정규식 기반 추정에 따른 주의사항

View는 `CREATE VIEW ... AS SELECT ...` 형태를 감지해 View 노드와 원천 테이블 의존성을 만듭니다. Procedure/Function/Package는 객체 노드와 내부에서 감지 가능한 SQL 관계만 부분적으로 표시하며, 동적 SQL은 누락될 수 있습니다.

## 보고서 / 문서화

보고서 기능은 다건 SQL 분석 결과, 테이블 자산 지도, 시스템 의존성 지도를 공통 보고서 모델로 재구성한 뒤 여러 형식으로 내보냅니다.

지원 산출물:

- Markdown 보고서 다운로드
- PDF 저장용 인쇄 HTML 보고서 열기
- Excel에서 열 수 있는 테이블 사용 현황 CSV 다운로드
- Notion용 Markdown 복사
- Confluence용 문서 복사

보고서 포함 옵션:

- 테이블 자산 지도 포함
- 시스템 지도 포함
- warnings 포함
- 원본 SQL 포함
- AI 설명 보강 결과 포함

보고서 주요 섹션:

- 분석 대상 요약
- Executive Summary
- 사용 테이블 목록
- 주요 JOIN 관계
- SQL별 요약
- 업무 목적 분류
- 위험 SQL 목록
- 시스템 지도 요약
- 신규 개발자 설명
- 주의 사항

위험 SQL 목록은 분석 신뢰도, warnings 수, INSERT INTO SELECT, Procedure 포함 여부, JOIN/테이블 수, 서브쿼리, SET 연산, WHERE 조건 부재 등을 기준으로 점수화합니다. 이 점수는 검토 우선순위를 정하기 위한 힌트이며 실제 운영 위험도를 확정하지 않습니다.

## 리스크 / 개선 포인트

리스크 탐지는 SQL 설명 결과 위에 유지보수와 운영 검토 포인트를 추가합니다. 각 finding은 심각도, 근거, 추천 개선, 신뢰도를 포함합니다.

탐지 항목:

- `SELECT *`
- WHERE 없는 `UPDATE` / `DELETE`
- 암묵적 JOIN
- 너무 많은 JOIN
- 중복 SQL 패턴
- WHERE 조건의 날짜 컬럼 함수 사용
- `LIKE '%keyword%'`
- GROUP BY 없는 집계 의심
- 하드코딩 코드값
- 개인정보 조건 사용 가능성

다건 SQL 분석 화면에서는 Critical/High/Medium/Low 요약과 심각도 필터를 제공합니다. 보고서에는 `리스크 / 개선 포인트` 섹션이 추가되며, `sql-risk-findings.csv`로도 다운로드할 수 있습니다.

오탐 방지 기준:

- 단독 `COUNT(*)`는 GROUP BY 없는 집계 리스크로 보지 않습니다.
- SELECT 절의 날짜 함수는 WHERE/JOIN 조건의 인덱스 리스크로 단정하지 않습니다.
- 개인정보 조건은 컬럼명 기반 추정이며 실제 개인정보 포함 여부를 단정하지 않습니다.

## 분석 신뢰도와 Warnings

`analyzeSql(sql)`은 구조화 분석 결과와 함께 `confidence`와 `warnings`를 반환합니다.

- `confidence.score`: 0.0~1.0 사이의 분석 신뢰도 점수
- `confidence.level`: `low`, `medium`, `high`
- `confidence.reasons`: 신뢰도 판단 근거
- `warnings`: 정규식 기반 분석 한계, 서브쿼리/SET 연산 단순화, 테이블명 기반 추정 등의 주의사항

예를 들어 CTE, GROUP BY, SUM 집계, RANK 윈도우 함수, CASE 문이 명확히 추출되면 신뢰도가 높아집니다. 반대로 서브쿼리, UNION, 깊은 중첩 괄호가 포함되면 일부 절 해석이 제한될 수 있어 신뢰도를 낮춥니다.

## AI 설명 보강

AI 설명 보강은 사용자가 `AI로 설명 보강하기` 버튼을 클릭할 때만 호출됩니다. 단건 SQL에서는 현재 SQL과 단건 분석 결과를, 다건 SQL에서는 SQL 묶음과 다건 분석 요약을 `/api/ai-explain` 서버 API에 전달합니다. 서버는 SQL을 `maskSensitiveSql(sql)`로 마스킹한 뒤 AI API에 요청합니다.

데이터 인사이트의 `AI로 인사이트 해석`도 선택 실행 기능입니다. 원본 CSV/JSON 행은 브라우저에서만 계산하며, AI에는 계산 결과와 근거 ID만 전달합니다. AI가 계산되지 않은 숫자나 날짜를 포함한 문장을 반환하면 해당 문장을 표시에서 제외합니다.

다건 AI 설명 보강에는 다음 집계 정보가 포함됩니다.

- SQL별 요약
- 테이블 사용 현황
- 반복 JOIN 관계
- 반복 조건 패턴
- 업무 목적 분포
- 리스크 finding 요약
- 다건 분석 warnings

## AI 문서 초안

단건 SQL에서는 `AI 문서 초안 생성`으로 팀 문서에 바로 붙여넣을 수 있는 Markdown 초안을 만들 수 있습니다. 이 기능은 기존 룰 기반 분석 결과를 기준으로 문장화와 문서 구조화를 수행하며, SQL 원문은 서버에서 다시 마스킹한 뒤 AI provider에 전달합니다.

지원 문서 유형:

- 신규 개발자 온보딩
- 운영/장애 점검
- 리팩토링 검토
- 레거시 자산 분석

문서 초안에는 제목, 개요, 대상 독자, 업무 맥락, 데이터 흐름, 핵심 테이블, 주요 조건, 위험 요약, 리팩토링 제안, 신규 개발자 메모, 불확실한 부분, 복사 가능한 Markdown이 포함됩니다.

다건 SQL에서는 `AI 다건 문서 초안 생성`으로 여러 SQL을 하나의 시스템/업무 흐름 관점에서 정리합니다. 서버는 SQL 묶음을 다시 분석해 테이블 자산 지도, 시스템 지도, 리스크 finding을 재계산한 뒤 AI provider에 전달합니다.

다건 문서 초안에는 업무 영역 요약, 시스템 맥락, 데이터 흐름 요약, 핵심 테이블, 테이블 사용 요약, JOIN 요약, SQL 그룹 요약, 위험 요약, 리팩토링 제안, 신규 개발자 온보딩 경로, 운영 체크리스트, 불확실한 부분, 복사 가능한 Markdown이 포함됩니다.

다건 보고서 옵션에서 `AI 문서 초안 포함`을 켜면 생성된 다건 초안이 Markdown, Notion, Confluence, PDF용 보고서에 포함됩니다.

지원 provider:

- `ollama`: 로컬 Ollama 서버를 호출합니다.
- `openai`: OpenAI Responses API를 호출합니다.
- `azure_openai`: Azure OpenAI Responses API를 호출합니다.

보안 원칙:

- API 키는 브라우저 번들에 포함하지 않습니다.
- API 키와 모델명은 서버 환경변수로 관리합니다.
- SQL 원문은 AI 전송 전에 마스킹합니다.
- 마스킹 후에도 테이블명, 컬럼명, JOIN 구조, 업무 흐름 같은 메타 정보는 포함될 수 있습니다.
- 민감한 운영 SQL이나 개인정보가 포함된 SQL은 입력 전 별도 확인이 필요합니다.
- AI 호출이 실패해도 룰 기반 분석 결과는 계속 표시됩니다.

## 안전한 웹 데모 배포

현재 Cloudflare Worker 배포 주소는 `https://sql-diagnoser-demo.pletta900114.workers.dev`입니다. Worker는 정적 앱과 `/api/ai-*` endpoint를 같은 origin에서 제공합니다. API 키는 브라우저와 Git 저장소에 포함하지 않습니다.

AI 데모는 비용과 악용을 막기 위해 지정한 테스트 계정이 로그인한 경우에만 활성화됩니다. `DEMO_USERNAME`, `DEMO_PASSWORD`, `DEMO_SESSION_SECRET`을 Worker secret으로 설정하면 앱에 로그인 화면이 표시됩니다. 로그인 성공 시 Worker가 `HttpOnly`, `Secure`, `SameSite=Strict` 세션 쿠키를 발급하며, `/api/ai-*` 요청은 유효한 세션 없이는 처리되지 않습니다.

`DEMO_SESSION_SECRET`은 32자 이상인 무작위 값으로 별도 설정하는 것을 권장합니다. 설정하지 않은 기존 데모는 `DEMO_PASSWORD`를 세션 서명 키로 사용해 호환되지만, 운영성 데모에서는 별도 secret을 사용해야 합니다. 현재 환경 변수 방식은 한 개의 지정 테스트 계정을 위한 방식이며, 여러 개인 계정 관리가 필요하면 Cloudflare Access 또는 별도 사용자 저장소를 추가하는 단계로 확장합니다.

Cloudflare Worker 설정:

- 빌드 명령: `npm run build`
- 배포 명령: `npx wrangler versions upload`
- 배포 디렉터리: `dist`
- Worker entry: `src/cloudflareWorker.ts`

Azure OpenAI를 사용할 때 Worker 환경 변수/비밀값은 다음처럼 설정합니다.

```text
# 일반 변수 또는 secret
AI_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com
AZURE_OPENAI_MODEL=your-deployment-name
DEMO_USERNAME=test-user

# Worker secret
AZURE_OPENAI_API_KEY=...
DEMO_PASSWORD=...
DEMO_SESSION_SECRET=long-random-session-secret
```

OpenAI를 사용할 때는 다음을 사용합니다.

```text
AI_PROVIDER=openai
OPENAI_MODEL=your-model-name
DEMO_USERNAME=test-user

# Worker secret
OPENAI_API_KEY=...
DEMO_PASSWORD=...
DEMO_SESSION_SECRET=long-random-session-secret
```

Ollama는 Cloudflare Worker에서 PC의 `http://localhost:11434`에 접근할 수 없습니다. 웹 데모에 Ollama를 연결하려면 인증으로 보호된 HTTPS endpoint가 필요합니다. 로컬 검증에는 기존처럼 `OLLAMA_BASE_URL=http://localhost:11434`와 설치된 모델을 사용하세요.

데모는 SQL을 실행하지 않고 브라우저 저장소에 SQL을 저장하지 않지만, 실제 운영 SQL·개인정보·고객 식별값은 입력하지 않습니다. AI를 별도 승인 환경에서 켤 때에도 테이블명·컬럼명·업무 구조는 마스킹 후에도 요청에 포함될 수 있습니다.

### AI 기능 환경변수

`.env.example`을 복사해 `.env`를 만들고 사용할 provider와 모델명을 채웁니다. 실제 `.env` 파일은 커밋하지 않습니다.

Ollama를 쓰는 경우:

```bash
AI_PROVIDER=ollama
AI_MODEL=llama3.1
OLLAMA_BASE_URL=http://localhost:11434
```

`OLLAMA_BASE_URL`을 비워 두면 기본값으로 `http://localhost:11434`를 사용합니다. 모델만 별도로 바꾸고 싶으면 `AI_MODEL` 또는 `OLLAMA_MODEL`에 설치된 Ollama 모델명을 넣으면 됩니다.

OpenAI를 쓰는 경우:

```bash
AI_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=your_model_name_here
```

Azure OpenAI를 쓰는 경우:

```bash
AI_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=your_azure_openai_key_here
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com
AZURE_OPENAI_MODEL=your_deployment_name_here
```

Azure OpenAI의 `AZURE_OPENAI_MODEL`에는 일반 모델명이 아니라 Azure에 배포한 deployment name을 넣습니다.

로컬 개발에서는 `npm run dev`로 실행되는 Vite 개발 서버가 `POST /api/ai-explain`, `/api/ai-document-draft`, `/api/ai-multi-document-draft`, `/api/ai-data-insights`를 함께 처리합니다. 별도 API 서버를 직접 띄우지 않아도 됩니다.

Cloudflare Worker 배포에서는 `src/cloudflareWorker.ts`가 같은 origin의 `/api/auth/*`, `/api/runtime-config`, `/api/ai-*` endpoint를 처리합니다. provider별 키와 테스트 계정·세션 비밀값은 Worker secret으로 설정해야 합니다.

## 현재 한계

- 정규식 기반 MVP 분석기입니다.
- 모든 DBMS 방언을 완전하게 지원하지 않습니다.
- 복잡한 중첩 SQL, DBMS 특화 함수, 동적 SQL은 일부 누락될 수 있습니다.
- 테이블명만으로 업무 의미를 확정하지 않고 추정합니다.
- 핵심 테이블 후보 점수는 SQL 사용 패턴 기반 추정이며 운영 중요도와 다를 수 있습니다.
- 시스템 지도와 영향도 분석은 정적 SQL 텍스트 기반 추정이며 런타임 호출 관계나 권한/트리거 영향은 포함하지 않습니다.
- 위험 SQL 점수는 정적 분석 기반의 검토 우선순위이며 실제 성능/장애 위험을 단정하지 않습니다.
- 리스크 finding은 정규식 기반 정적 패턴 탐지이며 DBMS 실행 계획, 실제 데이터량, 인덱스 상태를 반영하지 않습니다.
- PDF는 현재 브라우저 인쇄 기능을 이용해 저장하는 방식입니다.
- Excel 다운로드는 현재 `.csv` 형식이며, 다중 시트 `.xlsx` 생성은 후속 고도화 대상입니다.
- AI 설명은 보강용이며, SQL 실행 결과나 실제 데이터 분포를 알 수 없습니다.
- 데이터 인사이트의 이상치 후보는 통계적 검토 우선순위이며, 오류나 원인을 단정하지 않습니다.

## SQL 마스킹 유틸리티

추후 AI 전송 전에 민감 정보를 가리기 위한 `maskSensitiveSql(sql)` 유틸리티가 포함되어 있습니다. 계산 결과의 자유 텍스트에는 `maskSensitiveText(text)`를 사용합니다.

마스킹 대상:

- 이메일 주소
- 전화번호
- UUID
- 긴 토큰처럼 보이는 문자열
- 긴 숫자 ID
- 민감 컬럼명 주변의 문자열 리터럴

테이블명과 컬럼명은 기본적으로 유지하고, SQL 구조는 가능한 한 보존합니다.

## 로컬 실행

```bash
npm install
npm run dev
```

Vite 개발 서버가 안내하는 로컬 URL에서 실행할 수 있습니다.

AI 보강 기능까지 로컬에서 확인하려면 `.env`에 사용할 provider의 환경변수를 채운 뒤 같은 명령을 실행하면 됩니다. 설정이 비어 있거나 Ollama 서버가 내려가 있으면 AI 섹션에 오류가 표시되고, 룰 기반 분석 결과는 계속 사용할 수 있습니다.

## 테스트 실행

```bash
npm test
```

테스트는 SQL 분석 회귀 테스트, SQL 마스킹 유틸리티 테스트, 기계식 CSV/JSON 계산 테스트, 원본 행 미전송 검증, AI payload/API mock 테스트를 함께 실행합니다. 실제 AI API는 호출하지 않습니다.

## 빌드

```bash
npm run build
```

TypeScript 타입 검증과 Vite 프로덕션 빌드를 수행합니다.

## 후속 계획

- 프로시저 / VIEW / 패키지 분석
- ERD 및 레거시 시스템 자산 지도 생성
- 런타임 로그 또는 실제 메타데이터 기반 객체 의존성 보강
- 다중 시트 XLSX 보고서 생성
