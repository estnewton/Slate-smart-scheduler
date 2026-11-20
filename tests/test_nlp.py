from datetime import date, datetime
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.nlp import parse_event

BASE = date(2027, 1, 11)  # a Monday


def test_the_demo_sentence():
    e = parse_event("math quiz on tuesday 5-6pm in wartik lab", BASE)
    assert (e.title, e.location) == ("Math Quiz", "Wartik Lab")
    assert e.start == datetime(2027, 1, 12, 17, 0) and e.end == datetime(2027, 1, 12, 18, 0)
    assert not e.all_day and e.notes == []


def test_explicit_date_wins_and_mismatch_is_explained():
    e = parse_event("math quiz on tuesday nov 20th 5-6pm in wartik lab", date(2026, 11, 19))
    assert e.start == datetime(2026, 11, 20, 17, 0)
    assert "Friday" in e.notes[0]


def test_course_code_single_time_and_default_hour():
    e = parse_event("add ie 322 study session tomorrow at 3pm @ library", BASE)
    assert e.title == "IE 322 Study Session" and e.location == "Library"
    assert e.start == datetime(2027, 1, 12, 15, 0) and e.end == datetime(2027, 1, 12, 16, 0)


def test_meridiem_carries_backwards_and_noon():
    e = parse_event("Lunch with Dr. Lee 11-1pm Friday at The Corner Room", BASE)
    assert e.title == "Lunch with Dr. Lee" and e.location == "Corner Room"
    assert (e.start.hour, e.end.hour) == (11, 13)
    e = parse_event("career fair 10:30 to noon wed", BASE)
    assert (e.start.hour, e.start.minute, e.end.hour) == (10, 30, 12)


def test_numeric_date_and_all_day():
    e = parse_event("Mom's birthday 1/20", BASE)
    assert e.all_day and e.start == datetime(2027, 1, 20) and e.title == "Mom's birthday"


def test_next_weekday_is_in_the_following_week():
    e = parse_event("dentist next thursday 9am", BASE)
    assert e.start == datetime(2027, 1, 21, 9, 0)


def test_video_call_location():
    e = parse_event("Coffee chat with IBM recruiter thursday 2:30-3pm on zoom", BASE)
    assert e.title == "Coffee chat with IBM recruiter" and e.location == "Zoom"
    assert (e.start.hour, e.start.minute, e.end.hour) == (14, 30, 15)
