"""A NOTAM's period cut into windows by its schedule, and the fallback to the whole period."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.finnish_airspace.schedule import excluded_dates, schedule_windows


def at(day: int, hhmm: str, month: int = 10) -> datetime:
    return datetime(2026, month, day, int(hhmm[:2]), int(hhmm[2:]), tzinfo=UTC)


def test_every_day() -> None:
    assert schedule_windows(at(2, "0600", 11), at(4, "1500", 11), "0600-1500") == [
        (at(2, "0600", 11), at(2, "1500", 11)),
        (at(3, "0600", 11), at(3, "1500", 11)),
        (at(4, "0600", 11), at(4, "1500", 11)),
    ]


def test_two_spans_a_day() -> None:
    assert schedule_windows(at(2, "0630", 11), at(3, "1350", 11), "0630-1015 1240-1350") == [
        (at(2, "0630", 11), at(2, "1015", 11)),
        (at(2, "1240", 11), at(2, "1350", 11)),
        (at(3, "0630", 11), at(3, "1015", 11)),
        (at(3, "1240", 11), at(3, "1350", 11)),
    ]


def test_weekdays_except_dates() -> None:
    # From Monday 21 to Monday 28 December, without Christmas Eve and Day (Thursday and Friday).
    assert schedule_windows(at(21, "0600", 12), at(28, "1500", 12), "MON-FRI 0600-1500 EXC DEC 24 25") == [
        (at(21, "0600", 12), at(21, "1500", 12)),
        (at(22, "0600", 12), at(22, "1500", 12)),
        (at(23, "0600", 12), at(23, "1500", 12)),
        (at(28, "0600", 12), at(28, "1500", 12)),
    ]


def test_groups_of_weekdays() -> None:
    # Thursday 5 to Monday 9 November.
    assert schedule_windows(at(5, "0500", 11), at(9, "1800", 11), "MON-THU 0500-1800, FRI 0500-1400") == [
        (at(5, "0500", 11), at(5, "1800", 11)),
        (at(6, "0500", 11), at(6, "1400", 11)),
        (at(9, "0500", 11), at(9, "1800", 11)),
    ]


def test_weekdays_over_the_weekend() -> None:
    windows = schedule_windows(at(6, "0800", 11), at(9, "1200", 11), "FRI-MON 0800-1200")
    assert [start.day for start, _ in windows] == [6, 7, 8, 9]


def test_days_of_the_month() -> None:
    # Issued during the first day's window, so the first window starts at FROM.
    assert schedule_windows(at(24, "0725"), at(25, "1400"), "24 0600-1900, 25 0700-1400") == [
        (at(24, "0725"), at(24, "1900")),
        (at(25, "0700"), at(25, "1400")),
    ]


def test_a_range_of_days() -> None:
    windows = schedule_windows(at(20, "0500"), at(26, "1400"), "20-23 0500-1300, 26 0600-1400")
    assert [(start.day, start.hour, end.hour) for start, end in windows] == [
        (20, 5, 13),
        (21, 5, 13),
        (22, 5, 13),
        (23, 5, 13),
        (26, 6, 14),
    ]


def test_across_midnight() -> None:
    assert schedule_windows(at(15, "0600"), at(18, "0500"), "0600-0500") == [
        (at(15, "0600"), at(16, "0500")),
        (at(16, "0600"), at(17, "0500")),
        (at(17, "0600"), at(18, "0500")),
    ]


def test_across_midnight_and_a_month() -> None:
    assert schedule_windows(at(30, "2200"), at(1, "0400", 11), "2200-0400") == [
        (at(30, "2200"), at(31, "0400")),
        (at(31, "2200"), at(1, "0400", 11)),
    ]


def test_issued_again_after_the_first_days_window() -> None:
    # The first day's window closed at 12:23, before the NOTAM issued again at 12:25 starts.
    assert schedule_windows(at(20, "1225"), at(25, "1500"), "20 0500-1223, 21 0500-1800, 25 0600-1500") == [
        (at(21, "0500"), at(21, "1800")),
        (at(25, "0600"), at(25, "1500")),
    ]


def test_issued_again_during_a_window_across_midnight() -> None:
    # The window that opened the evening before is still open at FROM.
    assert schedule_windows(at(16, "0200"), at(17, "0400"), "2200-0400") == [
        (at(16, "0200"), at(16, "0400")),
        (at(16, "2200"), at(17, "0400")),
    ]


def test_issued_again_between_two_spans() -> None:
    assert schedule_windows(at(2, "1100", 11), at(2, "1350", 11), "0630-1015 1240-1350") == [(at(2, "1240", 11), at(2, "1350", 11))]


@pytest.mark.parametrize(
    "schedule",
    [
        "SR-SS",
        "H24",
        "DAILY 0600-1500",
        "0600-1500 MON-FRI",
        "MON-FRI",
        "MON-FRI 0600-1500 EXC SUN",
        "30-02 0600-1500",
        "32 0600-1500",
        "0600-2460",
        "0600-2500",
        "0600-1500 EXC NOV",
        "0600-1500 EXC",
        "",
    ],
)
def test_a_form_not_known_falls_back_to_the_whole_period(schedule: str) -> None:
    assert schedule_windows(at(2, "0600", 11), at(4, "1500", 11), schedule) is None


MONTH_LENGTHS = {
    "JAN": 31,
    "FEB": 29,
    "MAR": 31,
    "APR": 30,
    "MAY": 31,
    "JUN": 30,
    "JUL": 31,
    "AUG": 31,
    "SEP": 30,
    "OCT": 31,
    "NOV": 30,
    "DEC": 31,
}


@pytest.mark.parametrize(
    ("text", "excluded"),
    [
        ("DEC 24 25", {(12, 24), (12, 25)}),
        ("DEC 31 JAN 1", {(12, 31), (1, 1)}),
        ("", set()),
        # Every month's last day, and the day after it. The year isn't known, so FEB 29 is one.
        *[(f"{month} {days}", {(number, days)}) for number, (month, days) in enumerate(MONTH_LENGTHS.items(), 1)],
        *[(f"{month} {days + 1}", None) for month, days in MONTH_LENGTHS.items()],
        # A month without days, alone, first, in the middle or last, is a form not known.
        ("NOV", None),
        ("NOV DEC 24", None),
        ("DEC 24 NOV JAN 1", None),
        ("DEC 24 25 JAN", None),
        ("24", None),
        ("DEC 0", None),
        ("SUN", None),
    ],
)
def test_excluded_dates(text: str, excluded: set[tuple[int, int]] | None) -> None:
    assert excluded_dates(text) == excluded


def test_excluded_dates_across_the_new_year() -> None:
    windows = schedule_windows(at(30, "0600", 12), datetime(2027, 1, 2, 15, tzinfo=UTC), "0600-1500 EXC DEC 31 JAN 1")
    assert [start.date().isoformat() for start, _ in windows] == ["2026-12-30", "2027-01-02"]


def test_the_last_window_is_cut_at_to() -> None:
    assert schedule_windows(at(2, "0600", 11), at(3, "1200", 11), "0600-1500") == [
        (at(2, "0600", 11), at(2, "1500", 11)),
        (at(3, "0600", 11), at(3, "1200", 11)),
    ]


@pytest.mark.parametrize(
    ("start", "end", "schedule", "windows"),
    [
        # Monday 2 November is in both groups.
        (
            at(2, "0600", 11),
            at(3, "1500", 11),
            "MON-FRI 0600-1500, 2 0600-1500",
            [(at(2, "0600", 11), at(2, "1500", 11)), (at(3, "0600", 11), at(3, "1500", 11))],
        ),
        # Inside another window, on the last day.
        (
            at(2, "0600", 11),
            at(3, "1500", 11),
            "0600-1500, 3 0700-1200",
            [(at(2, "0600", 11), at(2, "1500", 11)), (at(3, "0600", 11), at(3, "1500", 11))],
        ),
        # Overlapping and ending later.
        (
            at(2, "0600", 11),
            at(3, "1600", 11),
            "0600-1500, 0700-1600",
            [(at(2, "0600", 11), at(2, "1600", 11)), (at(3, "0600", 11), at(3, "1600", 11))],
        ),
        # Touching.
        (at(2, "0600", 11), at(2, "1500", 11), "0600-1200 1200-1500", [(at(2, "0600", 11), at(2, "1500", 11))]),
        # Across midnight, into the next day's window.
        (at(2, "2200", 11), at(3, "0500", 11), "2200-0400, 0300-0500", [(at(2, "2200", 11), at(3, "0500", 11))]),
        # Touching at midnight.
        (at(2, "1800", 11), at(3, "0600", 11), "2 1800-2400, 3 0000-0600", [(at(2, "1800", 11), at(3, "0600", 11))]),
        # Cut at TO, then merged.
        (
            at(2, "0600", 11),
            at(3, "1100", 11),
            "0600-1500, 0700-1200",
            [(at(2, "0600", 11), at(2, "1500", 11)), (at(3, "0600", 11), at(3, "1100", 11))],
        ),
        # Cut at FROM, then merged.
        (
            at(2, "0800", 11),
            at(3, "1500", 11),
            "0600-1500, 0700-1200",
            [(at(2, "0800", 11), at(2, "1500", 11)), (at(3, "0600", 11), at(3, "1500", 11))],
        ),
        # Issued again after the first day's window closed, with groups that overlap.
        (
            at(2, "1225", 11),
            at(3, "1800", 11),
            "0500-1223, 1000-1800",
            [(at(2, "1225", 11), at(2, "1800", 11)), (at(3, "0500", 11), at(3, "1800", 11))],
        ),
        # Across the new year.
        (
            at(31, "2200", 12),
            datetime(2027, 1, 1, 4, tzinfo=UTC),
            "2200-0200, 0100-0400",
            [(at(31, "2200", 12), datetime(2027, 1, 1, 4, tzinfo=UTC))],
        ),
    ],
)
def test_windows_that_overlap_or_touch_merge(start: datetime, end: datetime, schedule: str, windows: list) -> None:
    assert schedule_windows(start, end, schedule) == windows


@pytest.mark.parametrize(
    ("start", "end", "schedule", "windows"),
    [
        # Closing at 2359 is closing at midnight, so the next day's window starting at 0000 joins it.
        (at(2, "1800", 11), at(3, "0600", 11), "2 1800-2359, 3 0000-0600", [(at(2, "1800", 11), at(3, "0600", 11))]),
        # Every day, with TO at 23:59 on the last: the last window is still cut at TO.
        (
            at(2, "1800", 11),
            at(3, "2359", 11),
            "1800-2359",
            [(at(2, "1800", 11), at(3, "0000", 11)), (at(3, "1800", 11), at(3, "2359", 11))],
        ),
        # The whole day, every day: one window.
        (at(2, "0000", 11), at(4, "2359", 11), "0000-2359", [(at(2, "0000", 11), at(4, "2359", 11))]),
        # A minute earlier is a minute earlier.
        (
            at(2, "1800", 11),
            at(3, "0600", 11),
            "2 1800-2358, 3 0000-0600",
            [(at(2, "1800", 11), at(2, "2358", 11)), (at(3, "0000", 11), at(3, "0600", 11))],
        ),
        # Opening at 2359 is opening at 23:59.
        (at(2, "2359", 11), at(3, "0100", 11), "2359-0100", [(at(2, "2359", 11), at(3, "0100", 11))]),
    ],
)
def test_closing_at_2359_is_closing_at_midnight(start: datetime, end: datetime, schedule: str, windows: list) -> None:
    assert schedule_windows(start, end, schedule) == windows


@pytest.mark.parametrize(
    ("start", "end", "schedule"),
    [
        # The last window would end at 15:00, not at TO.
        (at(2, "0600", 11), at(4, "1600", 11), "0600-1500"),
        # Nothing of FROM's day closed before FROM, so the first window should start at it.
        (at(20, "0500"), at(26, "1400"), "26 0600-1400"),
        # No window within the period at all.
        (at(2, "0600", 11), at(2, "1500", 11), "3 0600-1500"),
    ],
)
def test_windows_that_dont_fit_the_period_fall_back(start: datetime, end: datetime, schedule: str) -> None:
    assert schedule_windows(start, end, schedule) is None


def test_a_permanent_notam_falls_back() -> None:
    assert schedule_windows(at(2, "0600", 11), None, "0600-1500") is None
