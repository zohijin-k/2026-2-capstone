"""Applicant-facing form numbers and ordering for all demo form exports."""

from __future__ import annotations

from collections.abc import Iterable


# Stored IDs follow the implementation form numbering. All applicant-facing
# labels and sequence decisions derive from this single mapping.
INTERNAL_TO_PUBLIC_FORM = {
    "서식1": "서식2",  # 참여 신청서
    "서식2": "서식1",  # 자가진단
    "서식3": "서식3",
    "서식4": "서식4",
    "서식5": "서식5",
}

JOB_FORM_ORDER = ("job_application", "job_consent", "job_interview_confirmation")


def public_form_no(internal_form: str) -> str | None:
    return INTERNAL_TO_PUBLIC_FORM.get(internal_form)


def internal_form_no(public_form: str) -> str | None:
    return next(
        (internal for internal, public in INTERNAL_TO_PUBLIC_FORM.items() if public == public_form),
        None,
    )


def form_order_key(internal_form: str) -> tuple[int, int, str]:
    public = public_form_no(internal_form)
    if public is not None:
        return (0, int(public.removeprefix("서식")), internal_form)
    try:
        return (1, JOB_FORM_ORDER.index(internal_form), internal_form)
    except ValueError:
        return (2, 0, internal_form)


def order_form_numbers(forms: Iterable[str]) -> list[str]:
    return sorted(forms, key=form_order_key)
