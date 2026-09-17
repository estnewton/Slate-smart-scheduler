"""
End-to-end demo using realistic mock data -- runs with zero setup, no API keys needed.
This is what you'd run to show the project working in an interview.

    python -m src.demo
"""
from datetime import datetime, timedelta
from .models import Task, TaskSource
from .scheduler import auto_generate_prep_tasks, build_daily_plan


def mock_week(today: datetime) -> list[Task]:
    """A believable week: recurring classes, a quiz, an exam, and a few personal tasks."""
    return [
        # --- fixed calendar events (classes) ---
        Task(id="c1", title="IE 322: Prob Models", due=None,
             fixed_time=today.replace(hour=9, minute=5), end_time=today.replace(hour=9, minute=55),
             effort_minutes=0, importance=0, location="West Campus", tags=["class:IE 322"]),
        Task(id="c2", title="1:1 with Professor Lin", due=None,
             fixed_time=today.replace(hour=10, minute=0), end_time=today.replace(hour=10, minute=30),
             effort_minutes=0, importance=0, location="West Campus", tags=["office-hours"]),
        Task(id="c3", title="IE 304: Service Systems", due=None,
             fixed_time=today.replace(hour=13, minute=0), end_time=today.replace(hour=13, minute=50),
             effort_minutes=0, importance=0, location="East Campus", tags=["class:IE 304"]),
        # a quiz later this week, used to demo auto-generated prep tasks
        Task(id="c4", title="IE 322 Quiz", due=None,
             fixed_time=(today + timedelta(days=3)).replace(hour=9, minute=5),
             end_time=(today + timedelta(days=3)).replace(hour=9, minute=55),
             effort_minutes=0, importance=0, location="West Campus", tags=["class:IE 322"]),
        # an exam next week
        Task(id="c5", title="IE 302 Midterm", due=None,
             fixed_time=(today + timedelta(days=8)).replace(hour=11, minute=0),
             end_time=(today + timedelta(days=8)).replace(hour=12, minute=30),
             effort_minutes=0, importance=0, location="East Campus", tags=["class:IE 302"]),

        # --- flexible personal tasks ---
        Task(id="t1", title="Morning workout", due=today.replace(hour=11, minute=0),
             effort_minutes=45, importance=0.4, location="West Campus Gym"),
        Task(id="t2", title="Coffee run", due=today.replace(hour=12, minute=0),
             effort_minutes=15, importance=0.2, location="West Campus"),
        Task(id="t3", title="Draft VALLEY sponsorship email", due=today + timedelta(days=2),
             effort_minutes=30, importance=0.6, location="Home"),
        Task(id="t4", title="Apply to Duolingo internship", due=today + timedelta(days=1),
             effort_minutes=40, importance=0.8, confidence=0.9, location="Home"),
    ]


def main():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tasks = mock_week(today)

    print("=== Auto-generated prep tasks (from quiz/exam detection) ===")
    generated = auto_generate_prep_tasks(tasks, now=today)
    for g in generated:
        print(f"  [{g.due:%a %m/%d %I:%M %p}] {g.title}  (@ {g.location})")

    all_flexible = [t for t in tasks if t.fixed_time is None] + generated
    fixed = [t for t in tasks if t.fixed_time is not None]

    print("\n=== Today's plan ===")
    plan = build_daily_plan(
        fixed_events=fixed, flexible_tasks=all_flexible,
        day_start=today.replace(hour=8), day_end=today.replace(hour=18),
        now=today,
    )
    for item in plan:
        marker = "📌" if item["kind"] == "fixed" else "  •"
        loc = f" @ {item['location']}" if item["location"] else ""
        print(f"{marker} {item['start']:%I:%M %p}-{item['end']:%I:%M %p}  {item['title']}{loc}")


if __name__ == "__main__":
    main()
