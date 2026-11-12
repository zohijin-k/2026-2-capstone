# Document OCR and Form Contracts

## 1. Scope and trigger

Use this contract when changing OCR/text ingestion, resident-number redaction, NHIS acquisition-loss/qualification/payment, insurance portal, NTS business-proof or resident-history readers and their demo verdict adapters. Form selection uses body text and coordinates. Preserve the existing government24 and generic qualification entry points.

## 2. Signatures

- `nhis_common.birth_from_rrn(text: str) -> date | None` preserves the established century mapping and legacy search behavior. New form value cells must separately full-match the allowed RRN shape.
- `extract(pages, today=None)` returns `detected_type`, `type_confidence`, `fields`, `validations`, `warnings`, and form metadata.
- New form metadata: `form_kind`, `structure_complete: bool | None`; `None` retains legacy validation behavior. A/B document numbers remain internal attributes, not extracted fields.
- `check_document(req, ocr, declared_issue_date=None, file_format="pdf", identity=None, related_nhis_docs=None, suggested_slot_label=None)` keeps its public signature. Its wrapper formats guidance after all rule paths, including early returns.
- `DocType.NHIS_QUALIFICATION` is registered in `engine_v2.engine.EXTRACTORS`. No DB migration or new environment setting is required.
- `privacy.mask_rrn(text: str) -> str`, `mask_markup_rrn(text: str) -> str`, `mask_data(value: Any) -> Any` and `mask_words(words)` are the shared text, markup, nested-data and coordinate-batch redaction boundaries.
- `format_text.normalize_numeric_text(text: str) -> tuple[str | None, tuple[str, ...]]` returns normalized integer text and correction categories. Empty input returns an empty string. Unreadable input returns `None`.
- `nhis_payment.PaymentResult` carries optional `form_kind` and `structure_complete` metadata. The government eight-column family enters through `nhis_payment.extract` and `nhis_payment_gov.recognizes`.
- `nhis_payment.has_failed_payment_validation(fields) -> bool` recognizes critical identity/type/month/numeric/arithmetic failures in serialized `판독검증실패`. Fresh conversion, monetary facts and engine conversion share it, including historical markerless rows with cached PASS.
- `business_registration.extract(pages, today=None)` is registered under `DocType.BIZ_REG_PROOF`. `ensure_business_required_fields(result)` and `ensure_nhis_required_fields(result)` retain required-field checks after common field filtering.

## 3. Data contracts

- Demo `OcrResult.fields` contains string values. `성명`, `생년월일`, `발급일` are required for the new forms; dates use ISO format.
- `양식판독상태` is `완전` or `불완전` for new form results. Failed structure caps confidence at 0.4 and remains visible in `판독검증실패`.
- Final header-value removal cannot leave acquisition-loss or notification missing required fields with all checks passed. Run `ensure_nhis_required_fields` after conversion and after the unchanged common safety filter.
- Qualification `가구원목록` is JSON with Korean keys `성명`, `생년월일`, `자격취득일`, `자격상실일`. Emit it and `가구원수` only for a complete structure. Partial members must not become an authoritative reduced household count.
- Emit `자격확인요청일` separately; it is never an issue-date source. Notification number and validity date stay internal, and validity adds no eligibility rule. Do not infer `가입구분` from subscriber-role labels.
- Insurance row output preserves existing names and fields. Acquisition and parenthesized receipt dates are separate occurrences even when their values are equal. Erase resident-number source tokens even when header identity is ambiguous.
- Payment `월별납부내역` is a JSON list with twelve printed months and eight amount cells per row. Empty optional cells serialize as JSON null. Existing `billed_by_month`, `paid_by_month`, `건강보험료` and average aliases retain their existing meanings. `숫자형식교정` records corrected row, column and categories. The dedicated government reader emits no unprinted insurance category.
- Business proof requires `발급번호`, `과세유형`, `상호`, `사업자등록번호`, `성명`, `생년월일`, `사업장소재지`, `개업일`, `사업자등록일`, `업태`, `종목`, `공동사업자유무` and `발급일`. `업태` and `종목` serialize nonempty string lists as JSON. `공동사업자유무` is `있음` or `없음`. Internal address/list values stay within existing response allowlists.
- Explicit payment review/failure, supplied subthreshold or invalid confidence, and present incomplete structure prevent monetary fields from establishing income facts. Preserve stored fields for officer inspection. Engine conversion carries a high-confidence explicit `NEEDS_REVIEW` through the existing OCR threshold without changing the stored confidence.
- Historical payment rows retaining a critical failed validation require the same read-time monetary suppression and review confidence even when cached status is PASS. Retain the stored row for owner-controlled cleanup.

## 4. Validation and error matrix

| Evidence | Result |
|---|---|
| Recognized complete new form | Continue existing business and identity rules |
| Unknown/conflicting form, missing required value, malformed cells | Failed checks, confidence at most 0.4, `NEEDS_REVIEW` |
| New A/B/C has two physical pages or wrong page marker | Incomplete structure; `NEEDS_REVIEW` |
| Acquisition identity missing or mismatching | `NEEDS_REVIEW`; another person's history must not establish `FAIL` |
| Qualification applicant is a household member | Existing subscriber assessment still requires the matching payment/qualification pair |
| Correct document in the wrong slot | Existing `WRONG_DOCUMENT_TYPE` behavior; qualification/acquisition are not substitutes |
| Issue date equals announcement date | Accepted by the unchanged inclusive lower bound |
| PDF finding with photo retake guidance | Remove only `PHOTO_RETAKE_GUIDANCE`; retain all other sentences and jpg/png output |
| Acquisition lower-row loss <= upper-row acquisition | Valid neighbor order, including a coverage gap |
| Acquisition lower-row loss > upper-row acquisition | Incomplete structure and `NEEDS_REVIEW` |
| Payment numeric correction with matching eight column sums and paid grand total | Retain correction record and continue normal checks |
| Payment unreadable amount, conflicting period, crossing metadata or mismatching arithmetic | Incomplete structure, confidence at most 0.4 and `NEEDS_REVIEW` |
| Business checksum failure, missing reference identity or missing/mismatching representative identity | `NEEDS_REVIEW` |
| Corporate/unknown business entity code or conflicting corporate text | Suppress representative birth and require identity review |
| Resident unassigned/duplicate ordinal or missing address-entry ordinal | Failed history validation, all field confidence at most 0.4 and `NEEDS_REVIEW` |

Structural review precedes eligibility rejection based on partial history. A strong title may establish document type while its form/fields remain incomplete. Preserve existing government24 multi-page behavior.

## 5. Good, base, and bad cases

- Good: one observed identity value row, a unique valid date between confirmation and issuer, correct table headers and marker, and complete row cells.
- Base: an existing generic qualification PDF stays on its prior PdfText reader; the existing family/subscriber helper is unchanged.
- Bad: a neighboring RRN header used as a name; two competing identity rows; malformed extra dates ignored after a valid date; a marker row hiding an extra member; missing headers replaced by default column guesses; management cells shortened by discarding unknown text.

## 6. Required tests

- Font/model independent coordinates: NHIS required identity, form structure, qualification rows, insurance portal cells and century mapping.
- Text-layer PDFs: use the existing cjk `TextWriter` helper and temporary storage. A model/font asset skip must not suppress coordinate coverage.
- `demo/backend/tests/test_portal_uploads.py`: actual TestClient uploads agree with direct reading under renamed nonfixture filenames and differing expectations; assert normal PASS, multi-page review, dedicated identity review and existing paired-member behavior.
- `test_document_guidance.py`: assert the exact photo fragment is the only output difference for PDF, including early returns.
- Run engine tests, backend pytest tests, P2 and the existing backend scenario modules. Compare failures against an explicit baseline; do not delete or weaken existing tests.
- Privacy suites must cover full/split and compact/spaced identifiers, all eight sex digits, date validation, merged ASCII labels, G+18 whole/split identifiers, markup entities/continuations, raw text, batch adapters and historical response projections. Actual temporary uploads must assert birth preservation and absence of the fictitious suffix in OCR JSON, findings, responses, logs and serialized objects.
- `test_p2_acquisition.py` and `test_p2_qualification.py` cover one-to-ten rows, two-to-four-character names, scaling/jitter/skew, optional empty columns, markers, missing/hidden cells and scoped date ambiguity. Keep the recent-five-year helper's established meaning when testing gaps.
- `test_p2_payment.py`, `test_p2_payment_uploads.py`, `test_p2_payment_facts.py` and review regressions cover twelve months/eight columns, optional nulls, all column totals, correction-plus-arithmetic, complete-cell metadata, final required guards and income-status propagation. Include legacy payment arithmetic failures through text-layer uploads.
- `test_business_registration.py` and `test_p2_business_uploads.py` cover all thirteen required fields, checksum, personal/corporate identity, multiline tails through the joint-section boundary, partial joint columns and competing issuer dates. Preserve registration-before-opening cases.
- `test_p2_resident.py` and `test_p2_resident_uploads.py` cover three-page history, source-shaped isolated note ordinals, arbitrary contiguous starting numbers, unnumbered annotations and unresolved-history confidence through core/demo verdicts.

## 7. Wrong versus correct

- Wrong: take the first name/date-like substring, ignore extra candidates, and trust successful-check counts after a field is removed.
- Correct: delimit the form's value cells, validate the entire value and candidate uniqueness, preserve failed checks after safety filtering, and connect missing/ambiguous evidence to review.
- Wrong: publish only the household rows that happened to parse or use default coordinates as proof that a table exists.
- Correct: require observed table structure and all required row evidence before publishing an authoritative list/count.

## 8. Coordinate layout evidence

- Spaced labels are comparison views only. Keep original value tokens/bounds; never merge single-character words into person or workplace values. New-form `nhis_forms.label_hits` checks glyph spacing without changing the legacy common reader.
- Identity values may start left of their centered header. Scope below the header, require horizontal overlap with that label and unique candidates, and stop before the next section. Side role labels and header-only values are not names.
- Derive ordered table boundaries from persistent gaps in body word intervals, including marker cells for empty optional columns. Headers identify/order columns; their start positions are not cell edges. Reject missing/ambiguous corridors. Reserve observed date tokens before measuring acquisition-history employer overprints, and preserve the employer continuation completeness check.
- Reconstruct label comparison order from normalized coordinate lines. `OcrResult.text` has pixel-sized reading-order buckets and can reorder separated glyphs after resolution changes or small vertical perturbations.
- Portal header/row regions use labels, header height, table end cues and row spacing. Portal numbers are 14 digits; government document-number validation remains separate. Receipt and acquisition dates remain distinct occurrences in the same row band.
- Resident-document coordinate classification is a fallback after legacy keywords fail. Require a large upper-page `주민등록표` title and adjacent title subtype, ignoring parenthesis damage. Side/lower notices and combined/contradictory subtype evidence cannot resolve a type. Preserve the resident field extractor and existing review behavior after classification.
- Cover both normalized geometry changes and resolution scaling, plus final adapter/verdict behavior. Coordinate evidence alone is not an end-to-end OCR accuracy claim.

## 9. Redaction lifecycle

Redact after the earliest complete textual context is acquired and before an adapter exposes or retains it. Own, Apple, EasyOCR and Paddle adapters sanitize complete word batches. `OcrResult.__post_init__` sanitizes generic coordinate results and split words. Text-layer `_load_pages` builds that result before extraction. PageImage text, PdfText raw reads, LocalOcr routing probes and external OCR text/HTML/OTSL results use the same recognizer. Raw `OcrWord` construction is transient because neighboring fragments can establish a preserved identifier.

A candidate has a date-valid front six digits and sex digit 1–8, with supported whitespace/dash separators. Retain those seven digits and replace the final six digits with stars, preserving text length and geometry. Century validation uses 2000 for sex digits 3/4/7/8 and 1900 otherwise. Digit boundaries and an explicit G+18-digit exclusion preserve other document identifiers. Complete batches must resolve G+13/five-digit and three-word splits before redaction. Geometry separates distant columns, and output preserves word order, coordinates and confidence.

OTSL continuation cells are sanitized after reconstruction. HTML matching spans inline markup/entities while retaining cell/block boundaries. `mask_data` covers newly persisted OCR/findings/review/score JSON and historical applicant/officer projections. Original upload and split-page bytes can retain printed identifiers. Existing artifacts and old database rows require separate owner-controlled cleanup.

```python
# Returned OCR batches have enough context for preserved split document IDs.
words = mask_words(recognized_words)
return OcrResult(engine=engine_name, words=words)

# Persisted or historical nested JSON receives a second shared boundary.
safe_payload = mask_data(payload)
```

## 10. Bounded OCR forms

- `nhis_forms.label_hits(..., x_bounds=...)` permits justified glyph labels only within observed label-cell bounds. Preserve source value tokens.
- `table_columns(..., optional_columns=(), minimum_gap_ratio=1.0)` keeps strict defaults. Supported OCR forms opt into observed header-backed optional columns and a half-glyph corridor where needed. Bound rows by the observed blank marker before discovering whitespace.
- Ignore artifacts only with scoped geometry/confidence evidence. Marker punctuation may vary. Ordinary names, dates, numbers and employer fragments beside/after a marker remain completeness evidence. Date-shaped invalid loss tokens retain their date-cell role even beside an oversized employer box.
- `confirmation_issue_date` requires a unique confirmation/organization block and a unique full date within it. Same-valued request/validity dates elsewhere are harmless. Extra valid/malformed date evidence overlapping the issuer invalidates uniqueness.
- Preserve the existing recent-five-year acquisition meaning. Neighbor gaps alone add no coverage rule.

## 11. Payment and business cells

Payment numeric correction is restricted to bounded OCR amount cells. Allowed substitutions are O/o to 0, I/l to 1 and valid three-digit grouping punctuation. Unknown letters or malformed grouping remain unreadable. Text-layer values keep their grammar. Every column sum and the paid grand total must match before corrected values establish completeness.

Read metadata as complete observed cells. Account for crossing words and all pre-table period candidates, including periods grouped with the unit annotation. Document numbers require full-cell matching. An explicitly observed empty workplace is valid. A missing workplace cell or header-only purpose remains reviewable after final field safety filtering. Legacy required/numeric/continuity/arithmetic payment validation failures also cap confidence.

Business number validation reuses `job_common.brn_is_valid` and full-matches the printed number. Personal entity codes are 01–79 and 90–99. Corporate codes 81–88, unknown codes 80/89 and explicit corporate taxpayer text cannot establish a representative birthday. Compare both representative name and birth with reference identity before continuing normal assessment.

Multiline business values extend through the observed following section header. Account for crossing fragments at that boundary. Joint-participant columns use observed side-caption/value bounds, aligned row counts and row pitch. Partial names or identifiers require review even when another cell states absence. Read opening/registration/issue dates as metadata, preserving the supported registration-before-opening case.

## 12. Resident history evidence

Associate an isolated ordinal with a law-change annotation only when adjacency is unique under relative font height and observed row pitch. Account for observed ordinals across pages. Preserve established contiguous offsets and unnumbered annotation handling. A remaining history failure caps every extracted field and demo confidence at 0.4 and contributes a review warning. Declared-date and residence checks using those uncertain fields must remain reviewable.
