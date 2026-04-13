import os
import json
import bcrypt
from flask import Flask, request, jsonify
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity, get_jwt
)
from flask_cors import CORS
from datetime import timedelta

app = Flask(__name__)
CORS(app)  # Allow Streamlit (different port) to call this API

# ── JWT config ────────────────────────────────────────────────────────────────
# The secret key signs every token. Anyone with this key can forge tokens,
# so in production you'd put this in an environment variable, never in code.
# For a portfolio/local project this is fine.
#
# Tokens expire after 1 day — after that the user must log in again.
# This is the key difference from st.session_state: JWT expiry is enforced
# server-side, not just "did the browser tab stay open".
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "itjobs-ph-dev-secret-2024")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=1)

jwt = JWTManager(app)

# ── User store ────────────────────────────────────────────────────────────────
# We keep your existing users.json format exactly — no migration needed.
# The Flask API reads and writes the same file your current auth.py uses.
USER_DB_FILE = "users.json"
ADMIN_USERS = {"admin"}   # usernames that get role="admin" — everyone else gets role="user"

DEFAULT_USERS = {
    "admin": "$2b$12$kpfPX8DsKINFIGB5nEkrkOla0Kkr9mdzm1Pk1WN4bWThps9EA640O"
}

def _load_users():
    if not os.path.exists(USER_DB_FILE):
        with open(USER_DB_FILE, "w") as f:
            json.dump(DEFAULT_USERS, f, indent=2)
        return DEFAULT_USERS.copy()
    with open(USER_DB_FILE, "r") as f:
        return json.load(f)

def _save_users(users: dict):
    with open(USER_DB_FILE, "w") as f:
        json.dump(users, f, indent=2)

def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def _check_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route("/auth/login", methods=["POST"])
def login():
    """
    POST /auth/login
    Body: { "username": "...", "password": "..." }
    Returns: { "token": "<jwt>", "role": "admin"|"user", "username": "..." }

    How JWT works here:
    - We verify the password with bcrypt (same as before)
    - If valid, we call create_access_token() — this returns a signed string
    - The signature uses JWT_SECRET_KEY, so nobody can tamper with the token
    - We embed the username AND role inside the token as "claims"
    - Streamlit stores this token and sends it on future requests
    """
    data = request.get_json()
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    users = _load_users()

    if username not in users or not _check_password(password, users[username]):
        # Intentionally vague — don't reveal which field was wrong
        return jsonify({"error": "Incorrect username or password."}), 401

    role = "admin" if username in ADMIN_USERS else "user"

    # additional_claims lets us embed extra data inside the JWT payload
    # We store role here so Streamlit can read it directly from the token
    token = create_access_token(
        identity=username,
        additional_claims={"role": role}
    )

    return jsonify({
        "token": token,
        "role": role,
        "username": username,
    }), 200


@app.route("/auth/register", methods=["POST"])
def register():
    """
    POST /auth/register
    Body: { "username": "...", "password": "..." }
    Returns: { "token": "<jwt>", "role": "user", "username": "..." }

    New registrations always get role="user".
    Only the ADMIN_USERS set determines admin status.
    """
    data = request.get_json()
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters."}), 400

    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters."}), 400

    users = _load_users()

    if username in users:
        return jsonify({"error": "Username already exists."}), 409  # 409 = Conflict

    users[username] = _hash_password(password)
    _save_users(users)

    # Auto-login after registration — same flow as /login
    token = create_access_token(
        identity=username,
        additional_claims={"role": "user"}
    )

    return jsonify({
        "token": token,
        "role": "user",
        "username": username,
        "message": "Account created successfully.",
    }), 201  # 201 = Created


@app.route("/auth/verify", methods=["GET"])
@jwt_required()
def verify():
    """
    GET /auth/verify
    Header: Authorization: Bearer <token>
    Returns: { "username": "...", "role": "..." }

    Streamlit calls this on every page load to check if the stored token
    is still valid. If the token is expired or tampered with, Flask returns
    401 automatically — no manual checking needed.

    @jwt_required() is a decorator that does all the verification for us.
    """
    username = get_jwt_identity()        # extracts username from token
    claims = get_jwt()                   # extracts additional_claims
    role = claims.get("role", "user")

    return jsonify({
        "username": username,
        "role": role,
        "valid": True,
    }), 200


@app.route("/auth/users", methods=["GET"])
@jwt_required()
def list_users():
    """
    GET /auth/users  (admin only)
    Returns list of all usernames (never passwords).
    Streamlit checks role before calling this — Flask double-checks here too.
    """
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"error": "Admin access required."}), 403

    users = _load_users()
    return jsonify({
        "users": [
            {"username": u, "role": "admin" if u in ADMIN_USERS else "user"}
            for u in users.keys()
        ]
    }), 200


@app.route("/health", methods=["GET"])
def health():
    """Simple health check — Streamlit pings this to confirm Flask is running."""
    return jsonify({"status": "ok", "service": "IT Jobs PH API"}), 200


if __name__ == "__main__":
    # Run on port 5050 so it doesn't clash with Streamlit (8501)
    # debug=True shows errors in the terminal — turn off for production
    print("Starting IT Jobs PH Flask API on http://localhost:5050")
    app.run(port=5050, debug=True)