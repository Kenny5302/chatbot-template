"""Business hours logic. Pure functions so open/closed is computed in code, not guessed by the model."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.businesses import Business

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _parse_time(text: str) -> time:
    hh, _, mm = text.strip().partition(":")
    return time(int(hh), int(mm or 0))


def parse_ranges(value: str) -> list[tuple[time, time]]:
    """'8:00-12:00, 13:00-17:30' -> [(8:00, 12:00), (13:00, 17:30)]; 'closed' -> []."""
    value = value.strip().lower()
    if value in ("", "closed"):
        return []
    ranges: list[tuple[time, time]] = []
    for part in value.split(","):
        try:
            start_s, end_s = part.split("-")
            start, end = _parse_time(start_s), _parse_time(end_s)
        except ValueError:
            raise ValueError(f"bad hours '{part.strip()}' (use '8:00-17:30' or 'closed')") from None
        if end <= start:
            raise ValueError(f"hours '{part.strip()}' must end after they start")
        ranges.append((start, end))
    return ranges


def fmt_time(t: time) -> str:
    return datetime.combine(date.today(), t).strftime("%-I:%M %p")


def describe_hours(business: "Business") -> list[str]:
    lines = []
    for key, name in zip(DAYS, DAY_NAMES):
        ranges = parse_ranges(business.hours.get(key, "closed"))
        text = ", ".join(f"{fmt_time(a)}-{fmt_time(b)}" for a, b in ranges) or "Closed"
        lines.append(f"{name}: {text}")
    return lines


@dataclass(frozen=True)
class OpenStatus:
    is_open: bool
    now_label: str
    next_open_label: str | None


def _ranges_on(business: "Business", day: date) -> list[tuple[time, time]]:
    if day in business.holidays_closed:
        return []
    return parse_ranges(business.hours.get(DAYS[day.weekday()], "closed"))


def get_status(business: "Business", now: datetime | None = None) -> OpenStatus:
    tz = ZoneInfo(business.timezone)
    local = now.astimezone(tz) if now else datetime.now(tz)
    today, t = local.date(), local.time()

    is_open = any(a <= t < b for a, b in _ranges_on(business, today))

    next_open = None
    if not is_open:
        for offset in range(15):
            day = today + timedelta(days=offset)
            starts = [a for a, _ in _ranges_on(business, day) if offset > 0 or a > t]
            if starts:
                when = datetime.combine(day, min(starts))
                next_open = f"{when.strftime('%a')} {fmt_time(min(starts))}"
                break

    return OpenStatus(
        is_open=is_open,
        now_label=f"{local.strftime('%a %b %-d, %-I:%M %p')} {local.tzname()}",
        next_open_label=next_open,
    )


def status_line(business: "Business", now: datetime | None = None, language_hint: str = "") -> str:
    """One line prepended to each customer turn so the model knows the real time and open state."""
    s = get_status(business, now)
    if s.is_open:
        state = f"{business.name} is OPEN right now."
    else:
        nxt = f" Next opens {s.next_open_label}." if s.next_open_label else ""
        state = f"{business.name} is CLOSED right now.{nxt}"
    hint = f" {language_hint}" if language_hint else ""
    return f"[System note, not written by the customer: it is {s.now_label}. {state}{hint}]"
