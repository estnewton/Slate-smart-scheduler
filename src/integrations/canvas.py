"""
Canvas LMS sync (OPTIONAL / ADVANCED).

Before using this module, consider the simpler route: Canvas → Calendar → "Calendar Feed"
(bottom right) gives you a private .ics URL. Subscribe to it directly in Google Calendar
(Google Calendar → Other calendars → + → From URL) and your Canvas due dates show up there
automatically — no code needed, and google_calendar.py already covers it. Use *this* module
only if you need something the calendar feed doesn't expose (e.g. assignment descriptions).

SETUP:
  1. In Canvas: Account -> Settings -> "+ New Access Token". Copy it once (Canvas won't show it again).
  2. Set two environment variables (don't hardcode these in the file):
       export CANVAS_BASE_URL="https://psu.instructure.com"   # your school's Canvas domain
       export CANVAS_TOKEN="<your token>"
  3. pip install requests
"""
import os
from datetime import datetime
from typing import List

import requests

from ..models import CalendarEvent, TaskSource


def _headers():
    token = os.environ.get("CANVAS_TOKEN")
    if not token:
        raise EnvironmentError("Set the CANVAS_TOKEN environment variable first (see module docstring).")
    return {"Authorization": f"Bearer {token}"}


def _base_url():
    base = os.environ.get("CANVAS_BASE_URL")
    if not base:
        raise EnvironmentError("Set the CANVAS_BASE_URL environment variable first (see module docstring).")
    return base.rstrip("/")


def fetch_upcoming_assignments(per_course_limit: int = 20) -> List[CalendarEvent]:
    """Fetches active courses, then upcoming assignments (which include quizzes/exams set up
    as Canvas assignments) for each. Skips assignments with no due date."""
    courses_resp = requests.get(
        f"{_base_url()}/api/v1/courses",
        params={"enrollment_state": "active", "per_page": 50},
        headers=_headers(),
    )
    courses_resp.raise_for_status()
    courses = courses_resp.json()

    events = []
    for course in courses:
        course_id = course.get("id")
        course_name = course.get("name", f"Course {course_id}")
        resp = requests.get(
            f"{_base_url()}/api/v1/courses/{course_id}/assignments",
            params={"order_by": "due_at", "per_page": per_course_limit},
            headers=_headers(),
        )
        if resp.status_code != 200:
            continue
        for a in resp.json():
            due_at = a.get("due_at")
            if not due_at:
                continue
            due_dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
            events.append(CalendarEvent(
                id=f"canvas-{a['id']}",
                title=f"{a.get('name', 'Assignment')} ({course_name})",
                start=due_dt, end=due_dt,
                location=course_name,  # used as a grouping tag, e.g. "study for X" clusters by course
                description=a.get("description"),
                source=TaskSource.CANVAS,
            ))
    return events


if __name__ == "__main__":
    for e in fetch_upcoming_assignments():
        print(e.start, "-", e.title)
