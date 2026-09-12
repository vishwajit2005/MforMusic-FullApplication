"""Read-only dashboard adapters. Never import serving or model-training modules."""
from datetime import datetime, timezone
from pathlib import Path
import os

import requests
import streamlit as st
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

PROJECT = Path(__file__).resolve().parents[4]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def settings():
    ml = {**dotenv_values(PROJECT / "mlops/.env"), **os.environ}
    backend = {**dotenv_values(PROJECT / "backend/.env"), **os.environ}
    mysql = ml.get("MYSQL_URL")
    if not mysql and all(backend.get(k) for k in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")):
        mysql = URL.create("mysql+pymysql", username=backend["DB_USER"],
                           password=backend["DB_PASSWORD"], host=backend["DB_HOST"],
                           port=int(backend.get("DB_PORT", 3306)), database=backend["DB_NAME"])
    return mysql, ml.get("DATABASE_URL")


@st.cache_resource
def engine(kind):
    mysql, postgres = settings()
    url = mysql if kind == "mysql" else postgres
    if not url:
        raise ValueError("Connection not configured")
    url = make_url(url) if isinstance(url, str) else url
    if kind == "mysql":
        url = url.set(drivername="mysql+pymysql")
        args = {"connect_timeout": 2, "read_timeout": 3, "write_timeout": 3,
                "ssl": {"check_hostname": True}}
        if url.query.get("ssl_ca"):
            args["ssl"]["ca"] = url.query["ssl_ca"]
    else:
        url = url.set(drivername="postgresql+psycopg2")
        args = {"connect_timeout": 2, "options": "-c statement_timeout=3000 -c default_transaction_read_only=on"}
    return create_engine(url, pool_size=1, max_overflow=0, pool_timeout=2,
                         pool_pre_ping=True, connect_args=args)


def read(kind, sql, params=None):
    with engine(kind).connect() as conn:
        if kind == "mysql":
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            conn.exec_driver_sql("START TRANSACTION READ ONLY")
        try:
            return [dict(row) for row in conn.execute(text(sql), params or {}).mappings()]
        finally:
            conn.rollback()


@st.cache_data(ttl=5, show_spinner=False)
def activity(kind):
    try:
        table = "user_interactions" if kind == "mysql" else "interactions"
        rows = read(kind, f"SELECT id,user_id,song_id,interaction_type,created_at FROM {table} ORDER BY id DESC LIMIT 100")
        return {"ok": True, "rows": rows, "at": now()}
    except Exception:
        return {"ok": False, "rows": [], "at": now()}


@st.cache_data(ttl=5, show_spinner=False)
def users():
    try:
        rows = read("mysql", "SELECT id,username,created_at FROM users ORDER BY id DESC LIMIT 2000")
        return {"ok": True, "rows": rows, "at": now()}
    except Exception:
        return {"ok": False, "rows": [], "at": now()}


@st.cache_data(ttl=30, show_spinner=False)
def song_names():
    try:
        rows = read("mysql", "SELECT external_track_id,title FROM songs ORDER BY id DESC LIMIT 5000")
        return {str(r["external_track_id"]): r["title"] for r in rows}
    except Exception:
        return {}


def api(base, path):
    try:
        configured = os.getenv("EXPLAINABILITY_API_URL", "").removesuffix("/api/v1/explainability").rstrip("/")
        headers = {}
        if configured and base.rstrip("/") == configured and os.getenv("MLOPS_API_KEY"):
            headers["X-MforMusic-Key"] = os.environ["MLOPS_API_KEY"]
        response = requests.get(f"{base.rstrip('/')}/{path.lstrip('/')}", headers=headers, timeout=(2, 4))
        if not response.ok:
            return {"ok": False, "status": response.status_code, "at": now()}
        body = response.json()
        return {"ok": True, "data": body, "at": now()}
    except (requests.RequestException, ValueError):
        return {"ok": False, "status": None, "at": now()}


@st.cache_data(ttl=30, show_spinner=False)
def model_status(base, path):
    return api(base, path)


@st.cache_data(ttl=300, show_spinner=False)
def factors(base):
    return api(base, "/api/v1/explainability/factors")


def history(uid):
    result = {}
    for kind, table in (("mysql", "user_interactions"), ("postgres", "interactions")):
        try:
            result[kind] = {"ok": True, "rows": read(kind,
                f"SELECT id,song_id,interaction_type,created_at FROM {table} WHERE user_id=:uid ORDER BY id DESC LIMIT 50",
                {"uid": str(uid)})}
        except Exception:
            result[kind] = {"ok": False, "rows": []}
    return result
