"""Presentation-only monitoring; explanation requests always require an explicit click."""
from pathlib import Path
import html
import os
import sys
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import monitor_data as data

st.set_page_config(page_title="MforMusic Monitor", page_icon="♫", layout="wide")
st.markdown("""<style>
.stApp {background:#101318;color:#edf1f7;}
[data-testid="stSidebar"] {background:#171c24;}
h1,h2,h3 {letter-spacing:-.025em;}
[data-testid="stMetric"] {background:#1b222c;border:1px solid #303b4b;border-radius:12px;padding:16px;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:14px;}
.stButton>button {border-radius:9px;min-height:44px;}
.event {padding:12px 0;border-bottom:1px solid #303b4b;line-height:1.5;}
.event small {color:#aab8cb;}
.badge {display:inline-block;padding:3px 9px;border-radius:6px;background:#293344;font-size:13px;}
</style>""", unsafe_allow_html=True)

TIER_NAMES = {"collaborative_filtering": "CF · Listening patterns", "content_based": "Content · Similar songs",
              "popular": "Popular · Global activity", "cold_start": "Cold start", "unknown": "Unknown"}
DEFAULT_BASE = os.getenv("EXPLAINABILITY_API_URL", "http://localhost:8000/api/v1/explainability").rstrip("/")
DEFAULT_BASE = DEFAULT_BASE.removesuffix("/api/v1/explainability")

with st.sidebar:
    st.header("Monitor controls")
    live = st.toggle("Live updates", value=True)
    st.caption("Activity: every 5 seconds\n\nModels: every 30 seconds")
    st.caption("Updates run while this dashboard session is active. Slow connections can delay a tick.")
    with st.expander("Connection settings"):
        base = st.text_input("FastAPI address", DEFAULT_BASE).rstrip("/")
        st.caption("Database connections use the project's existing environment settings. Credentials are never displayed.")
    st.divider()
    st.caption("This view reads activity and requests explanations. It does not train models or generate test interactions.")

st.title("MforMusic Monitor")
st.write("See recent listening activity, inspect recommendations, and understand the factors behind a score.")


def esc(value):
    return html.escape(str(value))


def retained(key, result):
    """Keep last successful data visible after a failed refresh, explicitly marked stale."""
    if result.get("ok"):
        st.session_state[key] = result
        return result
    previous = st.session_state.get(key)
    if previous:
        return {**previous, "stale": True}
    return result


def status_note(result, label):
    if result.get("stale"):
        st.warning(f"{label}: connection unavailable. Showing last successful update: {result['at']}.")
    elif not result.get("ok"):
        st.warning(f"{label}: unavailable. This does not mean there is no activity.")
    else:
        st.caption(f"{label} · updated {result['at']}")


@st.fragment(run_every="30s" if live else None)
def overview():
    st.subheader("System overview")
    st.caption("Active models and monitoring coverage. Missing measurements are shown explicitly.")
    cf = retained(f"cf:{base}", data.model_status(base, "/api/v1/recommendations/model/status"))
    content = retained(f"content:{base}", data.model_status(base, "/api/v1/content/model/status"))
    a, b, c = st.columns(3)
    for column, title, response, ready in ((a, "Collaborative filtering", cf, "trained"),
                                          (b, "Content similarity", content, "ready")):
        with column:
            body = response.get("data", {})
            state = "Ready" if body.get(ready) else "Not ready"
            if not response.get("ok"):
                state = "Unavailable"
            if response.get("stale"):
                state = "Stale"
            st.metric(title, state)
            st.write("Version:", body.get("model_version") or "Unavailable")
            st.caption("Last successful retrain: Not recorded")
            if title == "Content similarity" and body.get("retraining"):
                st.info("Retraining is in progress.")
            status_note(response, title)
    with c:
        st.metric("Tier distribution over time", "Not recorded")
        st.caption("CF · Content · Popular")
        st.info("Recommendation events are not stored. A reliable historical percentage cannot be calculated yet.")
    with st.expander("How to interpret this overview"):
        st.write("A rising Popular share can indicate reduced personalization, but it can also reflect new users. No percentages are inferred from interaction logs or surrogate training data.")
        st.write("Current status endpoints expose model versions, but not last successful retrain timestamps. A version change or file modification time is not presented as a retrain time.")


overview()
st.divider()
left, right = st.columns([1, 2], gap="large")


@st.fragment(run_every="5s" if live else None)
def live_feed():
    st.subheader("Live feed")
    st.caption("Recent registrations and listening activity. Recommendation event history is not recorded.")
    source = st.selectbox("Activity source", ["Backend received", "Available to ML"], key="feed_source")
    kind = "mysql" if source == "Backend received" else "postgres"
    people = retained("registrations", data.users())
    activity = retained(f"activity:{kind}", data.activity(kind))
    status_note(people, "Registrations")
    status_note(activity, source)
    registrations = [{"event": "Registered", "user": str(r["id"]), "detail": r["username"],
                      "at": str(r["created_at"]), "source": "Account database"} for r in people.get("rows", [])[:30]]
    events = [{"event": str(r["interaction_type"]).replace("_", " ").title(),
               "user": str(r["user_id"]), "detail": str(r["song_id"]), "at": str(r["created_at"]),
               "source": source} for r in activity.get("rows", [])]
    tab_activity, tab_registrations = st.tabs(["Activity", "Registrations"])
    for tab, rows in ((tab_activity, events), (tab_registrations, registrations)):
        with tab:
            if not rows:
                st.info("No records to display in this source's recent window.")
            for row in rows[:15]:
                st.markdown(f'<div class="event"><strong>{esc(row["event"])}</strong> · User {esc(row["user"])}<br>'
                            f'{esc(row["detail"])}<br><small>{esc(row["at"])} · {esc(row["source"])}</small></div>', unsafe_allow_html=True)
    st.caption("Latest 15 shown per tab. Database timestamps are displayed as stored; different database time zones may differ. These are separate observations, not merged duplicate events.")


with left:
    live_feed()


def explanation_chart(response, metadata):
    values = response.get("shap_values", {})
    if not values:
        st.info("No factor contributions were returned.")
        return
    ranked = sorted(values.items(), key=lambda pair: abs(pair[1]), reverse=True)
    labels = [metadata.get(k, {}).get("label", k.replace("_", " ").capitalize()) for k, _ in ranked]
    numbers = [float(v) for _, v in ranked]
    st.write("These factors raise or lower the explanation model’s estimated score for this song.")
    fig = go.Figure(go.Bar(x=numbers, y=labels, orientation="h",
                          marker_color=["#62b5ff" if v >= 0 else "#ffb16b" for v in numbers],
                          text=[f"{v:+.3f}" for v in numbers], textposition="outside",
                          cliponaxis=False, hovertemplate="%{y}<br>Score contribution: %{x:+.4f}<extra></extra>"))
    fig.update_layout(template="plotly_dark", paper_bgcolor="#101318", plot_bgcolor="#101318",
                      height=max(360, len(labels) * 39 + 100), margin=dict(l=10, r=65, t=20, b=60),
                      xaxis_title="Change in surrogate score (SHAP contribution)",
                      yaxis=dict(title="Contributing factor", autorange="reversed"),
                      font=dict(size=14), showlegend=False)
    fig.add_vline(x=0, line_color="#c5d1e0", line_width=1)
    st.caption("Blue / + raises score · Orange / − lowers score. Contributions are score units, not percentages or proof of causation.")
    st.plotly_chart(fig, use_container_width=True, key="shap_chart")
    with st.expander("Exact contributions"):
        st.dataframe(pd.DataFrame({"Factor": labels, "Score contribution": numbers}), hide_index=True, use_container_width=True)


with right:
    st.subheader("Per-user drill-down")
    st.caption("Choose an account, fetch its current recommendations, then explain a song on demand.")
    people = data.users()
    if not people.get("ok"):
        st.caption("Account directory unavailable. You can still enter a user ID below.")
    directory = {str(r["id"]): r["username"] for r in people.get("rows", [])}
    picked = st.selectbox("Search accounts", [""] + list(directory),
                         format_func=lambda uid: f'{directory[uid]} · ID {uid}' if uid else "Select an account")
    entered = st.text_input("Or enter a user ID", placeholder="e.g. 1")
    uid = entered.strip() or picked
    snapshot_key = f"snapshot:{base}:{uid}"
    if st.button("Fetch current recommendations", type="primary", disabled=not uid):
        with st.spinner("Fetching this user's current recommendations…"):
            result = data.api(base, f"/api/v1/recommendations/{quote(uid, safe='')}?n=20")
            if result.get("ok"):
                st.session_state[snapshot_key] = result
                st.session_state[f"history:{uid}"] = data.history(uid)
            st.session_state[f"attempt:{snapshot_key}"] = result
    if not uid:
        st.info("Select an account to begin. Live activity continues updating while you explore.")
    snapshot = st.session_state.get(snapshot_key)
    attempt = st.session_state.get(f"attempt:{snapshot_key}")
    if attempt and not attempt.get("ok"):
        st.error("Could not fetch recommendations. Check the service connection and try again.")
        if snapshot:
            st.warning("Showing the previous snapshot; it is not a fresh response.")
    if snapshot:
        body = snapshot["data"]
        tier = body.get("source", "unknown")
        st.write("Serving tier:", TIER_NAMES.get(tier, tier))
        st.caption(f"Current FastAPI snapshot · fetched {snapshot['at']} · model {body.get('model_version') or 'Unknown'}")
        st.caption("This request was made by the dashboard. It is not a historical app recommendation event, and Spring may omit songs with missing metadata.")
        recommendations = body.get("recommendations", [])
        titles = data.song_names()
        if recommendations:
            rows = [{"Rank": r.get("rank", i + 1), "Song": titles.get(str(r["song_id"]), str(r["song_id"])),
                     "Song ID": str(r["song_id"]), "Serving tier": TIER_NAMES.get(tier, tier),
                     "Serving score": r.get("score")} for i, r in enumerate(recommendations)]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            ids = list(dict.fromkeys(str(r["song_id"]) for r in recommendations))
            song = st.selectbox("Song to explain", ids, format_func=lambda sid: f"{titles.get(sid, sid)} · {sid}", key=f"song:{uid}")
            explanation_key = f"explanation:{base}:{uid}:{song}"
            if st.button("Explain selected song", type="primary"):
                with st.spinner("Calculating this song's explanation…"):
                    explanation = data.api(base, f"/api/v1/explainability/recommendation/{quote(uid, safe='')}/{quote(song, safe='')}")
                    st.session_state[explanation_key] = explanation
            explanation = st.session_state.get(explanation_key)
            if explanation:
                if explanation.get("ok"):
                    details = explanation["data"]
                    st.write(details.get("summary", ""))
                    st.metric("Explanation model's estimated score", f"{details.get('predicted_score', 0):.3f}")
                    st.caption(f"Calculated {explanation['at']}. Based on current data, not a replay of the original recommendation.")
                    metadata = data.factors(base).get("data", {})
                    explanation_chart(details, metadata)
                    st.caption(f"Explanation pipeline's heuristic tier: {details.get('tier_used', 'unknown')}. This is separate from the actual serving tier shown above.")
                    st.caption("The existing explanation pipeline and its feature calculations are unchanged. Live updates do not recalculate this explanation; click Explain again to update it.")
                elif explanation.get("status") == 404:
                    st.info("No explanation is available for this user/song. The explanation pipeline requires user interaction history.")
                else:
                    st.error("Explanation unavailable. The service or its saved artifacts may be unavailable. Try again when ready.")
        else:
            st.info("The recommendation service returned no songs for this snapshot. No explanation has been calculated.")
        with st.expander("Recent user activity"):
            histories = st.session_state.get(f"history:{uid}", {})
            for kind, label in (("mysql", "Backend received"), ("postgres", "Available to ML")):
                st.write(label)
                source = histories.get(kind, {})
                if not source.get("ok"):
                    st.warning("This activity source is unavailable.")
                elif not source.get("rows"):
                    st.caption("No activity recorded for this user in this source.")
                else:
                    st.dataframe(pd.DataFrame(source["rows"]), hide_index=True, use_container_width=True)
            st.caption("Up to 50 records per source, refreshed when you fetch recommendations. Matching events may appear in both sources.")
