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
# Color ids: 7 peacock (classes), 11 tomato (exams/quizzes), 2 sage (meetings), 5 banana (other)
EVENTS = [
    (0, "09:05", "09:55", "IE 322: Probability Models", "West Campus", "7"),
    (0, "10:00", "10:30", "Office hours with Professor Lin", "West Campus", "2"),
    (0, "13:00", "13:50", "IE 304: Service Systems", "East Campus", "7"),
    (0, "16:30", "17:30", "AFE ambassador meeting", "HUB", "2"),
    (1, "10:10", "11:00", "IE 302: Operations Research", "East Campus", "7"),
    (1, "14:30", "15:15", "Mock interview with career services", "HUB", "2"),
    (2, "09:05", "09:55", "IE 322 Quiz", "West Campus", "11"),
    (2, "13:00", "13:50", "IE 304: Service Systems", "East Campus", "7"),
    (3, "10:10", "11:00", "IE 302: Operations Research", "East Campus", "7"),
    (4, "09:05", "09:55", "IE 322: Probability Models", "West Campus", "7"),
    (4, "18:00", "20:00", "Hackathon kickoff", "HUB", "5"),
    (6, "11:00", "12:30", "IE 302 Midterm", "East Campus", "11"),
]
# All-day items, the way a Canvas calendar feed shows assignment due dates
ALL_DAY = [
    (3, "IE 304 case study due (Canvas)"),
]
# (day offset, due "HH:MM" or None, title, effort minutes, importance 0-1, location)
TASKS = [
    (0, "12:00", "Grab coffee before IE 304", 15, 0.2, "East Campus"),
    (0, "18:00", "Gym", 45, 0.4, "West Campus"),
    (0, "20:00", "Email Professor Lin about research", 15, 0.7, "West Campus"),
    (2, "17:00", "Draft AFE sponsorship email", 30, 0.6, "Home"),
    (3, "23:59", "Finish IE 304 case study", 120, 0.9, "Library"),
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
