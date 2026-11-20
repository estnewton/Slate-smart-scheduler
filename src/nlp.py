"""
Turns a typed sentence into a calendar event, e.g.

    "math quiz on tuesday 5-6pm in wartik lab"
    -> Math Quiz, Tue (next Tuesday), 5:00-6:00 PM, location "Wartik Lab"

Deterministic and offline on purpose: no API key, instant, and the same sentence always gives
the same answer (good for a live demo). Handles weekdays ("tue", "next friday"), dates
("nov 24th", "11/24", "24 november"), today/tomorrow, time ranges ("5-6pm", "10:30 to noon",
"from 2 until 3:15pm"), single times ("at 3pm", default 1 hour), and a place after "in"/"at"/"@".
No time at all -> an all-day event.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9,
    "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_WEEKDAYS = {
    "mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1, "wed": 2, "weds": 2,
    "wednesday": 2, "thu": 3, "thur": 3, "thurs": 3, "thursday": 3, "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5, "sun": 6, "sunday": 6,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_WEEKDAY_ALT = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))

_T = r"(\d{1,2}|noon|midnight)(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?"
_RANGE = re.compile(rf"\b(?:from\s+)?{_T}\s*(?:-|–|—|\bto\b|\buntil\b|\btill\b)\s*{_T}(?![\w/])", re.I)
_SINGLE = re.compile(r"\b(?:at\s+|@\s*)?(?:(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)|(\d{1,2}):(\d{2})|(noon|midnight))(?!\w)", re.I)
_MONTH_DAY = re.compile(rf"\b(?:on\s+)?(?:the\s+)?({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b", re.I)
_DAY_MONTH = re.compile(rf"\b(?:on\s+)?(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_ALT})\b(?:,?\s+(\d{{4}}))?", re.I)
_NUMERIC = re.compile(r"\b(?:on\s+)?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_WEEKDAY = re.compile(rf"\b(?:on\s+)?(next\s+|this\s+)?({_WEEKDAY_ALT})\b\.?", re.I)
_RELATIVE = re.compile(r"\b(today|tonight|tomorrow|tmrw|tmr)\b", re.I)
_PLACE = re.compile(r"(?:^|\s)(?:in|at|@)\s+(?:the\s+)?(.+)$"
                    r"|(?:^|\s)(?:on|over|via)\s+((?:zoom|teams|google meet|meet|facetime|the phone|phone)\b.*)$", re.I)

_LEAD_FILLER = re.compile(r"^(?:please\s+)?(?:add|schedule|create|put|book|make|new|set up)\b\s*(?:an?\s+|my\s+)?", re.I)
_EDGE_FILLER = re.compile(r"^(?:on|from|at|in|for|the|a|an|,|-)\s+|\s+(?:on|from|at|in|for|the|to my calendar|,|-)$", re.I)
_SMALL = {"of", "and", "the", "for", "with", "to", "a", "an", "on", "in", "at", "by"}


@dataclass
class ParsedEvent:
    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    location: Optional[str] = None
    notes: list = field(default_factory=list)


def _hour(raw: str) -> int:
    raw = raw.lower()
    return 12 if raw == "noon" else 0 if raw == "midnight" else int(raw)


def _apply_meridiem(h: int, ap: Optional[str]) -> int:
    if not ap:
        return h
    if ap[0].lower() == "p" and h < 12:
        return h + 12
    if ap[0].lower() == "a" and h == 12:
        return 0
    return h


def _guess_pm(h: int) -> int:
    """No am/pm given: 1-7 is almost always afternoon/evening for a student's calendar."""
    return h + 12 if 1 <= h <= 7 else h


def _parse_times(text: str):
    """Returns (start time, end time or None, span) or None."""
    m = _RANGE.search(text)
    if m:
        h1, m1, ap1, h2, m2, ap2 = m.groups()
        sh, eh = _hour(h1), _hour(h2)
        named = {h1.lower(), h2.lower()} & {"noon", "midnight"}
        if sh > 23 or eh > 23 or int(m1 or 0) > 59 or int(m2 or 0) > 59:
            return None
        if ap2 and not ap1 and h1.lower() not in ("noon", "midnight"):
            s_try = _apply_meridiem(sh, ap2)
            e_try = _apply_meridiem(eh, ap2)
            # "2-2:30pm" -> 2pm; "11-1pm" -> 11am (compare hours *and* minutes)
            ok = (s_try, int(m1 or 0)) < (e_try, int(m2 or 0))
            sh = s_try if ok else _apply_meridiem(sh, "am")
            eh = e_try
        else:
            if h1.lower() not in ("noon", "midnight"):
                sh = _apply_meridiem(sh, ap1) if ap1 else (sh if named or sh > 12 else _guess_pm(sh))
            if h2.lower() not in ("noon", "midnight"):
                eh = _apply_meridiem(eh, ap2) if ap2 else (eh if eh > 12 else _guess_pm(eh))
            if eh <= sh and eh < 12:
                eh += 12
        start, end = time(sh % 24, int(m1 or 0)), time(eh % 24, int(m2 or 0))
        return start, end, m.span()
    m = _SINGLE.search(text)
    if m:
        h_ap, m_ap, ap, h_colon, m_colon, named = m.groups()
        if named:
            h, mins = _hour(named), 0
        elif h_ap:
            h, mins = _apply_meridiem(int(h_ap), ap), int(m_ap or 0)
        else:
            h, mins = int(h_colon), int(m_colon)
            h = h if h > 12 else _guess_pm(h)
        if h > 23 or mins > 59:
            return None
        return time(h, mins), None, m.span()
    return None


def _year_for(month: int, day: int, base: date, year: Optional[str]) -> date:
    if year:
        y = int(year)
        return date(y + 2000 if y < 100 else y, month, day)
    d = date(base.year, month, day)
    return date(base.year + 1, month, day) if d < base - timedelta(days=60) else d


def _parse_date(text: str, base: date, notes: list):
    """Returns (date, [spans]). Explicit dates beat weekdays; weekdays beat today/tomorrow."""
    spans, explicit = [], None
    for rx, order in ((_MONTH_DAY, "md"), (_DAY_MONTH, "dm"), (_NUMERIC, "num")):
        m = rx.search(text)
        if not m:
            continue
        try:
            if order == "md":
                explicit = _year_for(_MONTHS[m.group(1).lower()], int(m.group(2)), base, m.group(3))
            elif order == "dm":
                explicit = _year_for(_MONTHS[m.group(2).lower()], int(m.group(1)), base, m.group(3))
            else:
                explicit = _year_for(int(m.group(1)), int(m.group(2)), base, m.group(3))
        except ValueError:
            notes.append(f"Couldn't read the date \"{m.group(0).strip()}\".")
            explicit = None
            continue
        spans.append(m.span())
        break

    wd_match = _WEEKDAY.search(text)
    weekday = None
    if wd_match:
        spans.append(wd_match.span())
        wd = _WEEKDAYS[wd_match.group(2).lower()]
        ahead = (wd - base.weekday()) % 7
        if (wd_match.group(1) or "").strip().lower() == "next":
            weekday = base - timedelta(days=base.weekday()) + timedelta(days=7 + wd)
        else:
            weekday = base + timedelta(days=ahead)

    rel = _RELATIVE.search(text)
    if rel:
        spans.append(rel.span())

    if explicit:
        if weekday and explicit.weekday() != weekday.weekday():
            notes.append(f"{explicit:%b} {explicit.day} is a {explicit:%A}, not a "
                         f"{weekday:%A}. Using {explicit:%A}, {explicit:%b} {explicit.day}.")
        return explicit, spans
    if weekday:
        return weekday, spans
    if rel:
        return base + timedelta(days=1 if rel.group(1).lower().startswith("t") and
                                rel.group(1).lower() not in ("today", "tonight") else 0), spans
    notes.append("No date mentioned, so I used today.")
    return base, spans


def _tidy_case(text: str) -> str:
    if any(c.isupper() for c in text):
        return text  # the user chose their own capitalization; keep it
    words = text.split()
    out = []
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if nxt[:1].isdigit() and w.isalpha() and len(w) <= 5:
            out.append(w.upper())  # course codes: "ie 322" -> "IE 322", "math 140" -> "MATH 140"
        elif w in _SMALL and i > 0:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def _clean(fragment: str) -> str:
    s = fragment.strip(" ,.;-")
    for _ in range(4):
        s = _EDGE_FILLER.sub("", s).strip(" ,.;-")
    return s


def parse_event(text: str, base: date) -> ParsedEvent:
    notes: list = []
    original = " ".join(text.strip().split())
    if not original:
        raise ValueError("Type what you want to add, e.g. \"Math quiz Tuesday 5-6pm in Wartik Lab\".")

    times = _parse_times(original)
    spans = [times[2]] if times else []
    # look for dates outside the time span so "5-6" isn't read as a date
    masked = original
    if times:
        a, b = times[2]
        masked = original[:a] + " " * (b - a) + original[b:]
    day, date_spans = _parse_date(masked, base, notes)
    spans += date_spans

    # Remove the date/time phrases; what's left is "<title> in <place>"
    chars = list(original)
    for a, b in spans:
        for i in range(a, b):
            chars[i] = "|"
    chunks = [c for c in "".join(chars).split("|") if c.strip()]
    title_parts, location = [], None
    for chunk in chunks:
        place = _PLACE.search(chunk)
        found = place and (place.group(1) or place.group(2))
        if found and location is None and _clean(found):
            location = _clean(found)
            if location.lower() in ("zoom", "teams", "facetime", "meet", "google meet"):
                location = {"zoom": "Zoom", "teams": "Teams", "facetime": "FaceTime"}.get(location.lower(), "Google Meet")
            chunk = chunk[:place.start()]
        cleaned = _clean(_LEAD_FILLER.sub("", chunk.strip()))
        if cleaned:
            title_parts.append(cleaned)
    title = _tidy_case(" ".join(title_parts)) or "New event"
    if location:
        location = _tidy_case(location)

    if times:
        start = datetime.combine(day, times[0])
        end = datetime.combine(day, times[1]) if times[1] else start + timedelta(hours=1)
        if end <= start:
            end += timedelta(days=1)
        return ParsedEvent(title, start, end, False, location, notes)
    start = datetime.combine(day, time.min)
    return ParsedEvent(title, start, start + timedelta(days=1), True, location, notes)
