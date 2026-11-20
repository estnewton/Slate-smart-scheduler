"""
Puts a realistic student week on your connected Google Calendar (and a starter task list in
Slate) so a live demo has something to show, and removes it all afterwards.

    python -m src.demo_calendar seed --date 2027-01-11 # demo week on the "IBM DEMO" calendar
    python -m src.demo_calendar seed --date 2027-01-11 --calendar primary   # ...or your main one
    python -m src.demo_calendar seed                  # ...or starting today
    python -m src.demo_calendar clear                 # remove it all and leave demo mode

While a demo week is seeded, Slate is in demo mode: it reads ONLY the demo events (nothing from
your real schedule) and treats the first demo day as "today".

Every event this creates is tagged privately (slate=demo), so `clear` only ever deletes those,
never your own events. `seed` runs `clear` first, so it is safe to re-run before each rehearsal.
Connect Google Calendar in the web app first (it writes token.json).
"""
import argparse
from datetime import date, datetime, time, timedelta

from . import store
from .integrations import google_calendar as gcal

TAG = "slate=demo"
DEFAULT_CALENDAR = "IBM DEMO"  # a separate Google calendar just for the demo (create it first)

# (day offset, start "HH:MM", end "HH:MM", title, location, Google color id)
# Color ids: 7 peacock (classes), 11 tomato (exams/quizzes), 2 sage (meetings),
#            6 tangerine (health), 3 grape (social/birthdays), 5 banana (other)
# Locations repeat on purpose ("West Campus", "Downtown", ...) so the planner can batch errands
# with the appointment or class that's already taking you there.
EVENTS = [
    # Monday
    (0, "09:05", "09:55", "IE 322: Probability Models", "West Campus", "7"),
    (0, "10:00", "10:30", "Office hours with Professor Lin", "West Campus", "2"),
    (0, "13:00", "13:50", "IE 304: Service Systems", "East Campus", "7"),
    (0, "14:30", "15:15", "Dr. Patel: annual physical", "University Health Services", "6"),
    (0, "16:30", "17:15", "Capstone team sync", "Library", "2"),
    (0, "19:00", "21:00", "Maya's birthday dinner", "Downtown", "3"),
    # Tuesday
    (1, "10:10", "11:00", "IE 302: Operations Research", "East Campus", "7"),
    (1, "12:00", "12:30", "Call Mom for her birthday", "Home", "3"),
    (1, "14:30", "15:15", "Mock interview with career services", "HUB", "2"),
    (1, "17:00", "18:00", "Math Quiz", "Wartik Lab", "11"),
    (1, "18:15", "19:15", "Intramural volleyball", "West Campus Gym", "5"),
    # Wednesday
    (2, "09:05", "09:55", "IE 322 Quiz", "West Campus", "11"),
    (2, "11:30", "12:00", "Dr. Kim: dermatology follow-up", "University Health Services", "6"),
    (2, "13:00", "13:50", "IE 304: Service Systems", "East Campus", "7"),
    (2, "16:30", "17:30", "AFE ambassador meeting", "HUB", "2"),
    # Thursday
    (3, "10:10", "11:00", "IE 302: Operations Research", "East Campus", "7"),
    (3, "15:00", "15:45", "Dentist: cleaning", "Downtown", "6"),
    (3, "17:00", "17:30", "1:1 with internship recruiter", "Zoom", "2"),
    (3, "18:00", "20:00", "IE 322 study group", "Library", "2"),
    # Friday
    (4, "09:05", "09:55", "IE 322: Probability Models", "West Campus", "7"),
    (4, "11:00", "12:30", "IE 302 Midterm", "East Campus", "11"),
    (4, "15:00", "17:00", "Hackathon kickoff", "HUB", "5"),
    (4, "19:00", "22:00", "Game night", "Jordan's apartment", "3"),
    # Weekend
    (5, "10:00", "12:00", "Volunteer shift: food bank", "Downtown", "5"),
    (6, "11:00", "12:00", "Brunch with roommates", "Downtown", "3"),
]
# All-day items: birthdays and due dates the way a Canvas calendar feed shows them
ALL_DAY = [
    (1, "Mom's birthday"),
    (3, "IE 304 case study due (Canvas)"),
]
# (day offset, due "HH:MM" or None, title, effort minutes, importance 0-1, location)
TASKS = [
    (0, "17:30", "Pick up birthday gift for Maya", 30, 0.7, "Downtown"),
    (0, "16:00", "Pick up prescription", 15, 0.6, "University Health Services"),
    (0, "12:00", "Grab coffee before IE 304", 15, 0.2, "East Campus"),
    (0, "20:00", "Email Professor Lin about research", 15, 0.7, "West Campus"),
    (1, "20:00", "Book flight home for spring break", 20, 0.8, "Home"),
    (3, "23:59", "Finish IE 304 case study", 120, 0.9, "Library"),
    (2, "17:00", "Draft AFE sponsorship email", 30, 0.6, "Home"),
    (2, "12:00", "Submit insurance form for physical", 10, 0.5, "Home"),
    (4, "18:00", "Buy snacks for game night", 30, 0.4, "Downtown"),
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


def _calendar_ids(service, extra: str | None = None) -> list[str]:
    """Primary + every calendar you own, so clear() finds demo events wherever they were put."""
    ids = ["primary"]
    for cal in service.calendarList().list().execute().get("items", []):
        if cal.get("accessRole") == "owner" and not cal.get("primary"):
            ids.append(cal["id"])
    if extra and extra not in ids:
        ids.append(extra)
    return ids


def clear() -> int:
    """Deletes every event tagged slate=demo or slate=plan on any of your calendars (from 60 days
    ago to ~13 months out), resets Slate's local tasks, and turns demo mode off. Untagged events,
    including anything you added by hand to the demo calendar, are left alone."""
    service = gcal._service(_creds())
    start = datetime.combine(date.today(), time.min) - timedelta(days=60)
    end = start + timedelta(days=460)
    deleted = 0
    for cal_id in _calendar_ids(service):
        for tag in (TAG, "slate=plan"):
            page = None
            while True:
                res = service.events().list(
                    calendarId=cal_id, timeMin=start.astimezone().isoformat(),
                    timeMax=end.astimezone().isoformat(), singleEvents=True,
                    privateExtendedProperty=tag, pageToken=page, maxResults=250,
                ).execute()
                for item in res.get("items", []):
                    service.events().delete(calendarId=cal_id, eventId=item["id"]).execute()
                    deleted += 1
                page = res.get("nextPageToken")
                if not page:
                    break
    store.reset()
    return deleted


def seed(start_day: date, calendar_name: str = DEFAULT_CALENDAR) -> tuple[int, str]:
    """Creates the demo week on the named calendar (or "primary"). Returns (count, calendar)."""
    creds = _creds()
    if calendar_name.strip().casefold() == "primary":
        cal_id, label = "primary", "your main calendar"
    else:
        cal_id = gcal.find_calendar(creds, calendar_name)
        if cal_id is None:
            raise SystemExit(f"No calendar named \"{calendar_name}\" that you own. Create it in Google "
                             "Calendar (Other calendars → + → Create new calendar) or pass --calendar primary.")
        label = f"\"{calendar_name.strip()}\""
    clear()
    service = gcal._service(creds)
    private = {"private": {"slate": "demo"}}
    created = 0
    for offset, s, e, title, loc, color in EVENTS:
        d = start_day + timedelta(days=offset)
        service.events().insert(calendarId=cal_id, body={
            "summary": title, "location": loc, "colorId": color,
            "start": {"dateTime": _at(d, s).astimezone().isoformat()},
            "end": {"dateTime": _at(d, e).astimezone().isoformat()},
            "reminders": {"useDefault": False}, "extendedProperties": private,
        }).execute()
        created += 1
    for offset, title in ALL_DAY:
        d = start_day + timedelta(days=offset)
        service.events().insert(calendarId=cal_id, body={
            "summary": title, "start": {"date": d.isoformat()},
            "end": {"date": (d + timedelta(days=1)).isoformat()},
            "transparency": "transparent", "extendedProperties": private,
        }).execute()
        created += 1
    soonest = max(datetime.now(), datetime.combine(start_day, time(8, 0))) + timedelta(hours=2)
    for offset, due, title, effort, importance, loc in TASKS:
        due_dt = _at(start_day + timedelta(days=offset), due) if due else None
        if due_dt and start_day <= date.today() and due_dt < soonest:  # seeding mid-day: no overdue tasks
            due_dt = soonest.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        store.add_task(title, due_dt, effort, importance, loc)
    # demo mode on: Slate shows only this calendar's demo week, starting from this day
    store.set_demo_start(start_day, cal_id)
    return created, label


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_seed = sub.add_parser("seed", help="create the demo week (clears any previous one first)")
    p_seed.add_argument("--date", type=date.fromisoformat, default=date.today(),
                        help="first day of the demo week, YYYY-MM-DD (default: today)")
    p_seed.add_argument("--calendar", default=DEFAULT_CALENDAR,
                        help=f'calendar to put it on (default: "{DEFAULT_CALENDAR}"; use "primary" for your main one)')
    sub.add_parser("clear", help="remove demo events, Slate plan blocks and Slate's local tasks")
    args = parser.parse_args()

    if args.cmd == "seed":
        n, label = seed(args.date, args.calendar)
        print(f"Added {n} demo events to {label} starting {args.date:%a %b %d}, and {len(TASKS)} tasks. "
              "Refresh the web app.")
    else:
        print(f"Removed {clear()} Slate events, reset Slate's local tasks, and left demo mode.")


if __name__ == "__main__":
    main()
