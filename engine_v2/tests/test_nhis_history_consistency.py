"""정부24 자격득실확인서 공통 5년 판정과 가입자구분의 합성 회귀 검사."""

from datetime import date

from ..extractors.nhis_acquisition_loss import history_covers_recent_years


def test_history_coverage_matches_old_loss_rule_without_query_period():
    issue = date(2031, 7, 8)
    cutoff = date(2026, 7, 8)

    assert history_covers_recent_years(issue, None, [(date(2019, 2, 3), date(2020, 4, 5))])
    assert not history_covers_recent_years(issue, None, [(date(2027, 1, 2), date(2028, 3, 4))])
    assert history_covers_recent_years(issue, None, [(date(2020, 1, 2), None)])
    assert history_covers_recent_years(issue, (date(2025, 1, 1), issue), [])
    assert not history_covers_recent_years(issue, (cutoff, date(2031, 7, 7)),
                                          [(date(2019, 2, 3), date(2020, 4, 5))])
