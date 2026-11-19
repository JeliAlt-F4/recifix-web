"""Small database layer.

Production target is MySQL via PyMySQL. SQLite is supported only so the test
suite can run without a MySQL server. All SQL in the app is written with %s
placeholders and standard syntax so it runs on both.
"""
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from flask import g

INTEGRITY_ERRORS = (sqlite3.IntegrityError,)
try:  # PyMySQL is only needed when talking to MySQL
    import pymysql
    import pymysql.cursors

    INTEGRITY_ERRORS += (pymysql.err.IntegrityError,)
except ImportError:  # pragma: no cover
    pymysql = None

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 1,
    role TEXT NOT NULL DEFAULT 'member',
    phone TEXT,
    two_factor_secret TEXT,
    two_factor_enabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS email_verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    new_password_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    meal_course TEXT NOT NULL,
    difficulty TEXT NOT NULL DEFAULT '',
    servings INTEGER NOT NULL DEFAULT 2,
    prep_minutes INTEGER, cook_minutes INTEGER, total_minutes INTEGER,
    time_notes TEXT NOT NULL DEFAULT '',
    allergen_text TEXT NOT NULL DEFAULT '',
    allergens_verified INTEGER NOT NULL DEFAULT 0,
    image TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recipe_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    section TEXT,
    raw TEXT NOT NULL,
    display TEXT NOT NULL DEFAULT '',
    match_spec TEXT NOT NULL DEFAULT '',
    is_optional INTEGER NOT NULL DEFAULT 0,
    is_staple INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS recipe_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recipe_tags (
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (recipe_id, kind, value)
);
CREATE TABLE IF NOT EXISTS saved_recipes (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, recipe_id)
);
CREATE TABLE IF NOT EXISTS contact_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT NOT NULL,
    subject TEXT,
    body TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def split_sql(text: str) -> list:
    """Split a schema file into statements. Comment lines are removed first, so a
    semicolon inside a comment can never be mistaken for the end of a statement."""
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


class Database:
    def __init__(self, url: str):
        parsed = urlparse(url)
        if parsed.scheme.startswith("mysql"):
            if pymysql is None:
                raise RuntimeError("PyMySQL is not installed. Run: pip install -r requirements.txt")
            self.kind = "mysql"
            self.mysql = {
                "host": parsed.hostname or "127.0.0.1",
                "port": parsed.port or 3306,
                "user": unquote(parsed.username or ""),
                "password": unquote(parsed.password or ""),
                "database": parsed.path.lstrip("/"),
            }
        elif parsed.scheme == "sqlite":
            self.kind = "sqlite"
            self.sqlite_path = url[len("sqlite:///"):]
        else:
            raise ValueError("DATABASE_URL must start with mysql:// or sqlite:///")

    # -- connection handling (one connection per request, stored on flask.g) --
    def _connect(self):
        if self.kind == "mysql":
            return pymysql.connect(
                **self.mysql,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=10,
            )
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def conn(self):
        if "db_conn" not in g:
            g.db_conn = self._connect()
        return g.db_conn

    def close(self, exc=None):
        conn = g.pop("db_conn", None)
        if conn is not None:
            try:
                if exc is not None:
                    conn.rollback()
            finally:
                conn.close()

    # -- queries --
    def _run(self, sql, params=()):
        if self.kind == "sqlite":
            sql = sql.replace("%s", "?")
        cur = self.conn().cursor()
        cur.execute(sql, params)
        return cur

    def one(self, sql, params=()):
        cur = self._run(sql, params)
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None

    def execute(self, sql, params=()):
        cur = self._run(sql, params)
        result = (cur.lastrowid, cur.rowcount)
        cur.close()
        return result

    def all(self, sql, params=()):
        cur = self._run(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        return rows

    def executemany(self, sql, seq):
        seq = list(seq)
        if not seq:
            return
        if self.kind == "sqlite":
            sql = sql.replace("%s", "?")
        cur = self.conn().cursor()
        cur.executemany(sql, seq)
        cur.close()

    def commit(self):
        self.conn().commit()

    # -- schema --
    def init_schema(self):
        conn = self.conn()
        if self.kind == "sqlite":
            conn.executescript(SQLITE_SCHEMA)
        else:
            sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
            cur = conn.cursor()
            for statement in split_sql(sql):
                cur.execute(statement)
            cur.close()
        self.ensure_email_verification()
        self.ensure_account_security()
        conn.commit()

    def _table_exists(self, table: str) -> bool:
        if self.kind == "sqlite":
            row = self.one(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = %s",
                (table,),
            )
        else:
            row = self.one(
                "SELECT TABLE_NAME AS name FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                (table,),
            )
        return row is not None

    def _column_exists(self, table: str, column: str) -> bool:
        if self.kind == "sqlite":
            rows = self.all(f"PRAGMA table_info({table})")
            return any(r["name"] == column for r in rows)
        row = self.one(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
            (table, column),
        )
        return row is not None

    def ensure_email_verification(self):
        """Add signup-verification storage to databases created before this feature.

        Existing accounts default to verified so current members are not locked out.
        """
        if not self._table_exists("users"):
            return
        if not self._column_exists("users", "email_verified"):
            if self.kind == "sqlite":
                self.execute(
                    "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1"
                )
            else:
                self.execute(
                    "ALTER TABLE users ADD COLUMN email_verified TINYINT(1) NOT NULL DEFAULT 1"
                )
        if not self._table_exists("email_verifications"):
            if self.kind == "sqlite":
                self.execute(
                    """
                    CREATE TABLE email_verifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        token_hash TEXT NOT NULL UNIQUE,
                        expires_at TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
            else:
                self.execute(
                    """
                    CREATE TABLE email_verifications (
                        id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                        user_id INT UNSIGNED NOT NULL,
                        token_hash CHAR(64) NOT NULL,
                        expires_at DATETIME NOT NULL,
                        created_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        UNIQUE KEY uq_email_verifications_token (token_hash),
                        KEY idx_email_verifications_user (user_id),
                        CONSTRAINT fk_email_verifications_user
                            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
        self.commit()

    def ensure_account_security(self):
        """Add role, phone, authenticator, and login-challenge storage on older databases."""
        if not self._table_exists("users"):
            return
        columns = {
            "role": ("TEXT NOT NULL DEFAULT 'member'", "VARCHAR(20) NOT NULL DEFAULT 'member'"),
            "phone": ("TEXT", "VARCHAR(20) NULL"),
            "two_factor_secret": ("TEXT", "VARCHAR(64) NULL"),
            "two_factor_enabled": ("INTEGER NOT NULL DEFAULT 0", "TINYINT(1) NOT NULL DEFAULT 0"),
        }
        for name, (sqlite_type, mysql_type) in columns.items():
            if self._column_exists("users", name):
                continue
            column_type = sqlite_type if self.kind == "sqlite" else mysql_type
            self.execute(f"ALTER TABLE users ADD COLUMN {name} {column_type}")
        if not self._table_exists("login_challenges"):
            if self.kind == "sqlite":
                self.execute(
                    """
                    CREATE TABLE login_challenges (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        token_hash TEXT NOT NULL UNIQUE,
                        expires_at TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
            else:
                self.execute(
                    """
                    CREATE TABLE login_challenges (
                        id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                        user_id INT UNSIGNED NOT NULL,
                        token_hash CHAR(64) NOT NULL,
                        expires_at DATETIME NOT NULL,
                        created_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        UNIQUE KEY uq_login_challenges_token (token_hash),
                        KEY idx_login_challenges_user (user_id),
                        CONSTRAINT fk_login_challenges_user
                            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
        self.commit()