"""A custom instance directory must isolate both SQLite and vault secrets."""
import json
import os
import subprocess
import sys
from pathlib import Path


def test_instance_directory_override_is_shared_by_database_and_vault(tmp_path):
    target = tmp_path / "isolated-demo"
    env = {**os.environ, "AEGIS_INSTANCE_DIR": str(target)}
    env.pop("AEGIS_DB", None)
    code = (
        "import json; from app import db, crypto_vault as vault; "
        "print(json.dumps([db.INSTANCE_DIR, db.DB_PATH, vault.INSTANCE_DIR, "
        "vault.VAULT_DIR, vault.MASTER_KEY_FILE]))"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                          env=env, text=True, capture_output=True, check=True)
    db_dir, db_file, vault_dir, blobs, key = json.loads(proc.stdout)
    assert db_dir == vault_dir == str(target)
    assert db_file == str(target / "aegis.db")
    assert blobs == str(target / "vault")
    assert key == str(target / "master.key")


def test_public_demo_users_are_fictional():
    from app.seed import USERS
    assert {profile[0] for profile in USERS} == {"admin", "analyst", "demo_user"}
