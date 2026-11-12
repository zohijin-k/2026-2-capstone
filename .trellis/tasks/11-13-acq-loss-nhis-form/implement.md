# 실행 기록 — 사용자 확인 대기

- [x] 0 준비: 정책 확정·B/C 확장, 원인 재현, 기준선 측정 — 2d9260f.
- [x] 1 거짓 통과: 실패 회귀 뒤 머리글/필수값/신원 판정 수정 — 231f38a.
- [x] 2 A: 공단 자격득실 추출·구조·단쪽 검증 — 2b103af.
- [x] 3 B: 통보서·가구원 추출과 기존 소비 계약 유지 — d6a75a2.
- [x] 4 C: 포털 신원/표/날짜/정확한 경고 — fef59ba.
- [x] 5 PDF 사진 안내: 지정된 두 문장만 제외 — b1fd0cd.
- [x] 6 통합 회귀: 실제 업로드 13건, 전체 엔진/백엔드/18시나리오 — d26ccfb.
- [x] 7 결과/추정/범위 밖 기록, review 상태로 확인 대기.
- [ ] 사용자 결과 확인. 완료/아카이브·푸시·PR은 수행하지 않음.

## 검증과 재현
명령·숫자·현재 코드 연결은 verification.md를 따른다. 기준선은 엔진260/3skip, 백엔드 pytest 수집0·18시나리오 성공, P2 53이다. 최종 엔진366/3skip, 백엔드61, 기존 시나리오1796 및 P14 8개 서식 검증 성공이며 실패는 모두0이다. 신규 시험167건, 기존 시험 삭제/완화 없음.

## 보존한 경계
공고일 이상, 슬롯 대체 불허, 기존 정부24, 일반 PdfText, Fixture, UI 구조, OCR 사슬 예외 처리와 기존 가입자/가족 규칙을 보존했다. 공통 도우미 변경은 기존 회귀와 새 값 셀 모호성 회귀로 확인했다. 실제 서류는 접근하지 않았고 모든 자료는 명백한 가짜 값이었다.

## Approved follow-up sequence
1. Freeze A/B/C failures using OcrWord/PageImage fixtures shaped like the redacted observations (strict xfail until each fix).
2. Add form-scoped spaced-label matching and table boundaries from persistent vertical gaps across body words; reject ambiguous evidence.
3. Read A identity below overlapping name label, then use observed history columns.
4. Reuse identity rule for B and publish the unchanged household JSON contract only after complete validation.
5. Recognize C by relative body labels; keep portal issue-number checks separate and group split date occurrences by row spacing.
6. Add a shared resident-title coordinate fallback and route both LocalOcr paths through existing resident extraction.
7. Run all engine/backend/scenario tests, review the complete diff, update task evidence and leave review status pending user verification.
