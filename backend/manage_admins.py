"""Create, promote, or list Recifix admin accounts.

Examples:
  python manage_admins.py list
  python manage_admins.py create --email you@example.com --name "Ada Lovelace"
  python manage_admins.py promote --email you@example.com

The password is requested in the terminal so it is not saved in shell history.
Accounts created here can open the admin dashboard (role = admin) and are
marked email-verified.
"""
import argparse
import getpass
import sys
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash

from app import clean_email, clean_name, clean_password, create_app
from db import INTEGRITY_ERRORS


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def list_admins(db):
    return db.all(
        "SELECT id, full_name, email, role, email_verified, two_factor_enabled "
        "FROM users WHERE role = %s ORDER BY email",
        ("admin",),
    )


def create_admin(db, name, email, password):
    name = clean_name(name)
    email = clean_email(email)
    password = clean_password(password)
    now = _now()
    password_hash = generate_password_hash(password)
    existing = db.one("SELECT id FROM users WHERE email = %s", (email,))
    if existing:
        db.execute(
            "UPDATE users SET full_name = %s, password_hash = %s, role = %s, "
            "email_verified = 1, updated_at = %s WHERE id = %s",
            (name, password_hash, "admin", now, existing["id"]),
        )
        db.commit()
        return "updated"
    try:
        db.execute(
            "INSERT INTO users (full_name, email, password_hash, role, email_verified, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (name, email, password_hash, "admin", 1, now, now),
        )
        db.commit()
    except INTEGRITY_ERRORS:
        return "exists"
    return "created"


def promote_admin(db, email):
    email = clean_email(email)
    user = db.one("SELECT id, full_name FROM users WHERE email = %s", (email,))
    if user is None:
        return None
    db.execute(
        "UPDATE users SET role = %s, email_verified = 1, updated_at = %s WHERE id = %s",
        ("admin", _now(), user["id"]),
    )
    db.commit()
    return user


def _read_password():
    first = getpass.getpass("Password (min 8 characters): ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords did not match.")
    return first


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create or list Recifix admin accounts.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Show accounts whose role is admin")

    create = sub.add_parser("create", help="Create an admin, or reset one that already exists")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--password", help="Prefer omitting this so the password is prompted")

    promote = sub.add_parser("promote", help="Give an existing account the admin role")
    promote.add_argument("--email", required=True)

    args = parser.parse_args(argv)
    app = create_app()
    with app.app_context():
        db = app.extensions["db"]
        db.init_schema()
        if args.command == "list":
            rows = list_admins(db)
            if not rows:
                print("No admin accounts yet.")
                return 0
            for row in rows:
                verified = "verified" if row["email_verified"] else "unverified"
                second = "2FA on" if row["two_factor_enabled"] else "2FA off"
                print(f"{row['email']}  {row['full_name']}  {verified}  {second}")
            return 0
        if args.command == "promote":
            user = promote_admin(db, args.email)
            if user is None:
                print("No account uses that email.", file=sys.stderr)
                return 1
            print(f"Promoted {args.email.strip().lower()} to admin.")
            return 0
        password = args.password or _read_password()
        result = create_admin(db, args.name, args.email, password)
        if result == "exists":
            print("That email was just created by someone else. Try again.", file=sys.stderr)
            return 1
        verb = "Updated" if result == "updated" else "Created"
        print(f"{verb} admin {args.email.strip().lower()}.")
        print("They can log in and open /admin.html.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
