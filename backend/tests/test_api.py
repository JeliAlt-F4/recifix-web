import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("SMTP_HOST", None)

from app import create_app  # noqa: E402


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outbox = []
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE_URL": f"sqlite:///{self.tmp.name}/test.db",
                "MAILER": lambda to, link: self.outbox.append((to, link)),
            }
        )
        with self.app.app_context():
            self.app.extensions["db"].init_schema()
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def link_path(self, link):
        return re.sub(r"^https?://[^/]+", "", link)

    def signup(self, client=None, name="Maria Santos", email="maria@example.com", password="secret123"):
        client = client or self.client
        response = client.post(
            "/api/auth/signup", json={"fullname": name, "email": email, "password": password}
        )
        if response.status_code == 201:
            _to, link = self.outbox.pop()
            confirmed = client.get(self.link_path(link))
            self.assertIn("verified=success", confirmed.headers.get("Location", ""))
            logged = client.post(
                "/api/auth/login",
                json={"email": email.strip().lower(), "password": password},
            )
            self.assertEqual(logged.status_code, 200, logged.get_json())
        return response

    def login(self, client=None, email="maria@example.com", password="secret123"):
        return (client or self.client).post("/api/auth/login", json={"email": email, "password": password})


class SignupTests(ApiTestCase):
    def test_signup_requires_email_confirmation_before_login(self):
        r = self.client.post(
            "/api/auth/signup",
            json={"fullname": "Maria Santos", "email": "maria@example.com", "password": "secret123"},
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json["verification_required"])
        self.assertNotIn("user", r.json)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        blocked = self.login()
        self.assertEqual(blocked.status_code, 403)
        self.assertTrue(blocked.json["verification_required"])

        confirmed = self.client.get(self.link_path(self.outbox[0][1]))
        self.assertIn("verified=success", confirmed.headers["Location"])
        self.assertEqual(self.login().status_code, 200)
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json["user"]["email"], "maria@example.com")

    def test_password_is_hashed_not_stored(self):
        self.signup()
        with self.app.app_context():
            row = self.app.extensions["db"].one("SELECT password_hash FROM users")
        self.assertNotIn("secret123", row["password_hash"])
        self.assertTrue(row["password_hash"].startswith(("scrypt:", "pbkdf2:")))

    def test_email_normalised_and_unique(self):
        self.signup(email="Maria@Example.com ")
        r = self.signup(client=self.app.test_client(), email="maria@example.com")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json["field"], "email")

    def test_validation(self):
        bad = [
            {"fullname": "", "email": "a@b.co", "password": "secret123"},
            {"fullname": "A", "email": "not-an-email", "password": "secret123"},
            {"fullname": "A", "email": "a@b.co", "password": "short"},
            {"fullname": "A", "email": "a@b.co", "password": 12345678},
            {"fullname": ["x"], "email": "a@b.co", "password": "secret123"},
            {"fullname": "x" * 101, "email": "a@b.co", "password": "secret123"},
        ]
        for payload in bad:
            r = self.client.post("/api/auth/signup", json=payload)
            self.assertEqual(r.status_code, 400, payload)
            self.assertIn("error", r.json)

    def test_non_json_body_rejected(self):
        r = self.client.post("/api/auth/signup", data={"email": "a@b.co"})
        self.assertEqual(r.status_code, 415)


class LoginTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.signup()
        self.client = self.app.test_client()  # logged out

    def test_login_success_and_logout(self):
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_login_is_case_insensitive_on_email(self):
        self.assertEqual(self.login(email="MARIA@example.com").status_code, 200)

    def test_wrong_password_and_unknown_user_look_identical(self):
        a = self.login(password="wrongpass1")
        b = self.login(email="nobody@example.com")
        self.assertEqual((a.status_code, a.json), (401, {"error": "Incorrect email or password."}))
        self.assertEqual((b.status_code, b.json), (401, {"error": "Incorrect email or password."}))

    def test_rate_limit_after_repeated_failures(self):
        for _ in range(5):
            self.assertEqual(self.login(password="wrongpass1").status_code, 401)
        r = self.login(password="wrongpass1")
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r.headers)
        # even the correct password is blocked during the lockout
        self.assertEqual(self.login().status_code, 429)

    def test_successful_login_resets_counter(self):
        for _ in range(4):
            self.login(password="wrongpass1")
        self.assertEqual(self.login().status_code, 200)
        for _ in range(4):
            self.assertEqual(self.login(password="wrongpass1").status_code, 401)

    def test_protected_routes_require_login(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.patch("/api/account", json={"name": "X"}).status_code, 401)
        self.assertEqual(self.client.post("/api/account/password", json={}).status_code, 401)


class AccountTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.signup()

    def test_update_name_and_email(self):
        r = self.client.patch("/api/account", json={"name": "  Maria  L. Santos ", "email": "New@Example.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json["user"],
            {
                "id": 1,
                "name": "Maria L. Santos",
                "email": "new@example.com",
                "role": "member",
                "phone": None,
                "two_factor_enabled": False,
            },
        )
        self.assertEqual(self.login(self.app.test_client(), email="new@example.com").status_code, 200)

    def test_cannot_take_another_accounts_email(self):
        other = self.app.test_client()
        self.signup(client=other, name="Juan", email="juan@example.com")
        r = self.client.patch("/api/account", json={"email": "juan@example.com"})
        self.assertEqual(r.status_code, 409)

    def test_update_requires_a_field(self):
        self.assertEqual(self.client.patch("/api/account", json={}).status_code, 400)

    def test_change_password(self):
        r = self.client.post(
            "/api/account/password", json={"current_password": "secret123", "new_password": "brandnew456"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)  # this device stays signed in
        fresh = self.app.test_client()
        self.assertEqual(self.login(fresh, password="secret123").status_code, 401)
        self.assertEqual(self.login(fresh, password="brandnew456").status_code, 200)

    def test_change_password_signs_out_other_devices(self):
        other = self.app.test_client()
        self.login(other)
        self.assertEqual(other.get("/api/auth/me").status_code, 200)
        self.client.post("/api/account/password", json={"current_password": "secret123", "new_password": "brandnew456"})
        self.assertEqual(other.get("/api/auth/me").status_code, 401)

    def test_change_password_checks(self):
        wrong = self.client.post("/api/account/password", json={"current_password": "nope", "new_password": "brandnew456"})
        self.assertEqual((wrong.status_code, wrong.json["field"]), (400, "current_password"))
        short = self.client.post("/api/account/password", json={"current_password": "secret123", "new_password": "abc"})
        self.assertEqual(short.status_code, 400)
        same = self.client.post("/api/account/password", json={"current_password": "secret123", "new_password": "secret123"})
        self.assertEqual(same.status_code, 400)


class ForgotPasswordTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.signup()
        self.anon = self.app.test_client()

    def request_reset(self, email="maria@example.com", pw="resetpass99"):
        return self.anon.post("/api/auth/forgot-password", json={"email": email, "new_password": pw})

    def test_password_unchanged_until_link_is_opened(self):
        r = self.request_reset()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.outbox), 1)
        self.assertEqual(self.login(self.app.test_client(), password="secret123").status_code, 200)
        self.assertEqual(self.login(self.app.test_client(), password="resetpass99").status_code, 401)

    def test_confirm_link_applies_new_password_once(self):
        self.request_reset()
        link = self.outbox[0][1]
        path = self.link_path(link)
        r = self.anon.get(path)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("reset=success"))
        self.assertEqual(self.login(self.app.test_client(), password="resetpass99").status_code, 200)
        self.assertEqual(self.login(self.app.test_client(), password="secret123").status_code, 401)
        # token is single-use
        again = self.anon.get(path)
        self.assertTrue(again.headers["Location"].endswith("reset=invalid"))

    def test_unknown_email_gets_same_response_and_no_mail(self):
        known = self.request_reset()
        unknown = self.request_reset(email="ghost@example.com")
        self.assertEqual((known.status_code, known.json), (unknown.status_code, unknown.json))
        self.assertEqual(len(self.outbox), 1)

    def test_invalid_or_expired_token(self):
        r = self.anon.get("/api/auth/confirm-reset?token=garbage")
        self.assertTrue(r.headers["Location"].endswith("reset=invalid"))
        self.request_reset()
        with self.app.app_context():
            self.app.extensions["db"].execute("UPDATE password_resets SET expires_at = '2000-01-01 00:00:00'")
            self.app.extensions["db"].commit()
        link_path = self.link_path(self.outbox[0][1])
        self.assertTrue(self.anon.get(link_path).headers["Location"].endswith("reset=invalid"))

    def test_cooldown_prevents_email_spam(self):
        self.request_reset()
        self.request_reset()
        self.assertEqual(len(self.outbox), 1)

    def test_weak_new_password_rejected(self):
        self.assertEqual(self.request_reset(pw="123").status_code, 400)
        self.assertEqual(len(self.outbox), 0)

    def test_reset_signs_out_existing_sessions(self):
        self.request_reset()
        self.anon.get(self.link_path(self.outbox[0][1]))
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)


class EmailVerificationTests(ApiTestCase):
    def raw_signup(self, email="maria@example.com"):
        return self.client.post(
            "/api/auth/signup",
            json={"fullname": "Maria Santos", "email": email, "password": "secret123"},
        )

    def test_invalid_or_expired_link(self):
        self.raw_signup()
        bad = self.client.get("/api/auth/verify-email?token=garbage")
        self.assertIn("verified=invalid", bad.headers["Location"])
        with self.app.app_context():
            self.app.extensions["db"].execute(
                "UPDATE email_verifications SET expires_at = '2000-01-01 00:00:00'"
            )
            self.app.extensions["db"].commit()
        expired = self.client.get(self.link_path(self.outbox[0][1]))
        self.assertIn("verified=invalid", expired.headers["Location"])
        self.assertEqual(self.login().status_code, 403)

    def test_link_is_single_use(self):
        self.raw_signup()
        path = self.link_path(self.outbox[0][1])
        self.assertIn("verified=success", self.client.get(path).headers["Location"])
        self.assertIn("verified=invalid", self.client.get(path).headers["Location"])

    def test_resend_is_generic_and_rate_limited(self):
        self.raw_signup()
        again = self.client.post("/api/auth/resend-verification", json={"email": "maria@example.com"})
        unknown = self.client.post("/api/auth/resend-verification", json={"email": "ghost@example.com"})
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json, unknown.json)
        self.assertEqual(len(self.outbox), 1)

        with self.app.app_context():
            self.app.extensions["db"].execute(
                "UPDATE email_verifications SET created_at = '2000-01-01 00:00:00'"
            )
            self.app.extensions["db"].commit()
        resent = self.client.post("/api/auth/resend-verification", json={"email": "maria@example.com"})
        self.assertEqual(resent.status_code, 200)
        self.assertEqual(len(self.outbox), 2)
        self.assertIn("verified=success", self.client.get(self.link_path(self.outbox[-1][1])).headers["Location"])

        verified = self.client.post("/api/auth/resend-verification", json={"email": "maria@example.com"})
        self.assertEqual(verified.json, again.json)
        self.assertEqual(len(self.outbox), 2)


class TwoFactorTests(ApiTestCase):
    def enable(self):
        from app import get_totp_token

        self.signup()
        setup = self.client.post("/api/account/2fa/setup")
        self.assertEqual(setup.status_code, 200)
        secret = setup.json["secret"]
        turned_on = self.client.post(
            "/api/account/2fa/verify",
            json={"secret": secret, "code": get_totp_token(secret)},
        )
        self.assertEqual(turned_on.status_code, 200, turned_on.get_json())
        self.client.post("/api/auth/logout")
        return secret

    def test_login_requires_authenticator_code(self):
        from app import get_totp_token

        secret = self.enable()
        blocked = self.login()
        self.assertEqual(blocked.status_code, 200)
        self.assertTrue(blocked.json["two_factor_required"])
        self.assertNotIn("user", blocked.json)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

        wrong = self.client.post(
            "/api/auth/login/2fa",
            json={"challenge": blocked.json["challenge"], "code": "000000"},
        )
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

        ok = self.client.post(
            "/api/auth/login/2fa",
            json={"challenge": blocked.json["challenge"], "code": get_totp_token(secret)},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json["user"]["email"], "maria@example.com")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

        reused = self.client.post(
            "/api/auth/login/2fa",
            json={"challenge": blocked.json["challenge"], "code": get_totp_token(secret)},
        )
        self.assertEqual(reused.status_code, 401)

    def test_settings_cannot_flip_the_flag(self):
        from app import get_totp_token

        secret = self.enable()
        started = self.login()
        self.client.post(
            "/api/auth/login/2fa",
            json={"challenge": started.json["challenge"], "code": get_totp_token(secret)},
        )
        rejected = self.client.patch("/api/account/settings", json={"two_factor_enabled": False})
        self.assertEqual(rejected.status_code, 400)
        still = self.client.post("/api/auth/logout")
        self.assertEqual(still.status_code, 200)
        again = self.login()
        self.assertTrue(again.json["two_factor_required"])

    def test_disable_requires_a_current_code(self):
        from app import get_totp_token

        secret = self.enable()
        challenge = self.login().json["challenge"]
        self.client.post(
            "/api/auth/login/2fa",
            json={"challenge": challenge, "code": get_totp_token(secret)},
        )
        denied = self.client.post("/api/account/2fa/disable", json={"code": "000000"})
        self.assertEqual(denied.status_code, 400)
        turned_off = self.client.post(
            "/api/account/2fa/disable",
            json={"code": get_totp_token(secret)},
        )
        self.assertEqual(turned_off.status_code, 200)
        self.assertFalse(turned_off.json["user"]["two_factor_enabled"])
        self.client.post("/api/auth/logout")
        self.assertIn("user", self.login().json)


class AdminHelperTests(ApiTestCase):
    def test_admin_recipe_cooking_time_must_be_a_reasonable_duration(self):
        from manage_admins import create_admin

        with self.app.app_context():
            create_admin(
                self.app.extensions["db"], "Recifix Admin", "admin@example.com", "secret123"
            )
        logged = self.login(email="admin@example.com")
        self.assertEqual(logged.status_code, 200, logged.get_json())
        payload = {
            "name": "Test recipe",
            "description": "A test recipe.",
            "course": "Main course",
            "cookingTime": "30270 min",
        }
        rejected = self.client.post("/api/admin/recipes", json=payload)
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("24 hours", rejected.get_json()["error"])

        payload["cookingTime"] = "1 hour 30 minutes"
        accepted = self.client.post("/api/admin/recipes", json=payload)
        self.assertEqual(accepted.status_code, 201, accepted.get_json())
        recipes = self.client.get("/api/admin/recipes").get_json()["recipes"]
        self.assertEqual(recipes[0]["cookingTime"], "90 min")
        self.assertTrue(recipes[0]["createdAt"])

        with self.app.app_context():
            db = self.app.extensions["db"]
            db.execute(
                "INSERT INTO recipes (slug, name, description, meal_course, difficulty, servings, "
                "total_minutes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("bad-time", "Legacy recipe", "Imported with a bad time.", "Main course", "easy", 2,
                 30270, "9999-01-01 00:00:00", "9999-01-01 00:00:00"),
            )
            db.commit()
        recipes = self.client.get("/api/admin/recipes").get_json()["recipes"]
        legacy = next(recipe for recipe in recipes if recipe["name"] == "Legacy recipe")
        self.assertEqual(legacy["cookingTime"], "")
        self.assertTrue(legacy["timeNeedsReview"])
        self.assertEqual(legacy["createdAt"], "9999-01-01 00:00:00")

    def test_marking_a_message_as_read_deletes_it(self):
        from manage_admins import create_admin

        with self.app.app_context():
            create_admin(
                self.app.extensions["db"], "Recifix Admin", "admin@example.com", "secret123"
            )
            db = self.app.extensions["db"]
            db.execute(
                "INSERT INTO contact_messages (name, email, subject, body, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("Visitor", "visitor@example.com", "Hello", "First message", "2026-11-16 12:00:00"),
            )
            db.execute(
                "INSERT INTO contact_messages (name, email, subject, body, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("Visitor", "visitor@example.com", "Question", "Second message", "2026-11-16 12:01:00"),
            )
            db.commit()
            message_id = db.one(
                "SELECT id FROM contact_messages WHERE subject = ?", ("Hello",)
            )["id"]

        logged = self.login(email="admin@example.com")
        self.assertEqual(logged.status_code, 200, logged.get_json())

        response = self.client.patch(
            f"/api/admin/messages/{message_id}/read?source=contact"
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(response.get_json()["deleted"])

        remaining = self.client.get("/api/admin/messages").get_json()["messages"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["subject"], "Question")

    def test_admin_member_count_matches_member_list_after_signup(self):
        from manage_admins import create_admin

        with self.app.app_context():
            create_admin(
                self.app.extensions["db"], "Recifix Admin", "admin@example.com", "secret123"
            )
        logged = self.login(email="admin@example.com")
        self.assertEqual(logged.status_code, 200, logged.get_json())

        initial_stats = self.client.get("/api/admin/stats").get_json()
        initial_members = self.client.get("/api/admin/members").get_json()["members"]
        self.assertEqual(initial_stats["total_users"], len(initial_members))

        signup_client = self.app.test_client()
        response = signup_client.post(
            "/api/auth/signup",
            json={"fullname": "New Member", "email": "new@example.com", "password": "secret123"},
        )
        self.assertEqual(response.status_code, 201, response.get_json())

        updated_stats = self.client.get("/api/admin/stats").get_json()
        updated_members = self.client.get("/api/admin/members").get_json()["members"]
        self.assertEqual(updated_stats["total_users"], len(updated_members))
        self.assertEqual(updated_stats["total_users"], initial_stats["total_users"] + 1)

    def test_created_admin_can_open_the_dashboard(self):
        from manage_admins import create_admin

        with self.app.app_context():
            result = create_admin(
                self.app.extensions["db"], "Recifix Admin", "admin@example.com", "secret123"
            )
        self.assertEqual(result, "created")
        with patch.dict(os.environ, {"ADMIN_EMAILS": ""}):
            logged = self.login(email="admin@example.com")
            self.assertEqual(logged.status_code, 200, logged.get_json())
            page = self.client.get("/admin.html")
            self.assertEqual(page.status_code, 200)
            page.close()


class FrontendTests(ApiTestCase):
    def test_public_pages_served(self):
        for path in ("/", "/index.html", "/pages/login.html", "/pages/signup.html", "/css/style.css", "/js/script.js"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            r.close()

    def test_dashboard_requires_login(self):
        r = self.client.get("/dashboard.html")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/pages/login.html"))
        self.signup()
        ok = self.client.get("/dashboard.html")
        self.assertEqual(ok.status_code, 200)
        self.assertIn("no-store", ok.headers["Cache-Control"])
        ok.close()

    def test_admin_dashboard_requires_allowlisted_login(self):
        with patch.dict(os.environ, {"ADMIN_EMAILS": ""}):
            response = self.client.get("/admin.html")
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.headers["Location"].endswith("/pages/login.html"))

            self.signup()
            denied = self.client.get("/admin.html")
            self.assertEqual(denied.status_code, 403)

        with patch.dict(os.environ, {"ADMIN_EMAILS": "maria@example.com"}):
            allowed = self.client.get("/admin.html")
            self.assertEqual(allowed.status_code, 200)
            self.assertIn("no-store", allowed.headers["Cache-Control"])
            allowed.close()

    def test_backend_source_is_not_exposed(self):
        for path in ("/backend/app.py", "/backend/.env", "/app.py", "/js/../backend/app.py", "/pages/../backend/app.py"):
            self.assertEqual(self.client.get(path).status_code, 404, path)


if __name__ == "__main__":
    unittest.main()
