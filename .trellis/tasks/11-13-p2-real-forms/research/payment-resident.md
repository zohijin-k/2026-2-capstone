# Payment and resident-history investigation

## Sources and limits

Read-only shape evidence comes from `/tmp/layout_shape2.txt` and document five of `/tmp/layout_shape.txt`. Every numeric digit is replaced by `9`, every Latin letter by `A`. Therefore actual alphabetic misrecognitions, printed date values, original sequence numbers and monetary values cannot be reconstructed. Statements about those values remain inference (추정). No private-document directory was accessed.

## Payment failures

| Validation | Category | Shape evidence | Source cause |
| --- | --- | --- | --- |
| `monthly_amounts_numeric` | (가), plus (다) unsafe cell-selection assumption | `/tmp/layout_shape2.txt:45`–`:89` has twelve one-digit or two-digit month labels with alphabetic `A` in mandatory money cells. Examples are x391–421 y962–1011 at .49, x1195–1231 y961–1013 at .50, x592–621 y1375–1421 at .38. Nonzero-looking late rows have valid digit/comma shapes at lines 90–104. | `nhis_payment.py:58` accepts only decimal money. Lines 257–260 record missing numeric rows. Lines 273–293 choose the nearest numeric amount among the whole row, so a neighboring valid cell can become a missing column's value. Boundaries and whole-cell validation are needed before correction. |
| `monthly_total_matches` | (가) cascading to arithmetic verification, with (다) grouped-header selection | Sum row has health/care amounts at x332–478 and x546–669, y1726–1780, source lines 105–109. Group header `고지금액` is centered x640–778, source line 22. Empty optional body columns span header centers around x809 and x1010, source lines 24–42. | `nhis_payment.py:221` uses distance to the whole group header when choosing the sum cell. That can select the care total, while body rows use the health subheader at line 273. Lines 461–466 then compare mismatched/incomplete sums. Original numeric mismatch remains inference. |
| `paid_total_matches` | (가) cascading to arithmetic verification, with (다) missing eight-column contract | Paid health/care group spans x1141–1284 and x1352–1476, source lines 107/109. `납부총액` has a separate bottom amount x738–879 y1799–1848, source lines 110–113. | `nhis_payment.py:225` selects the total nearest the whole paid-group header. Lines 274–280 use the same whole-group center for paid body values. Lines 468–474 compare this chosen component against chosen totals. The separate `납부총액` amount is unreachable because line 228 stops on `합계`. |

The visible `A` characters prove Latin recognition in numeric cells. They do not prove that the underlying characters were `O`, `I` or `l`, and cannot justify translating arbitrary `A` to zero. A future corrected OCR result may pass only with known lookalikes in numeric-only cells and successful arithmetic. Unknown Latin glyphs remain review cases.

## Existing payment field contract

`PaymentResult.fields` uses Korean string-valued fields. The private benchmark's `billed_by_month` is an alias to `월별고지금액`, and `long_term_care_by_month` aliases `월별장기요양보험료` (`engine_v2/tools/private_bench.py:119`). The alias contract should remain intact.

- `성명`, `생년월일`, `발급일` are produced by header consensus and the bottom issue-date fallback (`nhis_payment.py:348`). The date parser already accepts a trailing period through search, but the new bounded value reader should validate an entire date cell.
- `월별고지금액`, `월별장기요양보험료`, `월별보수외소득월액_건강` are JSON mappings from `YYYY-MM` to decimal strings (`nhis_payment.py:392`). Empty optional cells must stay empty and cannot borrow neighboring money.
- `건강보험료`, `장기요양보험료`, `보수외소득월액_건강` are existing three-month averages, using the fixed legacy three-month selection (`nhis_payment.py:300`). `고지월` lists every observed month.
- `demo/backend/ocr/localocr.py:215` copies all extracted field values and validations. It supports optional `structure_complete` metadata and caps confidence at .4 when incomplete (`:233`). Adding that metadata to this recognized form preserves the adapter contract and makes arithmetic/structural failure conservative.

## Eight-column form changes

The new recognized government form requires a bounded reader for the grouped four billed/four paid columns. Derive subcolumn order and boundaries from the multi-line header positions and persistent body gaps. Include empty optional columns from header evidence. Preserve all eight cells in a dedicated internal monthly table representation and publish existing mappings from the correct billed components.

Read twelve `1월` through `12월` rows, stop before `합계`, and separately read `납부총액`. The query text can describe a subperiod while the table contains twelve calendar months. Existing `nhis_payment.py:234` assigns every month earlier than the query's start month to the next year. For a twelve-month same-year calendar table this is incorrect. Use the query's same year for this recognized twelve-row form, while preserving existing cross-year query behavior on the legacy reader.

Verify each nonempty monetary column against its own sum-row cell, then verify all paid components against `납부총액`. Empty optional cells remain empty. Mandatory missing or invalid cells fail completeness. Numeric corrections produce validation details naming the cell and correction category without original sensitive values. Amounts may only be corrected through allowed lookalikes and punctuation rules.

Read government document number 4-4-4-5 from its label region (`/tmp/layout_shape2.txt:6`), subscriber name/birth at lines 13–16, optional empty workplace at line 17, payer number at lines 18–19, query period at line 20, total/purpose at lines 110–113, and unlabeled date below confirmation at line 115. Preserve empty workplace as an empty cell.

## Absent insurance category

`nhis_payment.py:369` currently regex-matches arbitrary text after `사업장명칭`. An empty workplace followed by another label can satisfy this expression. The resulting truthy match emits `가입구분=직장` at lines 370–373 even though the document lacks the category. The recognized variant should omit that inferred field and treat printed category as optional.

The upload payment requirement has no category required field (`demo/backend/rules/required_docs.py:355`). Monthly checks use `월별고지금액` (`demo/backend/rules/doc_check.py:500`). Downstream scoring currently uses qualification category, then payment category, then defaults to `직장` (`demo/backend/rules/facts.py:150`). This scoring fallback is an existing policy behavior outside this reader task. Preserve and report it. Changing the reader cannot establish the applicant's true category from the supplied form.

## Resident numbering

The parser already supports note-only row numbers when note text and number share the grouped OCR line (`resident_abstract.py:294`–`:300`). It also assigns a separate lower number line to the preceding address entry when that entry lacks a number (`:308`–`:311`). Sequence validation combines address and note numbers across pages (`:435`–`:444`), so page transitions alone do not reset or break numbering.

The own-OCR shape contains a numbered bracketed law-change note on the final page. Its number token is x170–221 y1101–1147 (`/tmp/layout_shape.txt:777`). The bracketed note is x278–1054 y1129–1160 (`:778`). Their vertical centers differ by about twenty pixels. `group_lines` compares against the incoming note's height of 31px times .6, which is 18.6px (`engine_v2/pipeline/layout.py:46`). The number and note therefore form separate lines. The number is ignored when the prior address already has a number, and the next bracketed line has no number to append to `note_numbers`.

The earlier bracketed note at x272–1109 y726–773 and number x170–225 y705–753 (`/tmp/layout_shape.txt:753`–`:754`) has a taller note token and remains grouped. This explains inconsistent note handling with the same semantic structure.

An in-memory synthetic probe preserved the source coordinates, assigned fictitious sequential numbers and dates, and called the unchanged `_parse_rows`. It created 29 input numbers, kept 27 address numbers plus one note number, and lost the other note number at the second bracketed law-change row. This reproduces a numbering false alarm from OCR line splitting. Actual original sequence values remain inference because the shape masks digits.

## Resident review gap and stage 8 plan

History checks already lower history field confidence (`resident_abstract.py:451`–`:467`). The demo adapter computes overall confidence solely from issue date/name/birth (`demo/backend/ocr/localocr.py:164`–`:166`), so it ignores a failed history-number validation and can return .95. This exactly matches the source summary (`/tmp/layout_shape.txt:795`–`:798`).

Associate an isolated number token with a nearby bracketed note row before parsing that note, using relative line height, row spacing and number-column geometry. Require unique proximity and avoid crossing a new dated address row. Keep missing or duplicated genuine numbers as failed validations. If numbering or another history validation still fails, cap the resident adapter's confidence below the review threshold and propagate a review warning. Test note-only rows split at two font heights, page boundaries, true gaps, duplicates and unreadable numbers. Existing aligned-note tests (`engine_v2/tests/test_resident_abstract.py:85`, `:132`) and genuine gap test (`:168`) remain intact.

## Stage 6 implementation outcome

`nhis_payment.extract` routes the recognized eight-column family to `nhis_payment_gov` (`engine_v2/extractors/nhis_payment.py:333`). Recognition combines body title, government information/document-number evidence and at least three surviving repeated outside-income subheaders above the first table month (`nhis_payment_gov.py:22`). A missing individual header, month or sum stays on the incomplete dedicated path. A legacy government-style three-month table with fewer columns retains the former reader and values.

The dedicated reader derives all nine column intervals, including the month column, from overlapping multi-line header components and observed empty body corridors (`nhis_payment_gov.py:105`). Twelve calendar-month rows retain out-of-query zero amounts. Empty optional cells become JSON null in `월별납부내역`. Existing Korean monthly mappings, fixed October–December averages and benchmark aliases keep their contracts. Each of eight columns has its own arithmetic check, and paid component totals must equal the separate bottom grand total. Unknown numeric glyphs and malformed whole cells remain incomplete.

OCR-only numeric correction uses the shared helper within bounded amount cells (`nhis_payment_gov.py:93`). Every correction's row, column and allowed category survives upload/DB serialization in `숫자형식교정`, with the `numeric_cell_corrections` validation contingent on successful arithmetic (`:257`). Text-layer inputs use the same observed form geometry and receive no alphabetic/punctuation correction. The reader returns all requested metadata, blank workplace, payer/document numbers, purpose and closing issue date, with no inferred category. Failed completeness caps every published field at .4 and adds the standard review warning (`:281`).

A normal-entry-point review found that income scoring consumed financial fields from incomplete or identity-review documents. `engine/pipeline.py:79` always proceeds to eligibility and permits income FAIL to determine final status, so this could turn an uncertain payment amount into a rejection. The bounded trust gate at `demo/backend/rules/facts.py:85` suppresses financial fields from every payment with explicit NEEDS_REVIEW or FAIL status. A present incomplete structure marker also blocks financial fields. This applies when damaged outside-income headers cause a legacy fallback and the dedicated marker is absent. Complete/statusless legacy inputs keep their prior behavior. Original OCR values remain available to officers. Existing category fallback to `직장` at the facts layer remains a policy inference outside this extraction change.

The adapter also dropped an explicit document NEEDS_REVIEW status when its raw OCR confidence was high. `demo/backend/engine_adapter.py:206` now lowers only the engine-facing confidence for such a row to .4. Already uncertain confidence, absent status, PASS and upstream FAIL retain their previous values. Saved OCR fields/confidence retain their original representation. Together these boundaries keep high unreadable amounts and another person's complete payment in final NEEDS_REVIEW and prevent income rejection from those values.

Stage 6 adds 49 engine tests and 34 backend tests. They include fifteen actual image-PDF uploads and one actual text-layer PDF upload, correction persistence, all eight columns with differing paid/billed values, optional populated/empty cells, relative geometry, fragmented labels/date/money words, full-calendar/query distinction, corruption cases, complete/uncertain financial scoring and adapter status compatibility. Markerless high-amount uncertainty and two-to-four damaged outside-income headers are covered. All eighteen independent scenario modules completed successfully with the unchanged 1,796 reported checks and the separate eight-form verification. Scenario logs are under `/tmp/p2-stage6-scenarios/`.

The real shape's alphabetic placeholders still do not reveal the actual glyphs. Corrected synthetic O/o/I/l cases prove permitted postprocessing. Actual source correction success and the unavailable first-applicant payment shape remain inference (추정).

## Stage 8 implementation outcome

The isolated-number/law-note geometry is repaired locally in `resident_abstract._join_note_numbers` (`engine_v2/extractors/resident_abstract.py:269`). Only a sole ordinal token in the number column and an adjacent bracketed note row can associate. The candidate must be unique in both directions and lie within relative font-height and observed date-row-pitch limits. OCR words, stored text and general line grouping retain their representations.

The in-memory source-coordinate probe that previously lost one synthetic note ordinal now retains all 29 fictitious ordinals across 27 address entries and two numbered note rows. The actual original digits remain masked in the source, so their correctness remains inference (추정). The structural reproduction establishes that the observed font-height difference alone can create the reported false alarm.

The parser now accounts for every observed numeric-column token (`resident_abstract.py:319`), and the sequential check also requires every parsed address entry to have a number (`:479`). This catches missing first, last or all observed address ordinals, true gaps, duplicates and discarded orphan numbers. Existing contiguous sequences beginning above one and unnumbered bracketed annotations remain valid. Source shapes cannot reveal a completely absent row with no surviving ordinal/date/address evidence, which remains an observability limit.

An unresolved history validation adds an extractor warning and caps every published field's confidence at .4 while retaining read values (`resident_abstract.py:495`, `:515`). This also protects direct core-engine date/name/residence checks from turning an incomplete history into an OCR-derived rejection. Independent wrong-kind and missing-page rules retain their existing behavior. The demo resident adapter carries the history warning and .4 cap (`demo/backend/ocr/localocr.py:168`), so an unchanged readable header cannot hide a history failure behind .95 confidence.

Stage 8 adds 35 engine tests and nine backend tests. They cover the unequal-height law note, two-to-four-character names, resolution/jitter/skew, a note carried across a page boundary, contiguous numbering offsets, unnumbered notes, true missing/duplicate/unreadable/orphan numbers and direct core review behavior. Nine actual three-page image-PDF uploads verify corrected normal PASS without warnings and remaining uncertainty as NEEDS_REVIEW. The focused resident/core/format/backend title suite passed 142 tests. P8 local-OCR scenarios retained 89 passing checks.
