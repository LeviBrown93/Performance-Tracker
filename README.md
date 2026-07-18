# Performance Tracker

A personal adaptive-coach app: log strength sets, conditioning sessions, and
weekly body-composition readings from your phone in under 15 seconds, and it
tells you exactly how hard to push next time — same logic that used to live
in a spreadsheet, now as a real mobile-first app.

## What it does

- Opens to **"today's suggestion"** — whatever's most behind on your weekly
  plan — but logging something else instead is always one tap away.
- Every strength exercise and conditioning metric tracks its own progression
  independently: complete a target at an easy RPE and it pushes you further;
  miss it and it backs off. No fixed schedule to fight against.
- Confirms PRs the moment you log one.
- Dashboard: this week's scores, trend charts, standing PRs, and a full table
  of next targets for everything you track.

## Files

| File | What it is |
|---|---|
| `config.py` | Every tunable rule (progression rates, weekly targets, score weights). Edit this to change behavior — no need to touch the logic. |
| `logic.py` | The adaptive-coach engine. Pure Python, no UI, fully unit-tested against hand-worked examples. |
| `app.py` | The Streamlit interface. |
| `requirements.txt` | Python dependencies. |
| `secrets.toml.example` | Template for the Neon database connection string (Streamlit Cloud only — not needed to run locally). |

## Running it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`. With no `DATABASE_URL` set, it uses a local
SQLite file (`tracker.db`) automatically — nothing else to configure.

## Deploying (so it works from your phone, anywhere)

See the step-by-step deployment guide for:
1. Pushing this folder to GitHub
2. Creating a free Neon Postgres database
3. Deploying to Streamlit Community Cloud
4. Setting the `DATABASE_URL` secret
5. Setting up a free UptimeRobot ping so the app never sleeps

## Data model

Three tables: `strength_log`, `conditioning_log`, `body_comp_log`. Works
identically on local SQLite or hosted Postgres — `logic.py` picks the right
one automatically based on whether `DATABASE_URL` is set.
