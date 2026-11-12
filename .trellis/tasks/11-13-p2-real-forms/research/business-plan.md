# Stage 7 business-registration proof implementation plan

## Existing contracts

- `engine_v2/engine.py:41` has no dedicated business-proof registry entry. Add `DocType.BIZ_REG_PROOF = "biz_reg_proof"` to `engine_v2/schemas/models.py` and register `business_registration.extract`.
- `demo/backend/rules/required_docs.py:196` selects `DocType.BIZ_REG_PROOF` for the business-income `work_proof` slot. The slot supplies issue-date requirements and no proof-specific `required_fields`. Extraction must supply its own completeness gate before generic slot checks.
- `demo/backend/rules/identity.py:51` compares the Korean keys `성명` and `생년월일`. The broad fallback at `demo/backend/rules/doc_check.py:672` permits absent identity and can emit FAIL for a mismatch. A dedicated business-proof identity branch must require both checked fields and route missing/mismatching evidence to NEEDS_REVIEW.
- `demo/backend/ocr/localocr.py:503` currently hands unsupported text PDFs to PdfText. Add the proof type to the supported text set, V2 type mapping and dedicated dispatch. The image path must dispatch after body classification at approximately line 590. Neither filename nor expected slot participates in this selection.
- Reuse `job_common.brn_is_valid` and `brn_check_digit` at `engine_v2/extractors/job_common.py:95`. Reuse `nhis_forms.label_hits(..., x_bounds=...)` for justified sparse labels inside the observed label column. Reuse normalized Word, common date parsing, source boxes and ExtractedField construction.

## Source shape and relative regions

Only `/tmp/layout_shape2.txt:242`–`:297` was read for the observed business-proof form. The source remains outside the repository. Shape coordinates below describe form geometry and never original applicant values.

1. Title occupies x683–1373, y372–443 on a 2065×2923 page. Left issuance label sits x226–430, y379–426 and its 4-3-4-3 value below at x166–486, y474–509. Parenthesized taxpayer type is below the title at x850–1215, y452–513. Require the upper-page title plus the observed label-grid evidence.
2. Nine left-side row labels occupy approximately x219–559, y568–1492. Right values begin x633–664 and extend as far as x1735. Derive the label/value corridor from full label bounds and repeated right-value starts. Require consistent observed whitespace. Avoid fixed page percentages as substitute evidence.
3. Justified `개 업 일` is three one-character boxes x229–280, x364–408 and x495–539 near y1011–1062. `업 태` has boxes at x233–270 and x497–545, near y1228–1276. `종 목` has boxes at x230–276 and x500–542 near y1443–1492. The ordinary glyph-gap threshold excludes these. Scope sparse-label matching to the independently established left label column.
4. Values above a vertically centered row label remain within the band delimited by neighboring observed label centers. Industry/category text occupies y1194–1234 and y1353–1410. Additional lines are read in source order within their bounded cells, with `|` separating list entries.
5. Joint-business headers occupy x862–1066 and x1441–1778, y1612–1660. The side `공동사업자` label sits lower, y1738–1787. Determine the section start from its observed headers and stop before `증명합니다` at y1939–1979. The no-participant phrase is at x799–1137, y1785–1834. Tall preceding fragments at y1703–1796 have redacted characters, so their original purpose remains 추정. They cannot supply a joint owner identity on their own.
6. Confirmation is y1939–1979, and the current-status notice is y2050–2091. The unlabeled issue date is x1311–1567, y2112–2156. The tax-office issuer occupies x1033–1561, y2250–2316. Require one date occurrence below both confirmation and the current-status notice, above the unique tax-office issuer, and horizontally aligned with that issuer block. A competing or malformed date candidate fails the issue-date-location check. Dates in opening/registration rows and bottom explanatory text remain outside this region.

## Dedicated reader

Create `engine_v2/extractors/business_registration.py` with `extract(pages, today=None)` and a result containing `detected_type`, `type_confidence`, `fields`, `validations`, `warnings`, `form_kind="nts_business_proof"` and `structure_complete`.

The field contract uses Korean keys so the demo conversion can preserve the established identity/date interface.

| Field | Engine value type | Evidence and validation |
| --- | --- | --- |
| `발급번호` | str | Full-match 4-3-4-3 beneath its upper-left label. Keep this issuance identifier distinct from the business number |
| `과세유형` | str | Unique parenthesized type between title and first grid row |
| `상호` | str | Nonempty right cell beside 상호/법인명 label |
| `사업자등록번호` | str | Whole-cell 3-2-5 format and existing NTS checksum function |
| `성명` | str | Unique full representative-name cell. Strip only an explicit representative-type parenthesis, preserving the actual person text |
| `생년월일` | date | Personal entity code, valid masked/full birth prefix and sex digit. Corporate/unknown entity types omit this field |
| `사업장소재지` | str | Nonempty right cell, retaining internal address text and line order |
| `개업일` | date | Whole right-cell date, no substring fallback from malformed residue |
| `사업자등록일` | date | Whole right-cell date, separate from opening and issuance |
| `업태` | list[str] | Bounded multiline cell, split on pipe delimiters, trim spacing, preserve nonempty item order |
| `종목` | list[str] | Same bounded multiline-list contract |
| `공동사업자유무` | bool | False from an explicit no-participant phrase without conflicting name+identifier rows. True from at least one fully evidenced participant row. Ambiguous/partial content requires review |
| `발급일` | date | Unique final date in the confirmation/notice/issuer block |

Birth must never come from a legal-entity identifier that happens to start with a valid date. Use the validated business number's middle two digits to identify an individual code 01–79 or 90–99. Corporate codes 81–88 yield no birth. Codes 80/89 and an invalid business number do not establish a personal identifier. NTS's allocation FAQ supports these ranges. This is extraction type evidence and does not decide employment eligibility. [NTS allocation FAQ](https://www.nts.go.kr/nts/na/ntt/selectNttInfo.do?mi=2448&nttSn=1386)

The raw resident/legal number stays source-local. The extracted birth uses the redacted source or normalized date as its raw evidence. Joint participant identifiers do not become output fields. Stage 1 sanitization already protects genuine resident suffixes in ingestion.

Explicit checks cover the physical page, title, label grid, business-number shape/checksum, all thirteen required fields, joint section, bounded issuance, entity-type consistency, registration no later than issuance and issuance no later than today.

No page counter was observed, so one physical page is the completeness requirement. Missing/duplicate labels, competing fields, malformed cell residue, invalid checksums or required values set structure incomplete and confidence at most .4. Corporate birth absence is exposed as identity uncertainty with the same review cap, while the remaining corporate fields can still be retained for the officer.

Conservative numeric correction can be deferred when a cell lacks an arithmetic cross-check. Date/identifier uncertainty should remain reviewable. Names, addresses and industry/category text receive whitespace normalization only.

## Adapter and final verdict boundaries

Add `_from_business_proof` to LocalOcr, rendering dates as ISO, booleans as a stable Korean/string value and industry/category lists as JSON strings with `ensure_ascii=False`. Populate `판독검증`, `판독검증실패`, `판독경고`, `양식판독상태`, bboxes, issue_date and classification metadata. Retain internal address/industry fields in officer data through the existing applicant whitelist.

Add `ensure_business_required_fields`, called by the dedicated converter and again after the common header-only safety filter in `demo/backend/ocr/__init__.py`. The guard validates required name, birth, issue date and the proof fields, removes stale bboxes, adds missing-field checks and caps confidence. Keep the NHIS guard behavior intact.

Add a proof-specific early completeness branch in `doc_check.py`, before generic issue/eligibility rules. Incomplete proof yields NEEDS_REVIEW. Add a representative identity branch alongside acquisition-loss, using `compare` and requiring both checked fields. Any missing/mismatch contributes only NEEDS_REVIEW and prevents uncertain issue-field evidence from producing FAIL. Wrong-document-slot behavior still follows the existing type branch.

## Synthetic fixture and verification plan

Create authored OCR fixtures with the source's word counts, sparse label positions, token widths/heights and confidence distribution. All values below are fictitious.

- Taxpayer type `(일반과세자)`, company `가상합성상점`, representative `김가상`, birth `1990-01-01`, identifier `900101-1654321`, issuance number `1234-567-8901-234` and checksum-valid business number `123-45-67891`.
- Opening `2018년 01월 02일`, registration `2018년 01월 03일`, final issuance `2026년 3월 3일`. These retain the source's padded row dates and unpadded final date.
- Corporate checksum-valid number `123-81-12341`, legal number deliberately resembling a valid birth prefix, and a representative name. Birth must remain absent.
- Pipe-separated fabricated industry/category lists with three entries and multiline variants. Address words use invented locality/street/unit text with the source's token layout.
- Sparse labels are positioned from the observed label grid and value corridor, then transformed by global translation, relative scale, slight tilt/jitter and name lengths 2–4. No production rule depends on those fixture coordinates.
- Verify full OCR parse and validation success, text-layer regression, arbitrary renaming and contradictory expected slots, actual upload PASS with matching identity, and absence of warnings.
- Review cases cover invalid checksum, missing/duplicate labels and values, missing birth/name/issue, corporate identity, mismatched name/birth, duplicate/malformed final dates, future dates, multi-page input and partial joint rows.
- Table variations cover no/one/multiple joint participants, one-to-ten complete participant rows, blank rows and multiline industry/category values. Ensure evidence after a section marker cannot be silently hidden.
- Run existing PR #27 tests and targeted new business tests before the final full engine/backend/scenario gate.

## Implementation decisions

The dedicated reader and its tests were implemented after stage 6. Industry/category values are lists in the engine and JSON strings in the existing demo string-field contract. The representative reader and final guard share full-cell name validation. Corporate evidence is taken from the normalized parenthesized taxpayer value, including split OCR words, and overrides birth derivation even when a conflicting personal business-number code is valid.

Opening dates are retained as metadata even when later than issuance. NTS permits business registration before opening. The extractor checks that registration itself is no later than issuance and that issuance is no later than today. Employment assessment remains outside this stage. [NTS business registration guidance](https://d.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=7806&mi=2486)

Detailed implementation evidence and verification counts are recorded in `business-results.md`.
