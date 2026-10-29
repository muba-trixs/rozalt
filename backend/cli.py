"""Command-line helpers: python -m backend.cli [init-db|load-synthetic|detect]"""
from __future__ import annotations

import json
import subprocess
import sys

from backend.app.config import BACKEND_DIR


def init_db() -> None:
    subprocess.run([sys.executable, "-m", "alembic", "-c", str(BACKEND_DIR / "alembic.ini"), "upgrade", "head"],
                   check=True)


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "help"
    if cmd == "init-db":
        init_db()
        print("Database migrated to head.")
        return
    from backend.database.session import SessionLocal

    db = SessionLocal()
    try:
        if cmd == "load-synthetic":
            from backend.services.synthetic_loader import load_synthetic

            print(json.dumps(load_synthetic(db), indent=2, default=str))
        elif cmd == "detect":
            from backend.services.anomaly_detection import run_detection

            r = run_detection(db)
            print(f"Created {r['created']} anomalies (kept {r['kept_investigated']} investigated).")
        else:
            print(__doc__)
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
