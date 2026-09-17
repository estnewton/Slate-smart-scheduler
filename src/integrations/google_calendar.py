"""
Google Calendar sync.

SETUP (one-time, on your own Google account -- this is standard for any personal project
that touches your calendar, there's no way around needing your own credentials):
  1. Go to console.cloud.google.com -> create a project -> enable the "Google Calendar API".
  2. Create an OAuth Client ID (type: Desktop app) -> download it as credentials.json,
     put it in this project's root (it's already in .gitignore -- NEVER commit this file).
  3. pip install google-auth-oauthlib google-api-python-client
  4. Run this file directly once (`python -m src.integrations.google_calendar`) to do the
     one-time browser login; it caches a token.json locally so you won't have to log in again.

This module only requests read-only scope -- it can see your events, not edit them.
"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from ..models import CalendarEvent, TaskSource

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TOKEN_PATH = Path("token.json")
CREDENTIALS_PATH = Path("credentials.json")


def _get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    "credentials.json not found. See the setup instructions at the top of this file."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
    return creds


def fetch_upcoming_events(days_ahead: int = 7) -> List[CalendarEvent]:
    """Pulls events from the user's primary calendar for the next `days_ahead` days."""
    from googleapiclient.discovery import build

    creds = _get_credentials()
    service = build("calendar", "v3", credentials=creds)

    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

    result = service.events().list(
        calendarId="primary", timeMin=time_min, timeMax=time_max,
        singleEvents=True, orderBy="startTime",
    ).execute()

    events = []
    for item in result.get("items", []):
        start_raw = item["start"].get("dateTime", item["start"].get("date"))
        end_raw = item["end"].get("dateTime", item["end"].get("date"))
        events.append(CalendarEvent(
            id=item["id"],
            title=item.get("summary", "(untitled event)"),
            start=datetime.fromisoformat(start_raw.replace("Z", "+00:00")),
            end=datetime.fromisoformat(end_raw.replace("Z", "+00:00")),
            location=item.get("location"),
            description=item.get("description"),
            source=TaskSource.GOOGLE_CALENDAR,
        ))
    return events


if __name__ == "__main__":
    # One-time interactive login + smoke test
    for e in fetch_upcoming_events():
        print(e.start, "-", e.title, "@", e.location)
