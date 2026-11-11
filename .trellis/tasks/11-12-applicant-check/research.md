(1) 본인 대조=서류별 부분, (2) 장수=초본·4대보험 추출 단계만 부분/그 밖에는 없음, (3) 기준일=설정 연동 구현·날짜 미판독 처리는 부분, (4) 요구 종류 대조=구현·저신뢰 보호는 부분, (5) 필수·고유 항목=주요 8종 부분/기타 서류는 대부분 없음, (6) 이미지 품질=해상도만 부분·흐림/잘림/회전 전용 검사는 없음.

# 신청자 제출 전 서류 검사 조사 — 2026-11-12

조사 대상은 `feat/own-default`의 현재 작업 트리다. 제품 코드·기존 테스트·기존 문서는 수정하지 않았다. 기준일 설정의 존재 여부는 재검토하지 않고 **신청서에 고정된 설정이 실제 검사에 전달되는지**를 조사했다. 외부 자료 검색이나 전북AI 호출은 하지 않았다. 실서류와 비공개 데이터 디렉터리는 읽거나 생성하지 않았다. 아래의 인물·날짜·금액·입력은 모두 코드가 만드는 합성 데이터 또는 설정 예다.

OCR은 사진에서 글자를 읽는 기술이다. 추출기는 읽은 글자에서 성명·발급일 같은 항목을 찾는 코드다. 규칙팩(rulepack)은 사업별 검사 규칙과 문구를 담은 설정 파일이다. 신뢰도는 이 코드에서 읽기·서류 내부 일치 정도를 수치화한 값이며, 정답 확률을 보증하지 않는다. 슬롯은 업로드 화면의 서류별 칸이다. 허용 목록은 응답에 넣어도 되는 항목을 미리 정하고 나머지를 제외하는 방식이다. 폴백은 앞 판독기가 결과를 못 내면 다음 판독기로 넘기는 처리다.

**핵심 결론:** 종류·날짜·일부 본인 대조는 업로드 API까지 연결되어 있다. 그러나 추출기가 감지한 쪽 누락을 신청자 판정이 소비하지 않아 합성 누락 초본이 `PASS`가 되었다. 읽기 불확실성을 처리하는 분기도 일관되지 않다. `PASS`는 여섯 검사를 모두 완료했다는 의미로 해석할 수 없다. 다른 사람 이름은 안내 문장에서는 숨기지만 `extracted.성명`에는 남는다.

## A. 프로젝트 지도와 필수 서류 연결

다음 다섯 안내 문서의 구조·실행·한계 설명을 확인했다: `README.md`, `docs/DEVELOPMENT.md`, `docs/USER_GUIDE.md`, `demo/README.md`, `engine_v2/README.md`. 문서의 기본 엔진 설명 일부는 현재 미커밋 코드보다 앞선 상태이므로 실행 경로는 코드로 판별했다.

| 디렉터리 | 역할 — 지도 8행 |
|---|---|
| `demo/backend/api/` | 신청·본인인증·체크리스트·업로드·제출·담당자 HTTP API |
| `demo/backend/ocr/` | 고정 시연 응답 → 전북AI(이번에는 비활성) → 로컬 OCR → PDF 글자층 판독 연결 |
| `demo/backend/rules/` | 요구 서류, 설정 버전, 본인 대조, 서류 검사, 제출 시 자격·점수 계산 |
| `demo/backend/forms/`, `demo/fixtures/` | 온라인 서식 렌더링·좌표·합성 시연 서류 생성 |
| `demo/frontend/` | React 신청자 4단계 및 담당자 원본 inline 검토 화면 |
| `engine/` | 데모가 재사용하는 단건 서류 검사·심사 파이프라인. `engine_adapter.py`가 연결 |
| `engine_v2/` | OCR·전처리·추출기·독립 규칙팩 엔진·합성 평가 도구. classifier는 독립 실험이며 데모 분류에 미연결 |
| `docs/`, `.trellis/` | 이용·개발 설명과 작업별 계획·보고·코딩 지침 |

두배적금 요구 목록은 `demo/backend/rules/required_docs.py:_double_savings_checklist`, 근로서류 선택은 `_work_proof`, 취업지원 목록은 `_job_package_checklist`와 `rules/subsidy.py:LIMITS`가 만든다. 종류 문자열은 `rules/doc_types.py:DocType`이 단일 정의다. 모든 업로드의 실제 판정은 `rules/doc_check.py:check_document` → `engine/stage1_document_check.py:check_single_document`다.

| 사업/조건 | 필수 서류·슬롯 | 실제 판독/추출 연결 | 독립 v2 규칙팩과 데모 규칙의 관계 |
|---|---|---|---|
| 두 사업 공통 | 주민등록초본 `resident_abstract` | 이미지: `localocr.py:_from_resident` ← `engine_v2/extractors/resident_abstract.py:extract`; 글자층 PDF: `pdftext.py:read_page_text`(첫 쪽) | `doubling_savings.yaml:documents.resident_abstract.rules`, `job_package.yaml:documents.resident_abstract.rules` 존재. 업로드는 이 YAML을 실행하지 않음 |
| 두배적금 항상 | 건강보험료 납부확인서 `nhis_payment` | `localocr.py:_from_nhis` ← `nhis_payment.py:extract`(이미지·글자층 PDF) | v2 YAML에 이 서류 규칙 없음. 데모 `check_document`의 고지월 검사 |
| 두배적금 항상 | 건강보험 자격확인서 `nhis_qualification` | 전용 추출기 없음. 이미지 `_generic`, PDF `read_page_text`의 가구원수 정규식 | YAML 없음. 본인·피부양 관계는 `identity.py:nhis_subscriber_assessment`; 가구원 검증은 제출 시 `facts.py:build_facts` |
| 두배적금 항상 | 건강보험 자격득실확인서 `nhis_acquisition_loss` | `_from_nhis` ← `nhis_acquisition_loss.py:extract` | YAML 없음. 데모에서 설정 연수·조회기간 검사 |
| 두배적금 직장가입자 | 4대보험 가입내역 `work_proof` 또는 `work_proof_N` | `_from_insurance4` ← `insurance_4.py:extract` | YAML 없음. 가입 요약 추출과 근로 자격 판정은 별개 |
| 두배적금 지역가입자·피부양자 | 고용·산재보험 일용근로내역서 | `_generic` → PDF 정규식(제목·날짜 중심) | 전용 추출기·YAML 없음. 근로계약서 예외는 안내만 있고 accepted 종류에는 추가되지 않음 |
| 두배적금 사업자 | 사업자등록증명 | 위와 같은 공통 판독 | `DocType.BIZ_REG_CERT`를 별도 인식해 사업자등록증과 구별 |
| 두배적금 농업·임업/어업 | 농업경영체 증명서 / 어업경영체 증명서 | 위와 같은 공통 판독 | 전용 추출기·YAML 없음 |
| 두배적금 행정기관 기간제 추가 | 근로계약서 `labor_contract` | 위와 같은 공통 판독 | 초기 요구 객체는 발급일 입력 제외이나 API 체크리스트가 설정으로 다시 덮음(C) |
| 두배적금 종이 서식5 선택 | 행정정보 공동이용 사전동의서 `admin_info_consent` | 공통 판독 + `admin_consent_scan.py:inspect_admin_consent_scan` | `documents.py:upload_document`가 동의 표시·서명 잉크 확인 추가 |
| 두배적금 온라인 | 서식1 신청서·서식2 자가진단·서식3/4 동의·서식5 전자서명 | OCR 대상 아님. `api/applications.py`, `api/forms.py`, `forms/values.py` | 제출 전 입력·동의·서명 누락 검사 `review.py:_blockers` |
| 취업지원 공통 | 신청서·개인정보 동의 | 온라인 작성, OCR 대상 아님 | 위와 동일한 제출 전 검사 |
| 취업지원 공통 | 본인 명의 통장 사본 `bank_account` | 체크리스트는 업로드 제외. 폼 모델에는 `bankbookFileName` 문자열만 선언 | `FormSheet.tsx:FileAttach`도 이름만 onChange하며 현재 화면에서 이 컴포넌트 호출 연결을 찾지 못함. 실제 파일 전송·예금주 OCR 대조 없음 |
| 면접비 / 정장비 | 면접확인서 `interview_N_confirmation` | `_from_job_doc` ← `interview_confirmation.py:extract` | `job_package.yaml:interview_confirm`; 데모는 본인·날짜 검사와 추출 신뢰도 사용. 연결된 면접 확인서는 재사용 |
| 정장비·사진비·응시료 | 결제영수증 `*_N_receipt` | `_from_job_doc` ← `receipt.py:extract` | `job_package.yaml:receipt`; 신청 금액 대조는 `documents.py:upload_document` |
| 면접사진비 | 면접용 사진사본 `photo_N_photo` | 공통 제목 판독만. 텍스트 없는 실제 사진 자체의 종류 확인 부품 없음 | 전용 추출·YAML 없음 |
| 자격증 응시료 | 응시확인서 **또는** 성적표 `certificate_N_exam` | `_from_job_doc` ← `exam_docs.py:extract` | `job_package.yaml:exam_admission / exam_score`; 데모 required_fields는 `응시일` |

복수 사업장이면 근로서류 슬롯이 사업장 수만큼 생긴다. `CONFUSION_GROUPS`는 초본/등본, 증명/증, 자격확인/득실, 영수증/접수확인, 응시서류/수험표를 정의한다. 실제 업로드 종류 거절은 이 혼동군에 한정하지 않고 `DocRequirement.accepts`로 모든 다른 종류를 검사한다.

## B. 업로드 흐름·신청자 응답·화면

| 순서 | 확인한 함수 | 동작 |
|---|---|---|
| 1 | `api/documents.py:required_documents`, `set_doc_context`; `api/common.py:checklist_for` | 신청 건의 기준 버전·근로유형·선택 지원 항목으로 요구 슬롯·날짜 범위 조립 |
| 2 | `api/documents.py:upload_document` | `POST /api/applications/{id}/documents`; multipart `file`, `slot_key`, `declared_issue_date`. 확장자 pdf/jpg/jpeg/png 확인 후 파일 저장. 파일명은 경로 정리에 사용 |
| 3 | `ocr/__init__.py:read_document` | Fixture → Jbai → LocalOcr → PdfText → Upstage(미구성)를 순서대로 호출. 종류 판별이 OCR보다 먼저 독립 호출되는 구조는 아님 |
| 4 | `localocr.py:LocalOcr._read` | PDF 글자층 여부를 먼저 확인. 지원 PDF는 제목 판별 후 v2 추출, 이미지는 OCR 후 `pdftext.classify_with_evidence`로 본문 판별 후 전용 추출. 기대 슬롯 종류는 분류 입력으로 사용하지 않음 |
| 5 | `ocr/__init__.py:read_document` | 머리표만 잘못 추출된 값은 `field_safety.py:remove_header_only_fields`로 제거 |
| 6 | `doc_check.py:check_document` | 종류 미판별이면 REVIEW 반환, 다른 종류면 FAIL 반환. 맞는 종류에 단건 검사·필수 항목·본인·서류별 추가 검사 |
| 7 | `documents.py:upload_document`, `_refresh_nhis_identity`, `_save_row` | 서식5 관찰·영수증 금액 비교·건보 명의 재평가 추가. 같은 슬롯의 DB 행 교체 후 저장 |
| 8 | `api/common.py:document_dict` | 신청자용 허용 항목만 직렬화하여 응답. OCR 전체 필드·근거·엔진은 DB 내부 기록에 보관 |

전북AI의 비활성 조건은 `ocr/jbai.py:enabled`(키 존재 AND 허용 값 참) 및 `JbaiOcr.read`의 초반 return이다. 조사 스크립트는 관련 환경변수를 제거했다. 네트워크 호출을 흉내 내거나 p15를 실행하지 않았다. own 기본 선택은 `localocr.py:engine_decision`; 명시 환경값 우선, 기본 own 모델 파일 누락 때만 easyocr 대체다. 이번 환경은 `('own', '')`를 반환했고 실제 own CPU 추론을 확인했다.

`slot_key=auto`는 별도 경로다. `documents.py:_upload_merged` → `pdftext.py:split_pdf_pages`가 **쪽별 글자층만** 읽고 한 슬롯당 첫 배정 쪽만 채운다. 일반 `read_document` 체인을 쪽마다 부르지 않는다. 이미지 PDF는 대부분 미배정, 여러 쪽짜리 같은 서류는 후속 쪽이 미배정될 수 있다. 파일 분할과 원본의 쪽 완전성 검사는 다른 기능이다. 손상 PDF의 `fitz.open` 예외는 이 함수에 포괄 처리되지 않아 일반 업로드와 오류 대응도 다르다.

### 신청자 응답의 정확한 범위

| 범위 | 실제 필드/값 |
|---|---|
| 문서 응답 최상위 | `document_id`, `slot_key`, `file_name`, `file_format`, `file_url`, `expected_doc_type`, `detected_doc_type`, `declared_issue_date`, `status`, `findings`, `extracted`, `ocr_confidence`, `elapsed_ms`, `page_index`, `uploaded_at` |
| findings 허용 목록 | `code`, `message`, `how_to_fix`, `link`, `severity`만. `detail` 제외 |
| extracted 기본 허용 목록 | `발급일`, `성명`, `응시일`, `결제금액`, `동의여부`, `서명잉크확인` |
| 예외 | 4대보험은 `생년월일` 추가. 납부/자격확인서는 가입자 이름 노출을 막으려고 `성명` 제외 |
| 응답에서 제외 | `tier`, `engine`, `fallback_reason`, `quality_note`, `classification_evidence`, `classification_confidence`, `fields` 전체, `bboxes`, findings의 `detail`, 전입일·가구원수·보험료·검증 결과·점수 |
| 체크리스트 별도 응답 | 요구 종류·필수 항목·발급처·min/max 날짜·date_basis·issue_rule_label·notes/warnings·제출 건수·설정 버전·가정값 설명. `assumption_notes`에 OCR/화질 임계 설명은 여전히 있음 |

`api/forms.py:form_layout`는 내부 폼 키를 `f0000` 같은 불투명 ID로 바꾸고 조건식의 필드 참조도 변환한다. 이는 **폼 배치 API**의 처리다. 업로드 API의 공개 서류 슬롯과 `extracted`의 한글 표시용 키까지 불투명화하는 구조는 아니다.

| 상태 | 신청자 화면 `StatusBadge.tsx:APPLICANT_DOCUMENT_STATUS` | 제출 동작 |
|---|---|---|
| `PASS` | 확인 완료 | 해당 서류로 인한 차단 없음 |
| `NEEDS_REVIEW` | 담당자 확인 예정 | `review.py:_warnings`로 담당자 원본 확인·더 선명한 파일 권고, 제출 가능 |
| `FAIL` | 다시 올려 주세요 | `review.py:_blockers`가 제출 차단. 담당자 화면에는 부적합으로 표시 |

`DocumentUpload.tsx:DocumentResult`는 허용된 추출값, 사유 message/how_to_fix/link, 미리보기와 다시 올리기를 표시한다. PASS가 아니면 읽은 종류도 표시한다. `?debug` 매개변수가 있으면 신뢰도/소요시간 표시(값이 1인지 확인하지 않음). 엔진 표시 코드는 없다. `SlotCard`는 설정 기준과 발급일 직접입력·입력일 사전 경고를 보여 주며, `upload` 후 체크리스트를 다시 받아 갱신한다. `upload_done`은 업로드 존재 건수이지 검사 통과 건수가 아니다.

문구 출처는 구분해야 한다. 원문 PDF 전체를 이번에 재검증하지 않았다. `programs.py`·`required_docs.py`·`subsidy.py`는 주석상 공고문/시행지침/사업계획서 기반이고, 날짜와 필수 항목은 신청 건의 설정 버전에서 온다. 실제 문장은 `engine/reason_messages.py:MESSAGES`, `doc_check.py:HOW_TO_FIX` 및 `check_document`, `documents.py:upload_document`에 작성되어 있다. 상태 배지와 버튼은 프론트 코드다. 해상도·신뢰도 임계값과 촬영 추정은 데모 가정값이므로 공고문 규칙과 구분한다. `HOW_TO_FIX[UNKNOWN_DOCUMENT_TYPE]`가 있어도 실제 조기반환 분기는 이를 채우지 않아 `how_to_fix=""`다.

### 공개/담당자 경계 검사 근거와 한계

| 검사 위치 | 실제로 보장/검사하는 내용 |
|---|---|
| `run_p4_scenarios.py:test_inline_only` | 원본·서식 inline 헤더 및 다운로드 경로 경계 |
| 같은 파일 `test_no_download_in_source`, `APPLICANT_FORM_FILE_ALLOWLIST`, `test_applicant_form_archive_access` | 담당자 원본 저장 기능 금지, 신청자 작성 서식 다운로드 예외와 접근 검사 |
| 같은 파일 `test_applicant_still_blind` | 마이페이지 응답의 점수·담당자 메모 미노출. **엔진 이름 전체를 검사하는 테스트는 아님** |
| `run_p8_localocr_scenarios.py:test_applicant_payload` | extracted 허용 목록 검사 |
| `run_p15_jbai_scenarios.py:test_api_privacy_cache_and_views` | 신청자 엔진/대체 사유 키 제외 검사(p15는 이번에 미실행) |
| `run_p17_own_scenarios.py:test_real_upload` | 업로드·목록·체크리스트 응답에 own/엔진 메타데이터 없음 검사. 기존 작업 트리 신규 파일이며 수정하지 않음 |
| 이번 `probe.py` | 9개 API 업로드 × 업로드/목록/체크리스트에서 금지 메타데이터 키 없음 확인. 정상 4대보험 추가 실행은 엔진 문자열 없음도 확인 |

주의: 타인 초본 안내 문구에 이름을 넣지 않는 P9 검사는 findings만 검색한다. F에서 `extracted.성명`에 합성 타인 이름이 남아 실제 화면이 이를 표시하는 것을 확인했다. 허용 목록 자체가 있어도 본인 불일치 때의 값 공개 제한은 별도로 필요하다.

## C. 판정별·서류별 구현 매트릭스

기준은 **현재 신청자 업로드까지 연결되었는가**다. 추출기에만 있는 검사는 부분으로 적는다. (4)는 요구 칸과의 대조, 마지막 열은 그 대조에 넣을 본문 종류를 알아내는 단계다. 아래 칸의 참조 ID는 바로 뒤 표에서 **파일:함수·값·신청자 문구·기존 검증 이름**으로 풀었다. 기존 검증을 읽은 것과 이번에 실행한 것은 F/검증 절에서 구분한다. 없음은 대응 판정·문구·전용 검사가 없다는 뜻이다.

| 서류 | (1) 본인 성명·생일 | (2) 장수·쪽 간 일치 | (3) 설정 날짜 | (4) 요구 칸 적합 | (5) 필수·고유 항목 | (6) 품질 | 본문 종류 판별 |
|---|---|---|---|---|---|---|---|
| 주민등록초본 | 부분 I-R: 신청인·본문 비교, 저신뢰 예외 있음 | 부분 P-R: 누락 검출 후 PASS 가능 | 부분 D: 기본 issue_date, 누락·저신뢰 예외 | 구현 T | 부분 U-R: 주소/신청인, 병역 미검사 | 부분 Q | 구현 K |
| 건강보험료 납부확인서 | 부분 I-N: 본인 또는 피부양 관계 | 부분 P-N: 쪽 성명/날짜 일치, 장수 없음 | 부분 D: issue_date | 구현 T | 부분 U-N: 설정 고지월·고지금액, 자료 전체 미판독 공백 | 부분 Q | 구현 K + 전용 제목 |
| 건강보험 자격확인서 | 부분 I-N: 가구원 목록 판독 경로 부족 | 없음 | 부분 D: issue_date | 구현 T | 부분 U-H: 가구원수 정규식, 목록 대조는 제출 시 | 부분 Q | 구현 K |
| 건강보험 자격득실확인서 | 부분 I-G: 읽힌 항목만 비교 | 부분 P-N: 쪽 성명·생일·일자 일치, 장수 없음 | 부분 D: issue_date | 구현 T | 부분 U-A: 설정 연수, 미판독도 FAIL 가능 | 부분 Q | 구현 K + 전용 제목 |
| 4대보험 가입내역 | 부분 I-G: 값 없는 항목은 생략 | 부분 P-4: 1/1 검사 결과가 상태에 직접 미연결 | 부분 D: issue_date | 구현 T | 부분 U-4: 네 보험·가입 요약 추출, 가입 중 요건 판정 없음 | 부분 Q | 구현 K + 전용 제목 |
| 결제영수증 | 없음: 보통 명의 추출 안 함 | 없음 | 부분 D/J: 기본 issue_date, payment_date 선택 가능 | 구현 T | 부분 U-JR: 금액 REVIEW, 취소/일괄결제 검증 직접 미연결 | 부분 Q | 구현 K + 전표 단서 |
| 응시확인서 | 부분 I-G: 생일 없으면 성명만 | 없음 | 부분 D/J: 기본 issue_date, exam_date 선택 가능 | 구현 T: 성적표도 허용 | 부분 U-JE: 응시일 필수, PDF 경계 문제 E | 부분 Q | 구현 K + 전용 제목 |
| 성적표 | 부분 I-G | 없음 | 부분 D/J: 위와 동일 | 구현 T: 응시확인서도 허용 | 부분 U-JE: 응시일 필수, 시험명 필수 판정 없음 | 부분 Q | 구현 K + 전용 제목 |
| 면접확인서 | 부분 I-G: 생일은 있을 때만 | 없음 | 부분 D/J: 기본 issue_date, interview_date 선택 가능 | 구현 T | 부분 U-JI: 성명·회사·면접일 신뢰도, 서명 직접 검사 없음 | 부분 Q | 구현 K + 전용 제목 |
| 일용근로내역서 | 없음: 공통 판독기가 명의 추출 안 함 | 없음 | 부분 D: issue_date | 부분 T: 근로계약서 대체 안내만 | 없음: 근로일·시간 전용 추출/검사 | 부분 Q | 구현 K |
| 근로계약서 | 없음: 공통 판독기가 명의 추출 안 함 | 없음 | 부분 D: 초기 입력 제외가 설정에서 덮임 | 구현 T | 없음: 주당 시간·계약기간 검증 | 부분 Q | 구현 K |
| 사업자등록증명 | 없음: 공통 판독기가 명의 추출 안 함 | 없음 | 부분 D: issue_date | 구현 T: 등록증 구별 | 없음: 대표자·개업일·사업장 검증 | 부분 Q | 구현 K |
| 농업경영체 증명서 | 없음: 공통 판독기가 명의 추출 안 함 | 없음 | 부분 D: issue_date | 구현 T | 없음: 단독·공동경영주 검증 | 부분 Q | 부분 K: 농업경영체 단어 기반 |
| 어업경영체 증명서 | 없음: 공통 판독기가 명의 추출 안 함 | 없음 | 부분 D: issue_date | 구현 T | 없음: 단독·공동경영주 검증 | 부분 Q | 부분 K: 어업경영체 단어 기반 |
| 면접용 사진사본 | 없음 | 없음 | 부분 D: 기본 issue_date지만 사진 날짜 미판독 | 부분 T: 종류를 알면 대조 | 없음: 사진·신청인 시각 대조 | 부분 Q | 부분 K: 제목 없는 사진은 종류 미판별 |
| 종이 서식5 | 부분 I-S: 성명·생일/신뢰도 비교 | 없음 | 적용 제외: paper_forms 서식5면 none | 구현 T | 부분 U-S: 동의/서명 잉크, 의미·진위 확인 아님 | 부분 Q | 구현 K |
| 온라인 서식1~5, 취업지원 신청서·동의 | 부분 O: 인증값 고정·입력검사; OCR 대조 대상 아님 | 해당 없음: 서버 템플릿 | 해당 없음: 작성일 고정 O | 해당 없음 | 구현 O: 제출 전 필수값·동의·서명 확인 | 해당 없음 | 해당 없음 |
| 통장 사본 | 없음 | 없음 | 해당 없음 | 없음: 파일 내용 전송 없음 | 부분 O-B: 파일명 입력 여부만 검사 | 없음 | 없음 |

### 셀별 근거·값·문구·검사 이름

다음 표의 `localocr.py`, `pdftext.py`, `doc_check.py`는 각각 `demo/backend/ocr/`, `demo/backend/ocr/`, `demo/backend/rules/` 아래 파일이다. 추출기는 `engine_v2/extractors/` 아래다. P번호는 `demo/backend/tests/run_p…_scenarios.py`다.

| ID | 구현 위치와 판정 값 | 신청자 문구/연결 공백 | 검증 근거 |
|---|---|---|---|
| I-R | `localocr.py:_from_resident`, `pdftext.py:extract_applicant`; `doc_check.py:check_document`; `identity.py:identity_of/compare` | identity_json vs 초본신청인성명·생년월일, 그다음 본문 성명·생일. 미판독 `RESIDENT_APPLICANT_UNREADABLE`: “초본의 신청인 정보를 읽지 못해 담당자가 확인합니다.” 신청인 불일치는 신뢰도 무관 `FAIL` | P8 `test_abstract_applicant_identity_and_history`, P9 `test_matching`; F 정상·다른 이름 |
| I-G | `identity.py:compare`, `doc_check.py:check_document` | 읽힌 성명/생일만 비교; .85 이상 불일치 `IDENTITY_MISMATCH`, 미만 `IDENTITY_UNCERTAIN`: “본인 서류가 맞다면 그대로 두셔도 됩니다…” 둘 다 없으면 대조하지 않음 | P9 `test_matching`, `test_insurance4_reader_privacy`; P16 `test_text_pdfs`; F 4대보험(생일 미판독도 PASS) |
| I-N | `identity.py:nhis_subscriber_assessment`, `documents.py:_refresh_nhis_identity` | 납부/자격확인 가입자명·생일·가구원목록 vs identity_json. 관계 증거 부족 `NHIS_SUBSCRIBER_IDENTITY_REVIEW`: “가입자 명의 확인이 필요해 담당자가 확인합니다.” 이름만 본인과 같고 생일 없으면 인정 | P9 `test_nhis_dependent_reconciliation`; 실제 자격확인서 전용 목록 추출 부품은 없음 |
| I-S | `doc_check.py:check_document` 서식5 분기 | 성명·생일 모두 요구, 없으면 `ADMIN_CONSENT_IDENTITY_UNREADABLE`; 확실한 불일치 FAIL, 낮은 신뢰도 REVIEW | P14 `run`의 종이 서식5 시나리오; 이번은 코드 확인 |
| P-R | `resident_abstract.py:extract`의 pages_complete·doc_no_consistent·name_consistent·issue_date_consistent | 쪽 번호 집합 1..총수, 문서번호·성명·날짜 일치. `localocr.py:_from_resident`는 실패 이름을 내부 문자열로만 옮기고 pages_complete는 신뢰도 계산에 안 넣음. **신청자 쪽 누락 문구 없음** | `test_resident_abstract.py:test_missing_page_detected`, `test_inconsistent_issue_date_lowers_confidence`; F missing_page의 PASS 재현 |
| P-N | `nhis_payment.py:extract`, `nhis_acquisition_loss.py:extract`; `nhis_common.py:consensus` | 쪽별 성명·생일·날짜 일치 실패는 해당 필드 신뢰도 상한 .6, `LOW_OCR_CONFIDENCE`로 REVIEW 가능. **인쇄 쪽 번호 연속·총수 검사 없음** | `test_nhis_extractors.py:test_payment_checks_names_across_pages`, `test_acquisition_loss_rejects_reversed_dates_and_page_name_mismatch`; P8 `test_nhis_extractors_text_and_image_pdf` |
| P-4 | `insurance_4.py:extract` | page_complete(1쪽), page_marker_1_of_1, 머리값 일치 검사. `_from_insurance4`에서 실패 문자열 저장만; 별도 페이지 안내 없음 | `test_insurance_4.py:test_rejects_other_types_and_checks_page_marker_and_future_issue_date`, `test_page_marker_accepts_joined_spaced_and_split_tokens` |
| D | `api/common.py:checklist_for` → `criteria.py:issue_bounds` → `doc_check.py:to_engine_spec/to_engine_document` → `engine/stage1_document_check.py:check_single_document` | 선택된 날짜 필드 vs min/max. 기준 이전 `DOCUMENT_ISSUED_TOO_EARLY`: 실제일·설정일과 “이후 새로 발급받아 올려 주세요.” 미판독 None이면 날짜 검사가 건너뛰어짐. 낮은 신뢰도 날짜도 기준 이전이면 FAIL | P11 `run`(버전별 같은 문서의 상이한 결과); P8 `test_declared_date_second_check`; F old_issue; diagnose DATE_MODE/UNCERTAIN_OLD_ISSUE |
| J | `subsidy.py:ExtraDoc/criteria_catalog_defaults`, `required_docs.py:_job_package_checklist`, `common.py:checklist_for` | catalog의 날짜 종류 + 설정의 기간 방식. 현재 catalog 기본은 추가서류도 issue_date. 결제일/응시일/면접일은 선택했을 때만 기준 날짜가 됨 | P12 `test_payment_date_basis`, `test_legacy_and_frozen_criteria`; P11 `run` |
| T | `required_docs.py:DocRequirement.accepts`, `doc_check.py:check_document` | detected_doc_type vs doc_type_choices. 다른 종류는 `WRONG_DOCUMENT_TYPE`: “이 자리에는 …이 필요합니다.” 미판별은 REVIEW. 종류 판독 신뢰도 자체로 FAIL을 완화하지 않음 | P8 `test_slot_independent_classification`; P16 `test_lookalikes_are_wrong_documents`; F wrong_type |
| K | `pdftext.py:classify_with_evidence/DOC_TYPE_KEYWORDS`; 이미지 `LocalOcr._read`에서 OCR 다음 호출 | 제목·본문 단서 순차 첫 일치. 파일명·기대 슬롯은 입력 안 함. 분류 모델은 호출 안 함. 단, `fixture.py:FixtureOcr.read`는 파일명 고정 결과라는 별도 예외 | P8 `test_title_with_parentheses`, `test_slot_independent_classification`; P16 종류 시나리오; F own 종류 판별 |
| Q | `localocr.py:_quality/_merge_image_heuristics`; `pdftext.py:_read_image`; 엔진 단건 검사 | PDF DPI와 이미지 짧은 변만 점수화. `LOW_IMAGE_QUALITY` FAIL 문구는 “선명한 사진으로 다시 제출해 주세요.” 화면캡처는 REVIEW. 흐림·잘림·방향별 전용 코드/측정 없음 | P2 `test_scenarios_fixture`/`test_pdftext`; F blur/rotate90; 실제 저해상도 파일 API 검사는 이번에 안 함 |
| U-R | `resident_abstract.py:extract`; `localocr.py:_from_resident`; `doc_check.py:check_document` | 주소변동내역 “미포함/없음”이면 `MISSING_ADDRESS_HISTORY` FAIL(“최근 5년 … 포함을 체크”). 이력 1건이면 `PAST_ADDRESS_OMISSION_SUSPECTED` REVIEW. 신청인 미판독 REVIEW. 병역·실제 5년 범위 충족은 직접 검사 없음 | P8 `test_abstract_applicant_identity_and_history`; `test_resident_abstract.py:test_single_address_history_count_is_preserved`, `test_missing_row_number_detected`(행 누락 결과도 상태에 직접 미연결) |
| U-N | `nhis_payment.py:extract`; `doc_check.py:check_document` | 고지금액·월별고지금액, 설정 premium_months. 일부 월 없으면 `MISSING_BILLING_MONTHS` FAIL: “조회기간에 …이 포함되도록 다시 발급해 주세요.” 월별고지금액 자체 없으면 이 검사는 안 함. 합계·실납부·요양보험 분리 검증이 모두 직접 사유로 전달되지는 않음 | `test_nhis_extractors.py:test_payment_uses_billed_amounts_and_supported_month_formats`, `test_payment_missing_month_leaves_average_empty`, `test_payment_ambiguous_combined_total_is_not_used`; P8 건보 판독 |
| U-H | `pdftext.py:extract_household_size/read_page_text`; `rules/facts.py:build_facts`, `household.py:parse_household_members` | 자격확인서에서만 가구원수/목록 사용. 목록 불완전·인원 불일치는 제출 시 확인필요 경로. **업로드 단건 필수 가구원 추출 검사와 실제 목록 전용 추출은 없음** | P13 `test_household_source_and_income_review`, `test_missing_household_forces_review`; 입력값으로 대체하지 않는 원칙은 확인 |
| U-A | `nhis_acquisition_loss.py:extract`; `doc_check.py:check_document` | 자격이력자료 period/rows, 발급일, req.recent_years. 미포함 `NHIS_HISTORY_PERIOD_MISSING` FAIL; 읽기 실패 `NHIS_HISTORY_PERIOD_UNREADABLE`도 `_finding` 기본 FAIL이라 문구와 충돌 | `test_nhis_extractors.py:test_acquisition_loss_five_years_not_covered`; diagnose HISTORY_UNREADABLE |
| U-4 | `insurance_4.py:extract`; `localocr.py:_from_insurance4` | 네 보험 행·가입/미가입·근로관련가입여부·취득일·사업장 요약 추출. `doc_check.py`에는 가입 중 여부를 요구하는 분기 없음. 누락 필드는 confidence 최솟값 계산에서 빠질 수 있음 | `test_insurance_4.py:test_work_summary_and_receipt_warning_are_not_eligibility_judgments`; P9 보험 판독; F 4대보험 2조건 |
| U-JR | `receipt.py:extract`; `localocr.py:_from_job_doc`; `documents.py:upload_document` | 결제금액·결제일을 못 읽으면 신뢰도 .5. 금액 미판독/입력 불일치는 `RECEIPT_AMOUNT_UNREADABLE/MISMATCH` REVIEW. 취소전표·일괄결제·사업자번호 등의 검증은 내부 기록으로 남고 개별 사유 미연결 | P12 `test_receipt_amounts`; P16 `test_image_receipt_without_title_word`; `test_receipt.py:test_cancelled_slip_is_flagged`, `test_several_items_flag_bulk_payment`는 추출기 검증 |
| U-JE | `exam_docs.py:extract`; `_from_job_doc`; `doc_check.py:check_document` | 응시일 필수. 이미지 미판독 `REQUIRED_FIELD_UNREADABLE` REVIEW, 글자층으로 취급하면 `MISSING_REQUIRED_FIELD` FAIL. 시험명·미래 여부/발급 전후 검사 일부는 신뢰도·내부 경고에 반영 | P5 `test_exam_date_required`; P16 `test_text_pdfs`, `test_unread_exam_date_goes_to_review`; `test_exam_docs.py:test_missing_exam_date_is_not_filled_and_warns`, `test_exam_date_after_issue_fails_order` |
| U-JI | `interview_confirmation.py:extract`; `_from_job_doc` | 성명·회사명·면접일 중 하나라도 없으면 신뢰도 .5 → LOW_OCR_CONFIDENCE REVIEW. 회사명 대조·면접/확인일 순서가 내부 검사에 있음. 회사 직인·서명 유무 확정 검사는 없음 | P16 `test_text_pdfs`; `test_interview_confirmation.py:test_signed_company_must_match_company_cell`, `test_unfilled_template_date_is_not_read` |
| U-S | `admin_consent_scan.py:inspect_admin_consent_scan`; `documents.py:upload_document` | 정해진 서식5 원본과 비교한 동의표시·서명 잉크. 동의 안 함은 FAIL, 표시/서명 미판독은 REVIEW. 서명 잉크는 자필 이름 인식이나 서명 진위 판별을 의미하지 않음 | P14 `run` 종이서식5·미판독 처리 시나리오 |
| O | `applications.py:_lock_identity/verify_identity/save_consents`; `review.py:_blockers`; `forms.py:form_layout`; `forms/values.py:form_date` | 인증 성명·생일 고정, 필수입력·동의·서명 확인. “동의해야 제출…”/“입력해 주세요.” 온라인 생성 서식의 발급일·장수 OCR 검사는 해당 없음 | P9 `test_identity_api`; P14 `run`; P4 작성 서식 공개 경계 |
| O-B | `FormSheet.tsx:FileAttach`, `form1-model.ts:Form1Value`, `review.py:_blockers`, `programs.py:required_form_fields` | 서버는 `bankbookFileName` 비었는지만 확인하여 “통장 사본(본인 명의)을(를) 첨부해 주세요.” FileAttach는 이름만 다루는 보조 코드이고 현재 호출 연결은 못 찾음. 파일 내용·예금주 검증 없음 | P5 `test_program_branching` 등 입력 누락 검사와 별개로 실제 통장 업로드 검사는 없음 |

### (3) 날짜 설정의 적용 확인

`applications.py:create`가 `criteria_version`을 고정한다. `common.py:checklist_for` → `criteria.py:for_application/read_criteria/issue_rule_for/issue_bounds`로 해당 버전을 읽어 각 요구 객체의 min/max 날짜를 채운다. `to_engine_document`는 date_basis에 따라 **fields의 해당 날짜**를 사용한다. issue_date 속성만 채우고 `fields[발급일]`이 없으면 실제 검사 날짜는 None이 될 수 있다.

| 설정 방식 | 실제 경계 계산 | 이번 합성 함수 확인 |
|---|---|---|
| after_date | 설정 date ≤ 문서 날짜 | 설정 2026-04-01 → 하한 2026-04-01 |
| after_notice | 설정 announcement_date ≤ 문서 날짜 | 기본 두배적금 → 하한 2026-03-03 |
| within_days | 생성일/제출일 - N일 ≤ 문서 날짜 ≤ 생성일/제출일 | 2026-11-12, 30일 → 2026-10-13~2026-11-12 |
| none | min/max 없음 | 양쪽 None |

경계는 `< min`/`> max`로 실패시키므로 기준 당일은 포함한다. D/J의 날짜 종류는 기간 방식과 별개다: `issue_date→발급일`, `payment_date→결제일`, `interview_date→면접일`, `exam_date→응시일`, `none→날짜 검사 제외`.

기본 두배적금은 건보·초본·근로서류 등 after_notice, 취업지원은 after_date(2026-01-01)다. 슬롯 직접 설정 → 근로서류 번호형/영수증·확인서·사진·응시서류 꼬리 종류 → fallback 순으로 적용한다. 서류별 다르게 설정할 수 있으며 P11은 버전 고정, P12는 결제일 전환을 검사한다.

다음은 **설정 존재의 문제가 아니라 적용/읽기 경계의 문제**다.

- `checklist_for`는 모든 업로드의 `check_declared_date`를 basis!=none으로 다시 정한다. 그래서 `_job_package_checklist`의 “영수증·확인서는 발급일 직접입력을 받지 않음”과 `_double_savings_checklist`의 근로계약서 입력 제외가 기본 issue_date 설정에서 덮인다. 실제 화면은 이 API 값을 따라 입력 칸을 요구한다. 문서 설명과 차이가 있다.
- 종이 서식5는 별도 분기로 날짜 none을 강제한다. 온라인 서식·통장도 none이 기본이다.
- 날짜가 None이면 단건 검사에서 기준일 비교를 건너뛴다. 모든 서류에 공통 “날짜 미판독” 필수 검사 코드가 없다.
- 기본 issue_date인 취업서류에서 `결제일/응시일/면접일`이 올바르게 추출되어도 그 값은 **basis를 설정한 경우에만** 기준 비교에 쓰인다. `_from_job_doc`가 보완한 issue_date 속성이 `fields[발급일]` 부재까지 해결하지는 않는다.
- within_days는 draft에서는 created_at, submitted 후 조회에서는 submitted_at 기준이다. 제출 시점에 저장된 단건 status를 모두 다시 검사하는 구조는 아니므로 날짜가 바뀌는 제출 경계 테스트가 필요하다.

## D. 읽기 불확실성·사유 코드·잘못된 FAIL 경로

공통 사유 코드는 `engine/models.py:ReasonCode`, 엔진 문구는 `engine/reason_messages.py:MESSAGES`. 데모 추가 코드는 `doc_check.py:CODE_*`, severity 선택은 `_finding/REVIEW_ONLY_CODES`다. 일부 경로는 `CheckFinding`을 직접 만들며 기본 severity는 FAIL이다. findings 중 FAIL 하나라도 있으면 최종 FAIL이고, 없을 때 REVIEW가 우선한다.

| 조건/코드 | 현재 상태·실제 안내 | 판단 |
|---|---|---|
| `LOW_OCR_CONFIDENCE` | .85 미만 → REVIEW, “담당자가 직접 확인… 더 선명한 파일… 교체” | 단독이면 불확실성을 부적합으로 단정하지 않음 |
| `MISSING_REQUIRED_FIELD` | 현재 추가서류 응시일이 없고 tier/engine 조건상 글자층·fixture로 취급 → FAIL, “표기된 서류로 다시 발급…” | 실제로 OCR을 했으나 pdftext 태그가 붙는 E 경로는 잘못된 단정 가능 |
| `REQUIRED_FIELD_UNREADABLE` | localocr/jbai이며 engine!=pdftext → REVIEW, “적혀 있다면 그대로… 담당자가 원본…” | 재촬영 권고는 how_to_fix에 있음 |
| `LOW_IMAGE_QUALITY` | .6 미만 → FAIL, “선명한 사진으로 다시 제출” | 화질 문제를 업무 부적합과 같은 status로 저장하여 제출 차단 |
| `UNKNOWN_DOCUMENT_TYPE` | 종류 None이면 **다른 검사보다 먼저** REVIEW 반환, “서류 종류를 판별하지 못했습니다. 담당자가 확인합니다.” | 실제 반환 how_to_fix 비어 있음. 흐림·회전·엔진 없음 원인을 구별 못 함 |
| OCR 미설치/읽기 실패 | LocalOcr None → 다음 계층. JPG/PNG는 PdfText가 종류 None 결과, 이미지 PDF는 최종 tier none 가능 → 위 UNKNOWN REVIEW | 엔진 이름은 신청자에게 안 나감. 영수증 tier none은 API가 `RECEIPT_OCR_UNAVAILABLE` REVIEW로 교체 |
| `UNREADABLE_FILE` | 암호·손상·페이지 없음 → FAIL, 비밀번호 해제/재발급 안내 | OCR 불확실과는 별개의 재업로드 대상. 손상 파일도 암호 안내로 합쳐져 원인 정확도는 제한 |
| `DECLARED_DATE_MISMATCH / UNCERTAIN` | .85 이상 FAIL, 미만 REVIEW | 이 비교에는 신뢰도 보호가 있음 |
| 일반 `IDENTITY_MISMATCH / UNCERTAIN` | 읽힌 본문 성명/생일이 다르면 .85 기준 FAIL/REVIEW | 빠진 값은 비교 생략, 모든 서류에서 두 항목을 필수로 요구하지 않음 |
| `RESIDENT_APPLICANT_UNREADABLE` | 초본 신청인 이름/생일 하나라도 없음 → REVIEW | 값이 있지만 틀리게 읽힌 경우는 아래 예외 |
| `NHIS_HISTORY_PERIOD_UNREADABLE` | “조회 기간을 확인하지 못했습니다. 담당자가 확인합니다.” **그러나 severity FAIL** | 코드가 REVIEW_ONLY_CODES에 빠짐. diagnose에서 재현 |
| `SCREEN_CAPTURE_SUSPECTED` | REVIEW | 저해상도 FAIL이 함께 있으면 최종 FAIL. UNKNOWN 조기반환 시 화면캡처 사유도 표시 안 됨 |

임계값·측정 근거:

| 위치 | 값/용도 |
|---|---|
| `engine/config.py` | OCR_CONFIDENCE_THRESHOLD=.85, IMAGE_QUALITY_THRESHOLD=.6. 코드 주석상 TF 미확정 데모 가정값 |
| `localocr.py:_quality` | PDF DPI≥200:.9, ≥150:.7, 미만:.5; DPI 없으면 .75 |
| `pdftext.py:_read_image` | 이미지 짧은 변 ≥1400px:.9, ≥1000:.75, ≥700:.55, 그 미만:.35. EXIF·화면 해상도는 캡처 의심에만 사용 |
| `localocr.py:GENERIC_CONFIDENCE_CAP` | 전용 검증 없는 이미지 OCR 일반 서류는 .8 상한 → 보통 REVIEW |
| `pdftext.py:_confidence` | 종류·날짜·텍스트 길이 신호를 더함. 종류+날짜만 있어도 .9, 본인 항목이 없다고 낮추지는 않음 |
| `resident_abstract.py:_confidence`, `nhis_common.py:confidence` | 일치/형식 검증 통과율. 여러 쪽 불일치 상한 .6. 단어 OCR confidence와 같은 값은 아님 |
| `localocr.py:_from_job_doc` | receipt 금액·결제일, exam 성명·응시일, interview 성명·회사·면접일 하나라도 없으면 .5 |
| `engine_v2/engine.py:LOW_CONFIDENCE` | 독립 v2 규칙 엔진은 .7. 현재 데모 단건 .85와 다른 체계이며 업로드 경로에 이 엔진 판정을 연결하지 않음 |
| `pipeline/preprocess.py` | TEXT_LAYER_MIN_CHARS=50, MAIN_IMAGE_MIN_COVERAGE=.90, RENDER_DPI=300, MIN_OCR_DPI=200. 흐림/잘림/방향 임계값 아님 |

### 신청자에게 잘못된 FAIL이 나갈 수 있는 코드 경로

| 우선 확인 경로 | 코드 근거/합성 확인 | 영향 |
|---|---|---|
| 초본 신청인 오독 | `check_document` 신청인 불일치 분기에 confidence 검사 없음. diagnose .5에서 `LOW_OCR_CONFIDENCE`+`IDENTITY_MISMATCH`, 최종 FAIL | 낮은 신뢰도에도 “본인이 직접 발급받은 초본이 아닙니다” 단정 |
| 날짜 오독 | `check_single_document` min/max 비교는 신뢰도 검사 없음. diagnose .5·옛 날짜 → FAIL | 입력일 불일치 보호와 달리 기준일 위반은 REVIEW로 내려가지 않음 |
| 자격득실 조회기간 미판독 | 위 UNREADABLE 코드 기본 FAIL; 기간 일부를 못 읽어 coverage=False여도 `NHIS_HISTORY_PERIOD_MISSING` FAIL | 담당자 확인 문구인데 제출 차단. 윤년 2/29 replace 예외도 UNREADABLE로 갈 수 있음 |
| 짧은 PDF의 응시일 미판독 | E의 실제 own OCR + pdftext 태그 → MISSING_REQUIRED_FIELD FAIL | 적혀 있지만 OCR이 놓친 경우도 “표기 안 됨”으로 안내할 가능성 |
| 저신뢰 종류 오판 | `check_document` 다른 종류 분기는 confidence/classification_confidence를 확인하지 않음 | 흐릿한 제목을 다른 종류로 오독하면 즉시 FAIL |
| 납부월 일부 오독 | `MISSING_BILLING_MONTHS`에 문서/월별 필드 신뢰도 보호 없음 | 필요한 월이 적혀도 OCR에서 한 월 누락 시 FAIL 가능 |
| 초본 주소이력 인식 실패/사업 차이 | `pdftext.py:has_address_history`는 단서 부재를 미포함으로 설정. `check_document`는 사업 구분 없이 MISSING_ADDRESS_HISTORY FAIL | 취업지원은 주소이력 요건이 없다는 required_docs 설명과 달리 그 사업도 같은 분기 적용 |
| 품질 미달 | `LOW_IMAGE_QUALITY`가 REVIEW_ONLY_CODES에 없음 | 문구는 재촬영이지만 내부 FAIL. UI에서는 “다시 올려 주세요”여도 제출 차단 의미가 같음 |

별도의 잘못된 PASS 위험: 본인·날짜 등 필드가 없으면 건너뛰는 분기와 추출 검증을 상태로 연결하지 않는 분기다. F의 쪽 누락·생일 미판독 4대보험, diagnose의 명의 없는 사업자등록증명으로 확인했다. `pdftext.py:extract_issue_date`는 발급일 라벨이 없으면 문서의 가장 늦은 다른 날짜를 발급일로 사용한다. 이는 “못 찾은 값을 다른 후보로 채우지 않는다”는 원칙과 맞지 않는 실제 코드 경로다(diagnose UNLABELED_ISSUE_DATE). `receipt.py:_single_dated`도 라벨 없는 단일 날짜를 경고와 함께 결제일로 사용하는 정책이므로 확인이 필요하다.

## E. p16 실패 1건의 재현과 원인

실행: `PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/.trellis/tasks/11-12-applicant-check" .venv/bin/python -m demo.backend.tests.run_p16_job_docs_scenarios`

샌드박스에서 정상 종료했다(TestClient를 쓰는 시나리오가 아님). **28 통과 / 1 실패, exit 1**. 제품·기존 테스트를 바꾸지 않았다.

| 항목 | 정확한 값 |
|---|---|
| 함수 | `run_p16_job_docs_scenarios.py:test_text_pdfs` |
| 실패 검사 이름 | `텍스트 PDF에 응시일 없음 → 부적합(그대로)` |
| 기대 | `('FAIL', ['MISSING_REQUIRED_FIELD'])` |
| 실제 | `('FAIL', ['LOW_OCR_CONFIDENCE', 'MISSING_REQUIRED_FIELD'])` |

`diagnose.py`에서 실제 추론 호출을 감싸 관찰했다. 텍스트 PDF의 `get_text().strip()` 길이는 **46자**, v2 전처리 임계는 **50자**, source는 `render`, 호출/실제 엔진은 **own**, 반환 메타데이터는 **tier localocr / engine pdftext / confidence .5**였다. 같은 입력을 `pdftext._read_pdf`로 직접 읽으면 confidence .9이고 기존 기대대로 MISSING_REQUIRED_FIELD만 나왔다. 이전 작업 보고서 `.trellis/tasks/11-11-own-default/report.md`의 동일 실패·원인 기록과 일치한다. 이전 소스를 새로 로드하는 비교 실험은 이번에는 하지 않았다.

원인은 세 경계의 조합이다.

1. `localocr.py:_tier2_can_read`는 첫 쪽에 공백 아닌 글자가 **하나라도** 있으면 text_pdf로 분기한다.
2. 지원 서류라 `_load_pages`로 넘기지만 `preprocess`는 50자 미만이면 글자층 대신 렌더링 후 own OCR을 수행한다. own 기본 전에는 앞 작업 보고상 미설치 easyocr 실패로 PdfText 계층까지 내려갔던 입력이다.
3. `_from_job_doc`는 응시일 부재를 .5로 낮춘다. 그런데 text_pdf 분기 끝에서 실제 page source와 무관하게 `engine="pdftext"`를 넣는다. 단건 검사는 LOW_OCR_CONFIDENCE를 추가하고, 필수 항목 분기는 engine==pdftext를 믿어 MISSING_REQUIRED_FIELD FAIL을 추가한다.

신청자에게는 담당자 확인/선명한 파일 권고와 “응시일이 표기된 서류로 재발급”이 같이 나간다. 상태 배지는 여전히 FAIL→“다시 올려 주세요”다. 특히 응시일이 있었는데 OCR이 놓친 짧은 PDF에서는 불확실한 읽기가 필수 표기 부재로 분류될 수 있다. **짧은 글자층·스캔/글자층 혼합 PDF도 같은 조건에 들 수 있다는 것은 코드 경로에 따른 판단**이며, 실서류로 재현했다는 뜻은 아니다. 이미지 문서만 사용하는 경우 이 특정 text_pdf 태그 문제는 발생하지 않는다.

| 해결 후보 — 구현하지 않음 | 기대 효과 | 주의·추가 검사 |
|---|---|---|
| 데모 text_pdf 경계와 v2 50자 정책 일치시키기, 또는 이미 글자층으로 확인한 경로는 글자층 직접 사용 | 짧지만 정상인 디지털 문서가 예기치 않게 OCR로 바뀌는 것 방지 | 전체 v2 임계를 무작정 0으로 낮추면 스캔의 소량 부수 텍스트까지 신뢰할 수 있음. 0/1/49/50/51자·혼합 쪽 테스트 필요 |
| `_load_pages` 실제 source/실행 엔진을 전달하고, 미판독 분기는 source를 근거로 정하기 | 실제 own을 pdftext로 표시하는 오류와 “없음/못 읽음” 오분류를 함께 다룸 | `localocr.py`, `engine_v2/engine.py`, `doc_check.py` 계약 협의. 담당자 표시·신청자 비노출 회귀 |
| p16을 긴 글자층 PDF와 짧은 PDF 두 사례로 나누기 | 원래 의도한 글자층 필수 항목 검사와 OCR 경계 검사를 분리 | 입력을 길게 하거나 기대 사유에 LOW만 추가하는 것만으로는 실제 태그/부적합 위험을 해결하지 못함 |

## F. 합성 서류의 업로드 API 끝에서 끝 확인

임시 `probe.py`는 기존 `make_synth_eval.py:documents/render`, `test_insurance_4.py:employed_words`를 사용했다. 초본은 가상 신청인과 두 주소행을 추가한 **1쪽 PNG**, 누락 사례는 인쇄 쪽표기를 1/2로 바꾼 1쪽 PNG다. 4대보험도 1쪽이다. 합성 번호는 기존 테스트의 가상 값이고 뒷자리 원문을 보고서에 남기지 않았다. DB·업로드·서약 서명은 모두 조사 폴더 아래 TemporaryDirectory로 격리하고 종료 시 삭제했다. 기존 샘플 디렉터리·데모 DB·기존 저장소를 사용하지 않았다.

처음 TestClient가 샌드박스에서 `CLIENT_START` 뒤 멈춰 인터럽트했다. 실행 승인 후 동일 스크립트를 샌드박스 밖에서 실행해 완료했다. 기본 엔진 환경변수는 제거했고 `engine_decision()=('own','')`였다. 전북AI 환경변수도 제거했다. 추론을 가짜 결과로 대체하지 않았다.

실행 예: `PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/.trellis/tasks/11-12-applicant-check" timeout --signal=INT 180 .venv/bin/python .trellis/tasks/11-12-applicant-check/probe.py` (TestClient는 승인된 샌드박스 밖 실행 필요). 4대보험 완전판 추가 실행은 마지막 인자 `insurance4_complete`로 한 건만 선택했다.

| 시나리오 | 기대 | 실제 HTTP/신청자 상태·주요 문구 | 내부 관찰과 차이 | 엔진 비노출 |
|---|---|---|---|---|
| 정상 초본 | PASS | 200 / PASS, findings=[] → 확인 완료 | own, .95, 검증 9/9, 주소 2건 | 업로드·목록·체크리스트에서 엔진 키 없음 |
| 다른 사람 이름 | FAIL | 200 / FAIL, `IDENTITY_MISMATCH`: “본인이 직접 발급받은 초본이 아닙니다. 본인 명의로 발급받아 다시 올려 주세요.” | own, .95. **extracted에 합성 타인 성명 남음** | 같음 |
| 쪽 누락(1/2만 제출) | 최소 REVIEW 또는 누락 재업로드 안내 | **200 / PASS**, findings=[] | own, .95, 검증 8/9, `판독검증실패=pages_complete`. 검증 결과가 status로 이어지지 않음 | 같음 |
| 기준일 이전 발급 | FAIL | 200 / FAIL, `DOCUMENT_ISSUED_TOO_EARLY`: “서류에서 읽은 발급일은 2025년 11월 10일입니다. 이 사업은 2026년 3월 3일 이후 발급된 서류만 인정합니다. (서류 발급일 2025-11-10)” | 합성 날짜 2025-11-10 vs 설정 2026-03-03. 설정 적용 확인 | 같음 |
| 초본 칸에 등본 | FAIL | 200 / FAIL, `WRONG_DOCUMENT_TYPE`: “'주민등록초본' 자리에 '주민등록등본'을 올리신 것 같습니다.” / “이 자리에는 주민등록초본이 필요합니다.” | own 본문 종류 분류, .95 | 같음 |
| 흐린 초본(GaussianBlur 반경 5px) | 불확실, 재촬영 권고 | 200 / NEEDS_REVIEW, `UNKNOWN_DOCUMENT_TYPE`: “'주민등록초본' 자리에 올리신 파일의 서류 종류를 판별하지 못했습니다. 담당자가 확인합니다.” how_to_fix="" | own 시도 후 결과 미채택, PdfText 이미지 휴리스틱 .0/화질 .9. 흐림 자체 측정 없음 | 같음 |
| 초본 90도 회전 | 불확실, 방향 수정 권고 | 위와 같은 200 / NEEDS_REVIEW, 동일 문구·빈 how_to_fix | 방향 전용 안내 없음, 해상도 점수 .9. 자동 방향 보정 없음 | 같음 |
| 4대보험 완전판 정상 | PASS | 200 / PASS, findings=[]; extracted 성명·생년월일·발급일 | own .98, 16/16 검증, 근로관련가입여부 True(내부) | 세 응답 금지 키 없음 + 엔진 문자열 없음 |
| 추가: 4대보험 번호 일부 가림 | 생년월일 미판독에 REVIEW 필요 | **200 / PASS**, findings=[]; extracted 성명·발급일만 | own .98, 15/16, `생년월일_consistent` 실패. 필수 본인 항목 미판독이 점수·판정에서 빠짐 | 세 응답 금지 키 없음 |

엔진 이름은 일반 결과에서 표시되지 않았다. 흐림/회전 결과의 `engine=pdftext`는 텍스트 OCR 성공을 뜻하지 않고 이미지 화질 휴리스틱을 반환한 계층 이름이다. 완료된 합성 API 검사 9건, 미수행한 요청 시나리오는 없다. 다만 다쪽 PDF·다양한 서식·실제 촬영 환경의 성능은 이 소규모 합성 검사로 판단하지 않는다.

추가 임시 `diagnose.py`는 코드 분기의 합성 함수 입력을 검사했다: .5 신뢰도 신청인 불일치→FAIL, .5 신뢰도 옛 발급일→FAIL, 조회기간 잘못된 JSON→문구 REVIEW이나 severity FAIL, 화질 .55→FAIL, 발급일 라벨 없는 타 날짜를 발급일로 선택, 네 날짜 mode의 경계 계산. 이는 실제 업로드 이미지가 아니라 **규칙 함수의 분기 확인**으로 구분한다. 실제 합성 글자층 사업자등록증명(제목·발급일만 있고 명의 없음)도 판독·단건 검사를 확인했다. confidence .9, fields에는 발급일만, 판정은 PASS였다. API 호출 사례와는 구분하되 본인 검사가 생략되는 실제 판독 경로를 확인한 결과다.

## G. 미완·알려진 문제 기록

`rg`로 demo/backend·engine_v2·docs의 소스/Markdown/YAML에서 TODO/FIXME/XXX/미구현/후속/예정을 찾았다. engine_v2 데이터·모델은 검색 범위에서 제외했다. `.trellis/tasks`의 작업 Markdown도 검색하고 최근 report.md 네 개를 확인했다. 다음은 사전 검사에 관련된 것만 추렸다. 오래된 계획상의 “미구현”을 현재 미구현의 증거로 사용하지 않았다.

| 위치(함수 또는 문서 절) | 기록 내용 | 현재 코드와의 관계 |
|---|---|---|
| `doc_check.py:CODE_*` 위 주석 | 엔진에 없는 사유 코드를 합의 후 옮기는 “후속” | 실제로 엔진/데모 코드·severity 정의가 분리되어 있음 |
| `engine_v2/engine.py:evaluate_document` | 미등록 rule type은 “미구현 규칙 유형”으로 UNKNOWN | 일반 안전장치. 현재 YAML에 미구현 규칙이 있다는 증거는 아님. registry에 date_order/amount_equals 등은 구현되어 있음 |
| `docs/USER_GUIDE.md:함께 두배적금` | 병역사항·근로 판정 진행 중 | 초본 업로드 병역 검사와 4대보험 가입 중 근로요건 분기 없음과 맞음. 맥 I/J 겹침 주의 |
| `engine_v2/README.md:취업지원패키지 추가서류`, `rulepacks/job_package.yaml` 머리 주석 | 인정 시험·업종·정장 대여기간·결제일≤면접일 등은 후속 범위, 데모 금액 대조는 유지 | 추출기 검증과 지원자격 규칙을 구분해야 함. 직접 업로드 규칙팩 연결은 없음 |
| `engine_v2/README.md:1-4` | 지역가입자 납부확인서 레이아웃·보수외소득 합산 확인 필요 | 직장형 중심 추출 범위. 전용 추출이 모든 가입형태를 처리한다고 단정 불가 |
| `README.md:현재 상태와 한계`, `engine_v2/docs/own-ocr-history.md:후속 학습 단계` | 큰 회전 자동보정 없음, 인식 미세조정·분류 운영 연결 미착수 | F의 90도 분류 실패와 맞음. 학습 미착수 자체를 규칙 미구현과 혼동하지 않음 |
| `.trellis/tasks/11-11-own-default/report.md:p16 regression` | 46자/50자 차이, 사유 목록 변동, 실제 OCR인데 pdftext 표시, 수정 보류 | E에서 그대로 재현한 알려진 문제 |
| `.trellis/tasks/11-11-own-fix/report.md:Synthetic verification` | 대시·도장·빈 값/잘못된 값·형식 인식 보강 및 합성 회귀 통과 | 추출 보강의 과거 검증. 현재 API 여섯 검사 모두 구현의 증거는 아님 |
| `.trellis/tasks/11-11-classifier-diagnosis/report.md` | 본문 키워드 기준과 독립 학습 분류기를 합성 데이터로 비교, fixture 제외 | 분류 모델은 데모에 연결되지 않았음. filename fixture 경계는 별도 고려 필요 |
| `.trellis/tasks/11-11-own-ocr-history/report.md` | 기존 기록 기반 문서 정리·이전 테스트 통과 기록 | 이번 실행 성적과 구분 |
| `demo/backend/forms/__init__.py`, `docs/demo-site-dev-plan.md`의 P7 “미구현이어도…” | 초기 선택 기능 계획 표현 | 현재 온라인 서식/내보내기 코드와 P14가 있으므로 현재 미구현으로 분류하지 않음 |

관련 소스에서 TODO/FIXME/XXX라는 영문 표지로 명확히 남겨진 추가 사전 검사 항목은 찾지 못했다. 그래서 코드상 연결 공백(C/D/F)을 별도로 기록했다. 과거 보고서가 통과한 환경과 현재 own 기본 환경은 같다고 가정하지 않았다.

## H. 빈 곳과 제안 — 구현하지 않음

우선순위 상은 잘못된 통과/부적합·정보 경계·이번 제출 경로의 재현된 문제, 중은 검사 범위와 안내 품질, 하는 정리·장기 검증이다. 모든 수정 후보는 다음 작업의 검토 대상이며 이번에는 적용하지 않았다.

| 우선 | 빈 곳/제안 | 예상 수정 파일 | 맥과 겹칠 위험 | 필요한 검증 |
|---|---|---|---|---|
| 상 | 초본 쪽 누락·행 누락·쪽 간 불일치 검증을 공통 사유로 연결. 못 읽은 쪽번호와 확인된 누락 구분 | `localocr.py`, `rules/doc_check.py`, 필요 시 `ocr/base.py`, `extractors/resident_abstract.py` | 판독 체인 높음; 신청자 응답 중간; I 거주 증거 높음 | 정상 1/N, 중간/마지막 누락, 중복 쪽, 총수 불일치, 쪽번호 미판독, 같은/다른 문서번호 API 검사 |
| 상 | 본인·날짜·필수 항목은 빠진 값도 명시적 REVIEW. 초본 신청인 오독/날짜 저신뢰/조회기간 UNREADABLE을 확정 FAIL로 보내지 않기 | `doc_check.py`, `identity.py`, `engine/stage1_document_check.py`, `localocr.py` | I 자격 기준화·J 근로 판정 높음; API status 의미 높음 | 낮은 신뢰도 불일치·기준일 전후, 이름만/생일만/둘 다 없음, 생일 미판독 4대보험, 날짜 None, 윤년 기간 |
| 상 | E 짧은 PDF의 글자층 경계·실제 엔진 태그·필수 표기 미판독 정책 함께 정리 | `localocr.py`, `engine_v2/pipeline/preprocess.py`, `engine_v2/engine.py`, `doc_check.py`, p16/p17 | 판독 체인 높음, pdftext.py 관련 경계 높음, 담당자 엔진 표시 높음 | 0/1/49/50/51자, 텍스트/스캔 혼합 PDF, 응시일 실제 있음/없음, OCR 오류, 정확한 사유 순서·비노출 |
| 상 | 본인 불일치 때 추출 성명·생일도 신청자 응답에서 제외 | `api/common.py:document_dict`, 필요 시 호출부 인증 문맥 | 신청자 API 응답 모양 높음; 담당자 원본 검토는 별도 유지 | 타인/동명이인/오독의 업로드·목록·체크리스트·최종 확인·화면 표시까지 타인값 미노출 |
| 상 | 파일명 fixture가 실제 판독을 덮는 경계를 명시적으로 제한 | `ocr/fixture.py`, `ocr/__init__.py`, 데모 설정 | 판독 체인 높음; 기존 시연 시나리오 높음 | 같은 내용에 다른 이름, fixture와 같은 이름의 임의 내용, 데모/일반 업로드 모드 구분. 현재 `FixtureOcr.read`는 이름 일치만으로 고정 결과 반환하므로 공통 “파일명 안 씀” 원칙의 예외 |
| 상 | 날짜 없는 값에 다른 날짜를 추측해 넣지 않기 | `ocr/pdftext.py:extract_issue_date`, `extractors/receipt.py:_single_dated` | pdftext.py 높음; 날짜 기준화 I 높음 | 생일·거래일만 있는 문서, 명시 발급일, 날짜 여러 개, 날짜 없음, 라벨 없는 날짜를 REVIEW로 처리 |
| 중 | 종류 오판·품질 저하를 업무 부적합과 분리하고 재촬영/회전/전체 쪽 안내 추가 | `doc_check.py`, `ocr/base.py`, `localocr.py`, `pdftext.py`, `DocumentUpload.tsx`, `StatusBadge.tsx` | 신청자 응답 모양·화면 높음; 담당자 상태 표기 중간 | 저신뢰 다른 종류, 흐림/잘림/90·180도, 저해상도, UNKNOWN how_to_fix와 제출 정책 |
| 중 | 서류별 필수 항목 목록과 validation 소비 정책 정리(건보월·자격확인 목록·4보험 가입·취업서류 취소/일괄 등) | `required_docs.py`, `doc_check.py`, `subsidy.py`, v2 해당 추출기, `facts.py` | I/J 매우 높음. 특히 4보험 가입 요약을 근로자격으로 바로 해석하지 말고 맥 J와 협의 | 항목 일부/전체 미판독, 월 일부 누락, 4보험 미가입/지역/직장피부양, 취소 영수증, 날짜 순서. “읽혔는가”와 “자격 충족인가” 별도 검사 |
| 중 | 일용·사업자·농어업·계약서의 본인·고유 필드 추출 및 안내된 대체서류 허용 정책 | `doc_types.py`, `required_docs.py`, `localocr.py`, 신규 추출기 | J 근로 판정 높음, 판독 체인 중간 | 소유자 성명·생일, 근로시간/기간, 대표자·경영주 구분, 대체 근로계약서 accepted 종류, 본문만 같은 제목인 빈 서류 |
| 중 | 기본 날짜종류와 입력 칸·문서 안내 일치; 설정 변경/제출 날짜 경계 검사 | `api/common.py`, `criteria.py`, `required_docs.py`, `subsidy.py`, 필요 시 `review.py` | I 및 신청자 화면·설정 API 높음 | 네 mode×basis, 버전 고정, 직접 날짜 입력 유무, 기간제 계약서·서식5 예외, 자정/다음날 제출 |
| 중 | auto 병합도 정상 체인과 같은 추출·단건/문서 묶음 검사를 사용 | `documents.py:_upload_merged`, `pdftext.py:split_pdf_pages` | pdftext.py·판독 체인·API 모양 높음 | 다쪽 초본 한 슬롯, 이미지 PDF, 서로 다른 문서 합침, 암호/손상, 같은 종류 여러 회차 |
| 중 | 통장 사본 실파일 첨부와 본인 예금주 대조 또는 현재 데모의 지원 범위를 화면에 정확히 표현 | `FormSheet.tsx`, `form1-model.ts`, 신청/첨부 API, `required_docs.py` | 신청자 폼·API·맥 화면 높음 | 이름만 저장한 상태/실파일 저장, 명의 불일치·미판독, 원본 inline, 허용 목록 |
| 하 | 안내 문서의 엔진 기본값·서류별 실제 검사 범위와 C 표 동기화 | README·USER_GUIDE·demo/engine_v2 README, 기존 작업 보고 후속 기록 | 맥 README/docs 담당과 높음 | 각 문구를 실제 API·기본 설정과 대조. 이번 문서는 수정 금지라 제안만 |
| 하 | 서식/촬영 변형을 넓힌 CPU 합성 회귀 세트 | 기존 synth 도구·해당 시나리오 | 판독 평가 중간; 기존 p17 작업과 협의 | 현재 1쪽 합성 외 장문·다쪽·폰 촬영·여러 기관 서식. 실서류 성능으로 일반화하지 않음 |

다음 구현 작업은 맥의 **I 자격요건 기준화**, **J 근로 판정**, 신청자/담당자 화면·README/docs 변경과 파일 단위로 맞춰야 한다. 조사 시점에 다른 채팅의 진행 내용은 확인하지 않았으므로 겹침은 가능성으로 표시했다. 이 보고서는 수요기관 운영의 평가가 아니라 현재 캡스톤 코드의 검사 범위와 연결 상태를 정리한 것이다.

## 검증 및 변경 보존

이번 실행: p16 전체(28/29), 합성 API 업로드 9건, 짧은 PDF 실제 own 호출 추적과 순수 규칙 분기·네 날짜 mode 확인. 기존 전체 시나리오·전체 pytest·프론트 빌드는 제품 변경이 없어 실행하지 않았다. 표의 그 밖 테스트 이름은 코드를 확인한 근거이며 이번 통과 실적으로 제시하지 않는다.

`verify.py`로 시작 시 기록한 SHA-256과 종료 시 값을 대조했다. 기존 5개 status 항목(수정 3파일, 신규 p17 파일, 기존 task 디렉터리)의 실제 파일 **12/12개가 바이트 단위로 동일**하다. 기존 task 디렉터리의 파일 집합도 동일하다. `git diff --stat`은 조사 전후 모두 `3 files changed, 31 insertions(+), 7 deletions(-)`이며 파일별 수치도 같다. 브랜치는 계속 `feat/own-default`다.

이번 작업의 영구 산출물은 조사 폴더의 `research.md`, `probe.py`, `diagnose.py`, `verify.py`뿐이다. 실행 중 합성 파일·임시 DB·빈 임시 폴더·ONNX 임시 상태 파일은 정리했다. 제품 코드·기존 테스트·기존 문서·spec/workflow 수정, 커밋·push·merge·stash·checkout·reset을 하지 않았다.

최종 `git status --short`:

```text
 M demo/backend/ocr/localocr.py
 M engine_v2/docs/own-ocr-history.md
 M engine_v2/docs/own-ocr.md
?? .trellis/tasks/11-11-own-default/
?? .trellis/tasks/11-12-applicant-check/
?? demo/backend/tests/run_p17_own_scenarios.py
```

조사 전후 동일한 `git diff --stat`:

```text
 demo/backend/ocr/localocr.py      | 32 ++++++++++++++++++++++++++++----
 engine_v2/docs/own-ocr-history.md |  2 +-
 engine_v2/docs/own-ocr.md         |  4 ++--
 3 files changed, 31 insertions(+), 7 deletions(-)
```
