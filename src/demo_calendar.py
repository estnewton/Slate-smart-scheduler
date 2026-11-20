"""
Puts a realistic student week on your connected Google Calendar (and a starter task list in
Slate) so a live demo has something to show, and removes it all afterwards.

    python -m src.demo_calendar seed                  # demo week starting today
    python -m src.demo_calendar seed --date 2026-12-03 # demo week starting on a given day
    python -m src.demo_calendar clear                 # remove demo events + Slate plan blocks

Every event this creates is tagged privately (slate=demo), so `clear` only ever deletes those,
never your own events. `seed` runs `clear` first, so it is safe to re-run before each rehearsal.
Connect Google Calendar in the web app first (it writes token.json).
"""
import argparse
from datetime import date, datetime, time, timedelta

from . import store
from .integrations import google_calendar as gcal

TAG = "slate=demo"

# (day offset, start "HH:MM", end "HH:MM", title, location, Google color id)
# Color ids: 7 peacock (classes), 11 tomato (exams/quizzes), 2 sage (meetings),
#            6 tangerine (health), 3 grape (social/birthdays), 5 banana (other)
# Locations repeat on purpose ("West Campus", "Downtown", ...) so the planner can batch errands
# with the appointment or class that's already taking you there.
EVENTS = [
    # Day 0
    (0, "09:05", "09:55", "IE 322: Probability Models", "West Campus", "7"),
    (0, "10:00", "10:30", "Office hours with Professor Lin", "West Campus", "2"),
    (0, "13:00", "13:50", "IE 304: Service Systems", "East Campus", "7"),
    (0, "14:30", "15:15", "Dr. Patel: annual physical", "University Health Services", "6"),
    (0, "16:30", "17:15", "Capstone team sync", "Library", "2"),
    (0, "19:00", "21:00", "Maya's birthday dinner", "Downtown", "3"),
    # Day 1
    (1, "10:00", "12:00", "Volunteer shift: food bank", "Downtown", "5"),
    (1, "12:30", "13:00", "Call Mom for her birthday", "Home", "3"),
    (1, "15:00", "17:00", "Hackathon kickoff", "HUB", "5"),
    # Day 2
    (2, "11:00", "12:00", "Brunch with roommates", "Downtown", "3"),
    (2, "18:00", "20:00", "IE 322 study group", "Library", "2"),
    # Day 3
    (3, "09:05", "09:55", "IE 322 Quiz", "West Campus", "11"),
    (3, "11:30", "12:00", "Dr. Kim: dermatology follow-up", "University Health Services", "6"),
    (3, "13:00", "13:50", "IE 304: Service Systems", "East Campus", "7"),
    (3, "16:30", "17:30", "AFE ambassador meeting", "HUB", "2"),
    # Day 4
    (4, "10:10", "11:00", "IE 302: Operations Research", "East Campus", "7"),
    (4, "14:30", "15:15", "Mock interview with career services", "HUB", "2"),
    (4, "18:00", "19:00", "Intramural volleyball", "West Campus Gym", "5"),
    # Day 5
    (5, "09:05", "09:55", "IE 322: Probability Models", "West Campus", "7"),
    (5, "11:00", "12:30", "IE 302 Midterm", "East Campus", "11"),
    (5, "15:00", "15:45", "Dentist: cleaning", "Downtown", "6"),
    (5, "17:00", "17:30", "1:1 with internship recruiter", "Zoom", "2"),
    # Day 6
    (6, "15:00", "19:00", "Friendsgiving dinner", "Jordan's apartment", "3"),
]
# All-day items: birthdays, holidays, and due dates the way a Canvas calendar feed shows them
ALL_DAY = [
    (1, "Mom's birthday"),
    (2, "IE 304 case study due (Canvas)"),
    (6, "Thanksgiving break: no classes"),
]
# (day offset, due "HH:MM" or None, title, effort minutes, importance 0-1, location)
TASKS = [
    (0, "17:30", "Pick up birthday gift for Maya", 30, 0.7, "Downtown"),
    (0, "16:00", "Pick up prescription", 15, 0.6, "University Health Services"),
    (0, "12:00", "Grab coffee before IE 304", 15, 0.2, "East Campus"),
    (0, "20:00", "Email Professor Lin about research", 15, 0.7, "West Campus"),
    (1, "20:00", "Book train home for Thanksgiving", 20, 0.8, "Home"),
    (2, "23:59", "Finish IE 304 case study", 120, 0.9, "Library"),
    (3, "17:00", "Draft AFE sponsorship email", 30, 0.6, "Home"),
    (4, "12:00", "Submit insurance form for physical", 10, 0.5, "Home"),
    (5, "13:00", "Bring dish for Friendsgiving: buy groceries", 40, 0.5, "Downtown"),
    (None, None, "Update resume with hackathon project", 45, 0.5, "Home"),
]


def _creds():
    creds = gcal.load_credentials()
    if creds is None:
        raise SystemExit("Not connected. Start the web app and click 'Connect Google Calendar' first.")
    return creds


def _at(day: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(day, time(h, m))


def clear(window_start: date | None = None) -> int:
    """Deletes events tagged slate=demo or slate=plan in a window around the given day."""
    service = gcal._service(_creds())
    start = datetime.combine(window_start or date.today(), time.min) - timedelta(days=30)
    end = start + timedelta(days=90)
    deleted = 0
    for tag in (TAG, "slate=plan"):
        page = None
        while True:
            res = service.events().list(
                calendarId="primary", timeMin=start.astimezone().isoformat(),
                timeMax=end.astimezone().isoformat(), singleEvents=True,
                privateExtendedProperty=tag, pageToken=page, maxResults=250,
            ).execute()
            for item in res.get("items", []):
                service.events().delete(calendarId="primary", eventId=item["id"]).execute()
                deleted += 1
            page = res.get("nextPageToken")
            if not page:
                break
    store.reset()
    return deleted


def seed(start_day: date) -> int:
    clear(start_day)
    service = gcal._service(_creds())
    private = {"private": {"slate": "demo"}}
    created = 0
    for offset, s, e, title, loc, color in EVENTS:
        d = start_day + timedelta(days=offset)
        service.events().insert(calendarId="primary", body={
            "summary": title, "location": loc, "colorId": color,
            "start": {"dateTime": _at(d, s).astimezone().isoformat()},
            "end": {"dateTime": _at(d, e).astimezone().isoformat()},
            "reminders": {"useDefault": False}, "extendedProperties": private,
        }).execute()
        created += 1
    for offset, title in ALL_DAY:
        d = start_day + timedelta(days=offset)
        service.events().insert(calendarId="primary", body={
            "summary": title, "start": {"date": d.isoformat()},
            "end": {"date": (d + timedelta(days=1)).isoformat()},
            "transparency": "transparent", "extendedProperties": private,
        }).execute()
        created += 1
    soonest = datetime.now() + timedelta(hours=2)
    for offset, due, title, effort, importance, loc in TASKS:
        due_dt = _at(start_day + timedelta(days=offset), due) if due else None
        if due_dt and due_dt < soonest:  # seeding mid-day: don't start the demo with overdue tasks
            due_dt = soonest.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        store.add_task(title, due_dt, effort, importance, loc)
    return created


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_seed = sub.add_parser("seed", help="create the demo week (clears any previous one first)")
    p_seed.add_argument("--date", type=date.fromisoformat, default=date.today(),
                        help="first day of the demo week, YYYY-MM-DD (default: today)")
    sub.add_parser("clear", help="remove demo events, Slate plan blocks and Slate's local tasks")
    args = parser.parse_args()

    if args.cmd == "seed":
        n = seed(args.date)
        print(f"Added {n} demo events starting {args.date:%a %b %d} and {len(TASKS)} tasks. "
              "Refresh the web app.")
    else:
        print(f"Removed {clear()} Slate events and reset Slate's local tasks.")


if __name__ == "__main__":
    main()
