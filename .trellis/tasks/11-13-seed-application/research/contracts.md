# Source evidence

- models.py: identity_json is the identity reference; arbitrary form1_json/form5_json avoid schema changes.
- api/applications.py patch (225), self_check (322), save_consents (349): shared writes; _lock_identity copies verified name/birth. Signatures use storage/signatures/{application_no}_{consent_type}.png.
- api/subsidy.py save_subsidy_items: configured selection validation/persistence.
- api/forms.py _form_is_complete (~396), BUILDERS/available_forms, snapshot_written_pdf (~559): completeness and rendered PDF exports. _form_has_saved_values iterates all keys; metadata is not proof of completion.
- api/officer.py Entry (~177), _eligibility (~690), detail response: project named fields; verify actual responses with sentinel.
- api/review.py _blockers (~157): required form fields, email format, subsidy presence/receipts, agreed consents, required uploads/FAILs, work category, eligibility blockers. Does not enforce every written-form/signature requirement.
- rules/programs.py DOUBLE_SAVINGS_REQUIRED_FIELDS (~292), JOB_PACKAGE_REQUIRED_FIELDS (~308), consent_types: required fields/consents.
- api/common.py doc_context (~87), checklist_for (~151): context, subsidy rows, pinned criteria build checklist.
- api/documents.py upload_document (~279): identity_of(app.identity_json), checklist, paper_forms.서식5 and SubsidyItem.receipt_amount feed upload checks. Contact fields are not identity reference.
- rules/facts.py build_facts: householdSize comparison only; transferIn residence fallback; employedAt work-duration scoring; birth age. Synthetic test inputs affect scores and must be documented.
- api/review.py _run_review (~470): form1 name, facts.birth_date, extract_region(form1.address, program.target_regions) become engine applicant. Address already affects municipality judgment.
- rules/required_docs.py WorkCategory differs from form1.workType; DocumentUpload and documents.set_doc_context store doc_context_json.work_category at stage three.
- frontend ApplyFlow.tsx savedPage (~65): /apply/upload plus sessionStorage applicant.activeApplicationId. Restore (~149-212) uses initialPage.stage with no completion redirect. Original tab required.
- vite.config.ts uses default Vite port; demo/README.md documents http://localhost:5173.
- Initial checkout main adb002f; preexisting untracked docs/audit excluded. No real demo DB contents read.
