# Consulting Output Reference Set

상태: reference-only  
분류: non-regression reference asset set

이 디렉터리는 runnable sample이 아니다.  
목적은 원가계산/컨설팅 계열 결과물을 만들 때 따라갈 수 있는 참고 산출물과 원본 입력 묶음을 함께 보관하는 것이다.

현재 포함된 자산:
- `assets/0_원가계산컨설팅자료_260418/`
  - 부산우유 컨설팅 산출물 PPT 5종
  - 결과 문서의 흐름, 챕터 구성, 설명 밀도, 표현 톤을 참고할 때 사용
- `assets/0_원가계산컨설팅자료_260418.zip`
  - 위 산출물 pack의 압축본
- `assets/0_선입선출 프로그램 소스_260418/`
  - FIFO/원가계산 관련 SQL, trigger, procedure 원본 소스 묶음
  - 컨설팅 결과물이 어떤 입력 자산을 바탕으로 만들어졌는지 추적할 때 사용
- `assets/0_선입선출 프로그램 소스_260418.zip`
  - 위 원본 소스 pack의 압축본

이 디렉터리에 현재 없는 것:
- `goal.txt`
- `constraints.txt`
- `input_manifest.json`
- `expected_assertions.yaml`
- 자동 회귀용 `scenario.md`

따라서 아래 용도로는 사용하지 않는다.
- canonical golden regression
- promoted expansion regression
- measured expansion sample 실행 입력
- deterministic assertion source

현재 허용 용도:
- 컨설팅형 결과 패키지의 섹션 순서, 슬라이드 흐름, 설명 톤 reference
- 원본 소스와 최종 산출물 사이의 대응 관계를 수동 검토할 때의 reference
- 향후 runnable consulting sample 또는 output contract를 만들 때 seed material
- 발표자료/보고서 자동 생성 결과를 사람 기준으로 비교할 때의 baseline 참고

운영 원칙:
- PPT 본문을 자동 assertion source로 직접 사용하지 않는다.
- zip 파일은 원본 보존용이며, 실제 비교/검토는 압축 해제된 디렉터리를 우선 본다.
- 이 디렉터리의 역할은 “정답 데이터”가 아니라 “따라갈 예시” 보관이다.

승격 또는 분리 조건:
1. 실행 입력으로 쓰려면 별도 runnable sample 디렉터리를 만든다.
2. 자동 검증 대상으로 쓰려면 `input_manifest.json`과 `expected_assertions.yaml`을 추가한다.
3. 산출물 계약으로 격상하려면 별도 output contract 문서 또는 sample contract를 만든다.
4. 템플릿으로 일반화할 수 있을 정도로 공통성이 확인되면 `_templates/` 계열로 다시 분리한다.
