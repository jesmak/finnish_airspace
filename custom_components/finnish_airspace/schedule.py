"""A NOTAM's SCHEDULE: the hours within its period when it is in force."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from .bulletin import MONTHS

WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
SPAN = re.compile(r"(\d{2})(\d{2})-(\d{2})(\d{2})")
DAYS = re.compile(r"(\d{1,2})(?:-(\d{1,2}))?")
WEEKDAY_RANGE = re.compile(r"(MON|TUE|WED|THU|FRI|SAT|SUN)(?:-(MON|TUE|WED|THU|FRI|SAT|SUN))?")
# The year isn't known where these are used, so February may have 29.
DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

Window = tuple[datetime, datetime]


def schedule_windows(start: datetime, end: datetime | None, schedule: str) -> list[Window] | None:
    """The period cut into the windows the schedule gives, or None when the whole period stands instead.

    That is when the schedule has a form this doesn't know, the period has no end, or the windows don't fit the period.
    Known forms: "0600-1500" (every day), "0630-1015 1240-1350", "MON-FRI 0600-1500 EXC DEC 24 25",
    "24 0500-1700, 25 0600-1800" and "20-23 0500-1300" (days of the month), and "0600-0500" (across midnight).
    """
    if end is None:
        return None
    text, _, excluded_text = schedule.partition(" EXC ")
    excluded = excluded_dates(excluded_text)
    groups = [parse_group(group) for group in text.split(",")]
    if excluded is None or None in groups:
        return None

    windows: list[Window] = []
    skipped_before_start = False
    # From the day before, for a window across midnight into the first day.
    day = start.date() - timedelta(days=1)
    while day <= end.date():
        if (day.month, day.day) not in excluded:
            for days, weekdays, spans in groups:
                if (days or weekdays) and day.day not in days and day.weekday() not in weekdays:
                    continue
                midnight = datetime.combine(day, datetime.min.time(), UTC)
                for opens_at, closes_at in spans:
                    opens, closes = midnight + opens_at, midnight + closes_at
                    if closes <= opens:
                        closes += timedelta(days=1)
                    if closes > start and opens < end:
                        windows.append((max(opens, start), min(closes, end)))
                    elif closes <= start and closes.date() == start.date():
                        skipped_before_start = True
        day += timedelta(days=1)
    windows = merged(windows)
    # Read right, the last window ends at TO, and the first starts at FROM, unless the NOTAM was issued again during
    # its period, after a window of FROM's day had closed. Anything else is a misreading.
    if not windows or windows[-1][1] != end or (windows[0][0] != start and not skipped_before_start):
        return None
    return windows


def merged(windows: list[Window]) -> list[Window]:
    """Sorted, with windows that overlap or touch made one, as groups such as "0600-1500, 3 0700-1200" may give."""
    result: list[Window] = []
    for opens, closes in sorted(windows):
        if result and opens <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], closes))
        else:
            result.append((opens, closes))
    return result


def excluded_dates(text: str) -> set[tuple[int, int]] | None:
    """Excluded dates such as "DEC 24 25 JAN 1", as (month, day) pairs.

    A month without days, or a day the month doesn't have, is a form not known.
    """
    excluded = set()
    month = None
    month_has_days = True
    for token in text.split():
        if token in MONTHS:
            if not month_has_days:
                return None
            month, month_has_days = MONTHS.index(token) + 1, False
        elif token.isdigit() and month and 1 <= int(token) <= DAYS_IN_MONTH[month - 1]:
            excluded.add((month, int(token)))
            month_has_days = True
        else:
            return None
    return excluded if month_has_days else None


def parse_group(group: str) -> tuple[set[int], set[int], list[tuple[timedelta, timedelta]]] | None:
    """A group such as "MON-FRI 0600-1500 1700-1800": the days of the month, the weekdays and the spans within a day."""
    tokens = group.split()
    selectors = [token for token in tokens if not SPAN.fullmatch(token)]
    if tokens[: len(selectors)] != selectors or len(selectors) == len(tokens):
        return None
    days: set[int] = set()
    weekdays: set[int] = set()
    for token in selectors:
        if m := DAYS.fullmatch(token):
            first, last = int(m[1]), int(m[2] or m[1])
            if not (valid_day(first) and valid_day(last) and first <= last):
                return None
            days |= set(range(first, last + 1))
        elif m := WEEKDAY_RANGE.fullmatch(token):
            first, last = WEEKDAYS.index(m[1]), WEEKDAYS.index(m[2] or m[1])
            weekdays |= {d % 7 for d in range(first, last + 1 if last >= first else last + 8)}
        else:
            return None
    spans = []
    for token in tokens[len(selectors) :]:
        h1, m1, h2, m2 = (int(part) for part in SPAN.fullmatch(token).groups())
        if m1 > 59 or m2 > 59 or h1 * 60 + m1 > 1440 or h2 * 60 + m2 > 1440:
            return None
        spans.append((timedelta(hours=h1, minutes=m1), timedelta(hours=h2, minutes=m2)))
    return days, weekdays, spans


def valid_day(day: int) -> bool:
    return 1 <= day <= 31
