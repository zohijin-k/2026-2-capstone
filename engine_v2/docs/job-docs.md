# 취업지원패키지 추가서류 판독 1단계

결제영수증·응시확인서/성적표·면접확인서를 읽는 판독기와 그 평가 경로를 정리한다. 이 단계는 **읽기와 서류 안
검증**까지다. 지원 한도·횟수·신청 금액 대조·인정 시험 목록·업종 판단은 하지 않는다. 모든 시험 자료는 가상
값이며 실서류는 이 문서 작성 중에 열지 않았다.

## 기존 구조와 호환 계약

- 판독기: `extractors/receipt.py`, `exam_docs.py`(응시확인서·성적표를 한 부품이 판별), `interview_confirmation.py`.
  공통 처리는 `extractors/job_common.py`(건강보험 서류의 `nhis_common`과 같은 역할).
- 계약: 다른 판독기와 같이 `extract(pages, today)` → `detected_type, type_confidence, fields, validations,
  warnings, diagnostics`. `engine.EXTRACTORS`에 등록돼 있다.
- 필드 이름은 데모 `doc_check`·`subsidy`가 이미 쓰는 한국어 이름이다. 날짜는 `date`, 금액은 `nhis_payment`·
  `make_gt`와 같이 숫자 문자열이다. 값을 못 읽으면 필드를 만들지 않는다(빈 값이 '통과'처럼 보이지 않게).
- 날짜·금액·번호는 `format_text.normalize_format_text`로 대시만 맞춘 사본에서 해석한다(`insurance_4`·
  `nhis_common`과 같음). 이름·OCR 단어·근거 원문은 바꾸지 않는다. 주민등록번호 뒷자리는 읽는 즉시 지운다.
- 서식이 하나로 정해져 있지 않아 좌표를 고정하지 않고 '라벨 → 값'으로 읽는다: 라벨 오른쪽, 없으면 바로 아래
  한두 줄. 줄 단위 상자(OCR이 '상호: 가상상점 사업자등록번호: …'를 한 상자로 낸 경우)에서도 다음 칸 라벨에서
  끊고, '2026.09.2112:02'처럼 날짜·시각이 붙어 읽힌 경우도 날짜로 읽는다.
- 팀 평가 도구에 그대로 붙어 있다:
  - `synth_bench.EXTRACTORS`에 4종 등록 → `ocr_bench --synth`, `extract_diag --doc`이 함께 받는다.
  - `private_bench`(`ocr_bench <파일> --gt`)에 `DOCS`·`KEYS` 추가. 정답 키는 `make_gt --doc receipt` 등과 같다.
    전북AI 결과 판독기(`jbai_text`)가 없어 jbai 엔진은 사유 코드 6(이 서류 미지원)으로 건너뛴다.
  - `make_synth_eval --suite job_package`로 팀 합성 세트와 같은 렌더링·글꼴·8가지 열화·train/test 배치를 쓴다.
- 바꾸지 않은 것: 기본 합성 세트(`--suite core`)의 출력, `extract_diag --synthetic-suite`의 재현 사례 28건,
  분류 모델 학습 데이터(`classifier/data.py`는 기본 세트의 초본·납부확인서만 가져다 쓴다).
- 데모: `demo/backend/ocr/localocr.py`가 텍스트 PDF와 이미지 모두 이 판독기를 쓴다. 접수확인서·수험표는
  `doc_types`에 별도 종류로 있어 '다른 서류' 안내가 나간다(초본 칸의 등본과 같은 처리). 사진·스캔에서 응시일을
  못 읽으면 부적합이 아니라 `REQUIRED_FIELD_UNREADABLE`(확인필요)이다.

## 필드와 서류 안 검증

| 판독기 | 서류 | 필드 | 서류 안 검증 (`validations`) |
|---|---|---|---|
| `receipt.py` | 카드 매출전표, 간이영수증, 온라인 결제 화면, 계좌이체 확인증 | 결제금액, 결제일, 상호, 받는분, 사업자등록번호, 결제수단, 공급가액, 부가세, 품목수 | `brn_checksum`(사업자등록번호 검증숫자), `supply_plus_vat_matches`, `single_total`, `payment_date_not_future`, `not_cancelled`, `single_item`(일괄결제 아님) |
| `exam_docs.py` | 응시확인서, 성적표 | 성명, 생년월일, 시험명, 응시일, 발급일 | `name_found`, `exam_date_found`, `exam_name_found`, `exam_date_not_future`, `exam_date_not_after_issue` |
| `interview_confirmation.py` | 사업계획서 면접확인서 서식, 기업 자체 양식 | 성명, 생년월일, 회사명, 업태업종, 면접일, 면접시간, 면접장소, 응시직군, 확인일 | `name_found`, `company_found`, `interview_date_found`, `interview_date_not_future`, `interview_not_after_confirmation`, `company_names_match`(회사명 칸 = 서명란) |

접수확인서(도청 문제 제안서: 결제영수증 대체 불가)와 수험표(응시 증명 아님)는 `document_type` 검증이 실패한다.
면접자 주소·연락처·이메일, 기업 소재지·담당자는 읽지 않는다. 필드 신뢰도는 다른 판독기와 같이 검증 통과율
(0.4+0.6×통과율)이며 보정된 확률이 아니다.

## 평가 정의

1. **팀 합성 세트** — `make_synth_eval --suite job_package`: 4종 × 8열화(clean, scan300, blur, noise, rotate,
   jpeg, phone_weak, phone_strong) × 분할별 글꼴. 칸은 기본 세트 규칙을 따른다(머리 칸 y 14/18/22에 라벨 x=10·
   값 x≥25, 본문 y 27–70, 맨 아래 합성 전용 문구). 그래서 train 배치에서는 머리 칸 값이 라벨 아래로 내려간다.
   상호·회사명 같은 글 값은 본문에 둔다. 표본 이름은 `job_` 접두사, 난수 씨앗은 문서 번호+100으로 기본 세트와
   겹치지 않는다. 채점은 `ocr_bench --synth`(= `synth_bench`, CER·필드 완전 일치).
2. **패키지 시나리오** — `make_job_docs`: 실제와 비슷한 영수증 모양 4종, 공식 면접확인서 서식(저장소 PDF 위에 채움)과
   기업 자체 양식, 결함 서류(취소 전표·일괄결제·접수확인서·수험표)를 화질 5조건으로 만든다. `job_docs_bench`가 서류 종류
   판별, 필드, 일부러 넣은 결함을 검증이 잡았는지를 본다. 팀 합성 세트에 없는 것을 보는 보조 시험이다.
3. **실서류(값 미출력)** — `make_gt --doc receipt`로 정답을 만들고 `ocr_bench <파일> --gt <정답> --doc receipt`,
   `extract_check <파일> --doc receipt`, `extract_diag <파일> --doc receipt`로 점검한다. 셋 다 값을 출력하지 않는다.

## 결과 (2026-11-11~12, Windows CPU)

**완전 OCR(모델 없음):** 패키지 세트 4종의 test·train 배치 모두 필드가 정답과 같고 서류 안 검증이 모두 통과한다
(`tests/test_job_eval_integration.py`).

**대체 측정:** 이 PC에는 `own` 모델과 나눔 글꼴이 없어, 같은 PP-OCRv5 한국어 모바일 모델을 쓰는 RapidOCR 3.10과
맑은 고딕(test 배치, 글꼴 1종)으로 `synth_bench`를 돌렸다. 기본 세트도 같은 조건으로 함께 재서 비교한다.
보정은 `--rectify-phone`(팀 원근 보정).

| 세트 | 휴대폰 외 6열화 | phone_weak | +보정 | phone_strong | +보정 |
|---|---|---|---|---|---|
| 기본(초본·납부·자격득실) | 96/96 | 4/16 | 16/16 | 2/16 | 2/16 |
| 패키지 4종 | 156/156 | 9/26 | 26/26 | 6/26 | 16/26 |

CER은 두 세트 모두 거의 0이다. 휴대폰 열화에서 필드가 틀리는 것은 인식이 아니라 원근 때문에 줄 묶기가 깨진
것이며, 기본 세트 판독기와 같은 모양이다. **`own`·나눔 글꼴·macOS로는 아직 재지 않았다.**

**시나리오(`make_job_docs` 120개, RapidOCR 대체):** 서류 종류 120/120, 필드 560/560, 결함 120/120, 건당 0.3–1.1초.
처음 측정에서 날짜·시각이 붙어 읽혀 결제일을 놓친 5건은 고친 뒤 다시 쟀다. 판독기를 만든 쪽이 만든 합성이라
쉬운 시험이다.

## 한계와 다음 단계

- `own`·나눔 글꼴로 위 표를 다시 잰다(`fetch_own_models`, `fetch_synth_fonts` 뒤 아래 재현 명령).
- 휴대폰 강한 원근은 보정 뒤에도 16/26이다. 실촬영 준실셋으로 다시 본다.
- 손글씨로 채운 면접확인서는 시험하지 않았다. 인쇄 후 손으로 채워 촬영한 준실셋이 필요하다.
- 전북AI 경로는 연결하지 않았다. 패키지 서류 녹화 응답이 생기면 `jbai_text`와 데모 `jbai.py`에 더한다.
- 팀 분류 모델(`classifier/catalog.py`)에는 이미 4종이 들어 있다. 신청 화면 분류에 연결하는 일은 팀 공통 작업이다.
- 판정 쪽: 영수증 금액과 신청 금액 대조를 엔진 규칙팩으로 옮기려면 '확인필요로 끝나는 불일치' 출력이 필요하다.
  인정 시험 목록·의심 업종 목록은 도청 원본을 받은 뒤 규칙으로 넣는다.

## 재현

```bash
python -m pip install -r engine_v2/requirements.txt
python -m engine_v2.tools.fetch_own_models
python -m engine_v2.tools.fetch_synth_fonts
python -m engine_v2.tools.make_synth_eval --suite job_package
python -m engine_v2.tools.ocr_bench --synth engine_v2/data/synth_eval/job_package/manifest.json --engines own --rectify-phone
python -m engine_v2.tools.make_job_docs
python -m engine_v2.tools.job_docs_bench --engine own
python -m pytest engine_v2/tests/test_job_eval_integration.py engine_v2/tests/test_receipt.py -q
```

실서류(본인 영수증 등)는 `engine_v2/data/private/`에만 두고 값이 출력되지 않는 도구로만 점검한다.

```bash
python -m engine_v2.tools.make_gt --doc receipt
python -m engine_v2.tools.ocr_bench engine_v2/data/private/영수증.jpg --gt engine_v2/data/private/receipt.gt.json --doc receipt --engines own
```
