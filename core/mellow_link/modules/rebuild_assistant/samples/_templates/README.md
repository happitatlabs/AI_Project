# Sample Template Root

상태: template-root  
분류: shared template and helper pack

이 디렉터리는 runnable sample 본문을 두는 곳이 아니다.  
목적은 새 샘플을 만들 때 복제하거나 참조할 공통 템플릿과 질문 팩을 보관하는 것이다.

현재 포함된 항목:
- `golden_samples_expansion/`
  - expansion sample 생성용 공통 템플릿 pack
- `phase3_qa_question_pack.json`
  - explanation / Q&A smoke용 질문 팩

운영 원칙:
- 실제 샘플 본문은 항상 `samples/<sample_name>/` 아래에 둔다.
- 이 디렉터리는 공통 뼈대나 helper asset만 둔다.
- 특정 사례에 종속적인 입력/출력 자산은 여기 두지 않는다.

새 runnable sample 추가 순서:
1. `samples/` 아래에 새 디렉터리를 만든다.
2. 필요 시 `golden_samples_expansion/`을 복제한다.
3. `scenario.md`, `input_manifest.json`, `expected_assertions.yaml`, `assets/`, `notes/`를 채운다.
4. 샘플 상태를 `measured`, `promoted`, `golden`, `fixture`, `reference-only` 중 하나로 분류한다.
