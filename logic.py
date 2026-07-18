"""
logic.py — Adaptive Coach engine for the Performance Tracker.

Pure Python. No Streamlit imports here on purpose — this file should be
fully testable and reusable from a notebook, a script, or the app, with
zero UI code mixed in.

Local dev (no DATABASE_URL set) uses SQLite (tracker.db). Set DATABASE_URL
to a postgres:// / postgresql:// connection string (e.g. from Neon) and
this switches to Postgres automatically — nothing else in this file, or
in app.py, needs to change.
"""

import os
import sqlite3
from datetime import date, timedelta

from config import (
    STRENGTH_EXERCISES,
    CONDITIONING_METRICS,
    WEEKLY_PLAN_TARGETS,
    WORKOUT_CATEGORIES,
    SCORE_WEIGHTS,
    DEFAULT_DB_PATH,
)

# ---------------------------------------------------------------------------
# Connection / schema
# ---------------------------------------------------------------------------
# Both wrappers expose the same tiny interface (.execute, .executescript,
# .commit) so every query below is written once and works on either backend.
# "?" placeholders are used throughout; the Postgres wrapper translates them
# to "%s" before executing.

class _SQLiteConn:
    dialect = "sqlite"

    def __init__(self, path):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql, params=()):
        return self._conn.execute(sql, params)

    def executescript(self, sql):
        self._conn.executescript(sql)

    def commit(self):
        self._conn.commit()


class _PostgresConn:
    dialect = "postgres"

    def __init__(self, dsn):
        import psycopg2
        import psycopg2.extras
        self._psycopg2 = psycopg2
        self._extras = psycopg2.extras
        self._conn = psycopg2.connect(dsn)

    def execute(self, sql, params=()):
        cur = self._conn.cursor(cursor_factory=self._extras.RealDictCursor)
        cur.execute(sql.replace("?", "%s"), params)
        return cur

    def executescript(self, sql):
        cur = self._conn.cursor()
        cur.execute(sql)
        cur.close()

    def commit(self):
        self._conn.commit()


def get_connection(db_path: str = None):
    url = db_path or os.environ.get("DATABASE_URL")
    if url and url.startswith(("postgres://", "postgresql://")):
        return _PostgresConn(url)
    return _SQLiteConn(url or DEFAULT_DB_PATH)


_SQLITE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS strength_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        session TEXT,
        exercise TEXT NOT NULL,
        load REAL NOT NULL DEFAULT 0,
        set1 INTEGER, set2 INTEGER, set3 INTEGER, set4 INTEGER,
        total INTEGER,
        completed INTEGER,          -- 0/1
        rpe INTEGER,
        notes TEXT,
        week TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS conditioning_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        workout_type TEXT NOT NULL,
        metric TEXT,
        value REAL,
        completed INTEGER,
        rpe INTEGER,
        notes TEXT,
        week TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS body_comp_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        weight REAL NOT NULL,
        body_fat_pct REAL NOT NULL,
        lean_mass REAL,
        waist REAL,
        resting_hr REAL,
        notes TEXT,
        week TEXT NOT NULL
    );
"""

_POSTGRES_SCHEMA = """
    CREATE TABLE IF NOT EXISTS strength_log (
        id SERIAL PRIMARY KEY,
        date TEXT NOT NULL,
        session TEXT,
        exercise TEXT NOT NULL,
        load REAL NOT NULL DEFAULT 0,
        set1 INTEGER, set2 INTEGER, set3 INTEGER, set4 INTEGER,
        total INTEGER,
        completed INTEGER,
        rpe INTEGER,
        notes TEXT,
        week TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS conditioning_log (
        id SERIAL PRIMARY KEY,
        date TEXT NOT NULL,
        workout_type TEXT NOT NULL,
        metric TEXT,
        value REAL,
        completed INTEGER,
        rpe INTEGER,
        notes TEXT,
        week TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS body_comp_log (
        id SERIAL PRIMARY KEY,
        date TEXT NOT NULL,
        weight REAL NOT NULL,
        body_fat_pct REAL NOT NULL,
        lean_mass REAL,
        waist REAL,
        resting_hr REAL,
        notes TEXT,
        week TEXT NOT NULL
    );
"""


def init_db(conn):
    conn.executescript(_POSTGRES_SCHEMA if conn.dialect == "postgres" else _SQLITE_SCHEMA)
    conn.commit()


# ---------------------------------------------------------------------------
# Week bucketing (matches the Excel M/N/J "Week" columns: Monday of that week)
# ---------------------------------------------------------------------------

def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday=0


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_strength(conn, entry_date: date, session: str, exercise: str, load: float,
                  sets: list, rpe: int, completed: bool, notes: str = ""):
    if exercise not in STRENGTH_EXERCISES:
        raise ValueError(f"Unknown exercise: {exercise}")
    sets = list(sets) + [None] * (4 - len(sets))
    total = sum(s for s in sets if s is not None)
    conn.execute(
        """INSERT INTO strength_log
           (date, session, exercise, load, set1, set2, set3, set4, total, completed, rpe, notes, week)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (entry_date.isoformat(), session, exercise, load, *sets, total,
         int(completed), rpe, notes, week_start(entry_date).isoformat()),
    )
    conn.commit()


def log_conditioning(conn, entry_date: date, workout_type: str, metric: str, value: float,
                      rpe: int, completed: bool, notes: str = ""):
    conn.execute(
        """INSERT INTO conditioning_log
           (date, workout_type, metric, value, completed, rpe, notes, week)
           VALUES (?,?,?,?,?,?,?,?)""",
        (entry_date.isoformat(), workout_type, metric, value,
         int(completed), rpe, notes, week_start(entry_date).isoformat()),
    )
    conn.commit()


def log_body_comp(conn, entry_date: date, weight: float, body_fat_pct: float,
                   waist: float = None, resting_hr: float = None, notes: str = ""):
    lean_mass = weight * (1 - body_fat_pct)
    conn.execute(
        """INSERT INTO body_comp_log
           (date, weight, body_fat_pct, lean_mass, waist, resting_hr, notes, week)
           VALUES (?,?,?,?,?,?,?,?)""",
        (entry_date.isoformat(), weight, body_fat_pct, lean_mass, waist, resting_hr,
         notes, week_start(entry_date).isoformat()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# "Last logged" lookups (equivalent of the Excel LOOKUP(2,1/(...)) pattern)
# ---------------------------------------------------------------------------

def get_strength_pr(conn, exercise: str):
    """Best all-time workload for this exercise, or None if never logged."""
    row = conn.execute(
        "SELECT MAX(total * (1 + load / 100.0)) AS pr FROM strength_log WHERE exercise = ?",
        (exercise,),
    ).fetchone()
    return row["pr"] if row and row["pr"] is not None else None


def get_conditioning_pr(conn, metric: str):
    """Best all-time value for this metric (max or min, depending on direction), or None."""
    cfg = CONDITIONING_METRICS[metric]
    agg = "MAX" if cfg["higher_is_better"] else "MIN"
    row = conn.execute(
        f"SELECT {agg}(value) AS pr FROM conditioning_log WHERE metric = ?", (metric,)
    ).fetchone()
    return row["pr"] if row and row["pr"] is not None else None


def get_last_strength_entry(conn, exercise: str):
    row = conn.execute(
        """SELECT * FROM strength_log WHERE exercise = ?
           ORDER BY date DESC, id DESC LIMIT 1""",
        (exercise,),
    ).fetchone()
    return dict(row) if row else None


def get_last_conditioning_entry(conn, metric: str):
    row = conn.execute(
        """SELECT * FROM conditioning_log WHERE metric = ?
           ORDER BY date DESC, id DESC LIMIT 1""",
        (metric,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Adaptive Coach — strength
# ---------------------------------------------------------------------------

def _distribute_reps(total: int, sets: int, exercise: str) -> str:
    if exercise == "Dead hang":
        return f"{total} sec"
    base, remainder = divmod(total, sets)
    parts = [base + 1 if i < remainder else base for i in range(sets)]
    return " / ".join(str(p) for p in parts)


def get_next_strength_target(exercise: str, last: dict = None) -> dict:
    cfg = STRENGTH_EXERCISES[exercise]
    base_total = cfg["base_reps"] * cfg["sets"]
    max_total = cfg["max_reps"] * cfg["sets"]

    if last is None:
        return dict(
            next_load=0, next_total=base_total,
            reps_scheme=_distribute_reps(base_total, cfg["sets"], exercise),
            message="Start with the base target",
        )

    load = last["load"] or 0
    total = last["total"] or 0
    completed = bool(last["completed"])
    rpe = last["rpe"]

    if completed and rpe is not None and rpe <= cfg["easy_rpe"] and total >= max_total:
        next_load, next_total = load + cfg["load_step"], base_total
        message = "Add load; reset reps"
    elif completed and rpe is not None and rpe <= cfg["easy_rpe"]:
        next_load, next_total = load, total + 1
        message = "Progress by one rep"
    elif completed and rpe is not None and rpe <= cfg["hard_rpe"]:
        next_load, next_total = load, total
        message = "Repeat target"
    else:
        next_load = load
        next_total = max(base_total, total - cfg["decrease_if_failed"])
        message = "Reduce slightly and rebuild"

    return dict(
        next_load=next_load, next_total=next_total,
        reps_scheme=_distribute_reps(next_total, cfg["sets"], exercise),
        message=message,
    )


# ---------------------------------------------------------------------------
# Adaptive Coach — conditioning
# ---------------------------------------------------------------------------

def get_next_conditioning_target(conn, metric: str, last: dict = None) -> dict:
    cfg = CONDITIONING_METRICS[metric]

    if last is None:
        return dict(next_target=cfg["start"], message="Establish baseline")

    value = last["value"]
    completed = bool(last["completed"])
    rpe = last["rpe"]

    # Hill sprint duration only advances once Hill sprint reps has hit its cap
    if "depends_on" in cfg:
        gate_metric, gate_value = cfg["depends_on"]
        gate_last = get_last_conditioning_entry(conn, gate_metric)
        gated_open = bool(gate_last and gate_last["value"] is not None and gate_last["value"] >= gate_value)
        if not gated_open:
            return dict(next_target=value, message="Keep duration")
        if completed and rpe is not None and rpe <= 7:
            return dict(next_target=value + cfg["easy"], message="Add one second per sprint")
        return dict(next_target=value, message="Keep duration")

    if completed and rpe is not None and rpe <= 7:
        delta = cfg["easy"]
    elif completed and rpe is not None and rpe <= 9:
        delta = cfg["moderate"]
    else:
        delta = cfg["hard"]

    next_value = value + delta
    if "min_value" in cfg:
        next_value = max(cfg["min_value"], next_value)
    if "max_value" in cfg:
        next_value = min(cfg["max_value"], next_value)

    if cfg["higher_is_better"]:
        message = "Increase target" if next_value > value else ("Repeat target" if next_value == value else "Reduce slightly")
    else:
        message = "Faster target" if next_value < value else ("Repeat target" if next_value == value else "Back off slightly")

    return dict(next_target=next_value, message=message)


# ---------------------------------------------------------------------------
# Weekly summary + scoring
# ---------------------------------------------------------------------------

def get_weekly_summary(conn, num_weeks: int = 12) -> list:
    """
    Returns one dict per week, oldest -> newest, for the last `num_weeks` weeks
    up to and including the current week. Indices are self-normalizing against
    the best value seen up to and including that week (a personal-best = 100).
    """
    this_week = week_start(date.today())
    weeks = [this_week - timedelta(weeks=i) for i in range(num_weeks - 1, -1, -1)]

    running_strength_pr = 0.0
    running_conditioning_pr = {m: None for m in CONDITIONING_METRICS}
    running_lean_mass_pr = 0.0

    summaries = []
    for wk in weeks:
        wk_str = wk.isoformat()

        strength_sessions = conn.execute(
            "SELECT COUNT(DISTINCT session) AS n FROM strength_log WHERE week = ?", (wk_str,)
        ).fetchone()["n"]

        cond_rows = conn.execute(
            "SELECT workout_type, metric, value FROM conditioning_log WHERE week = ?", (wk_str,)
        ).fetchall()
        mobility_sessions = sum(1 for r in cond_rows if r["workout_type"] == "Mobility")
        plan_sessions = {wt: sum(1 for r in cond_rows if r["workout_type"] == wt)
                          for wt in ("Jump circuit", "Rowing", "Hill sprints")}
        conditioning_sessions = sum(plan_sessions.values())

        strength_volume = conn.execute(
            "SELECT COALESCE(SUM(total * (1 + load / 100.0)), 0) AS n FROM strength_log WHERE week = ?",
            (wk_str,),
        ).fetchone()["n"]
        running_strength_pr = max(running_strength_pr, strength_volume)
        strength_index = (100 * strength_volume / running_strength_pr) if strength_volume > 0 else None

        # Conditioning: best value per metric this week, normalized against PR-to-date
        metric_scores = []
        for metric, cfg in CONDITIONING_METRICS.items():
            vals = [r["value"] for r in cond_rows if r["metric"] == metric and r["value"] is not None]
            if not vals:
                continue
            best_this_week = max(vals) if cfg["higher_is_better"] else min(vals)
            prev_pr = running_conditioning_pr[metric]
            if prev_pr is None:
                pr = best_this_week
            else:
                pr = max(prev_pr, best_this_week) if cfg["higher_is_better"] else min(prev_pr, best_this_week)
            running_conditioning_pr[metric] = pr
            if pr == 0:
                continue
            score = (100 * best_this_week / pr) if cfg["higher_is_better"] else (100 * pr / best_this_week)
            metric_scores.append(score)
        conditioning_index = (sum(metric_scores) / len(metric_scores)) if metric_scores else None

        bc_row = conn.execute(
            "SELECT lean_mass FROM body_comp_log WHERE week = ? ORDER BY date DESC LIMIT 1", (wk_str,)
        ).fetchone()
        if bc_row and bc_row["lean_mass"] is not None:
            running_lean_mass_pr = max(running_lean_mass_pr, bc_row["lean_mass"])
            body_comp_index = 100 * bc_row["lean_mass"] / running_lean_mass_pr if running_lean_mass_pr else None
        else:
            body_comp_index = None

        consistency = min(1.0, (
            (strength_sessions / WEEKLY_PLAN_TARGETS["Strength"]) +
            (conditioning_sessions / (WEEKLY_PLAN_TARGETS["Jump circuit"] +
                                       WEEKLY_PLAN_TARGETS["Rowing"] +
                                       WEEKLY_PLAN_TARGETS["Hill sprints"])) +
            (mobility_sessions / WEEKLY_PLAN_TARGETS["Mobility"])
        ) / 3)
        mobility_ratio = min(1.0, mobility_sessions / WEEKLY_PLAN_TARGETS["Mobility"])
        any_session_logged = (strength_sessions + conditioning_sessions + mobility_sessions) > 0

        # Overall score only averages categories with real data this week —
        # weights are renormalized over whatever's actually present, rather
        # than padding missing categories with an assumed 100.
        active_scores = {}
        if strength_index is not None:
            active_scores["strength"] = strength_index
        if conditioning_index is not None:
            active_scores["conditioning"] = conditioning_index
        if body_comp_index is not None:
            active_scores["body_comp"] = body_comp_index
        if any_session_logged:
            active_scores["consistency"] = consistency * 100
        if mobility_sessions > 0:
            active_scores["mobility"] = mobility_ratio * 100

        if active_scores:
            weight_sum = sum(SCORE_WEIGHTS[k] for k in active_scores)
            overall_score = sum(SCORE_WEIGHTS[k] * v for k, v in active_scores.items()) / weight_sum
        else:
            overall_score = None

        summaries.append(dict(
            week=wk_str,
            strength_sessions=strength_sessions,
            conditioning_sessions=conditioning_sessions,
            mobility_sessions=mobility_sessions,
            strength_volume=strength_volume,
            strength_index=strength_index,
            conditioning_index=conditioning_index,
            body_comp_index=body_comp_index,
            consistency=consistency,
            overall_score=round(overall_score, 1) if overall_score is not None else None,
        ))

    return summaries


def get_week_category_counts(conn, wk: date = None) -> dict:
    """Sessions logged so far this week, broken down by weekly-plan category."""
    wk = wk or week_start(date.today())
    wk_str = wk.isoformat()
    counts = {
        "Strength": conn.execute(
            "SELECT COUNT(DISTINCT session) AS n FROM strength_log WHERE week = ?", (wk_str,)
        ).fetchone()["n"]
    }
    for cat in ("Jump circuit", "Rowing", "Hill sprints", "Mobility"):
        counts[cat] = conn.execute(
            "SELECT COUNT(*) AS n FROM conditioning_log WHERE week = ? AND workout_type = ?",
            (wk_str, cat),
        ).fetchone()["n"]
    return counts


def get_todays_suggestion(conn) -> dict:
    """
    Picks whichever weekly-plan category is furthest behind target, then the
    specific exercise/metric within it that's least recently trained. This is
    a suggestion, not a schedule — logging something else instead is always
    a first-class option in the app, and doesn't break anything here, since
    every exercise/metric tracks its own progression independent of this.
    """
    counts = get_week_category_counts(conn)
    remaining = {cat: WEEKLY_PLAN_TARGETS[cat] - counts.get(cat, 0) for cat in WEEKLY_PLAN_TARGETS}
    priority_order = list(WEEKLY_PLAN_TARGETS.keys())
    best_cat = max(priority_order, key=lambda c: (remaining[c], -priority_order.index(c)))
    cat_info = WORKOUT_CATEGORIES[best_cat]

    if cat_info["kind"] == "strength":
        # Least-recently-trained exercise in this category (never-trained sorts first)
        ranked = sorted(
            cat_info["items"],
            key=lambda ex: (get_last_strength_entry(conn, ex) or {}).get("date", ""),
        )
        exercise = ranked[0]
        target = get_next_strength_target(exercise, get_last_strength_entry(conn, exercise))
        return dict(category=best_cat, kind="strength", exercise=exercise, target=target,
                    remaining_this_week=remaining[best_cat])

    if cat_info["kind"] == "conditioning":
        metric = cat_info["items"][0]  # hill sprints leads with reps; duration follows once reps are maxed
        target = get_next_conditioning_target(conn, metric, get_last_conditioning_entry(conn, metric))
        return dict(category=best_cat, kind="conditioning", metric=metric, target=target,
                    remaining_this_week=remaining[best_cat])

    return dict(category=best_cat, kind="mobility", remaining_this_week=remaining[best_cat])


def get_dashboard(conn, trend_weeks: int = 12) -> dict:
    """Everything the Dashboard screen needs in one call."""
    weekly = get_weekly_summary(conn, num_weeks=trend_weeks)
    latest = weekly[-1] if weekly else None

    next_strength = {}
    for exercise in STRENGTH_EXERCISES:
        last = get_last_strength_entry(conn, exercise)
        next_strength[exercise] = get_next_strength_target(exercise, last)

    next_conditioning = {}
    for metric in CONDITIONING_METRICS:
        last = get_last_conditioning_entry(conn, metric)
        next_conditioning[metric] = get_next_conditioning_target(conn, metric, last)

    # A "recent PR" = the most recent logged entry for that exercise/metric IS
    # the all-time best. Cheap and honest: no separate PR table to keep in sync.
    recent_prs = []
    for exercise in STRENGTH_EXERCISES:
        last = get_last_strength_entry(conn, exercise)
        if not last:
            continue
        workload = last["total"] * (1 + (last["load"] or 0) / 100.0)
        if workload >= (get_strength_pr(conn, exercise) or 0):
            recent_prs.append(dict(name=exercise, date=last["date"], detail=f"{last['total']} reps @ {last['load']} lb"))
    for metric in CONDITIONING_METRICS:
        last = get_last_conditioning_entry(conn, metric)
        if not last or last["value"] is None:
            continue
        pr = get_conditioning_pr(conn, metric)
        cfg = CONDITIONING_METRICS[metric]
        is_pr = pr is not None and (last["value"] >= pr if cfg["higher_is_better"] else last["value"] <= pr)
        if is_pr:
            recent_prs.append(dict(name=metric, date=last["date"], detail=f"{last['value']} {cfg['unit']}"))

    return dict(
        latest_week=latest,
        weekly_trend=weekly,
        next_strength=next_strength,
        next_conditioning=next_conditioning,
        recent_prs=recent_prs,
    )
