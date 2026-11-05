"""Server-rendered pages (the console itself is a small SPA on top of the API)."""
import io

from flask import Blueprint, redirect, render_template, request, send_file, url_for

from . import crypto_vault, db, security
from .ml import service

bp = Blueprint("views", __name__)


def _logged_in() -> bool:
    token = request.cookies.get("aegis_token")
    return bool(token and security.verify_token(token))


@bp.get("/")
def root():
    if _logged_in():
        return render_template("console.html", model=service().info())
    return render_template("login.html", model=service().info())


@bp.get("/console")
def console():
    if not _logged_in():
        return redirect(url_for("views.root"))
    return render_template("console.html", model=service().info())


@bp.get("/s/<link_id>/<token>")
def share_download(link_id, token):
    try:
        plain, meta = crypto_vault.consume_share_link(link_id, token)
    except PermissionError as e:
        return render_template("error.html", code=403, message=str(e)), 403
    security.audit("vault.share.download", "link:" + link_id, meta["filename"], {})
    security.alert("info", "Share link used", f"{meta['filename']} via {link_id}")
    return send_file(io.BytesIO(plain), as_attachment=True,
                     download_name=meta["filename"], mimetype="application/octet-stream")
