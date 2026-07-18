"""
app.py — Performance Tracker (mobile-first Streamlit interface)

Opens straight to "what's due today," lets you log something else instead
with one tap, confirms PRs on the spot, and rolls everything into a
Dashboard with score cards and trend charts.
"""

from datetime import date
import os

import pandas as pd
import streamlit as st

import logic
from config import STRENGTH_EXERCISES, CONDITIONING_METRICS, WORKOUT_CATEGORIES

st.set_page_config(page_title="Performance Tracker", page_icon="💪", layout="centered")

# On Streamlit Community Cloud, DATABASE_URL lives in st.secrets (set via the
# app's Settings > Secrets). Locally, there's usually no secrets.toml file at
# all, which makes st.secrets raise rather than just being empty — so this is
# wrapped in a try/except and quietly falls back to local SQLite.
try:
    if "DATABASE_URL" in st.secrets:
        os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
except Exception:
    pass

# ---------------------------------------------------------------------------
# Mobile-first styling — bigger tap targets, tighter top padding, cleaner type
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 640px; }
        div[data-testid="stButton"] button {
            min-height: 3rem; font-size: 1.05rem; font-weight: 600; border-radius: 0.6rem;
        }
        div[data-testid="stFormSubmitButton"] button {
            min-height: 3.2rem; font-size: 1.1rem; font-weight: 700; border-radius: 0.6rem;
        }
        div[data-testid="stMetricValue"] { font-size: 1.6rem; }
        .streamlit-expanderHeader { font-size: 1rem; }
        div[data-testid="stNumberInput"] input { min-height: 2.6rem; font-size: 1.05rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_conn():
    conn = logic.get_connection()
    logic.init_db(conn)
    return conn


conn = get_conn()

st.title("💪 Performance Tracker")

tab_log, tab_dashboard = st.tabs(["🏋️ Log a workout", "📊 Dashboard"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def reset_active_target():
    for key in ("active_category", "active_kind", "active_item"):
        st.session_state.pop(key, None)


def render_suggestion_card(suggestion):
    remaining = suggestion["remaining_this_week"]
    due_note = f"{remaining} more this week to hit target" if remaining > 0 else "Weekly target already hit — bonus session"

    if suggestion["kind"] == "strength":
        target = suggestion["target"]
        load_note = f" at **{target['next_load']:g} lb**" if target["next_load"] else ""
        st.info(
            f"**Today's suggestion — {suggestion['category']}: {suggestion['exercise']}**\n\n"
            f"Target: **{target['reps_scheme']}**{load_note}\n\n"
            f"_{target['message']}_ · {due_note}"
        )
    elif suggestion["kind"] == "conditioning":
        metric = suggestion["metric"]
        target = suggestion["target"]
        unit = CONDITIONING_METRICS[metric]["unit"]
        st.info(
            f"**Today's suggestion — {suggestion['category']}: {metric}**\n\n"
            f"Target: **{target['next_target']:g} {unit}**\n\n"
            f"_{target['message']}_ · {due_note}"
        )
    else:
        st.info(f"**Today's suggestion — {suggestion['category']}**\n\nAny mobility session counts · {due_note}")


# ---------------------------------------------------------------------------
# LOG A WORKOUT
# ---------------------------------------------------------------------------
with tab_log:
    suggestion = logic.get_todays_suggestion(conn)

    if "active_category" not in st.session_state:
        st.session_state.active_category = suggestion["category"]
        st.session_state.active_kind = suggestion["kind"]
        st.session_state.active_item = suggestion.get("exercise") or suggestion.get("metric")

    render_suggestion_card(suggestion)

    with st.expander("🔄 Doing something else instead"):
        categories = list(WORKOUT_CATEGORIES.keys())
        cat_choice = st.selectbox("Category", categories,
                                   index=categories.index(st.session_state.active_category))
        cat_info = WORKOUT_CATEGORIES[cat_choice]

        item_choice = None
        if cat_info["kind"] == "strength":
            item_choice = st.selectbox("Exercise", cat_info["items"])
        elif cat_info["kind"] == "conditioning":
            item_choice = st.selectbox("Metric", cat_info["items"])

        if st.button("Switch to this", use_container_width=True):
            st.session_state.active_category = cat_choice
            st.session_state.active_kind = cat_info["kind"]
            st.session_state.active_item = item_choice
            st.rerun()

    st.divider()

    kind = st.session_state.active_kind
    item = st.session_state.active_item

    # --- Strength logging form -------------------------------------------
    if kind == "strength":
        cfg = STRENGTH_EXERCISES[item]
        last = logic.get_last_strength_entry(conn, item)
        target = logic.get_next_strength_target(item, last)
        st.markdown(f"### Log: {item}")
        st.caption(f"Aiming for {target['reps_scheme']}" + (f" at {target['next_load']:g} lb" if target["next_load"] else ""))

        with st.form(f"strength_form_{item}", clear_on_submit=True):
            load = st.number_input("Load (lb, 0 if bodyweight)", min_value=0.0,
                                    value=float(target["next_load"] or 0), step=2.5)
            cols = st.columns(cfg["sets"])
            sets = []
            default_reps = target["next_total"] // cfg["sets"]
            for i, c in enumerate(cols):
                with c:
                    sets.append(st.number_input(f"Set {i+1}", min_value=0, value=int(default_reps), step=1, key=f"set_{item}_{i}"))
            completed = st.segmented_control("Completed target?", ["Yes", "No"], default="Yes", key=f"completed_{item}")
            rpe = st.pills("RPE", list(range(1, 11)), default=7, key=f"rpe_{item}")
            notes = st.text_input("Notes (optional)", key=f"notes_{item}")
            submitted = st.form_submit_button("✅ Log it", use_container_width=True)

        if submitted:
            prev_pr = logic.get_strength_pr(conn, item)
            logic.log_strength(conn, date.today(), f"session-{date.today().isoformat()}", item,
                                load=load, sets=sets, rpe=rpe, completed=(completed == "Yes"), notes=notes)
            new_workload = sum(sets) * (1 + load / 100.0)
            is_pr = prev_pr is None or new_workload >= prev_pr
            next_up = logic.get_next_strength_target(item, logic.get_last_strength_entry(conn, item))
            if is_pr:
                st.balloons()
                st.success(f"🏆 New PR on {item}! Next time: **{next_up['reps_scheme']}** — {next_up['message']}")
            else:
                st.success(f"Logged. Next time: **{next_up['reps_scheme']}** — {next_up['message']}")
            reset_active_target()

    # --- Conditioning logging form -----------------------------------------
    elif kind == "conditioning":
        cfg = CONDITIONING_METRICS[item]
        last = logic.get_last_conditioning_entry(conn, item)
        target = logic.get_next_conditioning_target(conn, item, last)
        category = st.session_state.active_category
        st.markdown(f"### Log: {item}")
        st.caption(f"Aiming for {target['next_target']:g} {cfg['unit']}")

        with st.form(f"conditioning_form_{item}", clear_on_submit=True):
            value = st.number_input(f"Result ({cfg['unit']})", min_value=0.0,
                                     value=float(target["next_target"]), step=1.0)
            completed = st.segmented_control("Completed target?", ["Yes", "No"], default="Yes", key=f"c_completed_{item}")
            rpe = st.pills("RPE", list(range(1, 11)), default=7, key=f"c_rpe_{item}")
            notes = st.text_input("Notes (optional)", key=f"c_notes_{item}")
            submitted = st.form_submit_button("✅ Log it", use_container_width=True)

        if submitted:
            prev_pr = logic.get_conditioning_pr(conn, item)
            logic.log_conditioning(conn, date.today(), category, item, value=value,
                                    rpe=rpe, completed=(completed == "Yes"), notes=notes)
            is_pr = prev_pr is None or (value >= prev_pr if cfg["higher_is_better"] else value <= prev_pr)
            next_up = logic.get_next_conditioning_target(conn, item, logic.get_last_conditioning_entry(conn, item))
            if is_pr:
                st.balloons()
                st.success(f"🏆 New PR on {item}! Next time: **{next_up['next_target']:g} {cfg['unit']}** — {next_up['message']}")
            else:
                st.success(f"Logged. Next time: **{next_up['next_target']:g} {cfg['unit']}** — {next_up['message']}")
            reset_active_target()

    # --- Mobility logging form ----------------------------------------------
    else:
        st.markdown("### Log: Mobility")
        with st.form("mobility_form", clear_on_submit=True):
            duration = st.number_input("Minutes", min_value=0, value=10, step=5)
            notes = st.text_input("Notes (optional)", key="mobility_notes")
            submitted = st.form_submit_button("✅ Log it", use_container_width=True)
        if submitted:
            logic.log_conditioning(conn, date.today(), "Mobility", None, value=duration,
                                    rpe=None, completed=True, notes=notes)
            st.success("Logged — nice work.")
            reset_active_target()


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------
with tab_dashboard:
    dash = logic.get_dashboard(conn, trend_weeks=12)
    latest = dash["latest_week"]

    st.subheader("This week")
    if latest is None or latest["overall_score"] is None:
        st.caption("Log a workout to see your first score.")
    else:
        r1c1, r1c2 = st.columns(2)
        r1c1.metric("Overall score", f"{latest['overall_score']:.0f}")
        r1c2.metric("Strength index", f"{latest['strength_index']:.0f}" if latest["strength_index"] is not None else "—")
        r2c1, r2c2 = st.columns(2)
        r2c1.metric("Conditioning index", f"{latest['conditioning_index']:.0f}" if latest["conditioning_index"] is not None else "—")
        r2c2.metric("Consistency", f"{latest['consistency']*100:.0f}%")

    if dash["recent_prs"]:
        st.subheader("🏆 Standing PRs")
        for pr in dash["recent_prs"]:
            st.success(f"**{pr['name']}** — {pr['detail']} ({pr['date']})")

    trend_df = pd.DataFrame(dash["weekly_trend"])
    if not trend_df.empty and trend_df["overall_score"].notna().any():
        trend_df["week"] = pd.to_datetime(trend_df["week"])
        st.subheader("Overall score by week")
        st.line_chart(trend_df.set_index("week")["overall_score"])

    if not trend_df.empty and (trend_df["strength_volume"] > 0).any():
        st.subheader("Strength volume trend")
        st.bar_chart(trend_df.set_index("week")["strength_volume"])

    st.subheader("Next targets")
    rows = []
    for exercise, t in dash["next_strength"].items():
        rows.append(dict(Category="Strength", Item=exercise, Target=t["reps_scheme"] +
                          (f" @ {t['next_load']:g} lb" if t["next_load"] else ""), Note=t["message"]))
    for metric, t in dash["next_conditioning"].items():
        unit = CONDITIONING_METRICS[metric]["unit"]
        rows.append(dict(Category="Conditioning", Item=metric, Target=f"{t['next_target']:g} {unit}", Note=t["message"]))
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
