# Portal Document Form Contracts

## 1. Scope and trigger

Use this contract when changing NHIS acquisition-loss, NHIS qualification notification, or insurance portal readers and their demo verdict adapters. Form selection uses body text and coordinates. File names and slot expectations are not form evidence. Preserve the existing government24 and generic qualification paths.

## 2. Signatures

- `nhis_common.birth_from_rrn(text: str) -> date | None` preserves the established century mapping and legacy search behavior. New form value cells must separately full-match the allowed RRN shape.
- `extract(pages, today=None)` returns `detected_type`, `type_confidence`, `fields`, `validations`, `warnings`, and form metadata.
- New form metadata: `form_kind`, `structure_complete: bool | None`; `None` retains legacy validation behavior. A/B document numbers remain internal attributes, not extracted fields.
- `check_document(req, ocr, declared_issue_date=None, file_format="pdf", identity=None, related_nhis_docs=None, suggested_slot_label=None)` keeps its public signature. Its wrapper formats guidance after all rule paths, including early returns.
- `DocType.NHIS_QUALIFICATION` is registered in `engine_v2.engine.EXTRACTORS`. No DB migration or new environment setting is required.

## 3. Data contracts

- Demo `OcrResult.fields` contains string values. `성명`, `생년월일`, `발급일` are required for the new forms; dates use ISO format.
- `양식판독상태` is `완전` or `불완전` for new form results. Failed structure caps confidence at 0.4 and remains visible in `판독검증실패`.
- Final header-value removal cannot leave acquisition-loss or notification missing required fields with all checks passed. Run `ensure_nhis_required_fields` after conversion and after the unchanged common safety filter.
- Qualification `가구원목록` is JSON with Korean keys `성명`, `생년월일`, `자격취득일`, `자격상실일`. Emit it and `가구원수` only for a complete structure. Partial members must not become an authoritative reduced household count.
- Emit `자격확인요청일` separately; it is never an issue-date source. Notification number and validity date stay internal, and validity adds no eligibility rule. Do not infer `가입구분` from subscriber-role labels.
- Insurance row output preserves existing names and fields. Acquisition and parenthesized receipt dates are separate occurrences even when their values are equal. Erase resident-number source tokens even when header identity is ambiguous.

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
