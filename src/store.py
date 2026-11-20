"""Tiny JSON-file store for tasks you add in the UI and tasks you've checked off.
Lives in data/state.json (gitignored), so your list survives restarts."""
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Task, TaskSource

STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "state.json"
_lock = threading.Lock()


def _read() -> dict:
    if not STATE_PATH.exists():
        return {"tasks": [], "done": []}
    return json.loads(STATE_PATH.read_text())


def _write(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_PATH)


def manual_tasks() -> list[Task]:
    return [
        Task(
            id=t["id"], title=t["title"],
            due=datetime.fromisoformat(t["due"]) if t.get("due") else None,
            effort_minutes=t["effort_minutes"], importance=t["importance"],
            confidence=t.get("confidence", 0.8), location=t.get("location"),
            source=TaskSource.MANUAL,
        )
        for t in _read()["tasks"]
    ]


def add_task(title: str, due: Optional[datetime], effort_minutes: int, importance: float,
             location: Optional[str]) -> str:
    with _lock:
        state = _read()
        task_id = f"manual-{uuid.uuid4().hex[:8]}"
        state["tasks"].append({
            "id": task_id, "title": title,
            "due": due.isoformat() if due else None,
            "effort_minutes": effort_minutes, "importance": importance,
            "location": location or None,
        })
        _write(state)
        return task_id


def delete_task(task_id: str) -> None:
    with _lock:
        state = _read()
        state["tasks"] = [t for t in state["tasks"] if t["id"] != task_id]
        state["done"] = [d for d in state["done"] if d != task_id]
        _write(state)


def done_ids() -> set[str]:
    return set(_read()["done"])


def set_done(task_id: str, done: bool) -> None:
    with _lock:
        state = _read()
        ids = set(state["done"])
        ids.add(task_id) if done else ids.discard(task_id)
        state["done"] = sorted(ids)
        _write(state)
