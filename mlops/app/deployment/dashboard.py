"""Password gate for the existing read-only monitoring dashboard."""
import os
import secrets
import runpy
from pathlib import Path
import streamlit as st

password = os.environ.get("DASHBOARD_PASSWORD", "")
if len(password) < 16:
    st.error("Dashboard access is not configured.")
    st.stop()
if not st.session_state.get("monitor_authenticated"):
    st.title("MforMusic Monitor")
    with st.form("monitor_sign_in"):
        entered = st.text_input("Monitor password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        if secrets.compare_digest(entered.encode("utf-8"), password.encode("utf-8")):
            st.session_state["monitor_authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password")
    st.stop()
runpy.run_path(str(Path(__file__).resolve().parents[1] / "explainability/dashboard/app.py"), run_name="__main__")
