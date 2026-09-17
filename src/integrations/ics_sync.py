"""
.ics import/export -- this is how Apple Calendar (and Outlook, and anything else) gets
covered without needing Apple's clunky CalDAV setup.

Import:  Apple Calendar -> File -> Export -> point this module at the exported .ics file.
Export:  This module can also write an .ics file of your generated plan, which you then
         drag into Apple Calendar / Outlook / Google Calendar to import back in.

pip install icalendar
"""
from datetime import datetime
from pathlib import Path
from typing import List

from icalendar import Calendar, Event as ICSEvent

from ..models import CalendarEvent, TaskSource


def import_ics(path: str) -> List[CalendarEvent]:
    cal = Calendar.from_ical(Path(path).read_bytes())
    events = []
    for component in cal.walk("VEVENT"):
        start = component.get("dtstart").dt
        end = component.get("dtend").dt if component.get("dtend") else start
        events.append(CalendarEvent(
            id=str(component.get("uid")),
            title=str(component.get("summary", "(untitled event)")),
            start=start if isinstance(start, datetime) else datetime.combine(start, datetime.min.time()),
            end=end if isinstance(end, datetime) else datetime.combine(end, datetime.min.time()),
            location=str(component.get("location")) if component.get("location") else None,
            description=str(component.get("description")) if component.get("description") else None,
            source=TaskSource.MANUAL,
        ))
    return events


def export_plan_to_ics(plan_items: list[dict], out_path: str) -> None:
    """plan_items: the list of dicts returned by scheduler.build_daily_plan()."""
    cal = Calendar()
    cal.add("prodid", "-//Smart Scheduler//github.com//")
    cal.add("version", "2.0")

    for item in plan_items:
        ev = ICSEvent()
        ev.add("summary", item["title"])
        ev.add("dtstart", item["start"])
        ev.add("dtend", item["end"])
        if item.get("location"):
            ev.add("location", item["location"])
        cal.add_component(ev)

    Path(out_path).write_bytes(cal.to_ical())
