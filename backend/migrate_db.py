import sqlite3

conn = sqlite3.connect('recifix.db')
cursor = conn.cursor()

# Check columns
cursor.execute('PRAGMA table_info(users)')
cols = [row[1] for row in cursor.fetchall()]

# Add columns
if 'role' not in cols:
    cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'member'")
if 'phone' not in cols:
    cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT")
if 'two_factor_secret' not in cols:
    cursor.execute("ALTER TABLE users ADD COLUMN two_factor_secret TEXT")
if 'two_factor_enabled' not in cols:
    cursor.execute("ALTER TABLE users ADD COLUMN two_factor_enabled INTEGER DEFAULT 0")
if 'email_verified' not in cols:
    cursor.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1")

cursor.execute('''
CREATE TABLE IF NOT EXISTS email_verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
)
''')

# Create messages table (for admin-sent messages)
cursor.execute('''
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (admin_id) REFERENCES users (id)
)
''')

# Create contact_messages table (for public submissions from contact form)
cursor.execute('''
CREATE TABLE IF NOT EXISTS contact_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT NOT NULL,
    subject TEXT,
    body TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
)
''')

conn.commit()
conn.close()
print("Migration completed.")
