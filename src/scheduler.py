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
      - Quizzes         -> a review task the evening before (9pm), and a meal reminder an hour
                           before (breakfast, lunch or a snack, depending on the quiz time)
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
            # the evening before (9pm), not a fixed offset that lands at 2am for an evening quiz
            night_before = (event.fixed_time - timedelta(days=1)).replace(hour=21, minute=0)
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
            morning_of = event.fixed_time  # due when the quiz starts, so it's planned right before it
            meal = ("breakfast" if event.fixed_time.hour < 11
                    else "lunch" if event.fixed_time.hour < 15 else "a snack")
            if morning_of - timedelta(minutes=15) > now:
                generated.append(Task(
                    id=f"auto-{event.id}-breakfast",
                    title=f"Eat {meal} before {event.title}",
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
    Builds an ordered day plan: fixed events stay where they are, and flexible tasks are placed
    into the open gaps between them, highest relevance score first. For each task Slate picks:
      1. A slot that finishes before the task is due (a task due at 10am never lands at 2pm).
      2. Preferably one next to a fixed event at the same location -- right after it, or else
         right before it -- so errands get batched with the class or appointment that already
         takes you there.
      3. Otherwise the earliest slot that fits.

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
    due_today_or_sooner = [t for t in flexible_tasks if t.due is None or t.due <= day_end]
    ranked = [t for t, _score in rank_tasks(due_today_or_sooner, now)]
    plan_start = max(day_start, earliest) if earliest else day_start

    # Open gaps between fixed events (overlapping events are merged). Each gap fills from the
    # front (after the previous event) and from the back (before the next one).
    # "prev" holds the locations of every event in the overlapping group just before the gap.
    gaps = []
    cursor, prev_locs = day_start, []
    for event in todays_fixed + [None]:
        gap_end = event.fixed_time if event else day_end
        start = max(cursor, plan_start)
        if gap_end > start:
            gaps.append({"front": start, "back": gap_end, "prev": prev_locs,
                         "next": event.location if event else None})
        if event:
            if event.fixed_time >= cursor:
                prev_locs = []  # a new group of events starts
            prev_locs = prev_locs + [event.location]
            cursor = max(cursor, event.end_time or event.fixed_time)

    placed: list[dict] = []
    for task in ranked:
        length = timedelta(minutes=task.effort_minutes)
        # A deadline we can still meet today constrains the slot; an already-missed one doesn't.
        deadline = task.due if task.due and task.due > plan_start else None
        options = []
        for g in gaps:
            if g["back"] - g["front"] < length:
                continue
            if any(_location_match(task.location, loc) for loc in g["prev"]):
                slot, side, match = g["front"], "front", True
            elif _location_match(task.location, g["next"]):
                slot, side, match = g["back"] - length, "back", True
            else:
                slot, side, match = g["front"], "front", False
            if deadline and slot + length > deadline:
                if side == "back" and g["front"] + length <= deadline:
                    slot, side, match = g["front"], "front", False
                else:
                    continue
            options.append((not match, side == "back", slot, side, g))
        if not options:
            continue  # nothing fits today; it stays in the ranked backlog
        # location match first; among matches, right *after* an event beats right before it
        # (you're already there); then earliest
        *_, slot, side, g = min(options, key=lambda o: (o[0], o[1], o[2]))
        if side == "front":
            g["front"] = slot + length
        else:
            g["back"] = slot
        placed.append({"start": slot, "end": slot + length, "title": task.title,
                       "kind": "task", "location": task.location})

    fixed_items = [{"start": e.fixed_time, "end": e.end_time or e.fixed_time, "title": e.title,
                    "kind": "fixed", "location": e.location} for e in todays_fixed]
    return sorted(fixed_items + placed, key=lambda p: (p["start"], p["kind"] != "fixed"))
