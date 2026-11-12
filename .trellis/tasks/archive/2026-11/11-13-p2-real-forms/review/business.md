# Independent business-proof review

Reviewed the thirteen-field contract, NTS checksum reuse, personal/corporate birth derivation, final required-field safety, identity-absent/mismatch handling, unique date selection and joint participant rows. Existing future-opening metadata behavior and synthetic fixture-tier exception retain their documented scope.

## Verified finding 1, repaired

The last `종목` value band ended halfway between the final label center and the joint-business header. Ordinary multiline category content before the actual joint header could be silently omitted while structure stayed complete.

Reproduction used `sample.business(noise=False)` plus the fictitious cell `(633, 1560, 1380, 1600, '|추가누락가상품목', .99)`. The original `business_registration.extract` returned complete with all checks passed, omitted the additional category item, and `_from_business_proof` plus `check_document` with matching identity returned PASS.

The parent authorized a stage 9 repair. `_grid` now reads the last value band through the observed joint-header start. It rejects a right-side word crossing that actual vertical boundary and ordinary competing content in the observed left label column. Existing internal row-center splitting and all earlier field contracts remain intact.

Eight added engine/backend regressions cover retained last-field content, two crossing-box center positions and competing left-column text. The full business suites plus portal upload tests passed 152 tests, including all original 131 business tests.

## Verified finding 2, repaired

The joint-business reader excludes words ending left of `name_header.x0 - 4 * glyph`. That cutoff can hide normal-sized ordinary participant text in the observed right-side value area.

Reproduction used `sample.business(noise=False)` plus the fictitious partial participant `(650, 1705, 730, 1750, '이합성', .99)`, while retaining the explicit absence phrase. The reader returned `공동사업자유무=False`, complete structure and PASS through `_from_business_proof` plus `check_document` with matching identity. Extending the same word to x790 made the existing partial-row check correctly return NEEDS_REVIEW.

The source code at `_joint_business` computed this cutoff from the centered name header. The side label ends near x547 and main right-side grid values begin near x633 in the authored source-shaped fixture, so the partial word could lie in the value area while missing that header-derived cutoff. This finding was reported promptly, and the parent authorized its repair within stage 9.

The joint value region now begins at the observed side caption's right edge. The existing name/identifier separator still comes from the observed headers. Words crossing either boundary are incomplete evidence. Ordinary partial names left of the centered header are accounted for and produce review when the absence phrase conflicts with them. A fully evidenced left-aligned name/identifier participant remains complete. The documented oversized-fragment exception still requires the explicit absence phrase.

Eight further engine/backend regressions cover normal and partial left-aligned participants and words crossing the side-caption or name/identifier boundary.

The final business-plus-portal focused run passed 160 tests. Both findings are resolved, all original 131 business tests pass, and sixteen new regressions cover the repairs. Diff checking and Python compilation passed. Production edits are frozen for the parent's full integration gate.

## Other checked boundaries

- The thirteen required fields are returned by a complete personal proof. Corporate/unknown entity codes, checksum failure and explicit corporate taxpayer evidence suppress birth and retain review.
- The final guard rechecks required identity and structured list fields after common header filtering.
- Missing reference identity or either representative identity mismatch returns NEEDS_REVIEW before generic date rules can reject the document. Correct identity preserves ordinary date checks.
- Duplicate and malformed issuing-date evidence within the closing issuer region is rejected, including overlapping issuer rows.
- Existing joint tests cover one through ten rows, skew, missing/conflicting participants and source-shaped oversized fragments. The reported second finding concerns an ordinary-sized partial participant excluded before those checks.
- All probes used authored fictitious fixtures. No private documents or audit walkthrough were accessed.
