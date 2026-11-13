# Implementation approval and binding refinements

The user approved implementation on 2026-11-13 with these binding conditions. They override conflicting details in earlier artifacts.

1. Existing verify_upload test expectations remain completely unchanged, including --validations and applicant_reason output. If an expectation would need to change, stop and report. Additive compatibility coverage is permitted.
2. Resolve symlinks and apply location policy to actual paths. Inside this repository: require git check-ignore and reject tracked files. Outside this repository: allow without calling check-ignore. Apply to manifest and expected. Symlinks are not inherently rejected.
3. Case execution exceptions print only case ID, X marker and exception class name; never message, path or stack. Any mismatch/case error exits 1; all match exits 0. Record-mode case errors also exit 1 and preserve prior expected bytes. Top-level CLI/schema/location/I/O errors may retain safe fixed codes and exit 2.
4. Manifest represents slot, optional work category, self-identity and three-path income mode. Snapshot includes statuses, codes/severities, applicant-visible codes and failed validation names.
5. No DB persistence, verdict/blocker rule, extractor or frontend changes. Tests use fake manifests/authored synthetic files only, without real documents or actual private-path references.
6. Before any commit show git diff --stat main and engine_v2/backend/scenario results and obtain approval. Implement/review agents must not commit or push.

These refinements are directly approved by the user and do not require a new planning approval.
