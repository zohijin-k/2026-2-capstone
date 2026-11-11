# Field extraction failure diagnosis (no extractor changes)

This report diagnoses the existing `004e45a` extractors. Every document/value below is synthesized by `make_synth_eval`; no real document was opened. The prior `2/4` and `3/4` describe field-match counts, not rotation degrees or blur radii. Seed `20261111`, test fonts Nanum Gothic and Nanum Myeongjo, and `inline_header_v1` are unchanged. The old 4-insurance sample deliberately includes a health-insurance acquisition/loss subtitle and is a composite synthetic test, not an authentic 4-insurance certificate.

Reproduction uses new `engine_v2/tools/extract_diag.py`. It regenerates the four failed Myeongjo resident conditions and both fonts × three documents × weak/strong phone × pre/post rectification: 28 revised runs. Optional `--include-legacy` adds the three prior bundled-CJK phone failures. The generator, OCR, rectifier, layout routines, extractors, scoring and backend remain unchanged. No geometry oracle is passed to extraction.

```bash
mkdir -p engine_v2/data/synth_eval/diagnosis
.venv/bin/python -m engine_v2.tools.extract_diag \
  --synthetic-suite --include-legacy --unmasked-synthetic \
  --output engine_v2/data/synth_eval/diagnosis/report.json
```

Without `--unmasked-synthetic`, every expected/actual field, OCR word and parsed header value is replaced with `[masked]`. The flag works only for internally generated synthetic pages; supplying a file with that flag is rejected before reading it. Real-file CLI use captures Python/native dependency output and returns a fixed error code rather than exception text. Output files require an explicit destination with an existing parent.

Mac example (masked, synthetic opt-out unavailable):

```bash
.venv/bin/python -m engine_v2.tools.extract_diag \
  "$HOME/Documents/ocr-input.pdf" --doc resident_abstract --engine own
# Repeat the same explicit file with --engine applevision to compare line/box geometry.
# Optional --gt expects a flat JSON object using extractor field keys.
```

## Actual replay results

All 31 executions completed without OCR errors. All field-match counts exactly match the prior recorded benchmark. For all 28 revised runs, the entire per-field match map was also programmatically compared with the existing revised benchmark JSON and was identical. Revised suite: 28 runs / 144 checked fields / 57 correct / 87 failed. Legacy supplement: 3 runs / 16 checked fields / 10 correct / 6 failed. The low scores are intentionally reproduced existing failures, not new regression-test failures.

| ID | Document / font / condition | Rectification applied | Field matches |
|---|---|---|---:|
| D00 | 초본 / 고딕 / phone_weak | X | 1/4 |
| D01 | 초본 / 고딕 / phone_weak+보정요청 | O | 4/4 |
| D02 | 초본 / 고딕 / phone_strong | X | 0/4 |
| D03 | 초본 / 고딕 / phone_strong+보정요청 | X | 0/4 |
| D04 | 납부 / 고딕 / phone_weak | X | 2/6 |
| D05 | 납부 / 고딕 / phone_weak+보정요청 | O | 6/6 |
| D06 | 납부 / 고딕 / phone_strong | X | 2/6 |
| D07 | 납부 / 고딕 / phone_strong+보정요청 | X | 2/6 |
| D08 | 가입(복합) / 고딕 / phone_weak | X | 1/6 |
| D09 | 가입(복합) / 고딕 / phone_weak+보정요청 | O | 6/6 |
| D10 | 가입(복합) / 고딕 / phone_strong | X | 0/6 |
| D11 | 가입(복합) / 고딕 / phone_strong+보정요청 | X | 0/6 |
| D12 | 초본 / 명조 / clean | X | 2/4 |
| D13 | 초본 / 명조 / scan300 | X | 2/4 |
| D14 | 초본 / 명조 / blur | X | 3/4 |
| D15 | 초본 / 명조 / rotate | X | 2/4 |
| D16 | 초본 / 명조 / phone_weak | X | 0/4 |
| D17 | 초본 / 명조 / phone_weak+보정요청 | O | 2/4 |
| D18 | 초본 / 명조 / phone_strong | X | 1/4 |
| D19 | 초본 / 명조 / phone_strong+보정요청 | X | 1/4 |
| D20 | 납부 / 명조 / phone_weak | X | 3/6 |
| D21 | 납부 / 명조 / phone_weak+보정요청 | O | 6/6 |
| D22 | 납부 / 명조 / phone_strong | X | 2/6 |
| D23 | 납부 / 명조 / phone_strong+보정요청 | X | 2/6 |
| D24 | 가입(복합) / 명조 / phone_weak | X | 0/6 |
| D25 | 가입(복합) / 명조 / phone_weak+보정요청 | O | 6/6 |
| D26 | 가입(복합) / 명조 / phone_strong | X | 0/6 |
| D27 | 가입(복합) / 명조 / phone_strong+보정요청 | X | 0/6 |
| D28 | 초본 / 내장CJK / legacy_phone | X | 2/4 |
| D29 | 납부 / 내장CJK / legacy_phone | X | 5/6 |
| D30 | 가입(복합) / 내장CJK / legacy_phone | X | 4/6 |

Weak phone correction applied to all six documents; strong correction applied to none of six. Strong “after” rows are explicitly no-op retries and are identical to “before.” Myeongjo weak resident geometry is repaired but a minus sign remains in RRN, leaving name/birth wrong.

## Every failed field: expected → actual, stage, code, cause

Only failing fields are listed; passing fields are covered by counts above. `∅` means absent, not an empty recognized string. IDs fully identify document/font/degradation; all “after” retries have their own IDs. Source paths below are relative to `engine_v2/extractors/` except `layout.py`, which is `engine_v2/pipeline/layout.py`. Cause codes expand to direct trace observations and code logic in the next table.

| Case | Field | Expected → actual | Failing stage | Code location | Cause |
|---|---|---|---|---|---|
| D00 | name | `가상시험` → `한자` | 행 묶기 | `layout.py:40; resident_abstract.py:190,199` | R2 |
| D00 | birth_date | `1999-01-01` → `∅ (누락)` | 행 묶기 | `layout.py:40; resident_abstract.py:190,199` | R2 |
| D00 | address_history_count | `1` → `∅ (누락)` | 행 묶기 → 라벨 찾기 | `layout.py:40; resident_abstract.py:244` | R5 |
| D02 | name | `가상시험` → `한자` | 좌표 범위 / 행 묶기 | `resident_abstract.py:190,199` | R3 |
| D02 | birth_date | `1999-01-01` → `∅ (누락)` | 좌표 범위 / 행 묶기 | `resident_abstract.py:190,199` | R3 |
| D02 | issue_date | `2026-11-10` → `∅ (누락)` | 좌표 범위 | `resident_abstract.py:177,184` | R4 |
| D02 | address_history_count | `1` → `∅ (누락)` | 행 묶기 → 라벨 찾기 | `layout.py:40; resident_abstract.py:244` | R5 |
| D03 | name | `가상시험` → `한자` | 좌표 범위 / 행 묶기 | `resident_abstract.py:190,199` | R3 |
| D03 | birth_date | `1999-01-01` → `∅ (누락)` | 좌표 범위 / 행 묶기 | `resident_abstract.py:190,199` | R3 |
| D03 | issue_date | `2026-11-10` → `∅ (누락)` | 좌표 범위 | `resident_abstract.py:177,184` | R4 |
| D03 | address_history_count | `1` → `∅ (누락)` | 행 묶기 → 라벨 찾기 | `layout.py:40; resident_abstract.py:244` | R5 |
| D04 | 성명 | `가상시험` → `생년월일` | 행 묶기 / 좌표 범위 | `nhis_common.py:123` | N1 |
| D04 | 생년월일 | `1999-01-01` → `∅ (누락)` | 행 묶기 / 좌표 범위 | `nhis_common.py:148,160` | N3 |
| D04 | 발급일 | `2026-11-10` → `∅ (누락)` | 행 묶기 | `nhis_common.py:183` | N5 |
| D04 | 건강보험료 | `110000` → `∅ (누락)` | 행 묶기 | `nhis_payment.py:228,256,301` | P1 |
| D06 | 성명 | `가상시험` → `∅ (누락)` | 행 묶기 | `nhis_common.py:128,138` | N2 |
| D06 | 생년월일 | `1999-01-01` → `2026-11-10` | 행 묶기 | `nhis_common.py:148` | N4 |
| D06 | 발급일 | `2026-11-10` → `∅ (누락)` | 행 묶기 | `nhis_common.py:183` | N5 |
| D06 | 건강보험료 | `110000` → `186667` | 행 묶기 | `nhis_payment.py:228,272,301` | P2 |
| D07 | 성명 | `가상시험` → `∅ (누락)` | 행 묶기 | `nhis_common.py:128,138` | N2 |
| D07 | 생년월일 | `1999-01-01` → `2026-11-10` | 행 묶기 | `nhis_common.py:148` | N4 |
| D07 | 발급일 | `2026-11-10` → `∅ (누락)` | 행 묶기 | `nhis_common.py:183` | N5 |
| D07 | 건강보험료 | `110000` → `186667` | 행 묶기 | `nhis_payment.py:228,272,301` | P2 |
| D08 | 생년월일 | `1999-01-01` → `∅ (누락)` | 행 묶기 / 좌표 범위 | `nhis_common.py:148,160` | N3 |
| D08 | 발급일 | `2026-11-10` → `∅ (누락)` | 행 묶기 | `nhis_common.py:183` | N5 |
| D08 | 가입구분 | `직장` → `∅ (누락)` | 행 묶기 | `nhis_acquisition_loss.py:106,123,196,225` | A1 |
| D08 | 취득일 | `2020-01-01` → `∅ (누락)` | 행 묶기 | `nhis_acquisition_loss.py:106,123,196,225` | A1 |
| D08 | 변동내역 | `최근 5년 포함` → `∅ (누락)` | 기타: 선행 필드 실패 | `nhis_acquisition_loss.py:206,221` | A2 |
| D10 | 성명 | `가상시험` → `∅ (누락)` | 행 묶기 | `nhis_common.py:128,138` | N2 |
| D10 | 생년월일 | `1999-01-01` → `2026-11-10` | 행 묶기 | `nhis_common.py:148` | N4 |
| D10 | 발급일 | `2026-11-10` → `2020-01-01` | 행 묶기 | `nhis_common.py:183` | N6 |
| D10 | 가입구분 | `직장` → `∅ (누락)` | 행 묶기 | `nhis_acquisition_loss.py:106,123,196,225` | A1 |
| D10 | 취득일 | `2020-01-01` → `∅ (누락)` | 행 묶기 | `nhis_acquisition_loss.py:106,123,196,225` | A1 |
| D10 | 변동내역 | `최근 5년 포함` → `최근 5년 미포함` | 기타: 선행 필드 실패 | `nhis_acquisition_loss.py:206,211` | A3 |
| D11 | 성명 | `가상시험` → `∅ (누락)` | 행 묶기 | `nhis_common.py:128,138` | N2 |
| D11 | 생년월일 | `1999-01-01` → `2026-11-10` | 행 묶기 | `nhis_common.py:148` | N4 |
| D11 | 발급일 | `2026-11-10` → `2020-01-01` | 행 묶기 | `nhis_common.py:183` | N6 |
| D11 | 가입구분 | `직장` → `∅ (누락)` | 행 묶기 | `nhis_acquisition_loss.py:106,123,196,225` | A1 |
| D11 | 취득일 | `2020-01-01` → `∅ (누락)` | 행 묶기 | `nhis_acquisition_loss.py:106,123,196,225` | A1 |
| D11 | 변동내역 | `최근 5년 포함` → `최근 5년 미포함` | 기타: 선행 필드 실패 | `nhis_acquisition_loss.py:206,211` | A3 |
| D12 | name | `가상시험` → `한자` | 정규식·형식 | `resident_abstract.py:41,190,199` | R1 |
| D12 | birth_date | `1999-01-01` → `∅ (누락)` | 정규식·형식 | `resident_abstract.py:41,190,199` | R1 |
| D13 | name | `가상시험` → `한자` | 정규식·형식 | `resident_abstract.py:41,190,199` | R1 |
| D13 | birth_date | `1999-01-01` → `∅ (누락)` | 정규식·형식 | `resident_abstract.py:41,190,199` | R1 |
| D14 | address_history_count | `1` → `∅ (누락)` | 정규식·형식 | `resident_abstract.py:35,279,300` | R6 |
| D15 | name | `가상시험` → `한자` | 정규식·형식 | `resident_abstract.py:41,190,199` | R1 |
| D15 | birth_date | `1999-01-01` → `∅ (누락)` | 정규식·형식 | `resident_abstract.py:41,190,199` | R1 |
| D16 | name | `가상시험` → `한자` | 좌표 범위 / 행 묶기 | `resident_abstract.py:190,199` | R3 |
| D16 | birth_date | `1999-01-01` → `∅ (누락)` | 좌표 범위 / 행 묶기 | `resident_abstract.py:190,199` | R3 |
| D16 | issue_date | `2026-11-10` → `∅ (누락)` | 좌표 범위 | `resident_abstract.py:177,184` | R4 |
| D16 | address_history_count | `1` → `∅ (누락)` | 행 묶기 → 라벨 찾기 | `layout.py:40; resident_abstract.py:244` | R5 |
| D17 | name | `가상시험` → `한자` | 정규식·형식 | `resident_abstract.py:41,190,199` | R1 |
| D17 | birth_date | `1999-01-01` → `∅ (누락)` | 정규식·형식 | `resident_abstract.py:41,190,199` | R1 |
| D18 | name | `가상시험` → `∅ (누락)` | 좌표 범위 | `resident_abstract.py:199` | R7 |
| D18 | birth_date | `1999-01-01` → `∅ (누락)` | 정규식·형식 / 행 묶기 | `resident_abstract.py:41,190` | R8 |
| D18 | address_history_count | `1` → `∅ (누락)` | 행 묶기 → 라벨 찾기 | `layout.py:40; resident_abstract.py:244` | R5 |
| D19 | name | `가상시험` → `∅ (누락)` | 좌표 범위 | `resident_abstract.py:199` | R7 |
| D19 | birth_date | `1999-01-01` → `∅ (누락)` | 정규식·형식 / 행 묶기 | `resident_abstract.py:41,190` | R8 |
| D19 | address_history_count | `1` → `∅ (누락)` | 행 묶기 → 라벨 찾기 | `layout.py:40; resident_abstract.py:244` | R5 |
| D20 | 생년월일 | `1999-01-01` → `∅ (누락)` | 행 묶기 / 좌표 범위 | `nhis_common.py:148,160` | N3 |
| D20 | 발급일 | `2026-11-10` → `∅ (누락)` | 행 묶기 | `nhis_common.py:183` | N5 |
| D20 | 건강보험료 | `110000` → `∅ (누락)` | 행 묶기 | `nhis_payment.py:228,256,301` | P1 |
| D22 | 성명 | `가상시험` → `∅ (누락)` | 행 묶기 | `nhis_common.py:128,138` | N2 |
| D22 | 생년월일 | `1999-01-01` → `2026-11-10` | 행 묶기 | `nhis_common.py:148` | N4 |
| D22 | 발급일 | `2026-11-10` → `∅ (누락)` | 행 묶기 | `nhis_common.py:183` | N5 |
| D22 | 건강보험료 | `110000` → `186667` | 행 묶기 | `nhis_payment.py:228,272,301` | P2 |
| D23 | 성명 | `가상시험` → `∅ (누락)` | 행 묶기 | `nhis_common.py:128,138` | N2 |
| D23 | 생년월일 | `1999-01-01` → `2026-11-10` | 행 묶기 | `nhis_common.py:148` | N4 |
| D23 | 발급일 | `2026-11-10` → `∅ (누락)` | 행 묶기 | `nhis_common.py:183` | N5 |
| D23 | 건강보험료 | `110000` → `186667` | 행 묶기 | `nhis_payment.py:228,272,301` | P2 |
| D24 | 성명 | `가상시험` → `생년월일` | 행 묶기 / 좌표 범위 | `nhis_common.py:123` | N1 |
| D24 | 생년월일 | `1999-01-01` → `∅ (누락)` | 행 묶기 / 좌표 범위 | `nhis_common.py:148,160` | N3 |
| D24 | 발급일 | `2026-11-10` → `∅ (누락)` | 행 묶기 | `nhis_common.py:183` | N5 |
| D24 | 가입구분 | `직장` → `∅ (누락)` | 행 묶기 | `nhis_acquisition_loss.py:106,123,196,225` | A1 |
| D24 | 취득일 | `2020-01-01` → `∅ (누락)` | 행 묶기 | `nhis_acquisition_loss.py:106,123,196,225` | A1 |
| D24 | 변동내역 | `최근 5년 포함` → `∅ (누락)` | 기타: 선행 필드 실패 | `nhis_acquisition_loss.py:206,221` | A2 |
| D26 | 성명 | `가상시험` → `∅ (누락)` | 행 묶기 | `nhis_common.py:128,138` | N2 |
| D26 | 생년월일 | `1999-01-01` → `2026-11-10` | 행 묶기 | `nhis_common.py:148` | N4 |
| D26 | 발급일 | `2026-11-10` → `2020-01-01` | 행 묶기 | `nhis_common.py:183` | N6 |
| D26 | 가입구분 | `직장` → `∅ (누락)` | 행 묶기 | `nhis_acquisition_loss.py:106,123,196,225` | A1 |
| D26 | 취득일 | `2020-01-01` → `∅ (누락)` | 행 묶기 | `nhis_acquisition_loss.py:106,123,196,225` | A1 |
| D26 | 변동내역 | `최근 5년 포함` → `최근 5년 미포함` | 기타: 선행 필드 실패 | `nhis_acquisition_loss.py:206,211` | A3 |
| D27 | 성명 | `가상시험` → `∅ (누락)` | 행 묶기 | `nhis_common.py:128,138` | N2 |
| D27 | 생년월일 | `1999-01-01` → `2026-11-10` | 행 묶기 | `nhis_common.py:148` | N4 |
| D27 | 발급일 | `2026-11-10` → `2020-01-01` | 행 묶기 | `nhis_common.py:183` | N6 |
| D27 | 가입구분 | `직장` → `∅ (누락)` | 행 묶기 | `nhis_acquisition_loss.py:106,123,196,225` | A1 |
| D27 | 취득일 | `2020-01-01` → `∅ (누락)` | 행 묶기 | `nhis_acquisition_loss.py:106,123,196,225` | A1 |
| D27 | 변동내역 | `최근 5년 포함` → `최근 5년 미포함` | 기타: 선행 필드 실패 | `nhis_acquisition_loss.py:206,211` | A3 |
| D28 | name | `가상시험` → `한자` | 행 묶기 | `resident_abstract.py:194,199` | R9 |
| D28 | address_history_count | `1` → `∅ (누락)` | 행 묶기 → 라벨 찾기 | `layout.py:40; resident_abstract.py:244` | R5 |
| D29 | 건강보험료 | `110000` → `∅ (누락)` | 행 묶기 | `nhis_payment.py:228,256,301` | P1 |
| D30 | 가입구분 | `직장` → `∅ (누락)` | 행 묶기 / 좌표 범위 | `nhis_acquisition_loss.py:90,102,104` | A4 |
| D30 | 취득일 | `2020-01-01` → `∅ (누락)` | 행 묶기 / 좌표 범위 | `nhis_acquisition_loss.py:90,102,104` | A4 |

| Cause | Explanation grounded in captured traces |
|---|---|
| R1 | RRN separator is en dash/minus, not ASCII hyphen. Preferred RRN/name branch is skipped; fallback takes parenthetical label 한자 as the first Hangul run. |
| R2 | RRN label and number are separate grouped rows. Birth branch cannot match both; name fallback returns 한자. |
| R3 | Identity label/value shifted outside y<26%; correct name is on a separate row. Fallback either chooses 한자 or does not run. |
| R4 | Recognized issue date lies below the fixed header y<16% boundary and is ignored. |
| R5 | All table-header words are recognized, but 번호 and 발생일/신고일/세대주 are not on one grouped row; _table_bounds returns None. |
| R6 | Both row dates are recognized as 2020–01–01. ISO_DATE accepts ASCII hyphen/dot only; no report-date anchor means no history entry. |
| R7 | 성명(한자) center y=26.1% exceeds y<26% gate; name was recognized at y=24.3% but is on another row. |
| R8 | RRN contains en dash and is also on a different grouped row from 주민등록번호; either prevents the birth branch. |
| R9 | Name row is separate from RRN row. Fallback first sets 한자; later RRN row contains no name-box candidate so does not replace it. |
| N1 | Name value is above the isolated 성명 row. Unbounded lower-row/x-overlap fallback chooses label 생년월일 as a name. |
| N2 | 성명 is grouped with numeric birth date; nonempty right-side candidates suppress below search and contain no valid Hangul name. Correct name is on previous row. |
| N3 | Birth label and correct date are separated. The fallback only checks same-row/right or lower boxes overlapping label x range; date is outside that range. |
| N4 | 생년월일 is grouped with issue date 2026.11.10 and accepts it as birth without role cross-check. |
| N5 | 발급일 and its value are in separate rows; issue parser searches only the label row (unlabeled payment fallback also finds no qualifying confirmation block). |
| N6 | 발급일 is grouped with query-period text 2020.01.01~2026.11.10; first parsed date 2020-01-01 becomes issue date. |
| P1 | Months and billed amounts are separate rows; required three monthly billed values are not available. Right-column next-row amount can also be associated with an earlier month; final average is absent. |
| P2 | Rows are shifted: 2025.10→110000, 2025.11→120000, 2025.12→330000 (total). Rounded average (110000+120000+330000)/3=186667; total label sits on the next row. |
| A1 | Acquisition-date row is recognized but category 직장가입자 belongs to another row. History category is empty, so 가입구분 and active-job 취득일 are omitted. |
| A2 | Issue date is absent, so existing recent-five-year calculation cannot run. Query-period label and its dates are also split across rows. |
| A3 | Issue date was misread as 2020-01-01; cutoff becomes 2015-01-01. Query-period row is not found and 2020 acquisition does not reach that cutoff, yielding 최근 5년 미포함. |
| A4 | Three-row header window includes the first actual data row: header_y becomes acquisition-date center 38.3%. Data row begins at 37.6% and is skipped as above header; no history rows remain. |

## Selected geometric evidence

Coordinates below are `(left x%, center y%)` from the actual own boxes. Each OCR output region is preserved; no synthetic transform is used to repair extraction.

| Case | Observation | Consequence |
|---|---|---|
| D12 명조 clean | One identity row contains `성명(한자)`, `가상시험`, `주민등록번호`, `990101–1******`; all centers y≈19.5%. | Geometry is fine; U+2013 dash is sufficient to disable RRN parsing and expose `한자` fallback. |
| D14 명조 blur | Both address dates are `2020–01–01`, at x53.7% and68.7%; table bounds31.03–77.5% are found. | Date regex failure, not a missing table or wrong columns. |
| D00 고딕 weak | RRN center18.9%, label20.4%, name row22.4–23.4%; all text recognized. | Fixed horizontal grouping separates same physical row. |
| D02 고딕 strong | Issue center23.4%; RRN label29.6%, number32.0%. | Fixed header16% and identity26% gates exclude values. |
| D04 고딕 payment weak | Correct name28.9%,18.0% precedes label16.8%,19.2%; below same-column label 생년월일16.7%,22.2%. | Lower fallback chooses 생년월일 as name. |
| D06 고딕 payment strong | Month2025.10 y39.8% groups billed110000 y39.6%; month11 y43.6% groups120000 y43.5%; month12 y47.7% groups total330000 y48.5%. | Wrong average186667 is a row-assignment error even though numeric strings are correct. |
| D10 고딕 acquisition strong | 발급일19.0%,27.0% groups query period33.9%,27.6%; category15.9%,40.4% separated from acquisition33.2%,38.1%. | Wrong issue date and empty history category cascade into recent-five-year and active-job failures. |
| D30 legacy acquisition | Header window indices6–8 includes actual data row8. Its max center38.3% becomes header_y; row8 first word center37.6% fails `<= header_y`. | Header window consumes first history row even though category/date are together. |

Own region granularity is variable: D12 has20 regions /9 grouped rows, maximum35 characters per region, heights1.23–1.91% page; D00 has21/15 and heights0.85–4.54%; corrected D01 restores20/9 and heights1.39–1.94%. In D06 a false background dash has height27.12%; D10 a false background L has height23.52%. These observed oversized boxes demonstrate sensitivity of height-based grouping. They do not establish Apple Vision box statistics.

New diagnostic tests: **5 passed in0.29s**. Tests cover all-value masking, unknown GT-key suppression, explicit synthetic-only unmask, real-file unmask rejection, sanitized runtime failure and invalid argument error. Existing tests are untouched.

## Box-shape assumptions and real-document risk

| Code | Assumption / evidence | Risk on real documents |
|---|---|---|
| `pipeline/ocr/own.py:73`, `:91`, `:99`, `:134` | DB detection runs at a longest side ≤1600 and expands detected polygons (`unclip` factor 1.5); each detected region becomes one `OcrWord` using an axis-aligned bounding rectangle. A region may contain multiple words, a whole line, or a small label fragment. | Expansion changes line height/gap; skew makes wide regions' axis-aligned boxes taller. Variable detector merging can move label/value boundaries. |
| `pipeline/ocr/__init__.py:58` | Vision's recognized `(text, confidence, rect)` is passed through as one `OcrWord`, converting normalized bottom-left coordinates to top-left pixels. There is no word segmentation or matching of box granularity to own. | Same API does not guarantee equal token/line granularity. Apple Vision cannot be executed on this Linux machine; actual comparative box-size/gap distributions remain unmeasured. Do not claim Apple always returns words or that it would succeed. |
| `pipeline/ocr/__init__.py:39`, `pipeline/ocr/own.py:135` | Raw reading order quantizes top edge with `round(y0 / 15)`: fixed 15 pixels. | Resolution/skew can change concatenation order. Extractors also independently group lines, so this is not the sole cause of the diagnosed failures. |
| `pipeline/layout.py:30`, `:40` | Coordinates are page percentages, not fixed pixels. Row membership compares center difference with the incoming box height ×0.6, floor 0.3% page height, and last row mean. No slope fit or rotation invariance. | Perspective breaks horizontal rows; region height changes can merge or split rows asymmetrically. Background margins also change percentages because the whole photograph is normalized. |
| `extractors/resident_abstract.py:3`, `:47`, `:169`, `:261` | File explicitly states calibration from one Apple Vision government-form print. Fixed page ranges: header y<16%, identity y<26%, name left x15–36%, date columns x50–61%/61–73%, footer77.5%. Date must fit one token and `fullmatch`. | New layout/crop/perspective and different box width/merging can remove otherwise legible values. These are percentage constants, not fixed-pixel distances. |
| `extractors/resident_abstract.py:190`, `:199` | Name extraction relies on same-row RRN detection; fallback chooses first 2–6 Hangul run after `성명`, including parenthetical label `한자`. RRN/date regexes accept ASCII hyphen (date also dot). | Unicode dash OCR substitutions can disable birth and the preferred name path. A label fragment may become a confident name. |
| `extractors/nhis_common.py:123`, `:148`, `:183` | Name/birth prefer same row/right-of-label; fallback scans all lower rows that overlap label x-range. Issue date is same-row only. | Tilt separates label/value; unrestricted downward fallback can pick another field's label (`생년월일`) or amount label (`고지금액`) as a person's name, or issue date as birth. |
| `extractors/nhis_common.py:86` | Split labels may span adjacent or two-away rows only if x intervals overlap. | Not a general two-dimensional table parser; skew/merging affects label reconstruction. |
| `extractors/nhis_payment.py:65`, `:145`, `:187`, `:256` | Currency fragment joining uses gap≤2×box height and up to four tokens; monthly values must share the grouped line with a month. Column center chosen from the first matching header and reused across pages. | A number split across regions or columns can join incorrectly. Skew separates month and amounts; different page layouts/margins shift reused column centers. |
| `extractors/nhis_acquisition_loss.py:87`, `:106`, `:123`, `:196` | Header search spans up to three grouped rows; a history row exists only when dates appear in it. Category and acquisition date must occupy the same grouped row; dates are assigned by nearest header x center. | Category/date split creates uncategorized rows, so valid employment/category fields disappear. Header fragments can consume data rows. |
| `pipeline/perspective.py:55`, `:59`, `:63`, `:69` | Pixel-only rectifier requires external convex four-corner contour of 35–97% image area, away from frame. Failure returns unchanged pixels (`applied=False`). | Strong shadows/background/partial crop can prevent correction. A requested correction must never be reported as applied when detection fails. |

The code evidence establishes a real-document risk, not a measured real-document failure rate. An Apple/own comparison on identical approved inputs is still required on Mac, without logging values. No fixed character-width assumption was found in these extraction paths; box width, box-height tolerance, fixed percentage bands and same-row membership are the actual assumptions.

## Proposed fixes (not implemented)

| Fields | Proposed change | Expected effect | Risk / validation needed |
|---|---|---|---|
| Resident birth and name | Canonicalize a narrowly allowlisted OCR dash variant only inside typed RRN/date parsers; keep original raw evidence. Parse `성명(한자)` as a full label and reject label lexemes as names. | Recover birth for en-dash/minus; avoid cascading fallback name `한자`. | Low–medium: never globally normalize identifiers; add negative cases for genuine separators and invalid dates. |
| Resident name, issue date, history count | Locate page boundary and anchor labels/table columns; fit local row baselines or use polygon geometry. Use document-relative coordinates after successful correction; fail closed when correction fails. | Recover valid date/name/row membership in tilted phone images. | Medium–high: bad corner detection/anchor association can create wrong fields. Preserve fallback and human review; test varied margins, scaling, forms and multiple pages. |
| NHIS name/birth/issue | Associate nearest compatible value in a bounded two-dimensional neighborhood with baseline slope; stop at next label; reject labels and conflicting date roles. | Prevent label-as-name and issue-date-as-birth; attach correct right-side values under skew. | Medium: vertical forms need explicit alternatives; avoid expanding search until a plausible but wrong value appears. |
| NHIS premium/months | Reconstruct table rows across column cells with local baseline/row separators; estimate columns per page, require unique month→amount assignment and existing sum checks. | Recover all three monthly billed amounts, including when text is recognized but lines split. | High: incorrect billed/paid assignment changes financial evidence. Validate separate health/care, refunds, totals and multipage columns. |
| Acquisition category/date | Link category/date cells within inferred table row, keep empty loss date distinct from missing detection; avoid allowing header window to consume a data row. | Restore employment category/acquisition date and preserve recent-five-year evidence. | Medium–high: date swap/lost-cell omission can falsely imply active employment. Test several history rows and ambiguous empty cells. |
| Acquisition recent-five-year field | Recover issue date/period with typed label association; retain existing downstream rule without modification. | Repair missing/wrong period evidence instead of changing the rule's result. | Medium: never infer coverage from a date-shaped token without its role. |
| All phone fields | Improve contour selection against shadows, report no-op explicitly, add low-confidence correction gate. | Weak corrections already demonstrate geometric recoverability; may extend to strong cases. | High: detector tuning can crop documents. Requires independent image/form test set; no evidence yet for making correction default. |
