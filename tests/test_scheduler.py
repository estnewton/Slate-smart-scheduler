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
    # The gym (location match) goes right next to the class despite lower importance;
    # the higher-importance laundry takes the earliest slot instead
    gym = next(p for p in plan if p["title"] == "Gym")
    assert gym["start"] == today.replace(hour=11) or gym["end"] == today.replace(hour=10)


def test_earliest_keeps_tasks_out_of_the_past_but_keeps_fixed_events():
    day = datetime(2026, 1, 1, 0, 0)
    morning_class = Task(id="c", title="Class", due=None, effort_minutes=0, importance=0,
                         fixed_time=day.replace(hour=9), end_time=day.replace(hour=10))
    chore = Task(id="t", title="Chore", due=day.replace(hour=17), effort_minutes=30, importance=0.5)
    plan = build_daily_plan([morning_class], [chore], day.replace(hour=8), day.replace(hour=18),
                            now=day.replace(hour=13), earliest=day.replace(hour=13))
    assert [p["title"] for p in plan] == ["Class", "Chore"]
    assert plan[1]["start"] == day.replace(hour=13)


def test_tasks_finish_before_their_deadline():
    day = datetime(2026, 1, 1, 0, 0)
    blocks = [Task(id=f"c{h}", title=f"Class {h}", due=None, effort_minutes=0, importance=0,
                   fixed_time=day.replace(hour=h), end_time=day.replace(hour=h + 1))
              for h in (9, 10, 11)]
    breakfast = Task(id="b", title="Breakfast", due=day.replace(hour=9), effort_minutes=15, importance=0.3)
    plan = build_daily_plan(blocks, [breakfast], day.replace(hour=8), day.replace(hour=18), now=day)
    slot = next(p for p in plan if p["title"] == "Breakfast")
    assert slot["end"] <= day.replace(hour=9)


def test_errand_is_batched_right_after_appointment_at_same_place():
    day = datetime(2026, 1, 1, 0, 0)
    doctor = Task(id="d", title="Doctor", due=None, effort_minutes=0, importance=0,
                  fixed_time=day.replace(hour=14), end_time=day.replace(hour=15), location="Clinic")
    pickup = Task(id="p", title="Pick up prescription", due=day.replace(hour=17),
                  effort_minutes=15, importance=0.6, location="Clinic")
    plan = build_daily_plan([doctor], [pickup], day.replace(hour=8), day.replace(hour=18), now=day)
    slot = next(p for p in plan if p["title"] == "Pick up prescription")
    assert slot["start"] == day.replace(hour=15)


def test_meal_reminder_lands_right_before_the_quiz():
    day = datetime(2026, 1, 1, 0, 0)
    quiz = Task(id="q", title="Math Quiz", due=None, effort_minutes=0, importance=0,
                fixed_time=day.replace(hour=17), end_time=day.replace(hour=18), location="Wartik Lab")
    gen = auto_generate_prep_tasks([quiz], now=day.replace(hour=7))
    plan = build_daily_plan([quiz], gen, day.replace(hour=8), day.replace(hour=22), now=day.replace(hour=7))
    snack = next(p for p in plan if p["title"] == "Eat a snack before Math Quiz")
    assert snack["end"] == day.replace(hour=17)


def test_events_about_a_quiz_are_not_quizzes():
    day = datetime(2026, 1, 1, 0, 0)
    group = Task(id="g", title="Study group for Math Quiz", due=None, effort_minutes=0, importance=0,
                 fixed_time=day + timedelta(days=2, hours=12))
    contest = Task(id="c", title="Coding contest", due=None, effort_minutes=0, importance=0,
                   fixed_time=day + timedelta(days=2, hours=15))
    assert auto_generate_prep_tasks([group, contest], now=day) == []
