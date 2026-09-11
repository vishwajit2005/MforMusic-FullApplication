# MforMusic Monitor

Run from the `mlops` directory using its existing virtual environment:

```sh
venv/bin/python -m streamlit run app/explainability/dashboard/app.py --server.address=127.0.0.1
```

The dashboard opens at http://127.0.0.1:8501. Start FastAPI separately with the project's usual procedure to enable model status, recommendations and explanations. The monitor never starts or retrains it.

## Refresh and sources

* The live fragment polls every 5 seconds while the session is active. Slow database connections can delay updates. Pause with **Live updates**.
* Registrations read MySQL `users`; activity reads either MySQL `user_interactions` or PostgreSQL `interactions`. These are separate received/ML-available views. Reads use read-only transactions and bounded result windows: latest 100 activity rows, latest 2,000 accounts, latest 15 visible events per tab. Manual user ID entry supports accounts outside the directory window.
* Credentials come from project `backend/.env`, `mlops/.env`, or environment overrides, and are never displayed. Existing MYSQL_URL takes precedence over backend DB_* values. PostgreSQL uses DATABASE_URL. No database schema changes are made.
* Models refresh every 30 seconds through the existing `/api/v1/recommendations/model/status` and `/api/v1/content/model/status` endpoints.
* **Fetch current recommendations** calls `/api/v1/recommendations/{user_id}?n=20` and reads up to 50 recent user events per database. The snapshot is dashboard-generated, not an app event. The model's `source` is the serving tier for this snapshot. Song titles are a bounded, cached MySQL lookup; absent titles fall back to external IDs.
* **Explain selected song** calls the existing explainability API once. Results remain in session state through timer ticks and full reruns. Click again to recompute. This is an explanation from current data, not the original event's feature snapshot. The surrogate's inferred tier is labeled separately from the serving tier. The feature engineering, surrogate training and SHAP calculations are untouched.
* Independent fragment refreshes do not execute the explanation request. Small shared read caches have 5/30-second TTLs; factor labels cache for 5 minutes. Database engines are pooled resources. No models are loaded into Streamlit.

## Data limits

There is no recorded recommendation-event timeline or historical tier distribution in the current source. Last successful retrain timestamps are not exposed. The overview displays **Not recorded**, rather than deriving fake events or dates from heuristics/artifact modification times. Database timestamps display as stored and are not used to calculate cross-database delivery latency.

Last successful feed/model responses remain visible and explicitly stale after connection failure. An empty recommendation response is distinct from a request failure. Full browser reloads create a new Streamlit session, so on-demand snapshots/explanations must be fetched again.

## Verification

The redesign was exercised with Streamlit AppTest for initial rendering, account selection, on-demand recommendations/explanations, no repeat SHAP calls on rerun, retained stale snapshots, empty results and unavailable services. Live read-only checks verified both databases, and browser inspection verified the running page and live model status.
