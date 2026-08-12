from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from ..db.database import session as db_session

auth = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PLANS = {
    "monthly": {"label": "Monthly", "price_usd": 19},
    "annual": {"label": "Annual", "price_usd": 179},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _user_row(user_id: int):
    with db_session() as conn:
        return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def _user_public(row) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "subscribed": bool(row["subscribed"]),
        "plan": row["plan"],
    }


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return _user_row(user_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return jsonify({"error": "auth_required", "message": "Log in to continue."}), 401
        return view(*args, **kwargs)
    return wrapped


def subscription_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"error": "auth_required", "message": "Log in to continue."}), 401
        if not user["subscribed"]:
            return jsonify({"error": "subscription_required", "message": "Subscribe to unlock this."}), 402
        return view(*args, **kwargs)
    return wrapped


@auth.post("/signup")
def signup():
    body = request.get_json(force=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not EMAIL_RE.match(email):
        return jsonify({"error": "invalid_email", "message": "Enter a valid email address."}), 400
    if len(password) < 8:
        return jsonify({"error": "weak_password", "message": "Password must be at least 8 characters."}), 400

    with db_session() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            return jsonify({"error": "email_taken", "message": "An account with that email already exists."}), 409
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, created_at, subscribed) VALUES (?, ?, ?, 0)",
            (email, generate_password_hash(password), _now()),
        )
        user_id = cur.lastrowid

    session["user_id"] = user_id
    return jsonify({"user": _user_public(_user_row(user_id))}), 201


@auth.post("/login")
def login():
    body = request.get_json(force=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    with db_session() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "invalid_credentials", "message": "Email or password is incorrect."}), 401

    session["user_id"] = row["id"]
    return jsonify({"user": _user_public(row)})


@auth.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@auth.get("/me")
def me():
    user = current_user()
    return jsonify({"user": _user_public(user) if user else None})


@auth.post("/subscribe")
@login_required
def subscribe():
    body = request.get_json(force=True) or {}
    plan = body.get("plan")
    if plan not in PLANS:
        return jsonify({"error": "invalid_plan", "message": f"plan must be one of {list(PLANS)}"}), 400

    user_id = session["user_id"]
    with db_session() as conn:
        conn.execute(
            "UPDATE users SET subscribed=1, plan=?, subscribed_at=? WHERE id=?",
            (plan, _now(), user_id),
        )
    return jsonify({"user": _user_public(_user_row(user_id))})


@auth.post("/unsubscribe")
@login_required
def unsubscribe():
    user_id = session["user_id"]
    with db_session() as conn:
        conn.execute("UPDATE users SET subscribed=0, plan=NULL, subscribed_at=NULL WHERE id=?", (user_id,))
    return jsonify({"user": _user_public(_user_row(user_id))})
