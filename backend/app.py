"""Recifix backend: Flask + MySQL.

Serves the existing static front end and a JSON API under /api.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import struct
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from flask import Flask, app, g, jsonify, redirect, request, send_from_directory, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

import mailer
from db import INTEGRITY_ERRORS, Database

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_FRONTEND_DIR = BACKEND_DIR.parent

MIN_PASSWORD = 8
MAX_PASSWORD = 128
RESET_TTL = timedelta(hours=1)
VERIFY_TTL = timedelta(hours=24)
CHALLENGE_TTL = timedelta(minutes=5)
RESET_COOLDOWN_SECONDS = 60
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Used so that logging in with an unknown email takes as long as a real check.
_DUMMY_HASH = generate_password_hash("recifix-dummy-password")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def generate_totp_secret():
    return base64.b32encode(secrets.token_bytes(10)).decode("utf-8")


def totp_at(secret, counter):
    try:
        key = base64.b32decode(secret, casefold=True)
    except Exception:
        return None
    digest = hmac.new(key, struct.pack(">Q", counter), "sha1").digest()
    offset = digest[-1] & 15
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"


def get_totp_token(secret):
    return totp_at(secret, int(time.time()) // 30)


def verify_totp(secret, code, window=1):
    """Accept the current authenticator code, plus one step of clock drift."""
    if not secret or not isinstance(code, str) or not re.fullmatch(r"\d{6}", code.strip()):
        return False
    code = code.strip()
    counter = int(time.time()) // 30
    for offset in range(-window, window + 1):
        expected = totp_at(secret, counter + offset)
        if expected and hmac.compare_digest(expected, code):
            return True
    return False


def two_factor_active(user: dict) -> bool:
    return bool(int(user.get("two_factor_enabled") or 0)) and bool(user.get("two_factor_secret"))


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class AttemptLimiter:
    """Process-local failed-login limiter (use Redis or similar if you run many workers)."""

    def __init__(self, max_attempts=5, window_seconds=900):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._hits = {}
        self._lock = threading.Lock()

    def _prune(self, key, now):
        self._hits[key] = [t for t in self._hits.get(key, []) if now - t < self.window]
        if not self._hits[key]:
            del self._hits[key]

    def retry_after(self, key) -> int:
        """Seconds until the key may try again (0 if not blocked)."""
        now = time.time()
        with self._lock:
            self._prune(key, now)
            hits = self._hits.get(key, [])
            if len(hits) >= self.max_attempts:
                return int(self.window - (now - hits[0])) + 1
            return 0

    def fail(self, key):
        with self._lock:
            self._hits.setdefault(key, []).append(time.time())

    def reset(self, key):
        with self._lock:
            self._hits.pop(key, None)


# ---------- validation helpers ----------
class ValidationError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def clean_name(value):
    if not isinstance(value, str):
        raise ValidationError("Please enter your full name.", "fullname")
    name = " ".join(value.split())
    if not name:
        raise ValidationError("Please enter your full name.", "fullname")
    if len(name) > 100:
        raise ValidationError("Name must be 100 characters or fewer.", "fullname")
    return name


def clean_email(value):
    email = value.strip().lower() if isinstance(value, str) else ""
    if not email or len(email) > 254 or not EMAIL_RE.match(email):
        raise ValidationError("Please enter a valid email address.", "email")
    return email


def clean_password(value, field="password"):
    if not isinstance(value, str) or len(value) < MIN_PASSWORD:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD} characters.", field)
    if len(value) > MAX_PASSWORD:
        raise ValidationError(f"Password must be {MAX_PASSWORD} characters or fewer.", field)
    return value


def pw_version(password_hash: str) -> str:
    """Fingerprint stored in the session so a password change signs out other devices."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def email_is_verified(user: dict) -> bool:
    """Missing column means an older database; don't lock those accounts out."""
    flag = user.get("email_verified")
    if flag is None:
        return True
    return bool(int(flag))


def public_user(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["full_name"],
        "email": row["email"],
        "role": row.get("role", "member"),
        "phone": row.get("phone"),
        "two_factor_enabled": bool(row.get("two_factor_enabled", 0))
    }


def create_app(overrides=None) -> Flask:
    load_dotenv(BACKEND_DIR / ".env")
    app = Flask(__name__, static_folder=None)

    secret = os.environ.get("SECRET_KEY", "").strip()
    if not secret and _env_bool("FLASK_DEBUG"):
        secret = secrets.token_hex(32)  # dev only: sessions reset on every restart

    app.config.update(
        SECRET_KEY=secret,
        DATABASE_URL=os.environ.get("DATABASE_URL", "mysql://recifix:password@127.0.0.1:3306/recifix"),
        BASE_URL=os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/"),
        FRONTEND_DIR=os.environ.get("FRONTEND_DIR", str(DEFAULT_FRONTEND_DIR)),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_env_bool("SESSION_COOKIE_SECURE") or _env_bool("ENFORCE_HTTPS"),
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        MAX_CONTENT_LENGTH=16 * 1024,
        ENFORCE_HTTPS=_env_bool("ENFORCE_HTTPS"),
        SMTP_HOST=os.environ.get("SMTP_HOST", ""),
        SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USER=os.environ.get("SMTP_USER", ""),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD", ""),
        SMTP_STARTTLS=_env_bool("SMTP_STARTTLS", True),
        MAIL_FROM=os.environ.get("MAIL_FROM", "Recifix <no-reply@localhost>"),
        MAILER=None,  # tests inject a callable(to, link)
    )
    if overrides:
        app.config.update(overrides)

    if not app.config["SECRET_KEY"]:
        raise RuntimeError(
            "SECRET_KEY is not set. Generate one with:\n"
            '  python -c "import secrets; print(secrets.token_hex(32))"\n'
            "and put it in backend/.env (see .env.example)."
        )

    db = Database(app.config["DATABASE_URL"])
    app.extensions["db"] = db
    login_limiter = AttemptLimiter()
    app.extensions["login_limiter"] = login_limiter
    contact_limiter = AttemptLimiter(max_attempts=5, window_seconds=900)
    app.extensions["contact_limiter"] = contact_limiter
    signup_limiter = AttemptLimiter(max_attempts=10, window_seconds=900)
    app.extensions["signup_limiter"] = signup_limiter
    app.teardown_appcontext(db.close)

    # 🤖 OPTIMIZED RECIFIX ML CACHE SETUP
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b")
    recipes_cache = []
    tfidf_matrix = None

    # 🟢 WRAP IN AN APP CONTEXT SO EXTERNAL TOOLS (init_db.py) DON'T CRASH
    with app.app_context():
        try:
            db.ensure_email_verification()
            db.ensure_account_security()
        except Exception:
            app.logger.exception("Could not prepare email verification storage")
        try:
            query = """
                SELECT 
                    r.id, 
                    r.name AS title, 
                    r.image,
                    GROUP_CONCAT(REPLACE(REPLACE(i.match_spec, ';', ' '), '|', ' '), ' ') AS ingredients_blob
                FROM recipes r
                JOIN recipe_ingredients i ON r.id = i.recipe_id
                GROUP BY r.id, r.name, r.image
            """
            
            rows = db.all(query)
            if rows:
                recipes_cache = rows
                corpus = [r["ingredients_blob"] for r in rows]
                tfidf_matrix = vectorizer.fit_transform(corpus)
                app.logger.info("🤖 Recifix user taste-profile ML engine successfully loaded!")
        except Exception as e:
            app.logger.error(f"Recipe ML vectorizer initialization bypass: {e}")

    frontend = Path(app.config["FRONTEND_DIR"]).resolve()

    # ---------- plumbing ----------
    def error(message, status, field=None, **extra):
        body = {"error": message}
        if field:
            body["field"] = field
        body.update(extra)
        return jsonify(body), status

    @app.before_request
    def require_json_for_writes():
        # Browsers can't send application/json cross-site without a CORS preflight,
        # so this (plus SameSite=Lax cookies) blocks CSRF on the API.
        if request.path.startswith("/api/") and request.method in ("POST", "PATCH", "PUT", "DELETE"):
            if request.content_length and not request.is_json:
                return error("Requests must be sent as JSON.", 415)

    @app.before_request
    def enforce_https():
        # When ENFORCE_HTTPS is set (e.g., behind PaaS SSL termination), redirect HTTP to HTTPS.
        if app.config.get("ENFORCE_HTTPS"):
            if not request.is_secure:
                proto = request.headers.get("X-Forwarded-Proto", "")
                if proto != "https":
                    url = request.url.replace("http://", "https://", 1)
                    return redirect(url, code=301)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")  # login page is framed by the landing page
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(HTTPException)
    def http_error(exc):
        if request.path.startswith("/api/"):
            return error(exc.description or exc.name, exc.code)
        return exc

    @app.errorhandler(Exception)
    def unhandled(exc):
        app.logger.exception("Unhandled error")
        if request.path.startswith("/api/"):
            return error("Something went wrong. Please try again.", 500)
        return "Internal server error", 500

    def body_json():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValidationError("Invalid request.")
        return data

    @app.errorhandler(ValidationError)
    def validation_error(exc):
        return error(exc.message, 400, exc.field)

    def current_user():
        uid = session.get("user_id")
        if not uid:
            return None
        row = db.one("SELECT * FROM users WHERE id = %s", (uid,))
        if row is None or session.get("pv") != pw_version(row["password_hash"]):
            session.clear()
            return None
        return row

    def login_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return error("Please log in to continue.", 401)
            g.user = user
            return view(*args, **kwargs)

        return wrapper

    def is_admin_user(user):
        if str(user.get("role") or "").lower() == "admin":
            return True
        admin_emails_str = os.environ.get("ADMIN_EMAILS", "")
        admin_emails = [e.strip().lower() for e in admin_emails_str.split(",") if e.strip()]
        return user["email"].lower() in admin_emails

    def admin_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return error("Please log in to continue.", 401)
            if not is_admin_user(user):
                return error("Admin access required.", 403)
            g.user = user
            return view(*args, **kwargs)
        return wrapper

    def start_session(user_row):
        session.clear()  # new session on every login (prevents fixation)
        session["user_id"] = user_row["id"]
        session["pv"] = pw_version(user_row["password_hash"])
        session.permanent = True

    def send_auth_email(kind, to_address, link):
        sender = app.config.get("MAILER")
        if sender:
            sender(to_address, link)
            return
        if kind == "verify":
            mailer.send_verification_email(app, to_address, link)
        else:
            mailer.send_reset_email(app, to_address, link)

    def issue_verification(user, now=None):
        now = now or utcnow()
        token = secrets.token_urlsafe(32)
        db.execute("DELETE FROM email_verifications WHERE user_id = %s", (user["id"],))
        db.execute(
            "INSERT INTO email_verifications (user_id, token_hash, expires_at, created_at) "
            "VALUES (%s, %s, %s, %s)",
            (
                user["id"],
                hashlib.sha256(token.encode()).hexdigest(),
                fmt(now + VERIFY_TTL),
                fmt(now),
            ),
        )
        return f"{app.config['BASE_URL']}/api/auth/verify-email?token={token}"

    def issue_login_challenge(user, now=None):
        now = now or utcnow()
        token = secrets.token_urlsafe(32)
        db.execute("DELETE FROM login_challenges WHERE user_id = %s", (user["id"],))
        db.execute(
            "INSERT INTO login_challenges (user_id, token_hash, expires_at, created_at) "
            "VALUES (%s, %s, %s, %s)",
            (
                user["id"],
                hashlib.sha256(token.encode()).hexdigest(),
                fmt(now + CHALLENGE_TTL),
                fmt(now),
            ),
        )
        return token

    # ---------- auth API ----------
    @app.post("/api/auth/signup")
    def signup():
        key = f"signup|{request.remote_addr}"
        wait = signup_limiter.retry_after(key)
        if wait:
            resp = error("Too many signup attempts. Please try again later.", 429, retry_after=wait)
            resp[0].headers["Retry-After"] = str(wait)
            return resp

        data = body_json()
        name = clean_name(data.get("fullname"))
        email = clean_email(data.get("email"))
        password = clean_password(data.get("password"))

        if db.one("SELECT id FROM users WHERE email = %s", (email,)):
            return error("An account with this email already exists. Try logging in.", 409, "email")

        now = fmt(utcnow())
        try:
            user_id, _ = db.execute(
                "INSERT INTO users (full_name, email, password_hash, email_verified, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (name, email, generate_password_hash(password), 0, now, now),
            )
        except INTEGRITY_ERRORS:  # two signups racing on the same email
            return error("An account with this email already exists. Try logging in.", 409, "email")

        user = db.one("SELECT * FROM users WHERE id = %s", (user_id,))
        link = issue_verification(user)
        db.commit()
        send_auth_email("verify", user["email"], link)
        return jsonify(
            {
                "ok": True,
                "verification_required": True,
                "message": "Account created. Check your email for a link to confirm your address, then log in.",
            }
        ), 201

    @app.post("/api/auth/login")
    def login():
        data = body_json()
        email_raw = data.get("email")
        password = data.get("password")
        if not isinstance(email_raw, str) or not isinstance(password, str) or not email_raw.strip() or not password:
            return error("Enter your email and password.", 400)

        email = email_raw.strip().lower()[:254]
        key = f"{request.remote_addr}|{email}"
        wait = login_limiter.retry_after(key)
        if wait:
            resp = error("Too many failed attempts. Please try again later.", 429, retry_after=wait)
            resp[0].headers["Retry-After"] = str(wait)
            return resp

        user = db.one("SELECT * FROM users WHERE email = %s", (email,))
        if user:
            valid = check_password_hash(user["password_hash"], password)
        else:
            check_password_hash(_DUMMY_HASH, password)
            valid = False

        if not valid:
            login_limiter.fail(key)
            return error("Incorrect email or password.", 401)

        login_limiter.reset(key)
        if not email_is_verified(user):
            return error(
                "Confirm your email before logging in. Check your inbox for the verification link.",
                403,
                "email",
                verification_required=True,
            )
        if two_factor_active(user):
            challenge = issue_login_challenge(user)
            db.commit()
            return jsonify(
                {
                    "ok": True,
                    "two_factor_required": True,
                    "challenge": challenge,
                    "message": "Enter the 6-digit code from your authenticator app.",
                }
            )
        start_session(user)
        return jsonify({"ok": True, "user": public_user(user)})

    @app.post("/api/auth/login/2fa")
    def login_2fa():
        data = body_json()
        token = data.get("challenge")
        code = data.get("code")
        if not isinstance(token, str) or not token or not isinstance(code, str):
            return error("Enter the code from your authenticator app.", 400, "code")

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        row = db.one(
            "SELECT * FROM login_challenges WHERE token_hash = %s AND expires_at > %s",
            (token_hash, fmt(utcnow())),
        )
        if row is None:
            return error("That sign-in step expired. Enter your password again.", 401, "code")

        user = db.one("SELECT * FROM users WHERE id = %s", (row["user_id"],))
        key = f"2fa|{request.remote_addr}|{row['user_id']}"
        wait = login_limiter.retry_after(key)
        if wait:
            resp = error("Too many failed attempts. Please try again later.", 429, retry_after=wait)
            resp[0].headers["Retry-After"] = str(wait)
            return resp

        if user is None or not two_factor_active(user) or not verify_totp(user["two_factor_secret"], code):
            login_limiter.fail(key)
            return error("That authenticator code is incorrect.", 401, "code")

        login_limiter.reset(key)
        db.execute("DELETE FROM login_challenges WHERE user_id = %s", (user["id"],))
        db.commit()
        start_session(user)
        return jsonify({"ok": True, "user": public_user(user)})

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/auth/me")
    @login_required
    def me():
        return jsonify({"user": public_user(g.user)})

    # ---------- forgot password (confirmed by emailed link) ----------
    @app.post("/api/auth/forgot-password")
    def forgot_password():
        data = body_json()
        email = clean_email(data.get("email"))
        new_password = clean_password(data.get("new_password"), "new_password")
        generic = jsonify(
            {
                "ok": True,
                "message": "If an account exists for that email, we've sent a link to confirm the new password.",
            }
        )

        now = utcnow()
        db.execute("DELETE FROM password_resets WHERE expires_at < %s", (fmt(now),))
        user = db.one("SELECT * FROM users WHERE email = %s", (email,))
        if user is None:
            db.commit()
            return generic

        recent = db.one(
            "SELECT id FROM password_resets WHERE user_id = %s AND created_at > %s",
            (user["id"], fmt(now - timedelta(seconds=RESET_COOLDOWN_SECONDS))),
        )
        if recent:  # avoid using this form to spam someone's inbox
            db.commit()
            return generic

        token = secrets.token_urlsafe(32)
        db.execute("DELETE FROM password_resets WHERE user_id = %s", (user["id"],))
        db.execute(
            "INSERT INTO password_resets (user_id, token_hash, new_password_hash, expires_at, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                user["id"],
                hashlib.sha256(token.encode()).hexdigest(),
                generate_password_hash(new_password),
                fmt(now + RESET_TTL),
                fmt(now),
            ),
        )
        db.commit()

        link = f"{app.config['BASE_URL']}/api/auth/confirm-reset?token={token}"
        send_auth_email("reset", user["email"], link)
        return generic

    @app.get("/api/auth/confirm-reset")
    def confirm_reset():
        token = request.args.get("token", "")
        row = db.one(
            "SELECT * FROM password_resets WHERE token_hash = %s AND expires_at > %s",
            (hashlib.sha256(token.encode()).hexdigest(), fmt(utcnow())),
        )
        if row is None:
            return redirect("/pages/login.html?reset=invalid")

        db.execute(
            "UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s",
            (row["new_password_hash"], fmt(utcnow()), row["user_id"]),
        )
        db.execute("DELETE FROM password_resets WHERE user_id = %s", (row["user_id"],))
        db.commit()
        return redirect("/pages/login.html?reset=success")

    @app.get("/api/auth/verify-email")
    def verify_email():
        token = request.args.get("token", "")
        row = db.one(
            "SELECT * FROM email_verifications WHERE token_hash = %s AND expires_at > %s",
            (hashlib.sha256(token.encode()).hexdigest(), fmt(utcnow())),
        )
        if row is None:
            return redirect("/pages/login.html?verified=invalid")

        db.execute(
            "UPDATE users SET email_verified = 1, updated_at = %s WHERE id = %s",
            (fmt(utcnow()), row["user_id"]),
        )
        db.execute("DELETE FROM email_verifications WHERE user_id = %s", (row["user_id"],))
        db.commit()
        return redirect("/pages/login.html?verified=success")

    @app.post("/api/auth/resend-verification")
    def resend_verification():
        data = body_json()
        email = clean_email(data.get("email"))
        generic = jsonify(
            {
                "ok": True,
                "message": "If that account still needs confirmation, we've sent a new link.",
            }
        )

        now = utcnow()
        db.execute("DELETE FROM email_verifications WHERE expires_at < %s", (fmt(now),))
        user = db.one("SELECT * FROM users WHERE email = %s", (email,))
        if user is None or email_is_verified(user):
            db.commit()
            return generic

        recent = db.one(
            "SELECT id FROM email_verifications WHERE user_id = %s AND created_at > %s",
            (user["id"], fmt(now - timedelta(seconds=RESET_COOLDOWN_SECONDS))),
        )
        if recent:
            db.commit()
            return generic

        link = issue_verification(user, now)
        db.commit()
        send_auth_email("verify", user["email"], link)
        return generic

    # ---------- account API ----------
    @app.patch("/api/account")
    @login_required
    def update_account():
        data = body_json()
        if "name" not in data and "email" not in data:
            raise ValidationError("Nothing to update.")
        name = clean_name(data["name"]) if "name" in data else g.user["full_name"]
        email = clean_email(data["email"]) if "email" in data else g.user["email"]

        try:
            db.execute(
                "UPDATE users SET full_name = %s, email = %s, updated_at = %s WHERE id = %s",
                (name, email, fmt(utcnow()), g.user["id"]),
            )
            db.commit()
        except INTEGRITY_ERRORS:
            return error("That email is already used by another account.", 409, "email")

        user = db.one("SELECT * FROM users WHERE id = %s", (g.user["id"],))
        return jsonify({"ok": True, "user": public_user(user)})

    @app.post("/api/account/password")
    @login_required
    def change_password():
        data = body_json()
        current = data.get("current_password")
        if not isinstance(current, str) or not check_password_hash(g.user["password_hash"], current):
            return error("Your current password is incorrect.", 400, "current_password")
        new_password = clean_password(data.get("new_password"), "new_password")
        if new_password == current:
            return error("Choose a password different from your current one.", 400, "new_password")

        new_hash = generate_password_hash(new_password)
        db.execute(
            "UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s",
            (new_hash, fmt(utcnow()), g.user["id"]),
        )
        db.execute("DELETE FROM password_resets WHERE user_id = %s", (g.user["id"],))
        db.commit()

        user = db.one("SELECT * FROM users WHERE id = %s", (g.user["id"],))
        start_session(user)  # keeps this device signed in; other devices are signed out
        return jsonify({"ok": True})

    # ---------- contact messages ----------
    @app.post("/api/contact")
    def submit_contact():
        key = f"contact|{request.remote_addr}"
        wait = contact_limiter.retry_after(key)
        if wait:
            resp = error("Too many contact attempts. Please try again later.", 429, retry_after=wait)
            resp[0].headers["Retry-After"] = str(wait)
            return resp

        data = body_json()
        email_raw = data.get("email")
        if not isinstance(email_raw, str) or not email_raw.strip():
            return error("Please enter your email address.", 400, "email")
        email = clean_email(email_raw)
        body = data.get("body")
        if not isinstance(body, str) or not body.strip():
            return error("Please enter a message.", 400, "body")
        subject = str(data.get("subject", "")).strip()[:255]
        name = str(data.get("name", "")).strip()[:100] if data.get("name") else None

        now = fmt(utcnow())
        db.execute(
            "INSERT INTO contact_messages (name, email, subject, body, created_at) VALUES (%s, %s, %s, %s, %s)",
            (name, email, subject, body.strip()[:5000], now)
        )
        db.commit()

        # Notify the admin by email when SMTP is configured (silently skipped otherwise).
        admin_emails = [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]
        if admin_emails:
            link = f"{app.config['BASE_URL']}/admin.html"
            for admin_email in admin_emails:
                try:
                    mailer.send_contact_email(app, admin_email, name or "", email, subject, body.strip()[:5000], link)
                except Exception:
                    app.logger.exception("Contact notification to %s failed", admin_email)

        return jsonify({"ok": True, "message": "Message sent successfully! We'll get back to you soon."})

    # ---------- recipes ----------
    from recipes import register_recipe_routes

    register_recipe_routes(app, db, login_required, error)

    # ---------- admin API ----------
    @app.get("/api/admin/members")
    @admin_required
    def list_members():
        """Get all users for the admin members table."""
        rows = db.all("""
            SELECT id, full_name, email, role, created_at, phone, two_factor_enabled
            FROM users
            ORDER BY created_at DESC
        """)
        return jsonify({
            "members": [{
                "id": r["id"],
                "name": r["full_name"],
                "email": r["email"],
                "role": r["role"] or "member",
                "joined": r["created_at"],
                "phone": r["phone"],
                "two_factor_enabled": bool(r["two_factor_enabled"])
            } for r in rows]
        })

    @app.get("/api/admin/stats")
    @admin_required
    def admin_stats():
        """Get admin dashboard stats."""
        total_users = db.one("SELECT COUNT(*) as count FROM users")["count"]
        total_recipes = db.one("SELECT COUNT(*) as count FROM recipes")["count"]
        unread_messages = db.one("SELECT COUNT(*) as count FROM messages WHERE is_read = 0")["count"]
        unread_messages += db.one("SELECT COUNT(*) as count FROM contact_messages WHERE is_read = 0")["count"]

        return jsonify({
            "total_users": total_users,
            "total_recipes": total_recipes,
            "unread_messages": unread_messages
        })

    @app.get("/api/admin/messages")
    @admin_required
    def list_messages():
        """All messages: contact-form submissions plus messages sent from the admin panel."""
        rows = db.all("""
            SELECT id, 'contact' as source, COALESCE(name, 'Unknown sender') as sender_name,
                   email as sender_email, subject, body, is_read, created_at
            FROM contact_messages
            UNION ALL
            SELECT m.id, 'internal' as source, COALESCE(u.full_name, 'Unknown Admin') as sender_name,
                   u.email as sender_email, m.subject, m.body, m.is_read, m.created_at
            FROM messages m
            LEFT JOIN users u ON m.admin_id = u.id
            ORDER BY created_at DESC
        """)
        return jsonify({
            "messages": [{
                "id": r["id"],
                "source": r["source"],
                "sender_name": r["sender_name"],
                "sender_email": r["sender_email"],
                "subject": r["subject"],
                "body": r["body"],
                "is_read": bool(r["is_read"]),
                "created_at": r["created_at"]
            } for r in rows]
        })

    @app.post("/api/admin/messages")
    @admin_required
    def send_message():
        """Send a message through the admin panel."""
        data = body_json()
        subject = str(data.get("subject", "")).strip()[:255]
        body = str(data.get("body", "")).strip()[:5000]

        if not subject:
            return error("Subject is required.", 400, "subject")
        if not body:
            return error("Message body is required.", 400, "body")

        db.execute(
            "INSERT INTO messages (admin_id, subject, body, created_at) VALUES (%s, %s, %s, %s)",
            (g.user["id"], subject, body, fmt(utcnow()))
        )
        db.commit()
        return jsonify({"ok": True, "message": "Message sent successfully!"})

    @app.delete("/api/admin/messages/<int:message_id>")
    @admin_required
    def delete_message(message_id):
        """Delete a message (contact form or admin panel)."""
        source = request.args.get("source", "")
        if source == "contact":
            db.execute("DELETE FROM contact_messages WHERE id = %s", (message_id,))
        else:
            db.execute("DELETE FROM messages WHERE id = %s AND admin_id = %s", (message_id, g.user["id"]))
        db.commit()
        return jsonify({"ok": True})

    @app.patch("/api/admin/messages/<int:message_id>/read")
    @admin_required
    def mark_message_read(message_id):
        """Remove a message from the inbox when an admin marks it as read."""
        source = request.args.get("source", "")
        if source == "contact":
            db.execute("DELETE FROM contact_messages WHERE id = %s", (message_id,))
        elif source == "internal":
            db.execute("DELETE FROM messages WHERE id = %s", (message_id,))
        else:
            return error("Invalid message source.", 400, "source")
        db.commit()
        return jsonify({"ok": True, "deleted": True})

    @app.patch("/api/admin/members/<int:member_id>/role")
    @admin_required
    def update_member_role(member_id):
        """Update member role (admin/moderator/member)."""
        data = body_json()
        new_role = data.get("role", "").lower()

        if new_role not in ["admin", "mod", "member"]:
            return error("Invalid role. Must be admin, mod, or member.", 400, "role")

        db.execute(
            "UPDATE users SET role = %s, updated_at = %s WHERE id = %s",
            (new_role, fmt(utcnow()), member_id)
        )
        db.commit()

        return jsonify({"ok": True, "role": new_role})

    # ---------- admin recipes ----------
    def _split_list(value):
        if not isinstance(value, list):
            return []
        return [str(v).strip() for v in value if str(v).strip()]

    def _slugify(text):
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return slug[:120] or "recipe"

    def _unique_slug(base, exclude_id=None):
        slug = base
        suffix = 1
        while True:
            row = db.one("SELECT id FROM recipes WHERE slug = %s", (slug,))
            if row is None or (exclude_id is not None and row["id"] == exclude_id):
                return slug
            suffix += 1
            tail = f"-{suffix}"
            slug = base[: 120 - len(tail)] + tail

    def _minutes_from_text(text):
        if not isinstance(text, str) or not text.strip():
            return None
        from importer.normalize import parse_minutes

        return parse_minutes(text)

    def _recipe_values(data):
        name = str(data.get("name") or "").strip()
        if not name:
            return None, error("Recipe name is required.", 400, "name")
        description = str(data.get("description") or "").strip()
        if not description:
            return None, error("Description is required.", 400, "description")
        course = str(data.get("course") or "").strip()
        if not course:
            return None, error("Course is required.", 400, "course")
        difficulty = str(data.get("difficulty") or "").strip().lower()[:10]
        try:
            servings = int(data.get("servings") or 2)
        except (TypeError, ValueError):
            servings = 2
        servings = max(1, min(servings, 999))
        image = str(data.get("image") or "").strip().lstrip("/")[:255]
        cooking_time = data.get("cookingTime", "")
        total_minutes = _minutes_from_text(cooking_time)
        if cooking_time is not None and cooking_time != "" and (
            not isinstance(cooking_time, str)
            or not cooking_time.strip()
            or total_minutes is None
            or total_minutes < 1
            or total_minutes > 1440
        ):
            return None, error("Cooking time must be a valid duration from 1 minute to 24 hours.", 400, "cookingTime")
        meals = [p.strip() for p in str(data.get("mealTime") or "").split("·") if p.strip()]
        return {
            "name": name[:150],
            "description": description,
            "course": course[:40],
            "difficulty": difficulty,
            "servings": servings,
            "total_minutes": total_minutes,
            "image": image,
            "meals": [m[:40] for m in meals],
            "flavors": [v[:40] for v in _split_list(data.get("flavors"))],
            "dietary": [v[:40] for v in _split_list(data.get("dietary"))],
            "allergens": [v[:40] for v in _split_list(data.get("allergens"))],
            "ingredients": _split_list(data.get("ingredients")),
            "steps": _split_list(data.get("steps")),
        }, None

    def _replace_recipe_children(recipe_id, values):
        db.execute("DELETE FROM recipe_tags WHERE recipe_id = %s", (recipe_id,))
        db.execute("DELETE FROM recipe_ingredients WHERE recipe_id = %s", (recipe_id,))
        db.execute("DELETE FROM recipe_steps WHERE recipe_id = %s", (recipe_id,))
        tags = (
            [("meal", v) for v in values["meals"]]
            + [("flavor", v) for v in values["flavors"]]
            + [("occasion", v) for v in values["dietary"]]
            + [("allergen", v) for v in values["allergens"]]
        )
        for kind, value in tags:
            db.execute(
                "INSERT INTO recipe_tags (recipe_id, kind, value) VALUES (%s, %s, %s)",
                (recipe_id, kind, value),
            )
        for pos, raw in enumerate(values["ingredients"], start=1):
            db.execute(
                "INSERT INTO recipe_ingredients (recipe_id, position, raw, display, match_spec) VALUES (%s, %s, %s, %s, %s)",
                (recipe_id, pos, raw[:500], raw[:600], raw[:1000]),
            )
        for pos, body in enumerate(values["steps"], start=1):
            db.execute(
                "INSERT INTO recipe_steps (recipe_id, position, body) VALUES (%s, %s, %s)",
                (recipe_id, pos, body),
            )

    def _admin_recipes_payload():
        rows = db.all("SELECT * FROM recipes ORDER BY created_at DESC, id DESC")
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        ph = ",".join(["%s"] * len(ids))
        tag_rows = db.all(f"SELECT recipe_id, kind, value FROM recipe_tags WHERE recipe_id IN ({ph})", ids)
        ing_rows = db.all(
            f"SELECT recipe_id, raw, display FROM recipe_ingredients WHERE recipe_id IN ({ph}) ORDER BY recipe_id, position",
            ids,
        )
        step_rows = db.all(
            f"SELECT recipe_id, body FROM recipe_steps WHERE recipe_id IN ({ph}) ORDER BY recipe_id, position",
            ids,
        )
        tags, ings, steps = {}, {}, {}
        for t in tag_rows:
            tags.setdefault(t["recipe_id"], []).append(t)
        for i in ing_rows:
            ings.setdefault(i["recipe_id"], []).append(i)
        for s in step_rows:
            steps.setdefault(s["recipe_id"], []).append(s)
        out = []
        for r in rows:
            rid = r["id"]
            rtags = tags.get(rid, [])
            total = r.get("total_minutes")
            time_needs_review = total is not None and (total < 1 or total > 1440)
            out.append({
                "id": rid,
                "name": r["name"],
                "createdAt": r["created_at"],
                "description": r["description"],
                "image": ("/" + r["image"]) if r.get("image") else "",
                "flavors": [t["value"] for t in rtags if t["kind"] == "flavor"],
                "course": r["meal_course"],
                "mealTime": " · ".join(t["value"] for t in rtags if t["kind"] == "meal"),
                "cookingTime": (f"{total} min" if total and not time_needs_review else ""),
                "timeNeedsReview": time_needs_review,
                "difficulty": r["difficulty"] or "",
                "servings": r["servings"],
                "dietary": [t["value"] for t in rtags if t["kind"] == "occasion"],
                "allergens": [t["value"] for t in rtags if t["kind"] in ("allergen", "allergen_may")],
                "ingredients": [(i.get("display") or i["raw"]) for i in ings.get(rid, [])],
                "steps": [s["body"] for s in steps.get(rid, [])],
            })
        return out

    @app.get("/api/admin/recipes")
    @admin_required
    def admin_list_recipes():
        return jsonify({"recipes": _admin_recipes_payload()})

    @app.post("/api/admin/recipes")
    @admin_required
    def admin_create_recipe():
        data = body_json()
        values, err = _recipe_values(data)
        if err:
            return err
        slug = _unique_slug(_slugify(values["name"]))
        now = fmt(utcnow())
        try:
            db.execute(
                """INSERT INTO recipes (slug, name, description, meal_course, difficulty, servings,
                       total_minutes, image, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (slug, values["name"], values["description"], values["course"], values["difficulty"],
                 values["servings"], values["total_minutes"], values["image"], now, now),
            )
            recipe_id = db.one("SELECT id FROM recipes WHERE slug = %s", (slug,))["id"]
            _replace_recipe_children(recipe_id, values)
            db.commit()
        except Exception:
            db.conn().rollback()
            raise
        return jsonify({"recipe": {"id": recipe_id, "slug": slug}}), 201

    @app.put("/api/admin/recipes/<int:recipe_id>")
    @admin_required
    def admin_update_recipe(recipe_id):
        if db.one("SELECT id FROM recipes WHERE id = %s", (recipe_id,)) is None:
            return error("Recipe not found.", 404)
        data = body_json()
        values, err = _recipe_values(data)
        if err:
            return err
        slug = _unique_slug(_slugify(values["name"]), exclude_id=recipe_id)
        try:
            db.execute(
                """UPDATE recipes SET slug = %s, name = %s, description = %s, meal_course = %s, difficulty = %s,
                       servings = %s, total_minutes = %s, image = %s, updated_at = %s WHERE id = %s""",
                (slug, values["name"], values["description"], values["course"], values["difficulty"],
                 values["servings"], values["total_minutes"], values["image"], fmt(utcnow()), recipe_id),
            )
            _replace_recipe_children(recipe_id, values)
            db.commit()
        except Exception:
            db.conn().rollback()
            raise
        return jsonify({"recipe": {"id": recipe_id, "slug": slug}})

    @app.delete("/api/admin/recipes/<int:recipe_id>")
    @admin_required
    def admin_delete_recipe(recipe_id):
        if db.one("SELECT id FROM recipes WHERE id = %s", (recipe_id,)) is None:
            return error("Recipe not found.", 404)
        db.execute("DELETE FROM recipes WHERE id = %s", (recipe_id,))
        db.commit()
        return jsonify({"ok": True})

    # ---------- 2FA and Account Settings API ----------
    @app.post("/api/account/2fa/setup")
    @login_required
    def setup_2fa():
        """Setup 2FA: generates a secret."""
        secret = generate_totp_secret()
        label = quote(g.user["email"])
        otpauth = f"otpauth://totp/Recifix:{label}?secret={secret}&issuer=Recifix"
        return jsonify({"ok": True, "secret": secret, "otpauth_url": otpauth})

    @app.post("/api/account/2fa/verify")
    @login_required
    def verify_2fa():
        """Verify 2FA code and enable."""
        data = body_json()
        secret = data.get("secret")
        code = data.get("code")

        if not isinstance(secret, str) or not isinstance(code, str) or not verify_totp(secret, code):
            return error("Invalid 2FA code.", 400)

        db.execute(
            "UPDATE users SET two_factor_secret = %s, two_factor_enabled = 1, updated_at = %s WHERE id = %s",
            (secret, fmt(utcnow()), g.user["id"])
        )
        db.commit()
        return jsonify({"ok": True, "user": public_user(db.one("SELECT * FROM users WHERE id = %s", (g.user["id"],)))})

    @app.post("/api/account/2fa/disable")
    @login_required
    def disable_2fa():
        """Turn off authenticator login. Requires a current code."""
        data = body_json()
        if not two_factor_active(g.user):
            return jsonify({"ok": True, "user": public_user(g.user)})
        code = data.get("code")
        if not isinstance(code, str) or not verify_totp(g.user["two_factor_secret"], code):
            return error("Enter a current authenticator code to turn off 2FA.", 400, "code")
        db.execute(
            "UPDATE users SET two_factor_secret = NULL, two_factor_enabled = 0, updated_at = %s WHERE id = %s",
            (fmt(utcnow()), g.user["id"]),
        )
        db.commit()
        user = db.one("SELECT * FROM users WHERE id = %s", (g.user["id"],))
        return jsonify({"ok": True, "user": public_user(user)})

    @app.patch("/api/account/settings")
    @login_required
    def update_account_settings():
        """Update account settings including name, email, phone, and 2FA."""
        data = body_json()
        update_fields = []
        update_values = []

        if "name" in data:
            name = clean_name(data["name"])
            update_fields.append("full_name = %s")
            update_values.append(name)

        if "email" in data:
            email = clean_email(data["email"])
            update_fields.append("email = %s")
            update_values.append(email)

        if "phone" in data:
            phone = str(data.get("phone", "")).strip()
            if phone and len(phone) > 20:
                return error("Phone number must be 20 characters or fewer.", 400, "phone")
            update_fields.append("phone = %s")
            update_values.append(phone or None)

        if "two_factor_enabled" in data:
            return error(
                "Use authenticator setup to change two-factor authentication.",
                400,
                "two_factor_enabled",
            )

        if not update_fields:
            return error("Nothing to update.", 400)

        update_values.extend([fmt(utcnow()), g.user["id"]])
        db.execute(
            f"UPDATE users SET {', '.join(update_fields)}, updated_at = %s WHERE id = %s",
            update_values
        )
        db.commit()

        user = db.one("SELECT id, full_name, email, phone, two_factor_enabled FROM users WHERE id = %s", (g.user["id"],))
        return jsonify({"ok": True, "user": {"id": user["id"], "name": user["full_name"], "email": user["email"], "phone": user["phone"], "two_factor_enabled": bool(user["two_factor_enabled"])}})

    # ---------- front end ----------
    def page(name):
        return send_from_directory(frontend, name)

    @app.get("/")
    @app.get("/index.html")
    def landing():
        return page("index.html")

    @app.get("/dashboard.html")
    def dashboard():
        if current_user() is None:
            return redirect("/pages/login.html")
        resp = page("dashboard.html")
        resp.headers["Cache-Control"] = "no-store"  # don't show it from cache after logout
        return resp

    @app.get("/admin.html")
    @app.get("/admin-members.html")
    @app.get("/admin-messages.html")
    @app.get("/admin-recipes.html")
    @app.get("/admin-settings.html")
    def admin_dashboard():
        name = request.path.lstrip("/") or "admin.html"
        user = current_user()
        if user is None:
            return redirect("/pages/login.html")
        if not is_admin_user(user):
            return error("Admin access required.", 403)
        resp = page(name)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/<any(css,js,images,pages):folder>/<path:filename>")
    def assets(folder, filename):
        return send_from_directory(frontend / folder, filename)

# 🤖 RECIFIX PERSONALIZED HISTORY ML ENGINE ROUTE
    @app.route("/api/recipes/recommend", methods=["POST"])
    def recommend_recipes():
        nonlocal tfidf_matrix, recipes_cache, vectorizer
        
        if tfidf_matrix is None or not recipes_cache:
            return error("The recommendation matrix engine is currently empty or updating.", 503)

        uid = session.get("user_id")
        user_saved_keywords = []

        if uid:
            # Gathers the taste keywords from recipes the logged-in user has saved
            saved_query = """
                SELECT REPLACE(REPLACE(i.match_spec, ';', ' '), '|', ' ') AS clean_keywords
                FROM saved_recipes s
                JOIN recipe_ingredients i ON s.recipe_id = i.recipe_id
                WHERE s.user_id = %s
            """
            try:
                saved_rows = db.all(saved_query, (uid,))
                user_saved_keywords = [row["clean_keywords"] for row in saved_rows]
            except Exception as e:
                app.logger.error(f"Error fetching user saved history matrix: {e}")

        # Determine personalization state
        if user_saved_keywords:
            query_ingredients = " ".join(user_saved_keywords)
            is_personalized = True
        else:
            # Baseline fallback staples if user hasn't saved anything yet
            query_ingredients = "garlic onion olive oil salt pepper flour"
            is_personalized = False

        # Transform and calculate geometric cosine distance metrics
        user_vector = vectorizer.transform([query_ingredients])
        similarity_scores = cosine_similarity(user_vector, tfidf_matrix).flatten()

        scored_recipes = []
        for index, score in enumerate(similarity_scores):
            recipe = recipes_cache[index]
            
            # Exclude items they have already saved from cluttering their recommendations section
            if uid and is_personalized:
                already_saved = db.one("SELECT 1 FROM saved_recipes WHERE user_id = %s AND recipe_id = %s", (uid, recipe["id"]))
                if already_saved:
                    continue

            if score > 0.02:
                scored_recipes.append((score, recipe))

        # Sort from highest mathematical similarity down to lowest
        scored_recipes.sort(key=lambda x: x[0], reverse=True)

        top_matches = []
        for score, recipe in scored_recipes[:3]:
            top_matches.append({
                "id": recipe["id"],
                "title": recipe["title"],
                "image": recipe["image"], # Added this mapping value
                "match_percentage": int(round(float(score) * 100))
            })

        return jsonify({
            "recipes": top_matches, 
            "personalized": is_personalized
        })
        
    # FETCH FULL RECIPE DETAILS FOR THE MODAL VIEWER
    @app.route("/api/recipes/<int:recipe_id>", methods=["GET"])
    def get_recipe_details(recipe_id):
        # 1. Fetch primary recipe details
        recipe = db.one("SELECT id, name, description, image, prep_minutes, cook_minutes, servings, difficulty FROM recipes WHERE id = %s", (recipe_id,))
        if not recipe:
            return error("Recipe not found.", 404)

        # 2. Fetch linked structural ingredient listings with safe explicit tuple parameters
        ingredients = db.all("SELECT display FROM recipe_ingredients WHERE recipe_id = %s ORDER BY position", (recipe_id,))
        
        # 3. Fetch step-by-step procedures with safe explicit tuple parameters
        steps = db.all("SELECT body FROM recipe_steps WHERE recipe_id = %s ORDER BY position", (recipe_id,))

        # 🟢 SECURE FORMAT RETRIEVAL DEFENSE LAYER
        return jsonify({
            "id": int(recipe["id"]),
            "title": recipe["name"],
            "description": recipe["description"],
            "image": recipe["image"] or "images/intro-image.jpg",
            "prep_time": recipe["prep_minutes"] or 0,
            "cook_time": recipe["cook_minutes"] or 0,
            "servings": recipe["servings"] or 2,
            "difficulty": recipe["difficulty"] or "Easy",
            "ingredients": [i["display"] for i in ingredients] if ingredients else [],
            "steps": [s["body"] for s in steps] if steps else []
        })
    return app
