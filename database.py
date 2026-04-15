"""
database.py — SQLite user store with Fernet (AES-128) field encryption.

Replaces users.json entirely. Drop this file into your project root.

Schema
------
  users(
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username  TEXT    UNIQUE NOT NULL,          -- stored plain (lookup key)
    password  TEXT    NOT NULL,                 -- bcrypt hash
    role      TEXT    NOT NULL DEFAULT 'user',  -- 'admin' | 'user'
    email_enc BLOB,                             -- Fernet-encrypted if provided
    created_at TEXT   DEFAULT (datetime('now'))
  )

Encryption
----------
  FERNET_KEY in .env  →  encrypts/decrypts email_enc (and any future PII columns).
  If FERNET_KEY is missing, a warning is printed and values are stored plain.
  Passwords use bcrypt (not Fernet) — bcrypt is the right tool for passwords;
  Fernet is for PII you need to read back as plaintext.

Usage
-----
  from database import init_db, get_user, create_user, list_users, set_role

  init_db()                              # call once at app startup
  user = get_user("sean")               # returns dict or None
  ok, err = create_user("sean", hash)
  users = list_users()
  set_role("sean", "admin")
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = os.environ.get("DB_PATH", "users.db")

_fernet = None
_FERNET_KEY = os.environ.get("FERNET_KEY")

if _FERNET_KEY:
    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(_FERNET_KEY.encode() if isinstance(_FERNET_KEY, str) else _FERNET_KEY)
    except Exception as e:
        print(f"[database] WARNING: FERNET_KEY found but failed to load: {e}")
else:
    print(
        "[database] WARNING: FERNET_KEY not set in .env — "
        "email/PII fields will NOT be encrypted.\n"
        "[database] Generate one with: "
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )

# Per-thread connections (SQLite connections are not thread-safe to share)
_local = threading.local()


# ── Encryption helpers ────────────────────────────────────────────────────────

def _encrypt(value: str) -> bytes | None:
    if value is None:
        return None
    if _fernet is None:
        return value.encode()  # no key: store plain bytes
    return _fernet.encrypt(value.encode())


def _decrypt(value: bytes) -> str | None:
    if value is None:
        return None
    if _fernet is None:
        return value.decode() if isinstance(value, bytes) else value
    return _fernet.decrypt(value).decode()


# ── Connection management ─────────────────────────────────────────────────────

@contextmanager
def _get_conn():
    """Yield a per-thread SQLite connection with WAL mode for safe concurrency."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.row_factory = sqlite3.Row
    try:
        yield _local.conn
    except Exception:
        _local.conn.rollback()
        raise


# ── Schema init ───────────────────────────────────────────────────────────────

def init_db():
    """
    Create the users table if it doesn't exist, then seed the default admin.
    Call once at the top of flask_api.py.
    """
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT    UNIQUE NOT NULL,
                password   TEXT    NOT NULL,
                role       TEXT    NOT NULL DEFAULT 'user',
                email_enc  BLOB,
                two_fa_secret TEXT,
                created_at TEXT    DEFAULT (datetime('now'))
            )
        """)
        
        # Add two_fa_secret to existing tables
        try:
            conn.execute("ALTER TABLE users ADD COLUMN two_fa_secret TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE users ADD COLUMN verification_token TEXT")
        except sqlite3.OperationalError:
            pass
            
        conn.commit()

    # Create pending verifications table for temporary email codes
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_verifications (
                email TEXT PRIMARY KEY,
                code TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

    # Seed default admin only if table is empty
    if not get_user("admin"):
        import bcrypt
        default_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
        create_user("admin", default_hash, role="admin")
        # Verify admin by default
        with _get_conn() as conn:
            conn.execute("UPDATE users SET is_verified = 1 WHERE username = 'admin'")
            conn.commit()
        print("[database] Default admin seeded — user: admin  password: admin123")
        print("[database] !! Change the admin password after first login !!")


# ── CRUD ──────────────────────────────────────────────────────────────────────

def get_user(identifier: str) -> dict | None:
    """
    Look up a user by username or email.
    """
    identifier = identifier.strip().lower()
    
    with _get_conn() as conn:
        # First try exact username match
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (identifier,)
        ).fetchone()

        if row is None and "@" in identifier:
            # If not found and it looks like an email, we must scan the DB 
            # because Fernet encryption is non-deterministic
            all_rows = conn.execute("SELECT * FROM users").fetchall()
            for r in all_rows:
                email = _decrypt(r["email_enc"])
                if email and email.strip().lower() == identifier:
                    row = r
                    break
        
    if row is None:
        return None

    return {
        "username":      row["username"],
        "password":      row["password"],
        "role":          row["role"],
        "email":         _decrypt(row["email_enc"]),
        "two_fa_secret": _decrypt(row["two_fa_secret"]),
        "is_verified":   row["is_verified"] if "is_verified" in row.keys() else 1,
        "verification_token": row["verification_token"] if "verification_token" in row.keys() else None,
        "created_at":    row["created_at"],
    }


def create_user(
    username: str,
    hashed_password: str,
    role: str = "user",
    email: str = None,
    verification_token: str = None,
) -> tuple[bool, str]:
    """
    Insert a new user. hashed_password must already be a bcrypt hash.
    Returns (True, "") on success or (False, error_message) on failure.
    """
    username = username.strip().lower()
    email_enc = _encrypt(email) if email else None

    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, password, role, email_enc, verification_token, is_verified) VALUES (?, ?, ?, ?, ?, 0)",
                (username, hashed_password, role, email_enc, verification_token),
            )
            conn.commit()
        return True, ""
    except sqlite3.IntegrityError:
        return False, "Username already exists."
    except Exception as e:
        return False, str(e)


def update_password(username: str, new_hashed_password: str) -> bool:
    """Update a user's bcrypt password hash. Returns True if a row was updated."""
    with _get_conn() as conn:
        cur = conn.execute(
            "UPDATE users SET password = ? WHERE username = ?",
            (new_hashed_password, username.strip().lower()),
        )
        conn.commit()
    return cur.rowcount > 0


def set_role(username: str, role: str) -> bool:
    """Promote or demote a user. Returns True if a row was updated."""
    with _get_conn() as conn:
        cur = conn.execute(
            "UPDATE users SET role = ? WHERE username = ?",
            (role, username.strip().lower()),
        )
        conn.commit()
    return cur.rowcount > 0

def update_email(username: str, email: str) -> bool:
    """Update a user's email."""
    email_enc = _encrypt(email) if email else None
    with _get_conn() as conn:
        cur = conn.execute(
            "UPDATE users SET email_enc = ? WHERE username = ?",
            (email_enc, username.strip().lower()),
        )
        conn.commit()
    return cur.rowcount > 0

def set_2fa_secret(username: str, secret: str | None) -> bool:
    """Set or clear a user's 2FA secret."""
    secret_enc = _encrypt(secret) if secret else None
    with _get_conn() as conn:
        cur = conn.execute(
            "UPDATE users SET two_fa_secret = ? WHERE username = ?",
            (secret_enc, username.strip().lower()),
        )
        conn.commit()
    return cur.rowcount > 0

def list_users() -> list[dict]:
    """Return all users as [{username, role, created_at}] — no passwords returned."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT username, role, created_at FROM users ORDER BY created_at"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_user(username: str) -> bool:
    """Delete a user by username. Returns True if a row was deleted."""
    with _get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM users WHERE username = ?",
            (username.strip().lower(),)
        )
        conn.commit()
    return cur.rowcount > 0

def verify_user_by_token(token: str) -> bool:
    """Verify a user via their token. Returns True if successfully updated."""
    with _get_conn() as conn:
        cur = conn.execute(
            "UPDATE users SET is_verified = 1, verification_token = NULL WHERE verification_token = ?",
            (token,)
        )
        conn.commit()
    return cur.rowcount > 0

def save_verification_code(email: str, code: str) -> bool:
    """Save a verification code for an email. Returns True if successful."""
    email = email.strip().lower()
    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pending_verifications (email, code, created_at) VALUES (?, ?, datetime('now'))",
                (email, code),
            )
            conn.commit()
        return True
    except Exception as e:
        print(f"[database] Error saving verification code: {e}")
        return False

def verify_email_code(email: str, code: str) -> bool:
    """Check if email + code match and delete the record. Returns True if valid."""
    email = email.strip().lower()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM pending_verifications WHERE email = ? AND code = ?",
            (email, code)
        ).fetchone()
        
        if row:
            # Delete the verified code
            conn.execute("DELETE FROM pending_verifications WHERE email = ?", (email,))
            conn.commit()
            return True
    return False



# ── One-time migration from users.json ───────────────────────────────────────

def migrate_from_json(json_path: str = "users.json") -> int:
    """
    Import users from the old users.json into SQLite.
    Skips users that already exist. Returns count of imported users.

    Run once from your terminal:
        python -c "from database import init_db, migrate_from_json; init_db(); migrate_from_json()"
    """
    import json

    if not os.path.exists(json_path):
        print(f"[migrate] {json_path} not found — nothing to migrate.")
        return 0

    with open(json_path) as f:
        data = json.load(f)

    count = 0
    for username, value in data.items():
        if isinstance(value, str):
            # Old format: value is just the hash string
            pw_hash = value
            role = "admin" if username == "admin" else "user"
        else:
            pw_hash = value.get("password", "")
            role = value.get("role", "user")

        ok, _ = create_user(username, pw_hash, role=role)
        if ok:
            count += 1
            print(f"[migrate] Imported : {username} ({role})")
        else:
            print(f"[migrate] Skipped  : {username} (already exists)")

    print(f"[migrate] Done — {count} user(s) imported from {json_path}")
    return count