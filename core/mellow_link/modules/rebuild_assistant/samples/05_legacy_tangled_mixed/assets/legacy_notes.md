# Legacy Tangled Notes

- validation, access control, state transition, persistence, UI navigation이 한 함수에 섞여 있다.
- query와 status 변경이 한 기능 안에 분산돼 있다.
- mixed responsibility와 validation leak를 동시에 보기 위한 최악 구조 샘플이다.
- UI가 repository와 query를 직접 참조하도록 만들어 boundary mismatch와 UI/data coupling 후보를 함께 드러낸다.
