# 최종 검증 — 2026-11-13

## 결과
| 대상 | 기준선 | 최종 | 실패 | 새 시험 |
|---|---|---|---|---|
| engine_v2 pytest | 260 통과·3 건너뜀 | 366 통과·3 건너뜀 | 0 | 106 |
| demo/backend pytest | 수집 0개(exit 5) | 61 통과·0 건너뜀 | 0 | 61 |
| 기존 독립 시나리오 | 18모듈 성공 | 18모듈 성공, 수치 보고 합계 1796 통과·0 건너뜀 | 0 | 기존 수 유지 |
| P2(위 합계에 포함) | 53 통과 | 53 통과 | 0 | 0 |

신규 시험 총 167건이다. 시나리오 수치 합계는 17개 모듈의 보고값이고 P14는 별도로 8개 서식 검증 성공이다. 기존 시험을 삭제하거나 약화하지 않았다.

## 실행
```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest engine_v2/tests -q
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest demo/backend/tests -q
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m demo.backend.tests.run_p2_scenarios
```
기존 run_p*_scenarios.py 18개를 독립 프로세스로 실행했고 결과 수·exit code가 기준선과 같았다. 모든 시험과 재현은 명백한 가짜 값과 임시 DB/저장소를 사용했다. 최종 로그는 /tmp/nhis-engine-final.txt, /tmp/nhis-demo-final.txt, /tmp/nhis-demo-scenarios-final.json이며 소스 검증 지점은 d26ccfb다.

## 세 문제와 현재 연결 근거
- A: 옆 주민번호 머리글을 성명으로 읽고 안전 필터 뒤에도 통과하던 문제. nhis_common.py:147에서 머리글 후보를 제외하고 nhis_forms.py의 값 셀 유일성을 검사한다. localocr.py:180과 ocr/__init__.py:81에서 최종 필수값/신뢰도를 보정하고 doc_check.py의 전용 자격득실 분기에서 누락·불일치를 검토한다.
- B: 전용 추출기 없이 generic PdfText가 라벨 없는 날짜/가입자/가구원을 못 읽던 문제. nhis_qualification.py:132의 전용 추출기와 localocr.py:505의 알려진 통보서 라우팅으로 해결한다. 요청일/유효기간을 발급일로 쓰지 않고, 불완전 목록은 인원수 근거로 내보내지 않는다.
- C: 기존 숫자 뒷자리 전용 주민번호 판독이 마스킹 값을 놓치던 문제. insurance_4.py:128의 라벨 오른쪽 전체 값 셀에서 공유 세기 판단을 사용한다. doc_check.py:247은 실제 미판독 항목만 문구에 넣는다. 포털 번호/관찰된 가입 표/단쪽/날짜 쌍 검증도 포함한다.
- 사진 안내: doc_check.py:731의 공개 함수가 PDF 결과에서 지정된 사진 두 문장만 제거한다.

## 실제 업로드 통합
신규 test_portal_uploads.py 13건은 실제 TestClient와 격리 저장소에서 다음을 확인한다: 정상 A/B/C의 직접 판독·expected·파일명·저장 OCR 결과 일치 및 PASS, 세 양식 다쪽 NEEDS_REVIEW, 자격득실→자격확인 슬롯 WRONG_DOCUMENT_TYPE, A 성명 누락/신원 불일치 검토, B 가구원 신청자의 기존 짝 규칙. 추출기 단위와 글자층 PDF, B 합성 이미지 경로도 별도 회귀로 확인했다.

## 0단계에서 추가 확인한 차이
B/C의 사용자 설명은 합성 자료로 재현됐다. C는 추가로 정부24 문서확인번호 조건이 포털에도 적용돼 13/16인데 신뢰도 .98인 상태였다. 취득일과 신고접수일이 같으면 신고접수일을 지우는 날짜 중복 제거도 발견해 포털에서 수정했다. A의 이전 화면 경고 조합은 동일 합성 A 파일로 재현되지 않았고, 이번 요청에서 B의 증상으로 분리해 처리했다. 운영 원본을 확인했다는 뜻은 아니다.

## 남은 추정과 경계
실제 양식의 모든 좌표·글꼴·역할 표기 변형과 실제 이미지 OCR 정확도는 미확인(추정)이다. 신규 세 양식의 다쪽은 승인대로 검토 대상이다. OCR 일반 예외 폴백, generic PdfText 날짜 라벨 제한, Fixture, UI 구조와 기존 정부24 검증 범위는 보존했다. 관련 코드 근거는 design.md 6절에 있다. 원래 미추적 docs/audit/는 커밋에 포함하지 않았다.
