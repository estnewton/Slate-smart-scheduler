"""
Relevance scoring, adapted from the RICE framework (Reach x Impact x Confidence / Effort)
that product teams use to prioritize a feature backlog -- applied here to a personal task list.

Mapping:
    Reach x Impact  -> Urgency x Importance   (how soon it's due, how much it matters)
    Confidence      -> Confidence              (same concept: how sure we are this estimate is right)
    Effort          -> Effort                  (same concept: time cost)

    relevance_score = (urgency * importance * confidence) / effort
"""
from datetime import datetime
from math import exp
from .models import Task


def urgency(task: Task, now: datetime) -> float:
    """
    Returns a 0-1 urgency score that rises sharply as the due date approaches.
    A task due in 5 minutes scores near 1.0; a task due in 3 weeks scores near 0.
    No due date at all (open-ended task) gets a flat low-but-nonzero urgency.
    """
    if task.due is None:
        return 0.15
    hours_remaining = (task.due - now).total_seconds() / 3600
    if hours_remaining <= 0:
        return 1.0  # overdue -- max urgency
    # Exponential decay: half-life tuned so "due tomorrow" is noticeably more
    # urgent than "due in a week", without a hard cliff.
    half_life_hours = 36
    return exp(-hours_remaining / (half_life_hours / 0.693))


def relevance_score(task: Task, now: datetime) -> float:
    """Higher = do this sooner. Effort divides the score, same as RICE penalizes high-effort work."""
    u = urgency(task, now)
    effort_hours = max(task.effort_minutes / 60, 0.05)  # avoid division by ~0
    return (u * task.importance * task.confidence) / effort_hours


def rank_tasks(tasks: list[Task], now: datetime | None = None) -> list[tuple[Task, float]]:
    """Returns (task, score) pairs sorted highest-relevance first. Fixed calendar events
    (task.fixed_time is set) are excluded -- they're anchors, not things to rank."""
    now = now or datetime.now()
    flexible = [t for t in tasks if t.fixed_time is None]
    scored = [(t, relevance_score(t, now)) for t in flexible]
    return sorted(scored, key=lambda pair: pair[1], reverse=True)
