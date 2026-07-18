"""
config.py — Tunable rules for the Performance Tracker.

This is the equivalent of the Setup tab in the old spreadsheet: every number
that defines "what counts as progress" lives here, not buried in logic.py.
Edit this file to change progression rules — no need to touch the engine.
"""

# ---------------------------------------------------------------------------
# Strength exercises
# ---------------------------------------------------------------------------
# base_reps / sets   -> starting rep scheme (e.g. 6 reps x 4 sets)
# max_reps           -> reps/set ceiling before you add load and reset
# load_step          -> how much load to add when you hit the ceiling
# easy_rpe           -> RPE at or below this + target met -> progress
# hard_rpe           -> RPE at or below this (but above easy) -> repeat
#                        (above hard_rpe, or target missed -> reduce)
# decrease_if_failed -> how many reps/lb to back off on failure
STRENGTH_EXERCISES = {
    "Pull-ups":       dict(base_reps=6,  sets=4, max_reps=12, load_step=5,  easy_rpe=7, hard_rpe=9, decrease_if_failed=1, unit="reps"),
    "Dips":           dict(base_reps=8,  sets=4, max_reps=20, load_step=5,  easy_rpe=7, hard_rpe=9, decrease_if_failed=1, unit="reps"),
    "Toes-to-bar":    dict(base_reps=6,  sets=4, max_reps=15, load_step=0,  easy_rpe=7, hard_rpe=9, decrease_if_failed=1, unit="reps"),
    "Pistol squats":  dict(base_reps=3,  sets=4, max_reps=10, load_step=5,  easy_rpe=7, hard_rpe=9, decrease_if_failed=1, unit="reps/leg"),
    "Push-ups":       dict(base_reps=10, sets=4, max_reps=25, load_step=10, easy_rpe=7, hard_rpe=9, decrease_if_failed=2, unit="reps"),
    "Dead hang":      dict(base_reps=30, sets=1, max_reps=90, load_step=5,  easy_rpe=7, hard_rpe=9, decrease_if_failed=5, unit="seconds"),
}

# ---------------------------------------------------------------------------
# Conditioning metrics
# ---------------------------------------------------------------------------
# start              -> baseline target before any data exists
# easy / moderate / hard -> adjustment applied at each RPE tier
# higher_is_better   -> True for jump rope / hill sprints, False for rowing
# min_value / max_value -> guard rails so targets can't run away
# depends_on         -> (optional) another metric that must be "maxed" first
CONDITIONING_METRICS = {
    "Jump rope 10 min":    dict(start=1250, easy=25,   moderate=10, hard=-10, unit="jumps",     higher_is_better=True,  min_value=0),
    "Row intervals":       dict(start=120,  easy=-0.5, moderate=0,  hard=1,   unit="sec/500m",  higher_is_better=False, min_value=60),
    "Hill sprint reps":    dict(start=6,    easy=1,    moderate=0,  hard=-1,  unit="reps",      higher_is_better=True,  min_value=4, max_value=10),
    "Hill sprint duration": dict(start=10,  easy=1,    moderate=0,  hard=0,   unit="seconds",   higher_is_better=True,  min_value=10,
                                  depends_on=("Hill sprint reps", 10)),  # only climbs once hill sprint reps has hit 10
}

# ---------------------------------------------------------------------------
# Weekly plan — how many sessions of each type you're aiming for per week
# ---------------------------------------------------------------------------
WEEKLY_PLAN_TARGETS = {
    "Strength": 2,
    "Jump circuit": 1,
    "Rowing": 1,
    "Hill sprints": 1,
    "Mobility": 3,
}

# What each weekly-plan category actually means when it's time to log something.
# "Strength" covers every strength exercise; the coach picks whichever one you
# haven't trained most recently. Conditioning categories map to one (or, for
# hill sprints, two related) metrics.
WORKOUT_CATEGORIES = {
    "Strength":     dict(kind="strength",     items=list(STRENGTH_EXERCISES.keys())),
    "Jump circuit": dict(kind="conditioning", items=["Jump rope 10 min"]),
    "Rowing":       dict(kind="conditioning", items=["Row intervals"]),
    "Hill sprints": dict(kind="conditioning", items=["Hill sprint reps", "Hill sprint duration"]),
    "Mobility":     dict(kind="mobility",     items=[]),
}

# ---------------------------------------------------------------------------
# Overall score weights — must sum to 1.0
# ---------------------------------------------------------------------------
SCORE_WEIGHTS = dict(
    strength=0.35,
    conditioning=0.30,
    body_comp=0.15,
    consistency=0.10,
    mobility=0.10,
)

RPE_SCALE = list(range(1, 11))

# Training week starts Monday (Python weekday(): Monday=0)
WEEK_START_WEEKDAY = 0

# Local dev database. Overridden by DATABASE_URL env var when deployed to Neon.
DEFAULT_DB_PATH = "tracker.db"
