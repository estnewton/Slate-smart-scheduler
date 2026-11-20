"""
Google Calendar sync.

SETUP (one-time, on your own Google account -- there's no way around needing your own
credentials for a personal project that touches your calendar):
  1. console.cloud.google.com -> create a project -> enable the "Google Calendar API".
  2. "OAuth consent screen": External, add yourself as a Test user.
  3. Credentials -> Create OAuth client ID -> type "Web application", with
     Authorized redirect URI:  http://localhost:8000/auth/callback
     Download the JSON and save it as credentials.json in the project root
     (already in .gitignore -- NEVER commit it).
  4. Start the web app (`uvicorn src.server:app --reload`) and click "Connect Google Calendar".
     The token is cached in token.json so you only log in once.

Scopes: read your events, and create/delete the plan blocks Slate adds when you click
"Add plan to Google Calendar". Slate only ever deletes events it created itself (tagged with a
private extended property), never your own events.
"""
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import List, Optional

from ..models import CalendarEvent, TaskSource

# Google's callback comes back over plain http on localhost; oauthlib refuses that by default.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
# Google may return the granted scopes in a different order / with extras -- don't treat as an error.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
ROOT = Path(__file__).resolve().parents[2]
TOKEN_PATH = ROOT / "token.json"
CREDENTIALS_PATH = ROOT / "credentials.json"
SLATE_TAG = {"slate": "plan"}  # private extendedProperty marking events Slate created
DEMO_TAG = "slate=demo"         # events created by `python -m src.demo_calendar seed`

# state -> Flow, kept between /auth/login and /auth/callback (holds the PKCE code verifier)
_pending_flows: dict = {}


# ---------------- credentials ----------------

def has_client_secrets() -> bool:
    return CREDENTIALS_PATH.exists()


def load_credentials():
    """Returns valid cached credentials, refreshing if needed, or None if not connected."""
    if not TOKEN_PATH.exists():
        return None
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            TOKEN_PATH.unlink(missing_ok=True)  # revoked or expired -- make the user reconnect
            return None
        TOKEN_PATH.write_text(creds.to_json())
        return creds
    return None


def start_web_flow(redirect_uri: str) -> str:
    """Returns the Google consent-screen URL to send the browser to."""
    from google_auth_oauthlib.flow import Flow

    if not has_client_secrets():
        raise FileNotFoundError("credentials.json not found -- see the setup steps at the top of this file.")
    flow = Flow.from_client_secrets_file(str(CREDENTIALS_PATH), scopes=SCOPES, redirect_uri=redirect_uri)
    auth_url, state = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true",
    )
    _pending_flows[state] = flow
    return auth_url


def finish_web_flow(state: str, authorization_response: str) -> None:
    flow = _pending_flows.pop(state, None)
    if flow is None:
        raise ValueError("Unknown or expired login attempt -- please try connecting again.")
    flow.fetch_token(authorization_response=authorization_response)
    TOKEN_PATH.write_text(flow.credentials.to_json())


def disconnect() -> None:
    """Revokes the token with Google (best effort) and forgets it locally."""
    creds = load_credentials()
    if creds is not None:
        try:
            import requests
            requests.post("https://oauth2.googleapis.com/revoke",
                          params={"token": creds.token}, timeout=5)
        except Exception:
            pass
    TOKEN_PATH.unlink(missing_ok=True)


def _service(creds):
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# ---------------- reading ----------------

def _to_local_naive(raw: str) -> datetime:
    """Google returns RFC3339 with an offset; the scheduler works in naive local time."""
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def find_calendar(creds, name: str) -> Optional[str]:
    """Calendar id for a calendar you own or can edit, matched by name (case/space-insensitive)."""
    want = " ".join(name.split()).casefold()
    for cal in _service(creds).calendarList().list().execute().get("items", []):
        if " ".join(cal.get("summary", "").split()).casefold() == want and \
                cal.get("accessRole") in ("owner", "writer"):
            return cal["id"]
    return None


def fetch_events(creds, start: datetime, end: datetime, only_tag: Optional[str] = None,
                 calendar_id: str = "primary") -> List[CalendarEvent]:
    """All events on one calendar between two naive local datetimes.
    only_tag="slate=demo" limits it to events carrying that private tag."""
    service = _service(creds)
    time_min = start.astimezone().isoformat()
    time_max = end.astimezone().isoformat()

    events: List[CalendarEvent] = []
    page_token: Optional[str] = None
    while True:
        result = service.events().list(
            calendarId=calendar_id, timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy="startTime", maxResults=250, pageToken=page_token,
            **({"privateExtendedProperty": only_tag} if only_tag else {}),
        ).execute()
        for item in result.get("items", []):
            if item.get("status") == "cancelled":
                continue
            if item.get("extendedProperties", {}).get("private", {}).get("slate") == "plan":
                continue  # our own plan blocks -- don't feed them back in as fixed events
            all_day = "date" in item["start"]
            if all_day:
                s = datetime.combine(date.fromisoformat(item["start"]["date"]), time.min)
                e = datetime.combine(date.fromisoformat(item["end"]["date"]), time.min)
            else:
                s = _to_local_naive(item["start"]["dateTime"])
                e = _to_local_naive(item["end"]["dateTime"])
            events.append(CalendarEvent(
                id=item["id"],
                title=item.get("summary", "(untitled event)"),
                start=s, end=e,
                location=item.get("location"),
                description=item.get("description"),
                source=TaskSource.GOOGLE_CALENDAR,
                all_day=all_day,
            ))
        page_token = result.get("nextPageToken")
        if not page_token:
            return events


# ---------------- writing ----------------

def create_event(creds, title: str, start: datetime, end: datetime, all_day: bool = False,
                 location: Optional[str] = None, tag: Optional[dict] = None,
                 calendar_id: str = "primary") -> dict:
    """Adds one event to a calendar. Returns Google's event resource."""
    body = {"summary": title, "description": "Added from Slate"}
    if all_day:
        body["start"] = {"date": start.date().isoformat()}
        body["end"] = {"date": end.date().isoformat()}
    else:
        body["start"] = {"dateTime": start.astimezone().isoformat()}
        body["end"] = {"dateTime": end.astimezone().isoformat()}
    if location:
        body["location"] = location
    if tag:
        body["extendedProperties"] = {"private": tag}
    return _service(creds).events().insert(calendarId=calendar_id, body=body).execute()


def push_plan(creds, plan_items: list[dict], day: date, calendar_id: str = "primary") -> int:
    """Writes the task blocks of a day plan to Google Calendar. Re-running replaces the
    blocks Slate added for that day earlier, so you never get duplicates."""
    service = _service(creds)
    day_start = datetime.combine(day, time.min)
    day_end = day_start + timedelta(days=1)

    existing = service.events().list(
        calendarId=calendar_id, timeMin=day_start.astimezone().isoformat(),
        timeMax=day_end.astimezone().isoformat(), singleEvents=True,
        privateExtendedProperty="slate=plan",
    ).execute()
    for item in existing.get("items", []):
        service.events().delete(calendarId=calendar_id, eventId=item["id"]).execute()

    created = 0
    for item in plan_items:
        if item["kind"] != "task":
            continue
        body = {
            "summary": item["title"],
            "start": {"dateTime": item["start"].astimezone().isoformat()},
            "end": {"dateTime": item["end"].astimezone().isoformat()},
            "description": "Scheduled by Slate",
            "colorId": "8",  # graphite
            "extendedProperties": {"private": SLATE_TAG},
        }
        if item.get("location"):
            body["location"] = item["location"]
        service.events().insert(calendarId=calendar_id, body=body).execute()
        created += 1
    return created


# ---------------- CLI (original desktop flow, still works) ----------------

def _get_credentials():
    """Interactive desktop login for command-line use."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = load_credentials()
    if creds:
        return creds
    if not has_client_secrets():
        raise FileNotFoundError("credentials.json not found. See the setup instructions at the top of this file.")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    return creds


def fetch_upcoming_events(days_ahead: int = 7) -> List[CalendarEvent]:
    """Pulls events from the primary calendar from the start of today through `days_ahead` days."""
    today = datetime.combine(date.today(), time.min)
    return fetch_events(_get_credentials(), today, today + timedelta(days=days_ahead))


if __name__ == "__main__":
    for e in fetch_upcoming_events():
        print(e.start, "-", e.title, "@", e.location)
