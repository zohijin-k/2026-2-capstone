# Design

## Authorization and boundary

The user explicitly authorized task creation, planning followed by implementation, and ordered commits. Main was fetched and equals `5d0833d`. Existing untracked `docs/audit/` predates this work and is excluded from all commits.

The smallest behavior gaps are unredacted coordinate/text ingestion, OCR tokenization assumptions in existing readers, rejected valid NHIS variations, and an absent business-proof reader. Extend the existing ingestion/reader/adapter boundaries and preserve result field contracts. Trellis workflow explicitly requests implement/check delegation. Subagents receive this task's specifications and bounded file ownership.

## Ordered implementation

1. Central resident-number sanitizer reused at every textual ingress and serialization safety boundary. Date-valid six digits and sex digit 1–8 identify a candidate. Preserve coordinates and word segmentation while redacting same-line split words.
2. Classify each observed failed validation using shape and coordinates. Shape placeholders cannot establish the original misrecognized character, date values or checksums, so those conclusions remain inference.
3. Extend shared coordinate helpers only where OCR forms require it, retaining strict ambiguity checks.
4. Acquisition history accepts gaps and rejects overlaps. Preserve the existing five-year meaning.
5. Qualification scopes the issue date between confirmation and issuer and reads one member with empty management cells.
6. Payment preserves `billed_by_month` and other existing contracts, reads eight observed columns and retains empty cells. Correct only documented numeric lookalikes, then verify sums.
7. Dedicated business-proof reader returns existing fields used by identity/slot logic plus requested internal fields, checksum and completeness checks.
8. Resident history investigation determines whether numbering failure indicates missing input or a false alarm and connects actual uncertainty to review.
9. Full engine/backend/scenario regression and cross-layer review.
10. Record final outcomes and set status to review.

## Initial cause classification

| Form and failed checks | Category | Shape evidence and investigation target |
| --- | --- | --- |
| Payment `monthly_amounts_numeric`, `monthly_total_matches`, `paid_total_matches` | (가), cascading arithmetic failures | Numeric cells at x390–421 and x1195–1231, y959–1487 contain `A` at confidence .33–.67. Original glyph identity is inference. Eight header columns include entirely empty optional columns. |
| Qualification `nhis_issue_location_unique`, `발급일_consistent`, `발급일_required` | (나)/(다), pending code trace | Request date x1841–2079 y677–729, issue date x1114–1375 y2726–2789, validity date in sentence x278–889 y3011–3059. Confirmation y2635–2689 and issuer y2855–2950 bound the intended date. |
| Qualification `nhis_blank_marker`, `household_rows_read`, `subscriber_matches_first_member` | (나)/(다), pending code trace | Single member y1481–1547, marker x977–1159 y1596–1655, empty management cell and trailing low-confidence artifacts y1976–2186. |
| Acquisition `nhis_history_cells_read`, `nhis_row_numbers_continuous`, `nhis_current_loss_blank`, `history_dates_read` | (나)/(다), pending code trace | Three numbered rows y1111–1427, empty employer column under header x966–1226, low-confidence tall overprint x845–1105 y1201–1420. |
| Acquisition `nhis_neighbor_dates_continuous` | (다) | User reports genuine gaps. Shape dates at x1652–1867 and x2048–2263 cannot establish ordering. Code and synthetic dates must verify the rule. |
| Acquisition `nhis_blank_marker`, `recent_five_years_covered` | (나)/(다), pending trace | Marker x646–831 y1489–1554 and trailing blank rows/overprints y2033–2339. Five-year coverage depends on valid row extraction. |
| Business proof lacking validations | (라) | Dedicated extractor absent from engine registry. Labels and right-side values span y568–1834, final unlabeled date x1311–1567 y2112–2156. |

## Privacy inventory

To be completed before the privacy stage commit by tracing ingestion, serialized fields, diagnostics and storage metadata. Existing raw PDF uploads remain source artifacts with printed identifiers. The user owns deletion of existing artifacts.

## Verification and unresolved assumptions

Only masked shape sources are used for real-document structure. Synthetic integration proves pipeline behavior. Actual original glyph correction and resulting real-file accuracy cannot be established from placeholders alone.
