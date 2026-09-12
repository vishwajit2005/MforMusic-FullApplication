"""Resolve cloud certificate/cache paths and launch exactly one service process."""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
root = Path(__file__).resolve().parent
os.chdir(root)
role = os.environ.get("MFORMUSIC_ROLE", "api")
if role not in {"api", "embeddings", "dashboard"}:
    raise RuntimeError("Unknown deployment role")
if os.getenv("DATABASE_URL"):
    p = urlsplit(os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1))
    q = dict(parse_qsl(p.query))
    q.update(sslmode="verify-full", sslrootcert=str(root / "aiven-ca.pem"))
    os.environ["DATABASE_URL"] = urlunsplit(p._replace(query=urlencode(q)))
if os.getenv("MYSQL_URL"):
    p = urlsplit(os.environ["MYSQL_URL"])
    q = dict(parse_qsl(p.query))
    q.pop("ssl_verify_cert", None)
    q.pop("ssl_verify_identity", None)
    q.update(ssl_ca=str(root / "aiven-ca.pem"), ssl_check_hostname="true")
    os.environ["MYSQL_URL"] = urlunsplit(p._replace(query=urlencode(q)))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(root / ".model_cache"))
port = os.environ.get("PORT", "8000")
if role == "dashboard":
    args = [sys.executable, "-m", "streamlit", "run", "app/deployment/dashboard.py",
            "--server.address=0.0.0.0", "--server.port=" + port, "--browser.gatherUsageStats=false"]
else:
    args = [sys.executable, "-m", "uvicorn", "app.deployment." + role + ":app",
            "--host", "0.0.0.0", "--port", port, "--workers", "1", "--no-access-log"]
os.execv(sys.executable, args)
