"""Core data models shared across the scoring engine, scheduler, and integrations."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TaskSource(str, Enum):
    MANUAL = "manual"
    CANVAS = "canvas"
    GOOGLE_CALENDAR = "google_calendar"
    AUTO_GENERATED = "auto_generated"  # e.g. "Study for X" created by the scheduler itself


@dataclass
class Task:
    """A single actionable to-do. This is what gets scored and slotted into a day."""
    id: str
    title: str
    due: Optional[datetime]          # when it's due / when the event happens
    effort_minutes: int              # how long it actually takes
    importance: float                # 0-1, e.g. exam worth 30% of grade -> 0.9, a reading quiz -> 0.3
    confidence: float = 0.8          # 0-1, how sure we are this estimate/task is accurate
    location: Optional[str] = None   # free-text tag, e.g. "West Campus", "IST Building", "Home"
    source: TaskSource = TaskSource.MANUAL
    fixed_time: Optional[datetime] = None  # set if this is an immovable calendar event (a class)
    end_time: Optional[datetime] = None    # end of the fixed event (ignored for flexible tasks)
    tags: list = field(default_factory=list)  # e.g. ["exam-prep", "class:IE 322"]


@dataclass
class CalendarEvent:
    """A raw event pulled from Google Calendar / Canvas / an .ics file, before conversion to a Task."""
    id: str
    title: str
    start: datetime
    end: datetime
    location: Optional[str] = None
    description: Optional[str] = None
    source: TaskSource = TaskSource.GOOGLE_CALENDAR
