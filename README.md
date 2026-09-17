# Smart Scheduler

A personal task organizer that syncs your class schedule (Canvas), calendar (Google Calendar,
or anything exportable as `.ics` — Apple Calendar, Outlook), and ranks your to-do list the way
a product team ranks a feature backlog: using a RICE-inspired scoring model, adapted here as

    relevance_score = (urgency × importance × confidence) / effort

instead of manually deciding what to do next, or forgetting to study until the night before a
quiz, the scheduler:

- **Auto-generates prep tasks.** Detects "Quiz" / "Exam" / "Midterm" in your class schedule and
  creates study sessions and reminders automatically (a review task the night before a quiz, two
  study sessions — one a week out, one the day before — for an exam).
- **Ranks your open tasks by relevance**, not just by due date — a low-effort, high-importance
  task can outrank a due-sooner-but-trivial one.
- **Sequences your day by location**, not just by score — a flexible task is preferred in a gap
  when it shares a location with the class/meeting right before or after it, so you're not
  crossing campus twice for things you could've batched together.

## Why this exists

Built as a portfolio project applying product-management prioritization frameworks (RICE,
effort/impact tradeoffs) to a full-stack tool with real external API integrations, rather than
a plain scoring calculator.

## Architecture

```
src/
  models.py                 Task / CalendarEvent data models
  scoring.py                 RICE-inspired relevance scoring (pure logic, fully tested)
  scheduler.py                Auto-generated prep tasks + location-aware daily planner
  demo.py                     Runnable end-to-end demo, mock data, no credentials needed
  integrations/
    google_calendar.py        OAuth read-only sync (needs your own Google Cloud credentials)
    canvas.py                 Canvas REST API sync (needs your own Canvas access token)
    ics_sync.py                Import/export .ics — covers Apple Calendar, Outlook, etc.
tests/
  test_scoring.py
  test_scheduler.py
```

## Quickstart (no setup required)

```bash
pip install -r requirements.txt
python -m src.demo          # runs the full pipeline on realistic mock data
python -m pytest tests/     # 9 tests covering scoring + scheduling logic
```

## Connecting your real calendars (optional)

**Recommended setup — one integration instead of two:** Canvas has a built-in "Calendar Feed"
(Canvas → Calendar → bottom-right "Calendar Feed" link) — a private `.ics` URL you can subscribe
to directly from Google Calendar (Google Calendar → Other calendars → **+** → **From URL** →
paste the link). Every Canvas assignment and due date then shows up as a normal event on your
Google Calendar automatically, kept in sync going forward with zero extra code. That means the
app only needs to connect to **Google Calendar** — Canvas comes along for free.

| Source | What you need | Setup effort |
|---|---|---|
| Google Calendar (recommended — also covers Canvas via the feed above) | A Google Cloud OAuth client (`credentials.json`) | ~10 min, one-time |
| Canvas direct API (optional/advanced — only needed if the calendar feed doesn't expose something you want) | A personal access token from your school's Canvas | ~2 min |
| Apple Calendar / Outlook / anything else | Export as `.ics`, point `ics_sync.import_ics()` at it | ~1 min |

Credentials are never committed — `.gitignore` already excludes `credentials.json`, `token.json`,
and `.env`.

## Current scope vs. roadmap

**Built:** relevance scoring, auto-generated exam/quiz prep tasks, location-aware daily
sequencing, Google Calendar + Canvas + `.ics` sync.

**Not yet built (good "phase 2" story):** live business-hours-aware suggestions (e.g., "hit the
gym before the coffee shop next door opens") — this needs a places/hours API (e.g., Google
Places) rather than manually-tagged locations, which is the natural next integration once the
core scheduling logic is proven out.
