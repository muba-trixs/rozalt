import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

BACKEND = Path(__file__).resolve().parents[1]


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None and body["data"]["status"] == "ok"


def test_unknown_route_uses_envelope(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "http_error"


def test_migrations_build_full_schema(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'mig.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    res = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "upgrade", "head"],
        capture_output=True, text=True, cwd=BACKEND.parent,
    )
    assert res.returncode == 0, res.stderr
    tables = set(inspect(create_engine(url)).get_table_names())
    for t in ["demand_records", "anomalies", "investigations", "evidence_records", "hypothesis_evidence", "analyst_feedback"]:
        assert t in tables
