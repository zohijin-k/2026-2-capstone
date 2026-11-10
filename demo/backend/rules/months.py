"""신청자 안내에 쓰는 고지월 표기."""

import re


_MONTH = re.compile(r"^(\d{4})-(0?[1-9]|1[0-2])$")


def format_month_ranges(months: list[str]) -> str:
    """월 목록을 시간순으로 정리하고 연속된 월은 한 구간으로 묶는다."""
    parsed = set()
    for value in months:
        match = _MONTH.fullmatch(str(value))
        if match:
            parsed.add((int(match.group(1)), int(match.group(2))))
    ordered = sorted(parsed)
    if not ordered:
        return ", ".join(months)

    groups: list[tuple[tuple[int, int], tuple[int, int]]] = []
    first = prior = ordered[0]
    for current in ordered[1:]:
        prior_index = prior[0] * 12 + prior[1]
        current_index = current[0] * 12 + current[1]
        if current_index == prior_index + 1:
            prior = current
            continue
        groups.append((first, prior))
        first = prior = current
    groups.append((first, prior))

    def one(month: tuple[int, int]) -> str:
        return f"{month[0]}년 {month[1]}월"

    rendered = []
    for start, end in groups:
        if start == end:
            rendered.append(one(start))
        elif start[0] == end[0]:
            rendered.append(f"{start[0]}년 {start[1]}월~{end[1]}월")
        else:
            rendered.append(f"{one(start)}~{one(end)}")
    return ", ".join(rendered)
