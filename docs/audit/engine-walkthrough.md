# 엔진 동작 설명과 문제 목록

기준일: 2026-11-12. 근거는 저장소 상대경로:줄로 표기했다. 운영 환경 변수와 실서류는 확인하지 않았다. engine_v2/data/private/는 열거나 나열하지 않았으며 명령 인자로도 사용하지 않았다. 검증에는 저장소 가상환경 테스트와 P2 합성 시나리오만 사용했다.

## 가설 H1–H11 판정

| 가설 | 판정 | 코드 근거 및 설명 |
|---|---|---|
| H1 Fixture → 전북AI → LocalOcr → PdfText → Upstage 순서, 키 없으면 전북AI·Upstage 생략 | 맞음 | 순서: demo/backend/ocr/__init__.py:21-27. JBAI 키와 허용 설정이 모두 필요: demo/backend/ocr/jbai.py:43-46,220-228. Upstage는 키 없으면 None: demo/backend/ocr/upstage.py:28-38. 첫 결과에서 체인 종료: demo/backend/ocr/__init__.py:37-50. |
| H2 _tier2_can_read는 첫 쪽 글자가 하나라도 있으면 글자층으로 보고 뒤쪽은 안 봄 | 맞음 | 첫 쪽 텍스트의 공백 제거 결과만 검사: demo/backend/ocr/localocr.py:403-413. |
| H3 글자층 PDF의 건강보험·4대보험·취업서류는 LocalOcr _load_pages와 추출기를 거치고 초본·등본은 PdfText로 감 | 부분적으로 맞음 | 지원 유형이면 _load_pages와 대응 추출기 호출: demo/backend/ocr/localocr.py:438-479. 페이지별 50자 이상은 텍스트층, 그 외 OCR: engine_v2/pipeline/preprocess.py:24,82-92,136-155 및 engine_v2/engine.py:168-200. 그 밖은 PdfText로 넘어가나 첫 쪽만 판독: localocr.py:443-446, pdftext.py:312-337. 첫 쪽 유형 분류 실패도 예외. |
| H4 PdfText는 첫 쪽만 추출하므로 여러 쪽 초본·등본의 뒤쪽은 판독되지 않고 전입일이 틀릴 수 있음 | 맞음 | doc[0]만 read_page_text에 전달하고 페이지 수만 기록: demo/backend/ocr/pdftext.py:325-337. 뒤쪽에만 있는 값이 빠질 수 있음. 다른 첫 쪽 날짜가 전입일로 잡히는지는 실제 입력에 좌우되는 추정. |
| H5 이미지 경로 LocalOcr는 한 쪽이라도 글자층이면 None | 맞음 | preprocess 결과의 TEXT_LAYER 페이지가 하나라도 있으면 반환: demo/backend/ocr/localocr.py:481-487. 혼합 PDF 후속 내용 누락 가능. |
| H6 easyocr 대체 사유는 로그에만, run_ocr 오류는 무기록 | 맞음 | 모델 누락 대체 결정 및 warning: demo/backend/ocr/localocr.py:51-65,419-427. engine은 저장되지만 fallback_reason은 설정 안 함; 담당자 뷰는 이 두 항목을 표시: demo/backend/api/officer.py:674-678. run_ocr error는 None, 일반 예외도 chain에서 삼킴: localocr.py:488-493, demo/backend/ocr/__init__.py:37-48. |
| H7 split_pdf_pages는 병합 업로드 전용 | 맞음 | 정의/호출: demo/backend/ocr/pdftext.py:406-435 및 demo/backend/api/documents.py:475-493. 일반 슬롯은 원본 전체를 read_document에 전달: documents.py:342-379. |
| H8 Fixture 일반 업로드 매칭 기준 | stem 정확 일치. own을 생략할 수 있음 | 내용이 아닌 파일명 stem으로 FIXTURES 조회: demo/backend/ocr/fixture.py:373-399. 일치하면 chain이 Fixture 결과로 종료: demo/backend/ocr/__init__.py:37-50. 해시 기준 없음. |
| H9 engine_v2 default_engine은 macOS applevision이고 서비스도 씀 | 기본값은 맞음, 서비스 사용은 틀림 | 환경변수 없을 때 macOS=applevision: engine_v2/pipeline/ocr/__init__.py:134-137. 서비스 LocalOcr는 별도 engine_decision 기본 own을 사용: demo/backend/ocr/localocr.py:51-69,419-427; engine 이름을 _load_pages에 명시 전달: localocr.py:461-463. engine_v2.engine.run 기본과 demo 업로드는 별도: engine_v2/engine.py:202-207; demo/backend/api/documents.py:378-390. |
| H10 ocr_bench는 OCR 전체 문자열 정답 포함, private_bench는 필드별 비교. “4대보험 own 5/5” 출처 | 앞 두 문장 맞음, 숫자 출처 불명 | score_gt는 공백 제거 후 문자열 포함 여부: engine_v2/tools/ocr_bench.py:9-34. private_bench는 추출 필드 완전일치/CER: engine_v2/tools/private_bench.py:115-152. 4대보험은 이름·생년월일·발급일·확인번호·가입내역 5키를 비교: engine_v2/tools/insurance_bench.py:17-39. 저장소에서 해당 “5/5” 기록을 찾지 못했다. private_bench 5필드 만점이라는 해석은 추정. |
| H11 private_bench raster_pages와 서비스 preprocess 동일 | PDF는 다름, 이미지 일부 동일 | private_bench PDF는 각 쪽 전체를 300dpi 렌더: engine_v2/tools/private_bench.py:63-77. 서비스는 페이지별 텍스트층/임베디드 이미지/렌더: engine_v2/pipeline/preprocess.py:82-133. 비PDF는 private_bench도 preprocess 사용: private_bench.py:67-69. |

## 1. 전체 흐름

### 1.1 업로드부터 판정까지

1. POST /api/applications/{id}/documents는 신청 건과 동적 체크리스트를 읽고 PDF/JPG/PNG만 허용한다. slot_key가 auto/비어 있으면 병합, 지정 슬롯이면 체크리스트 업로드 대상인지 확인한다(demo/backend/api/documents.py:342-370).
2. 일반 업로드는 파일을 슬롯 경로에 저장하고 read_document(path, req.doc_type)를 호출한다. 기대 유형은 전달되나 Fixture·LocalOcr·PdfText·Upstage는 기대값으로 분류하지 않는다. JBAI만 지원 expected 종류를 조건으로 쓴다(documents.py:372-390; fixture.py:378-383; localocr.py:419-421; pdftext.py:394-403; jbai.py:220-222).
3. 체인은 Fixture→전북AI→LocalOcr/engine_v2→PdfText→Upstage 순으로 첫 결과를 선택한다. 모두 실패하면 confidence 0, tier=none 결과를 만든다(demo/backend/ocr/__init__.py:21-82; base.py:41-77).
4. check_document는 유형, 암호/화질/서명/발급일/입력일/confidence, 초본 페이지, 캡처, 필수필드, 고지월, 최근 5년, 본인일치를 검사한다(demo/backend/rules/doc_check.py:291-390,392-493,495-662).
5. 판정과 OCR 원값을 저장한다. 신청자 응답은 상태·finding·제한 필드·confidence만 포함하고 OCR 계층/engine/fallback 상세는 제외한다(demo/backend/api/documents.py:217-243; demo/backend/api/common.py:175-227). 담당자 화면은 원본 URL·필드·bbox·confidence·tier·engine·fallback을 제공한다(demo/backend/api/officer.py:652-683).
6. final-check는 필수 미업로드와 FAIL만 차단하고 NEEDS_REVIEW는 경고로 둔다(demo/backend/api/review.py:203-250,253-280,418-444). submit은 전체 legacy pipeline과 점수 계산을 실행해 저장한 뒤 신청자에게 접수·다음 절차·보완 안내를 준다(review.py:447-582,690-751). 따라서 NEEDS_REVIEW 제출 가능, FAIL/필수 미업로드 제출 차단이다.

### 1.2 입력 형태 × 문서 종류 경로

아래 표는 일반 슬롯 업로드 경로다. 병합 PDF는 별도 split_pdf_pages 경로이며 JBAI/LocalOcr/own 추출을 거치지 않는다. JBAI는 JBAI_API_KEY와 JBAI_ALLOW_REAL_DOCS가 모두 참이고, 초본·등본·납부확인·자격득실이며 글자층 PDF가 아닐 때 먼저 처리한다. 4대보험과 취업서류는 미지원(jbai.py:6-13,43-46,220-240). 기본 own 선택은 환경과 자산 파일에 따라 달라진다(localocr.py:51-65). own은 PP-OCRv5 DB 검출+한국어 CTC 인식이며 CPUExecutionProvider만 지정한다(engine_v2/pipeline/ocr/own.py:1-4,37-53). 서비스는 공개 사전학습 모델을 쓰며 현재 미세조정은 하지 않았다(engine_v2/docs/own-ocr.md:2-14).

| 형태 | 초본·등본 | 건강보험·4대보험 | 취업서류 | 그 밖 |
|---|---|---|---|---|
| 글자층 PDF, 첫 쪽 문자 있음 | JBAI 건너뜀. PdfText면 첫 쪽만; own 통상 불사용 | 첫 쪽 분류 성공 시 LocalOcr _load_pages/추출기. 쪽마다 50자 이상 텍스트층, 그 외 선택 OCR | 분류 성공 시 LocalOcr engine_v2 추출기 | PdfText 첫 쪽 |
| 이미지 PDF | 조건부 JBAI 또는 LocalOcr 모든 이미지 쪽(기본 own) | JBAI는 4대보험 미지원; LocalOcr OCR 및 추출기 | LocalOcr OCR 및 receipt/exam/interview 추출기 | OCR 후 일반 정규식 파싱. 분류 실패 시 PdfText는 첫 쪽 무텍스트 |
| JPG/PNG 사진 | JBAI 조건 또는 LocalOcr 선택 엔진 1장 OCR | LocalOcr OCR/추출기 | LocalOcr OCR/추출기 | LocalOcr 일반 파싱; PdfText는 캡처/화질만 |
| 혼합 PDF | 첫 쪽 텍스트면 text 경로. PdfText면 1쪽만. 첫 쪽 이미지·뒤 텍스트는 LocalOcr 거절 가능 | 첫 쪽 분류가 되면 _load_pages가 페이지별 처리, 아니면 누락 가능 | 동일 | PdfText 첫 쪽만. 한 쪽 TEXT_LAYER면 LocalOcr 거절 가능 |
| 암호 PDF | Fixture stem 일치 예외 외 PdfText unreadable | 동일 | 동일 | UNREADABLE_FILE |
| 병합 PDF(auto) | split_pdf_pages 페이지별 분류 후 빈 슬롯 배정, own OCR 없음 | 동일 | 동일 | 미배정 페이지 NEEDS_REVIEW; 분할 실패는 단일 판독 |

근거: chain demo/backend/ocr/__init__.py:21-50; JBAI jbai.py:6-13,220-250; LocalOcr localocr.py:429-530; PdfText pdftext.py:312-403; 병합 documents.py:475-587; 전처리 engine_v2/pipeline/preprocess.py:24,82-155.

**유형 판별:** 슬롯 기대값으로 문서 유형을 강제하지 않는다. PdfText는 본문 키워드, LocalOcr는 OCR 텍스트에 pdftext 분류기를 적용한다(pdftext.py:23-51,220-227; localocr.py:495-498). 미판별=NEEDS_REVIEW, 슬롯과 유형 불일치=WRONG_DOCUMENT_TYPE; 유형 confidence<.85면 모호화한다(doc_check.py:306-341). 병합은 감지 유형이 맞는 최초 빈 슬롯을 쓴다(documents.py:521-570).

**실제 규칙 엔진:** demo/backend/engine_adapter.py는 루트 engine의 config/models/check_single_document/run_pipeline을 import하고(demo/backend/engine_adapter.py:25-31), 시작 때 공고 cutoff·필수문서·confusion group·소득 제한을 덮어쓴다(43-140; demo/backend/main.py:24-29). 단건 업로드는 legacy engine 단건검사와 demo 보강 규칙(demo/backend/rules/doc_check.py:3-10,343-390), 제출은 legacy run_pipeline(demo/backend/api/review.py:484-498)을 쓴다. engine_v2/engine.py 및 rulepacks는 별도 CLI/테스트 경로다. LocalOcr가 engine_v2 전처리·추출기를 재사용하는 것과 rulepack 판정은 다르다.

## 2. own이 의도대로 작동하는가

| 항목 | 판정 | 설명 |
|---|---|---|
| (a) 서비스 기본 own | 의도대로(조건부) | ENGINE_V2_OCR가 비고 모델 파일이 있으면 own. 파일 누락 시 easyocr이므로 무조건 own은 아님(demo/backend/ocr/localocr.py:51-65). |
| (b) 이미지 PDF·사진 모든 쪽 own | 다름 | JBAI 조건, 모델 누락, 환경변수 엔진 선택에 따라 다르다. 정상 이미지 PDF는 모든 전처리 쪽을 선택 엔진으로 읽는다(localocr.py:447-503; engine_v2/pipeline/preprocess.py:136-155). |
| (c) own 실패·대체 사유가 담당자 화면에 표시 | 다름 | easyocr 사유는 경고 로그에만 있고 결과 fallback_reason은 비어 있음. engine 이름만 화면에 표시(localocr.py:51-65,419-427; demo/backend/api/officer.py:674-678). run_ocr 오류는 None만 내고 계층 전환 기록 없음(localocr.py:488-493). JBAI OcrFallback은 체인이 사유를 저장하는 별도 경로(__init__.py:40-44). |
| (d) applevision/easyocr 등 다른 엔진이 조용히 쓰이지 않음 | 다름 | own 모델 파일 없으면 easyocr 자동 선택, 환경변수로 easyocr/applevision/paddle/off 지정 가능(localocr.py:51-65,421-427). |
| (e) own 신뢰도와 판정 | 연결됨 | 추출기 필드 confidence에서 OcrResult confidence를 만든다(localocr.py:163-176,196-238,331-369). legacy 기준 OCR .85, 화질 .6(engine/config.py:12-15). 낮은 신뢰도는 NEEDS_REVIEW, 저신뢰 날짜/본인 mismatch도 모호화(engine/stage1_document_check.py:59-78; doc_check.py:387-390,567-589). |
| (f) 벤치마크와 서비스 일치 | 부분적으로 다름 | ocr_bench 합성 score_gt는 전체 문자열 내 정답 포함(engine_v2/tools/ocr_bench.py:22-34). private_bench는 추출 필드 완전일치/CER(private_bench.py:115-190). synth_bench는 engine_v2 합성 필드·CER·신뢰도 보정(synth_bench.py:1-7,21-28,84-87,171-190). job_docs_bench 기본은 텍스트, 이미지 엔진 선택지에 own 없음(job_docs_bench.py:1-7,85-107). PDF 전처리는 서비스와 다름(H11). |

이번 실행에서는 합성 이미지 read_document의 실제 engine을 확인하지 않았다. P2 러너는 own 실추론을 하지 않으며 설치 모델로 추론 성공 여부를 단정할 수 없다. P17 러너는 자산 있을 때 합성 업로드 own CPU 추론을 검사하도록 작성돼 있지만 이번 범위에서 실행하지 않았다(demo/backend/tests/run_p17_own_scenarios.py:191-256).

## 3. 판정 기준

### 3.1 사업별 요건

기본 발급일 규칙은 신청별 기준 버전으로 저장된다. 두배적금 기본 after_notice(2026-03-03), 취업패키지 after_date(2026-01-01). 담당자 API에서 새 버전을 편집할 수 있다(demo/backend/rules/criteria.py:17-68,73-101,142-165; demo/backend/api/criteria.py:29-40,72-103,180-198; programs.py:357-452). legacy 비교는 min보다 이전만 실패이므로 경계 날짜 포함(engine/stage1_document_check.py:44-50).

| 사업·항목 | 쓰는 필드 | 기준값과 출처 | PASS | FAIL | NEEDS_REVIEW | 코드 |
|---|---|---|---|---|---|---|
| 공통 파일 | 암호·화질·confidence | OCR .85/화질 .6, engine 설정(engine/config.py:12-15) | 암호 없음, 기준 통과 | 암호/열기 실패 | 낮은 신뢰도·화질·유형불명 | engine/stage1_document_check.py:28-37,73-78; doc_check.py:129-145 |
| 두배적금 초본 | 유형, 발급일, 신청인/대상자 신원, 주소이력·쪽표시 | 2026-03-03 이후, 최근 5년 주소이력; checklist(required_docs.py:223-251,352-385), 기준(criteria.py:28-35,56-57) | 유형·날짜·본인·쪽 완전성 통과 | 오분류, 확정 날짜/신원 불일치, 이력 미포함, 쪽 누락·중복 | 신원·쪽표기 미판독, 저신뢰, 한 건 이력 누락 의심 | doc_check.py:255-288,306-390,495-589,634-655 |
| 두배적금 납부확인서 | 유형·발급일·월별 고지액·가입구분·가입자 | 공고일 이후, 2025-10~12 기본 고지월; 고지금액 기준(required_docs.py:355-367; criteria.py:28-57; scoring.py:122-125) | 대상월·신원 대조 통과 | 확정 유형·날짜·본인 위반 또는 대상월 누락 | 가입자/가구 대조 불확실, 금액 미판독 | doc_check.py:443-458,531-553; identity.py:70-157 |
| 두배적금 자격확인서 | 유형·발급일·가구원수·가구원목록 | 공고일 이후; 소득 가구원 수 기준(required_docs.py:369-377; scoring.py:122-133) | 유형·날짜·가입자 검사 및 가구원 판독 통과 | 확정 유형·날짜·본인 위반 | 가구원수/내부일치 판독 불명, 전체 재검토 | doc_check.py:531-553; api/review.py:500-523 |
| 두배적금 자격득실 | 유형·발급일·자격이력·문서확인번호·5년 coverage | 공고일 이후·최근 5년(criteria.py:28-57; required_docs.py:378-386) | 최근 5년 및 내부 검증 통과 | 확정 기간 미포함·날짜/유형 위반 | 기간 파싱 불가, 확인번호 불일치 confidence 저하 | doc_check.py:460-493; localocr.py:202-218 |
| 두배적금 근로증빙 | 유형·발급일, 신청서 근로유형 | 직장 4대보험, 지역 일용근로, 사업자는 사업자등록증명, 농/어업 경영체; 공고일 이후(required_docs.py:164-220; programs.py:358-370) | 선택 유형 문서 및 날짜 통과 | 확정 오분류·날짜 위반 | 저신뢰·필드 미판독 | required_docs.py:164-220,389-411 |
| 두배적금 행정동의 | 동의·서명·성명·생년월일 | 기본 전자서명 대체, 종이 선택 시 업로드(required_docs.py:413-440; criteria.py:65-68) | 동의·서명·본인 일치 | 명시 비동의, 확신 있는 본인 불일치 | 동의/서명/본인정보 미판독 | api/documents.py:378-412; doc_check.py:590-611 |
| 취업패키지 초본 | 유형·발급일·성명·생년월일·주소 | 2026-01-01 이후, 출생 1987-01-01~2008-12-31, 전북 주소(programs.py:400-417; v2 초안 rulepack:35-63) | 유형·날짜·신원·주소 통과 | 확정 유형·날짜·신원·주소 위반 | 저신뢰/불확실 | required_docs.py:223-251; 서비스 pipeline api/review.py:484-498 |
| 취업패키지 면접확인서 | 성명·면접일 | 기본 날짜 cutoff 2026-01-01, 기준 버전 편집 가능(criteria.py:17-47; subsidy.py:78-111) | 유형·본인·날짜 통과 | 확정 유형·날짜·신원 위반 | 저신뢰/미판독 | subsidy.py:78-111; required_docs.py:304-340; doc_check.py:306-390,531-632 |
| 취업패키지 영수증 | 결제금액·날짜 basis | 정장 실비 5만원×2, 사진 2만원×1, 자격증 5만원×2, 면접비 5만원 정액×2(subsidy.py:92-154). 카탈로그 담당자 편집 가능(criteria API:113-138) | 판독액과 신청액 일치, 문서/날짜 적합 | 확정 오분류·날짜 위반 | 금액 미판독 또는 입력액과 불일치 | api/documents.py:412-454; rules/subsidy.py:92-154 |
| 취업패키지 응시확인서/성적표 | 문서유형·응시일·성명 | 응시일 필수, 날짜 basis 설정 가능(subsidy.py:130-153; criteria.py:20-27) | 종류·응시일·날짜·본인 통과 | 글자층에서 응시일 확정 누락, 유형/날짜/본인 위반 | OCR 이미지에서 응시일 미판독 | doc_check.py:404-441; localocr.py:300-369; subsidy.py:130-153 |

### 3.2 공통 판정 및 합산

- **판독 실패와 confidence:** 체인 무결과는 confidence 0 및 tier=none(demo/backend/ocr/__init__.py:52-59). generic OCR confidence 상한 .8(localocr.py:43-45,372-390)로 .85 기준 아래에 둔다.
- **화질:** .6 기준. LocalOcr는 DPI 기반 .5/.7/.9 또는 사진 DPI 불명 .75(localocr.py:87-93). PdfText 이미지는 짧은 변 1400/1000/700px 기준 .9/.75/.55/.35(pdftext.py:365-380). 낮은 화질은 review-only(doc_check.py:129-145).
- **화면 캡처:** 알려진 화면 해상도 근처 + 카메라 EXIF 없음이면 의심 표시, 자동 FAIL 대신 NEEDS_REVIEW(pdftext.py:340-364; doc_check.py:395-402).
- **필수 필드 부재:** text/fixture는 MISSING_REQUIRED_FIELD FAIL, localocr/JBAI OCR은 미기재와 미판독을 구분할 수 없어 REQUIRED_FIELD_UNREADABLE NEEDS_REVIEW. 영수증 금액은 별도 review(doc_check.py:404-441). 취업서류는 텍스트층만으로 처리하면 confidence .9, OCR이 섞이고 필드가 없으면 .5(localocr.py:331-369).
- **발급일 mode:** after_notice=공고일 이후 기준, after_date=지정일 기준, within_days=신청일-N일부터 신청일까지, none=날짜 컷 없음(criteria.py:172-195). 기본 두배적금 after_notice, 취업패키지 after_date 2026-01-01(criteria.py:28-47). min 이전만 실패여서 기준일 당일은 통과(engine/stage1_document_check.py:44-57).
- **본인 일치:** identity 있을 때 맞는 유형의 성명/생년월일 비교. confidence≥.85 mismatch FAIL, 미만 REVIEW. 초본은 신청인과 대상자를 비교하고 NHIS는 가입자 규칙 적용(doc_check.py:531-589; identity.py:70-157).
- **5년:** 자격득실 최근 5년 coverage, 기간 미포함 FAIL·파싱 불가는 REVIEW(doc_check.py:460-493; criteria.py:56-57). 초본 주소이력 미포함은 별도 FAIL, 1건 이력은 누락 의심 REVIEW(doc_check.py:634-655).
- **미업로드/최종합산:** 필수 미업로드와 FAIL은 submit blocker(review.py:203-250,690-705). NEEDS_REVIEW는 제출 가능(review.py:253-280). 문서/신청은 FAIL 우선, 다음 NEEDS_REVIEW, 나머지 PASS(doc_check.py:657-662; engine/pipeline.py:17-23,78-98).
- **문서확인번호:** 자격득실 추출기 검증 불일치면 confidence를 최대 .4로 낮춰 비교 실패를 review로 유도(localocr.py:202-218,226-238).
- **화면 차이:** 신청자는 제한된 필드·finding/status·confidence(common.py:175-227), 담당자는 engine/tier/fallback/bbox 및 상세 근거(officer.py:652-683,686-746). 제출 응답에 점수 없음(review.py:690-751).
- **미기준 요건:** 두배적금의 소득 100/110/120/130% 구간 환산은 데모 추정치, 8인 이상 참고값(scoring.py:22-46,229-269). 가구원 불일치/미판독은 전체 담당자 재검토(review.py:500-523). 근로유형에 맞는 문서는 요구하지만 legacy stage2에 재직여부 판정 규칙은 없음(required_docs.py:164-220; engine/stage2_eligibility_check.py:22-69). 취업패키지는 소득·근로 요건을 끈 상태(programs.py:400-423). 결제일≤면접일, 대여기간, 허용 시험/업종도 규칙 미구현으로 명시되나 v2 rulepack은 현재 서비스 경로가 아님(engine_v2/rulepacks/job_package.yaml:6-13).

## 4. 시험이 덮는 경로

### 4.1 실행 결과

| 실행 | 결과 | 범위 |
|---|---:|---|
| ./.venv/bin/python -m pytest -q engine_v2/tests demo/backend/tests | 260 passed, 3 skipped, 0 failed | pytest가 수집한 engine_v2 테스트. demo/backend/tests에는 test_*.py가 0개라 run_*_scenarios.py는 여기서 실행되지 않음. |
| ./.venv/bin/python -m demo.backend.tests.run_p2_scenarios | 53 passed, 0 failed | 근로유형별 체크리스트, fixture 판정, 합성 글자층 PDF PdfText, 암호/캡처, 병합 분리·배정(run_p2_scenarios.py:145-249,255-370). |
| 합계 | 313 passed, 3 skipped, 0 failed | 두 실행의 확인 항목 합산. |

처음 시스템 python 실행파일이 없었고 시스템 python3에는 pytest가 없어서 저장소 .venv로 실행했다. 테스트는 임시 합성 자료와 저장소 테스트 fixture만 썼다.

### 4.2 커버리지와 미실행 경로

- engine_v2 tests는 별도 engine_v2.run/추출기/규칙팩, own 어댑터 구조, 오류·좌표, synthetic metric을 단위검사한다(engine_v2/tests/test_own_ocr.py:13-75). own mock 경로와 실제 CPU 추론은 구분해야 한다.
- P2는 Tier1 fixture와 합성 글자층 PDF→PdfText, 병합 분리를 검사한다(run_p2_scenarios.py:191-249,255-370). 이미지 PDF→LocalOcr→own 실추론은 검사하지 않는다.
- P17 합성 업로드→own CPU 실제 추론 러너는 있지만 이번에는 P2 외 시나리오 실행기를 실행하지 않았다(demo/backend/tests/run_p17_own_scenarios.py:191-256).
- 이번 실행에서 덮지 않은 중요 경로: 다중 쪽 이미지 PDF own 실추론, easyocr 대체와 담당자 UI, run_ocr 오류 기록, 혼합 PDF 양쪽 페이지 순서, 2쪽 이후에만 있는 필드 추출, 업로드부터 최종 제출까지 통합, 18개 scenario runner 전체. 이 목록 자체가 실패 입증은 아니다.

### 4.3 18개 demo 시나리오 러너의 예정 커버리지

아래 매핑은 runner 코드를 읽어 정리한 것이며, 실제 실행한 것은 P2뿐이다. pytest 기본 패턴은 run_*.py를 자동 수집하지 않는다.

| 러너 | 표 1 경로/목적 | 이번 실행 |
|---|---|---|
| P2 run_p2_scenarios.py | 근로유형 체크리스트, fixture, 합성 텍스트 PDF, 암호·캡처, 병합 분리 | 실행, 53/0 |
| P3 run_p3_scenarios.py | 두배적금 scoring, 누락 facts, 동점, 제출 API 흐름 | 미실행 |
| P4 run_p4_scenarios.py | 담당자 목록/필터/역할/문서 하이라이트 및 판정 표시 | 미실행 |
| P5 run_p5_scenarios.py | 취업패키지 분기, 실비, 추가서류, 응시일, 보완, officer 화면 | 미실행 |
| P6 run_p6_scenarios.py | S1–S10 전체 시연 시나리오 재현성·멱등성 | 미실행 |
| P7 run_p7_scenarios.py | 작성 PDF 템플릿·좌표·렌더링, 신청자 API 비식별 | 미실행 |
| P8 run_p8_localocr_scenarios.py | 초본 이미지 PDF LocalOcr 추출·판정, 텍스트 PDF fallback, bbox/신뢰도 | 미실행. OCR은 fake로 대체하는 runner 설명 |
| P9 run_p9_identity_scenarios.py | 본인 대조, identity uncertainty, 신청자/담당자 표시, 4대보험 개인정보 | 미실행 |
| P11 run_p11_criteria_scenarios.py | 기준 버전 고정, 날짜/고지월/스캔본 정책 편집 | 미실행 |
| P12 run_p12_subsidy_criteria_scenarios.py | 취업패키지 횟수·영수증·날짜 기준 버전 | 미실행 |
| P13 run_p13_household_scenarios.py | 자격확인서 가구원 수·소득 산정·중복가구 review | 미실행 |
| P14 run_p14_pdf_forms_scenarios.py | 원본 서식 템플릿·좌표맵·PDF 렌더링 | 미실행 |
| P15 run_p15_jbai_scenarios.py | fake JBAI 응답·fallback·개인정보 마스킹·UI 분리 | 미실행, 네트워크 호출 없는 mock runner |
| P16 run_p16_job_docs_scenarios.py | 취업서류 extractor, text/image 필수항목 차이, 업로드 메타데이터 | 미실행. OCR mock/합성 파일 경로 |
| P17 run_p17_own_scenarios.py | own 기본값·모델 누락 대체·오류 처리·합성 own 실제 업로드 | 미실행 |
| P18 run_p18_applicant_precheck_scenarios.py | 쪽 완전성, uncertainty, 보험, API 노출, blur/rotation 합성 | 미실행 |
| P19 run_p19_nhis_history_scenarios.py | 자격득실 이미지 PDF 업로드와 5년 history 판정 | 미실행, fake OCR |
| P20 run_p20_nhis_continuation_scenarios.py | 자격득실 후속 쪽의 신원 생략·확인번호 비교 | 미실행, fake OCR |

근거: P2–P9 runner 헤더/검사항목 각 파일 1–20행; P11–P20의 설명 및 검사 함수: run_p11_criteria_scenarios.py:1-10, run_p12_subsidy_criteria_scenarios.py:1-10, run_p13_household_scenarios.py:1-10, run_p14_pdf_forms_scenarios.py:1-15, run_p15_jbai_scenarios.py:1-22, run_p16_job_docs_scenarios.py:1-18, run_p17_own_scenarios.py:1-8, run_p18_applicant_precheck_scenarios.py:1-6, run_p19_nhis_history_scenarios.py:1-8, run_p20_nhis_continuation_scenarios.py:1-8.

### 4.4 engine_v2 pytest 세부 경로

- own adapter/default/error/좌표: test_own_ocr.py:13-75, test_own_format_integration.py:1-40.
- PDF 전처리·분류 및 페이지 소스: test_classifier.py:75-113, test_synth_realism.py:42-66.
- 추출기별 자료: test_resident_abstract.py, test_nhis_extractors.py, test_insurance_4.py, test_exam_docs.py, test_receipt.py. 각 테스트는 엔진 추출기 중심이며 demo 업로드 API 전체를 자동으로 실행하는 것은 아니다.
- 엔진 규칙팩·상태 합산·벤치 지표: test_engine.py, test_job_package_rulepack.py, test_bench_metrics.py, test_private_bench.py, test_insurance_private_bench.py.
- demo/backend/tests pytest 수집 결과는 0건이다. demo backend 검증은 위 18개 수동 시나리오 러너가 제공하지만 이번 요청에서 P2만 실행했다.

## 5. 발견한 문제

코드는 수정하지 않았다. 영향 분류 우선순위에 따라 정렬했으며 재현은 합성 자료로만 가능하다.

| 순위 | 제목 | 근거 | 영향 분류 | 합성 재현 방법 | 수정 방향 |
|---:|---|---|---|---|---|
| 1 | 첫 쪽 글자층 PDF 후속 페이지 내용 누락 | demo/backend/ocr/pdftext.py:325-337; localocr.py:403-446 | 잘못된 통과 가능, 판독 누락 | 2쪽 합성 PDF, 1쪽 정상 유형/날짜, 2쪽에만 다른 주소·전입일·필수항목을 두고 슬롯 업로드 | 모든 페이지를 추출하거나 쪽 완전성 확인 |
| 2 | 첫 쪽 문자 1개 경계와 페이지별 50자 경계가 달라 혼합 PDF가 거절될 수 있음 | localocr.py:403-413,481-487; engine_v2/pipeline/preprocess.py:24,82-92 | 판독 누락 | 1쪽 이미지 무텍스트, 2쪽 50자 이상 텍스트층 합성 PDF와 반대 순서를 각각 업로드 | 전체 PDF의 페이지별 텍스트/이미지 처리를 단일 규칙으로 통일 |
| 3 | Fixture가 파일 내용이 아닌 이름 stem으로 일반 업로드를 대체 | demo/backend/ocr/fixture.py:373-399; ocr/__init__.py:37-50 | 잘못된 통과 가능 | fixture stem과 같은 이름의 무관한 합성 파일로 read_document 호출 | fixture 경로를 명시적인 테스트/시연 설정으로 격리 |
| 4 | 자격득실 확인번호 불일치가 제출 가능한 NEEDS_REVIEW로만 처리됨 | demo/backend/ocr/localocr.py:202-207,226-238; demo/backend/rules/doc_check.py:460-493; demo/backend/api/review.py:203-280 | 잘못된 통과 가능 | 서로 다른 확인번호가 든 합성 자격득실 페이지로 판독검증 실패를 만들고 confidence/status 및 final-check 응답 확인 | 확인번호 검증 실패의 제출 차단 여부를 정책으로 정하고 결과에 반영 |
| 5 | 취업패키지 결제일≤면접일 및 인정 시험/업종 규칙이 실행 규칙에 없음 | engine_v2/rulepacks/job_package.yaml:6-13; engine/stage2_eligibility_check.py:22-69 | 잘못된 통과 가능 | 결제일이 면접일보다 늦거나 임의 시험명인 합성 자료 업로드 | 기준 확정 후 날짜 교차검증/허용 목록 추가 |
| 6 | LocalOcr가 혼합 PDF를 거절하면 PdfText도 뒤 페이지로 구제하지 않음 | localocr.py:481-487; pdftext.py:325-337 | 판독 누락 | 첫 쪽 이미지 무텍스트·후속 쪽만 텍스트인 합성 PDF 업로드 | 나머지 페이지를 다음 계층이 이어 읽는 계약 추가 |
| 7 | easyocr 대체 사유가 담당자 화면에 보이지 않음 | localocr.py:51-65,419-427; officer.py:674-678 | 표시 누락 | 모델 경로를 없는 임시 디렉터리로 monkeypatch, easyocr stub, officer view의 engine/fallback 확인 | 대체 사유를 결과·저장값에 연결 |
| 8 | OCR 오류로 다음 tier로 갈 때 오류 원인이 남지 않음 | engine_v2/pipeline/ocr/__init__.py:152-162; localocr.py:488-493; ocr/__init__.py:45-48 | 표시 누락 | 합성 이미지에서 run_ocr를 오류 반환하도록 mock | 개인정보 없는 오류코드와 tier 전환 기록 |
| 9 | PdfText 사진 경로는 OCR 없이 confidence 0을 내어 재검토를 늘림 | demo/backend/ocr/pdftext.py:340-386 | 불필요한 담당자 확인 | OCR off 설정에서 합성 사진 결과 확인 | OCR 미실행과 OCR 판독 실패를 별도 상태로 표시 |
| 10 | score_gt 부분 문자열 점수는 오독·중복·오배치를 놓칠 수 있음 | engine_v2/tools/ocr_bench.py:22-34 | 측정 오류 | 정답 문자열을 포함하면서 오류값도 있는 합성 텍스트에 score_gt 실행 | CER·필드 점수와 구분된 지표명 사용 |
| 11 | private_bench PDF 전처리가 서비스와 달라 결과 직접 비교 곤란 | private_bench.py:63-77; preprocess.py:82-133 | 측정 오류 | 텍스트층/큰 이미지 합성 PDF를 양쪽 함수에 넣고 페이지 source/픽셀 비교 | 전처리 공유 또는 차이 설명 |
| 12 | “4대보험 own 5/5” 측정 출처를 현 저장소에서 특정할 수 없음 | ocr_bench.py:22-34; private_bench.py:115-152; insurance_bench.py:17-39 | 측정 오류 | 합성 5필드에 문자열 포함 점수와 추출 필드 점수를 각각 계산 | 벤치명·분모·지표 정의를 결과와 함께 보존 |
| 13 | OCR adapter 주석의 구형 3계층 설명이 현재 체인과 다름 | demo/backend/ocr/base.py:1-14; demo/backend/ocr/__init__.py:21-27 | 문서와 코드 불일치 | 정적 코드 확인 | 현재 체인과 fallback 동작으로 주석 갱신 |


