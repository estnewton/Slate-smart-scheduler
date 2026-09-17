from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import Task
from src.scoring import urgency, relevance_score, rank_tasks


def test_overdue_task_is_max_urgency():
    now = datetime(2026, 1, 1, 12, 0)
    t = Task(id="a", title="late thing", due=now - timedelta(hours=1),
             effort_minutes=30, importance=0.5)
    assert urgency(t, now) == 1.0


def test_far_future_task_has_low_urgency():
    now = datetime(2026, 1, 1, 12, 0)
    t = Task(id="b", title="far off", due=now + timedelta(days=30),
             effort_minutes=30, importance=0.5)
    assert urgency(t, now) < 0.05


def test_higher_importance_outranks_lower_at_equal_urgency_and_effort():
    now = datetime(2026, 1, 1, 12, 0)
    due = now + timedelta(hours=5)
    low = Task(id="c", title="low importance", due=due, effort_minutes=30, importance=0.2)
    high = Task(id="d", title="high importance", due=due, effort_minutes=30, importance=0.9)
    assert relevance_score(high, now) > relevance_score(low, now)


def test_high_effort_lowers_score_for_otherwise_identical_tasks():
    now = datetime(2026, 1, 1, 12, 0)
    due = now + timedelta(hours=5)
    quick = Task(id="e", title="quick", due=due, effort_minutes=15, importance=0.5)
    slow = Task(id="f", title="slow", due=due, effort_minutes=120, importance=0.5)
    assert relevance_score(quick, now) > relevance_score(slow, now)


def test_fixed_events_are_excluded_from_ranking():
    now = datetime(2026, 1, 1, 8, 0)
    fixed = Task(id="g", title="class", due=None, effort_minutes=0, importance=0,
                 fixed_time=now)
    flexible = Task(id="h", title="task", due=now + timedelta(hours=2),
                     effort_minutes=20, importance=0.5)
    ranked = rank_tasks([fixed, flexible], now)
    assert len(ranked) == 1
    assert ranked[0][0].id == "h"
