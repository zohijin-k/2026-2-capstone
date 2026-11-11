# 실행 계획

1. 기존 criteria, forms API, document checklist/OCR, PdfFormsWorkspace/ApplyFlow, 시나리오 테스트 구조를 조사한다. HWP 목록은 이름만 기록한다.
2. 기준 스키마/마이그레이션 호환성과 HWP manifest를 구현한다.
3. 다운로드 파일명, 작성본 미작성 차단, 템플릿/HWP/ZIP API를 구현하고 테스트한다.
4. 종이 모드 저장 및 제출 잠금, 동적 업로드 체크리스트와 판정 로직/개인정보 분리를 구현한다.
5. 서식 카드 메뉴, 모드 전환 확인, 안내, 저장/복원, 신청자·담당자 화면을 연결한다.
6. API/OCR 및 기준 호환 테스트를 추가한다.
7. 요청된 P 시나리오 전체, engine_v2 pytest, frontend tsc/oxlint/vite build를 실행한다.
8. Playwright 940px/1280px 종이 제출 경로를 실제 조작하고 결과를 `/private/tmp/paper-flow-playwright`에 저장한다.
9. staged diff에서 비밀 키 패턴과 private 경로를 확인하고, 변경분을 요청한 메시지로 새 커밋한다. push/amend하지 않는다.
