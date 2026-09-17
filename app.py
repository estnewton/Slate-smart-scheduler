"""
Local web UI for Smart Scheduler.

Run it with:
    streamlit run app.py

Opens automatically in your browser at http://localhost:8501

Uses mock data out of the box (same realistic week as src/demo.py) so it works with zero
setup. Once you've done the Google Calendar OAuth setup (see README), flip
USE_MOCK_DATA to False below to pull your real calendar instead.
"""
from datetime import datetime, timedelta

import streamlit as st

from src.demo import mock_week
from src.scheduler import auto_generate_prep_tasks, build_daily_plan
from src.scoring import rank_tasks
from src.models import Task, TaskSource

USE_MOCK_DATA = True

st.set_page_config(page_title="Smart Scheduler", page_icon="🗓️", layout="wide")

st.title("🗓️ Smart Scheduler")
st.caption("RICE-inspired task ranking + location-aware daily planning")

# ---------------- data source ----------------
today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

if "extra_tasks" not in st.session_state:
    st.session_state.extra_tasks = []

if USE_MOCK_DATA:
    base_tasks = mock_week(today)
else:
    from src.integrations.google_calendar import fetch_upcoming_events
    events = fetch_upcoming_events(days_ahead=7)
    base_tasks = [
        Task(id=e.id, title=e.title, due=None, fixed_time=e.start, end_time=e.end,
             effort_minutes=0, importance=0, location=e.location, source=TaskSource.GOOGLE_CALENDAR)
        for e in events
    ]

tasks = base_tasks + st.session_state.extra_tasks
fixed = [t for t in tasks if t.fixed_time is not None]
flexible = [t for t in tasks if t.fixed_time is None]

# ---------------- sidebar: add a task ----------------
with st.sidebar:
    st.header("Add a task")
    with st.form("add_task", clear_on_submit=True):
        title = st.text_input("Title")
        due_in_hours = st.slider("Due in (hours from now)", 1, 168, 24)
        effort = st.slider("Effort (minutes)", 5, 180, 30)
        importance = st.slider("Importance", 0.0, 1.0, 0.5)
        location = st.text_input("Location (optional)", placeholder="e.g. West Campus")
        submitted = st.form_submit_button("Add task")
        if submitted and title:
            st.session_state.extra_tasks.append(Task(
                id=f"manual-{len(st.session_state.extra_tasks)}",
                title=title,
                due=today + timedelta(hours=due_in_hours),
                effort_minutes=effort,
                importance=importance,
                location=location or None,
                source=TaskSource.MANUAL,
            ))
            st.rerun()

    if st.session_state.extra_tasks:
        st.divider()
        st.caption("Your added tasks")
        for t in st.session_state.extra_tasks:
            st.write(f"• {t.title}")
        if st.button("Clear added tasks"):
            st.session_state.extra_tasks = []
            st.rerun()

# ---------------- main layout ----------------
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📋 Ranked task backlog")
    st.caption("relevance = (urgency × importance × confidence) / effort")
    ranked = rank_tasks(flexible, now=today)
    for task, score in ranked:
        due_str = task.due.strftime("%a %I:%M %p") if task.due else "no deadline"
        loc_str = f" · 📍{task.location}" if task.location else ""
        st.metric(label=f"{task.title}{loc_str}", value=f"{score:.2f}", help=f"Due: {due_str}")

with col2:
    st.subheader("🤖 Auto-generated prep tasks")
    st.caption("Detected from Quiz/Exam/Midterm keywords in your schedule")
    generated = auto_generate_prep_tasks(tasks, now=today)
    if not generated:
        st.info("No quizzes or exams detected in the next few days.")
    for g in generated:
        st.write(f"**{g.title}**  \n{g.due:%a %m/%d %I:%M %p} · 📍{g.location or '—'}")

st.divider()
st.subheader("📅 Today's plan")
plan = build_daily_plan(
    fixed_events=fixed,
    flexible_tasks=flexible + generated,
    day_start=today.replace(hour=8),
    day_end=today.replace(hour=18),
    now=today,
)
for item in plan:
    icon = "📌" if item["kind"] == "fixed" else "✅"
    loc = f" · 📍{item['location']}" if item["location"] else ""
    st.write(f"{icon} **{item['start']:%I:%M %p}–{item['end']:%I:%M %p}** — {item['title']}{loc}")

if not USE_MOCK_DATA:
    st.caption("Connected to your live Google Calendar.")
else:
    st.caption("Showing mock demo data. Set USE_MOCK_DATA = False in app.py once your Google Calendar is connected (see README).")
