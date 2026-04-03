# Golden Sample Expansion QA Checklist

- [ ] feature slice 수가 기대와 일치하는가
- [ ] top detector / top decision_type이 기대와 일치하는가
- [ ] priority_score drift가 없는가
- [ ] score_breakdown이 explainability와 모순되지 않는가
- [ ] execution_stages가 decision_ids와 연결되는가
- [ ] AI on/off에서 deterministic core가 동일한가
- [ ] extensions["narrative"] provenance가 정상 기록되는가
- [ ] narrative 실패 시 fallback이 유지되는가
