from __future__ import annotations

import hmac
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, jsonify, request, session

from ..db.database import log_activity
from ..db.database import session as db_session

admin = Blueprint("admin", __name__, url_prefix="/api/admin")


def _admin_credentials() -> tuple[str, str]:
    return (
        os.environ.get("ADMIN_EMAIL", "admin@stockfindpro.local"),
        os.environ.get("ADMIN_PASSWORD", "changeme"),
    )


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return jsonify({"error": "admin_auth_required", "message": "Admin login required."}), 401
        return view(*args, **kwargs)
    return wrapped


@admin.post("/login")
def login():
    body = request.get_json(force=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    admin_email, admin_password = _admin_credentials()
    email_ok = hmac.compare_digest(email, admin_email.lower())
    password_ok = hmac.compare_digest(password, admin_password)
    if not (email_ok and password_ok):
        return jsonify({"error": "invalid_credentials", "message": "Email or password is incorrect."}), 401

    session["is_admin"] = True
    log_activity(None, "admin_login")
    return jsonify({"ok": True})


@admin.post("/logout")
def logout():
    session.pop("is_admin", None)
    return jsonify({"ok": True})


@admin.get("/me")
def me():
    return jsonify({"admin": bool(session.get("is_admin"))})


@admin.get("/stats")
@admin_required
def stats():
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_start = (now - timedelta(days=7)).isoformat()

    with db_session() as conn:
        total_users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        subscribed = conn.execute("SELECT COUNT(*) AS n FROM users WHERE subscribed=1").fetchone()["n"]
        plan_rows = conn.execute(
            "SELECT plan, COUNT(*) AS n FROM users WHERE subscribed=1 GROUP BY plan"
        ).fetchall()
        signups_today = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE created_at >= ?", (today_start,)
        ).fetchone()["n"]
        signups_7d = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE created_at >= ?", (week_start,)
        ).fetchone()["n"]
        backtests_7d = conn.execute(
            "SELECT COUNT(*) AS n FROM activity_log WHERE event_type='backtest_run' AND created_at >= ?",
            (week_start,),
        ).fetchone()["n"]

    return jsonify({
        "total_users": total_users,
        "subscribed": subscribed,
        "free": total_users - subscribed,
        "plan_breakdown": {r["plan"]: r["n"] for r in plan_rows},
        "signups_today": signups_today,
        "signups_7d": signups_7d,
        "backtests_7d": backtests_7d,
    })


@admin.get("/users")
@admin_required
def users():
    q = (request.args.get("q") or "").strip().lower()
    with db_session() as conn:
        if q:
            rows = conn.execute(
                "SELECT id, email, created_at, subscribed, plan, subscribed_at FROM users "
                "WHERE lower(email) LIKE ? ORDER BY id DESC",
                (f"%{q}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, email, created_at, subscribed, plan, subscribed_at FROM users ORDER BY id DESC"
            ).fetchall()
    return jsonify({"users": [
        {
            "id": r["id"], "email": r["email"], "created_at": r["created_at"],
            "subscribed": bool(r["subscribed"]), "plan": r["plan"], "subscribed_at": r["subscribed_at"],
        }
        for r in rows
    ]})


@admin.post("/users/<int:user_id>/toggle-subscription")
@admin_required
def toggle_subscription(user_id: int):
    with db_session() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404
        now_subscribed = not row["subscribed"]
        if now_subscribed:
            conn.execute(
                "UPDATE users SET subscribed=1, plan=COALESCE(plan, 'comp'), subscribed_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET subscribed=0, plan=NULL, subscribed_at=NULL WHERE id=?", (user_id,)
            )
    log_activity(None, "admin_toggle_subscription", f"user_id={user_id} -> subscribed={now_subscribed}")
    return jsonify({"ok": True, "subscribed": now_subscribed})


@admin.get("/activity")
@admin_required
def activity():
    limit = min(int(request.args.get("limit", 100)), 500)
    with db_session() as conn:
        rows = conn.execute(
            "SELECT a.id, a.event_type, a.detail, a.created_at, u.email "
            "FROM activity_log a LEFT JOIN users u ON u.id = a.user_id "
            "ORDER BY a.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return jsonify({"activity": [
        {
            "id": r["id"], "event_type": r["event_type"], "detail": r["detail"],
            "created_at": r["created_at"], "email": r["email"],
        }
        for r in rows
    ]})
