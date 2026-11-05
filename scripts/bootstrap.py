#!/usr/bin/env python3
"""
One-command bootstrap.

    python scripts/bootstrap.py

Idempotent: generates the session corpora if missing, trains and registers a
champion model if the registry is empty, and seeds demo users / vault files /
scored history if the database is fresh.
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db                                        # noqa: E402
from app import dataset, ml, seed                          # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(BASE, "artifacts")


def main():
    db.init_db()

    train_csv = os.path.join(ART, "sessions_train.csv")
    stream_csv = os.path.join(ART, "sessions_stream.csv")
    if not os.path.exists(train_csv) or not os.path.exists(stream_csv):
        print("[bootstrap] generating synthetic session corpora…")
        dataset.write_datasets()

    champion = os.path.join(ART, "champion.joblib")
    if not os.path.exists(champion):
        print("[bootstrap] training candidate models…")
        res = ml.train(register=True, notes="bootstrap")
        print(f"[bootstrap] champion={res['champion']} "
              f"acc={res['test']['accuracy']} f1={res['test']['f1']} auc={res['test']['roc_auc']}")

    if db.query("SELECT COUNT(*) c FROM model_versions", one=True)["c"] == 0:
        import joblib
        b = joblib.load(champion)
        version_dir = os.path.join(ART, "models")
        os.makedirs(version_dir, exist_ok=True)
        registered_path = os.path.join(version_dir, f"{b['version']}.joblib")
        if not os.path.exists(registered_path):
            shutil.copy2(champion, registered_path)
        db.execute(
            "INSERT INTO model_versions(version,engine,metrics,path,created_at,active,notes)"
            " VALUES(?,?,?,?,?,1,?)",
            (b["version"], b["champion"],
             json.dumps({"candidates": b.get("candidates", {}), "val": b.get("val_metrics"),
                         "test": b.get("test_metrics")}),
             registered_path, time.time(), "imported from artifacts/champion.joblib"))
        print("[bootstrap] registered existing champion artefact")

    if db.query("SELECT COUNT(*) c FROM users", one=True)["c"] == 0:
        print("[bootstrap] seeding demo data…")
        seed.run()

    print("[bootstrap] ready — start the server with:  python run.py")


if __name__ == "__main__":
    main()
