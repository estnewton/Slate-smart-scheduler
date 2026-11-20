"""
Two things live here:

1. auto_generate_prep_tasks() -- scans upcoming fixed events (classes, quizzes, exams) and
   creates the "study the night before" / "review the morning of" tasks a person would
   otherwise have to remember to add themselves.

2. build_daily_plan() -- takes today's fixed events (classes, meetings) plus the ranked
   flexible task list, and slots flexible tasks into the gaps between fixed events,
   preferring tasks whose location matches (or is near) the location you're already at,
   so you're not zig-zagging across campus.
"""
from datetime import datetime, timedelta
from typing import Optional
from .models import Task, TaskSource
from .scoring import rank_tasks

EXAM_KEYWORDS = ("exam", "midterm", "final")
QUIZ_KEYWORDS = ("quiz", "test")


def auto_generate_prep_tasks(fixed_events: list[Task], now: Optional[datetime] = None) -> list[Task]:
    """
    Looks at titles of fixed calendar events for exam/quiz keywords and generates:
      - Exams/midterms  -> a study task 7 days before AND 1 day before
      - Quizzes         -> a study task the night before, and a "good breakfast" reminder the morning of
    Generated tasks inherit the class location so they can be scheduled near where the class is.
    """
    now = now or datetime.now()
    generated: list[Task] = []
    counter = 0

    for event in fixed_events:
        if event.fixed_time is None:
            continue
        title_lower = event.title.lower()

        if any(k in title_lower for k in EXAM_KEYWORDS):
            for days_before, importance in [(7, 0.6), (1, 0.9)]:
                counter += 1
                study_time = event.fixed_time - timedelta(days=days_before)
                if study_time > now:
                    generated.append(Task(
                        id=f"auto-{event.id}-study-{days_before}d",
                        title=f"Study for {event.title}",
                        due=study_time,
                        effort_minutes=90 if days_before == 1 else 60,
                        importance=importance,
                        location=event.location,
                        source=TaskSource.AUTO_GENERATED,
                        tags=["exam-prep"] + event.tags,
                    ))

        elif any(k in title_lower for k in QUIZ_KEYWORDS):
            night_before = event.fixed_time - timedelta(hours=15)  # ~previous evening
            if night_before > now:
                counter += 1
                generated.append(Task(
                    id=f"auto-{event.id}-study",
                    title=f"Review notes for {event.title}",
                    due=night_before,
                    effort_minutes=30,
                    importance=0.5,
                    location=event.location,
                    source=TaskSource.AUTO_GENERATED,
                    tags=["quiz-prep"] + event.tags,
                ))
            morning_of = event.fixed_time - timedelta(hours=1)
            if morning_of > now:
                generated.append(Task(
                    id=f"auto-{event.id}-breakfast",
                    title=f"Eat breakfast before {event.title}",
                    due=morning_of,
                    effort_minutes=15,
                    importance=0.3,
                    location=event.location,
                    source=TaskSource.AUTO_GENERATED,
                    tags=["wellbeing"],
                ))

    return generated


def _location_match(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    return a.strip().lower() == b.strip().lower()


def build_daily_plan(fixed_events: list[Task], flexible_tasks: list[Task],
                      day_start: datetime, day_end: datetime,
                      now: Optional[datetime] = None,
                      earliest: Optional[datetime] = None) -> list[dict]:
    """
    Builds a simple ordered day plan: fixed events stay where they are; flexible tasks
    are dropped into the open gaps between them, preferring (in this order):
      1. A task whose location matches the fixed event that comes right before OR after the gap
         (so you do it on your way, instead of doubling back later)
      2. The highest relevance_score task that still fits the gap's duration

    `earliest` (optional) keeps flexible tasks from being slotted before that time, e.g. "now"
    when planning the rest of today; fixed events before it still appear in the plan.

    Returns a list of {start, end, title, kind, location} dicts in chronological order.
    """
    now = now or datetime.now()
    todays_fixed = sorted(
        [e for e in fixed_events if e.fixed_time and day_start <= e.fixed_time < day_end],
        key=lambda e: e.fixed_time,
    )
    # Only pull flexible tasks that are actually relevant to *this* day: due today (or overdue),
    # or open-ended (no due date). Tasks due further out stay in the backlog for a later day --
    # otherwise a high-importance task due next week would crowd out today's actual to-dos.
    due_today_or_sooner = [
        t for t in flexible_tasks
        if t.due is None or t.due <= day_end
    ]
    ranked = [t for t, _score in rank_tasks(due_today_or_sooner, now)]
    remaining = list(ranked)
    plan: list[dict] = []

    cursor = day_start
    boundaries = todays_fixed + [None]  # sentinel for the final gap to day_end

    for i, event in enumerate(boundaries):
        gap_end = event.fixed_time if event else day_end
        if earliest and cursor < earliest:
            cursor = min(earliest, gap_end) if gap_end > cursor else cursor
        gap_minutes = (gap_end - cursor).total_seconds() / 60
        neighbor_location = None
        if i > 0:
            neighbor_location = todays_fixed[i - 1].location
        elif event:
            neighbor_location = event.location

        # Try to slot in tasks that fit, preferring ones matching the neighboring location
        remaining.sort(key=lambda t: (not _location_match(t.location, neighbor_location),))
        fitted = []
        for task in list(remaining):
            if task.effort_minutes <= gap_minutes:
                fitted.append(task)
                remaining.remove(task)
                gap_minutes -= task.effort_minutes
                if gap_minutes < 10:  # stop once the gap's basically full
                    break

        for task in fitted:
            plan.append({
                "start": cursor, "end": cursor + timedelta(minutes=task.effort_minutes),
                "title": task.title, "kind": "task", "location": task.location,
            })
            cursor += timedelta(minutes=task.effort_minutes)

        if event:
            plan.append({
                "start": event.fixed_time, "end": event.end_time or event.fixed_time,
                "title": event.title, "kind": "fixed", "location": event.location,
            })
            cursor = event.end_time or event.fixed_time

    return plan
