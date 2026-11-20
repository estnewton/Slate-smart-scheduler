"""
Slate web app: a FastAPI backend over the scoring/scheduling engine, plus the web UI in web/.

    uvicorn src.server:app --reload        ->  http://localhost:8000

Works with zero setup on demo data. Drop a credentials.json in the project root (see
src/integrations/google_calendar.py) and a "Connect Google Calendar" button appears.
"""
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import store
from .demo import mock_week
from .nlp import parse_event
from .integrations import google_calendar as gcal
from .models import Task, TaskSource
from .scheduler import auto_generate_prep_tasks, build_daily_plan
from .scoring import rank_tasks, urgency

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
LOOKAHEAD_DAYS = 14  # how far ahead to read the calendar (exam prep starts a week out)
DEMO_CLOCK = time(8, 0)  # demo mode: "now" is 8:00 AM on the first demo day

app = FastAPI(title="Slate")


@app.middleware("http")
async def no_stale_ui(request: Request, call_next):
    """Always revalidate the UI files, so a browser never runs an old app.js after an update."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---------------- helpers ----------------

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat(timespec="minutes") if dt else None


def _task_json(task: Task, score: Optional[float] = None, now: Optional[datetime] = None) -> dict:
    out = {
        "id": task.id, "title": task.title, "due": _iso(task.due),
        "effort_minutes": task.effort_minutes, "importance": task.importance,
        "location": task.location, "source": task.source.value, "tags": task.tags,
        "score": round(score, 3) if score is not None else None,
    }
    if score is not None and now is not None:
        # the pieces of the RICE-style formula, so the UI can explain *why* a task ranks where it does
        out["breakdown"] = {
            "urgency": round(urgency(task, now), 3), "importance": task.importance,
            "confidence": task.confidence, "effort_hours": round(max(task.effort_minutes / 60, 0.05), 2),
        }
    return out


def _round_up(dt: datetime, minutes: int = 15) -> datetime:
    extra = -dt.minute % minutes
    return dt + timedelta(minutes=extra)


def _event_to_task(e) -> Task:
    return Task(id=e.id, title=e.title, due=None, fixed_time=e.start, end_time=e.end,
                effort_minutes=0, importance=0, location=e.location,
                source=TaskSource.GOOGLE_CALENDAR, tags=["all-day"] if e.all_day else [])


def _demo_active() -> bool:
    return store.demo_start() is not None and gcal.load_credentials() is not None


def _clock() -> tuple[date, datetime]:
    """Slate's idea of "today" and "now". In demo mode the clock is pinned to 8:00 AM on the
    first day of the seeded demo week, so the demo looks the same whenever it's given."""
    if _demo_active():
        return store.demo_start(), datetime.combine(store.demo_start(), DEMO_CLOCK)
    real_now = datetime.now().replace(second=0, microsecond=0)
    return real_now.date(), real_now


def _load_tasks(today: datetime) -> tuple[list[Task], str]:
    """Fixed + flexible tasks from Google Calendar if connected, otherwise built-in sample data.
    In demo mode only the seeded demo events are read -- nothing from the real schedule."""
    creds = gcal.load_credentials()
    if creds is None:
        tasks, source = mock_week(today), "sample"
    else:
        demo = _demo_active()
        try:
            events = gcal.fetch_events(creds, today - timedelta(days=1),
                                       today + timedelta(days=LOOKAHEAD_DAYS),
                                       calendar_id=store.demo_calendar() if demo else "primary",
                                       # a dedicated demo calendar is shown whole (so events you add
                                       # there in Google Calendar appear too); on the main calendar,
                                       # only the tagged demo events
                                       only_tag=gcal.DEMO_TAG if demo and store.demo_calendar() == "primary" else None)
        except Exception as exc:  # network / revoked access -- surface it rather than 500 silently
            raise HTTPException(502, f"Couldn't reach Google Calendar: {exc}") from exc
        tasks, source = [_event_to_task(e) for e in events], "demo" if demo else "google"
    return tasks + store.manual_tasks(), source


def _compute(day: date, start_hour: int, end_hour: int) -> dict:
    today_date, now = _clock()
    today = datetime.combine(today_date, time.min)
    day_dt = datetime.combine(day, time.min)

    tasks, source = _load_tasks(today)
    done = store.done_ids()

    fixed = [t for t in tasks if t.fixed_time is not None]
    timed_fixed = [t for t in fixed if "all-day" not in t.tags]
    generated = [g for g in auto_generate_prep_tasks(fixed, now=now) if g.id not in done]
    flexible = [t for t in tasks if t.fixed_time is None and t.id not in done]

    ranked = rank_tasks(flexible + generated, now=now)
    plannable = flexible + generated
    if day > today_date:
        # Looking ahead: anything due before that day is assumed handled by then.
        plannable = [t for t in plannable if t.due is None or t.due >= day_dt]
    plan = build_daily_plan(
        fixed_events=timed_fixed, flexible_tasks=plannable,
        day_start=day_dt.replace(hour=start_hour), day_end=day_dt.replace(hour=end_hour),
        now=now, earliest=_round_up(now) if day == today_date else None,
    )

    def on_day(t: Task, d: datetime) -> bool:
        return d <= t.fixed_time < d + timedelta(days=1)

    week = []
    for i in range(7):
        d = today + timedelta(days=i)
        items = sorted((t for t in fixed if on_day(t, d)), key=lambda t: t.fixed_time)
        week.append({"date": d.date().isoformat(),
                     "events": [{"title": t.title, "start": _iso(t.fixed_time),
                                 "all_day": "all-day" in t.tags} for t in items]})

    return {
        "source": source,
        "today": today_date.isoformat(),
        "date": day.isoformat(),
        "now": _iso(now),
        "hours": [start_hour, end_hour],
        "all_day": [t.title for t in fixed if "all-day" in t.tags and on_day(t, day_dt)],
        "plan": [{**p, "start": _iso(p["start"]), "end": _iso(p["end"])} for p in plan],
        "ranked": [_task_json(t, s, now) for t, s in ranked],
        "generated": [_task_json(g) for g in sorted(generated, key=lambda g: g.due)],
        "done": [_task_json(t) for t in tasks + generated if t.id in done and t.fixed_time is None],
        "week": week,
    }


def _parse_day(value: Optional[str]) -> date:
    if not value:
        return _clock()[0]
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(400, "date must be YYYY-MM-DD") from exc


# ---------------- API ----------------

@app.get("/api/status")
def status():
    today, now = _clock()
    return {"has_credentials": gcal.has_client_secrets(),
            "connected": gcal.load_credentials() is not None,
            "demo": _demo_active(), "today": today.isoformat(), "now": _iso(now)}


# ---------------- chat: sentence -> calendar event ----------------

class ChatText(BaseModel):
    text: str = Field(min_length=1, max_length=300)


def _event_json(e) -> dict:
    return {"title": e.title, "start": _iso(e.start), "end": _iso(e.end), "all_day": e.all_day,
            "location": e.location, "notes": e.notes}


@app.post("/api/chat/parse")
def chat_parse(body: ChatText):
    """Shows what Slate understood, before anything is written to the calendar."""
    try:
        return _event_json(parse_event(body.text, _clock()[0]))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class NewEvent(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start: datetime
    end: datetime
    all_day: bool = False
    location: Optional[str] = Field(default=None, max_length=200)


@app.post("/api/events", status_code=201)
def create_event(body: NewEvent):
    creds = gcal.load_credentials()
    if creds is None:
        raise HTTPException(401, "Connect Google Calendar first.")
    start, end = body.start.replace(tzinfo=None), body.end.replace(tzinfo=None)
    if end <= start:
        raise HTTPException(400, "The event has to end after it starts.")
    # In demo mode, tag it like the other demo events so it shows in the demo and
    # `demo_calendar clear` removes it afterwards. Otherwise it's a normal, permanent event.
    tag = {"slate": "demo"} if _demo_active() else None
    try:
        ev = gcal.create_event(creds, body.title.strip(), start, end, body.all_day,
                               (body.location or "").strip() or None, tag,
                               calendar_id=store.demo_calendar() if _demo_active() else "primary")
    except Exception as exc:
        raise HTTPException(502, f"Google Calendar rejected the event: {exc}") from exc
    return {"id": ev.get("id"), "link": ev.get("htmlLink"), "date": start.date().isoformat()}


@app.get("/api/dashboard")
def dashboard(date: Optional[str] = None, start_hour: int = 8, end_hour: int = 20):
    if not 0 <= start_hour < end_hour <= 24:
        raise HTTPException(400, "need 0 <= start_hour < end_hour <= 24")
    return _compute(_parse_day(date), start_hour, min(end_hour, 23))


class NewTask(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due: Optional[datetime] = None
    effort_minutes: int = Field(ge=5, le=600)
    importance: float = Field(ge=0, le=1)
    location: Optional[str] = Field(default=None, max_length=100)


@app.post("/api/tasks", status_code=201)
def create_task(body: NewTask):
    due = body.due.replace(tzinfo=None) if body.due else None
    return {"id": store.add_task(body.title.strip(), due, body.effort_minutes,
                                 body.importance, (body.location or "").strip() or None)}


@app.delete("/api/tasks/{task_id}", status_code=204)
def remove_task(task_id: str):
    store.delete_task(task_id)


class DoneBody(BaseModel):
    done: bool


@app.post("/api/tasks/{task_id}/done", status_code=204)
def mark_done(task_id: str, body: DoneBody):
    store.set_done(task_id, body.done)


@app.post("/api/plan/push")
def push_plan(date: Optional[str] = None, start_hour: int = 8, end_hour: int = 20):
    creds = gcal.load_credentials()
    if creds is None:
        raise HTTPException(401, "Connect Google Calendar first.")
    day = _parse_day(date)
    day_dt = datetime.combine(day, time.min)
    data = _compute(day, start_hour, min(end_hour, 23))
    plan = [{**p, "start": datetime.fromisoformat(p["start"]), "end": datetime.fromisoformat(p["end"])}
            for p in data["plan"]]
    try:
        created = gcal.push_plan(creds, plan, day_dt.date(),
                                 calendar_id=store.demo_calendar() if _demo_active() else "primary")
    except Exception as exc:
        raise HTTPException(502, f"Google Calendar rejected the update: {exc}") from exc
    return {"created": created}


# ---------------- Google OAuth ----------------

def _redirect_uri(request: Request) -> str:
    return str(request.url_for("auth_callback"))


@app.get("/auth/login")
def auth_login(request: Request):
    if not gcal.has_client_secrets():
        raise HTTPException(400, "credentials.json is missing -- see README → Connecting Google Calendar.")
    return RedirectResponse(gcal.start_web_flow(_redirect_uri(request)))


@app.get("/auth/callback", name="auth_callback")
def auth_callback(request: Request, state: str = "", error: Optional[str] = None):
    if error:
        return RedirectResponse(f"/?auth_error={error}")
    try:
        gcal.finish_web_flow(state, str(request.url))
    except Exception as exc:
        return RedirectResponse(f"/?auth_error={type(exc).__name__}")
    return RedirectResponse("/?connected=1")


@app.post("/auth/logout", status_code=204)
def auth_logout():
    gcal.disconnect()


# ---------------- UI ----------------

@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
