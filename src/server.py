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
from .integrations import google_calendar as gcal
from .models import Task, TaskSource
from .scheduler import auto_generate_prep_tasks, build_daily_plan
from .scoring import rank_tasks, urgency

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
LOOKAHEAD_DAYS = 14  # how far ahead to read the calendar (exam prep starts a week out)

app = FastAPI(title="Slate")


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


def _load_tasks(today: datetime) -> tuple[list[Task], str]:
    """Fixed + flexible tasks from Google Calendar if connected, otherwise demo data."""
    creds = gcal.load_credentials()
    if creds is None:
        tasks, source = mock_week(today), "demo"
    else:
        try:
            events = gcal.fetch_events(creds, today - timedelta(days=1),
                                       today + timedelta(days=LOOKAHEAD_DAYS))
        except Exception as exc:  # network / revoked access -- surface it rather than 500 silently
            raise HTTPException(502, f"Couldn't reach Google Calendar: {exc}") from exc
        tasks, source = [_event_to_task(e) for e in events], "google"
    return tasks + store.manual_tasks(), source


def _compute(day: date, start_hour: int, end_hour: int) -> dict:
    now = datetime.now().replace(second=0, microsecond=0)
    today = datetime.combine(date.today(), time.min)
    day_dt = datetime.combine(day, time.min)

    tasks, source = _load_tasks(today)
    done = store.done_ids()

    fixed = [t for t in tasks if t.fixed_time is not None]
    timed_fixed = [t for t in fixed if "all-day" not in t.tags]
    generated = [g for g in auto_generate_prep_tasks(fixed, now=now) if g.id not in done]
    flexible = [t for t in tasks if t.fixed_time is None and t.id not in done]

    ranked = rank_tasks(flexible + generated, now=now)
    plan = build_daily_plan(
        fixed_events=timed_fixed, flexible_tasks=flexible + generated,
        day_start=day_dt.replace(hour=start_hour), day_end=day_dt.replace(hour=end_hour),
        now=now, earliest=_round_up(now) if day == date.today() else None,
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
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(400, "date must be YYYY-MM-DD") from exc


# ---------------- API ----------------

@app.get("/api/status")
def status():
    return {"has_credentials": gcal.has_client_secrets(),
            "connected": gcal.load_credentials() is not None}


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
        created = gcal.push_plan(creds, plan, day_dt.date())
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
