from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import Task, TaskSource
from src.scheduler import auto_generate_prep_tasks, build_daily_plan


def test_quiz_generates_review_and_breakfast_tasks():
    today = datetime(2026, 1, 1, 0, 0)
    quiz = Task(id="q1", title="History Quiz", due=None, effort_minutes=0, importance=0,
                fixed_time=today + timedelta(days=2, hours=9), location="Main Hall")
    generated = auto_generate_prep_tasks([quiz], now=today)
    titles = [g.title for g in generated]
    assert "Review notes for History Quiz" in titles
    assert "Eat breakfast before History Quiz" in titles


def test_exam_generates_two_study_sessions():
    today = datetime(2026, 1, 1, 0, 0)
    exam = Task(id="e1", title="Chem Final", due=None, effort_minutes=0, importance=0,
                fixed_time=today + timedelta(days=10, hours=9))
    generated = auto_generate_prep_tasks([exam], now=today)
    study_tasks = [g for g in generated if "Study for" in g.title]
    assert len(study_tasks) == 2


def test_tasks_due_beyond_today_are_not_scheduled_today():
    today = datetime(2026, 1, 1, 8, 0)
    day_end = today.replace(hour=18)
    far_task = Task(id="t1", title="Next week thing", due=today + timedelta(days=5),
                     effort_minutes=30, importance=0.9, location="Home")
    today_task = Task(id="t2", title="Today thing", due=today.replace(hour=12),
                       effort_minutes=30, importance=0.3, location="Home")
    plan = build_daily_plan([], [far_task, today_task], today, day_end, now=today)
    titles = [p["title"] for p in plan]
    assert "Today thing" in titles
    assert "Next week thing" not in titles


def test_location_matching_task_is_preferred_next_to_matching_event():
    today = datetime(2026, 1, 1, 8, 0)
    day_end = today.replace(hour=18)
    class_event = Task(id="c1", title="Class", due=None, effort_minutes=0, importance=0,
                        fixed_time=today.replace(hour=10), end_time=today.replace(hour=11),
                        location="West Campus")
    gym = Task(id="t1", title="Gym", due=today.replace(hour=17), effort_minutes=30,
               importance=0.3, location="West Campus")
    home_task = Task(id="t2", title="Laundry", due=today.replace(hour=17), effort_minutes=30,
                      importance=0.9, location="Home")
    plan = build_daily_plan([class_event], [gym, home_task], today, day_end, now=today)
    # The gym (location match) should be scheduled before the class despite lower importance
    gym_idx = next(i for i, p in enumerate(plan) if p["title"] == "Gym")
    class_idx = next(i for i, p in enumerate(plan) if p["title"] == "Class")
    assert gym_idx < class_idx
