# Smart Scheduler

A personal task organizer that syncs your class schedule (Canvas), calendar (Google Calendar,
or anything exportable as `.ics`, like Apple Calendar or Outlook), and ranks your to-do list the way
a product team ranks a feature backlog: using a RICE-inspired scoring model, adapted here as

    relevance_score = (urgency × importance × confidence) / effort

instead of manually deciding what to do next, or forgetting to study until the night before a
quiz, the scheduler:

- **Auto-generates prep tasks.** Detects "Quiz" / "Exam" / "Midterm" in your class schedule and
  creates study sessions and reminders automatically (a review task the night before a quiz, two
  study sessions, one a week out and one the day before, for an exam).
- **Ranks your open tasks by relevance**, not just by due date: a low-effort, high-importance
  task can outrank a due-sooner-but-trivial one.
- **Sequences your day by location**, not just by score: a flexible task is preferred in a gap
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
  demo.py                     Runnable end-to-end CLI demo, mock data, no credentials needed
  server.py                   FastAPI backend for the web app + Google OAuth flow
  store.py                    Saves tasks you add / check off (data/state.json, gitignored)
  integrations/
    google_calendar.py        OAuth sync: reads events, writes your plan back (your own Google Cloud credentials)
    canvas.py                 Canvas REST API sync (needs your own Canvas access token)
    ics_sync.py                Import/export .ics, covers Apple Calendar, Outlook, etc.
web/                          The web UI (plain HTML/CSS/JS, no build step)
app.py                        Original Streamlit prototype UI
tests/
  test_scoring.py
  test_scheduler.py
```

## Quickstart (no setup required)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.server:app --reload   # web app at http://localhost:8000
python -m pytest tests/           # scoring + scheduling tests
python -m src.demo                # CLI version of the same pipeline
```

The web app shows:

- **Day plan**: a timeline of your calendar events with Slate's suggested task blocks slotted into
  the gaps (location-aware, never in the past). Step through days with ‹ ›.
- **Up next**: your backlog ranked by relevance score. Check tasks off, or remove ones you added.
- **Ask Slate**: type an event the way you'd text it ("Math quiz Tuesday 5-6pm in Wartik Lab").
  Slate shows what it understood, and one click adds it to Google Calendar. Quizzes and exams
  you add this way immediately get prep tasks. Parsing is local and deterministic (`src/nlp.py`).
- **Add a task**: title, due date, effort, importance, location. Saved locally across restarts.
- **Auto prep**: study and review tasks generated from quizzes and exams on your calendar.
- **This week**: a 7-day strip. Click a day to plan it.
- **Add plan to Google Calendar**: writes the day's task blocks to your calendar. Running it again
  replaces Slate's earlier blocks for that day; it never touches your own events.

It runs on demo data until you connect Google Calendar.

## Connecting Google Calendar

One-time setup, about 10 minutes:

1. Go to [console.cloud.google.com](https://console.cloud.google.com), create a project, and
   **enable the Google Calendar API** (APIs & Services → Library).
2. **OAuth consent screen**: choose *External*, fill in the app name and your email, and add
   your own Google account under **Test users**.
3. **Credentials → Create credentials → OAuth client ID**, application type **Web application**.
   Under *Authorized redirect URIs* add exactly `http://localhost:8000/auth/callback`.
4. Download the JSON, rename it `credentials.json`, and put it in the project root.
5. Restart the server, open http://localhost:8000, and click **Connect Google Calendar**.
   Google will warn that the app is unverified (expected for a personal test app). Click
   *Continue*.

Your token is cached in `token.json`. **Disconnect** in the top bar revokes it.

### Demo week

To give a live demo something to show, fill the connected calendar with a realistic student week
(classes, office hours, a quiz, a midterm, a Canvas due date) plus a starter task list:

```bash
python -m src.demo_calendar seed --date 2027-01-11  # demo week starting that Monday
python -m src.demo_calendar clear                   # remove it all and leave demo mode
```

While a demo week is seeded, Slate is in **demo mode** (an orange "Demo week" badge): it reads
*only* the demo events, nothing from your real schedule, and pins "now" to 8:00 AM on the first
demo day, so the demo looks the same whenever you give it. Events added through Ask Slate during
demo mode are tagged as demo events too.

Demo events are privately tagged, so `clear` deletes only what `seed` (or Ask Slate in demo mode)
created, plus Slate's plan blocks, and never your own events. `seed` clears first, so re-run it
before each rehearsal.

> While the OAuth consent screen is in *Testing* mode, Google expires the login after 7 days.
> Reconnect shortly before a demo.

## Other calendar sources (optional)

**Recommended setup: one integration instead of two.** Canvas has a built-in "Calendar Feed"
(Canvas -> Calendar -> bottom-right "Calendar Feed" link), a private `.ics` URL you can subscribe
to directly from Google Calendar (Google Calendar → Other calendars → **+** → **From URL** →
paste the link). Every Canvas assignment and due date then shows up as a normal event on your
Google Calendar automatically, kept in sync going forward with zero extra code. That means the
app only needs to connect to **Google Calendar**; Canvas comes along for free.

| Source | What you need | Setup effort |
|---|---|---|
| Google Calendar (recommended; also covers Canvas via the feed above) | A Google Cloud OAuth client (`credentials.json`) | ~10 min, one-time |
| Canvas direct API (optional/advanced, only needed if the calendar feed doesn't expose something you want) | A personal access token from your school's Canvas | ~2 min |
| Apple Calendar / Outlook / anything else | Export as `.ics`, point `ics_sync.import_ics()` at it | ~1 min |

Credentials are never committed: `.gitignore` already excludes `credentials.json`, `token.json`,
and `.env`.

## Current scope vs. roadmap

**Built:** web app, relevance scoring, auto-generated exam/quiz prep tasks, location-aware daily
sequencing, two-way Google Calendar sync (read events, write plan), Canvas + `.ics` sync.

**Not yet built (good "phase 2" story):** live business-hours-aware suggestions (e.g., "hit the
gym before the coffee shop next door opens"), this needs a places/hours API (e.g., Google
Places) rather than manually-tagged locations, which is the natural next integration once the
core scheduling logic is proven out.
