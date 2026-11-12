# Shape-derived follow-up verification

## Step 1 baseline
Three strict-xfail acceptance tests reproduce all extractor-level failures from the redacted observations. A reads nine history rows but fails name consistency, page names, history cells, numbering and blank marker. B fails name consistency, household rows and subscriber/first-member matching. C fails form recognition, government document-number consistency, birth consistency and number format. The demo-only `성명_required` is added after extraction; backend coverage will verify it separately. Baseline: 3 xfailed, 0 unexpected failures.

Fixtures: `engine_v2/tests/observed_form_samples.py`; acceptance: `engine_v2/tests/test_observed_forms.py`. All values are fabricated. External layout contents are neither copied nor committed.
