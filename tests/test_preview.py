"""The embedded preview must be opt-in, not the default security posture."""
from app import create_app, db
from app.api import _with_cookie


def test_cross_origin_embedding_requires_explicit_opt_in(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "preview-test.db"))
    monkeypatch.delenv("AEGIS_ALLOW_EMBED", raising=False)
    app = create_app()
    with app.test_client() as client:
        normal = client.get("/api/health")
        assert normal.status_code == 200
        assert normal.headers["X-Frame-Options"] == "SAMEORIGIN"
        with app.app_context():
            cookie = _with_cookie({"token": "test"}).headers["Set-Cookie"]
            assert "SameSite=Lax" in cookie
            assert "Partitioned" not in cookie

        monkeypatch.setenv("AEGIS_ALLOW_EMBED", "1")
        preview = client.get("/api/health")
        assert preview.status_code == 200
        assert "X-Frame-Options" not in preview.headers
        with app.app_context():
            cookie = _with_cookie({"token": "test"}).headers["Set-Cookie"]
            assert all(attribute in cookie for attribute in
                       ("HttpOnly", "Secure", "SameSite=None", "Partitioned"))
