"""
flask_api.py — IT Jobs PH authentication API (Flask)
Backed by SQLite + Fernet encryption via database.py.

Routes (unchanged — auth.py in Streamlit needs zero edits):
  POST  /auth/login
  POST  /auth/register
  GET   /auth/verify      (JWT required)
  GET   /auth/users       (admin only)
  POST  /auth/promote     (admin only)
  GET   /health

Run with:
    python flask_api.py
"""

import os
import bcrypt
from flask import Flask, request, jsonify
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity, get_jwt,
)
from flask_cors import CORS
from datetime import timedelta
from dotenv import load_dotenv
import smtplib
import ssl
from email.mime.text import MIMEText
import uuid

from database import init_db, get_user, create_user, set_role, list_users, update_email, set_2fa_secret, verify_user_by_token, save_verification_code, verify_email_code, _get_conn
import pyotp

load_dotenv()

# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

jwt_secret = os.environ.get("JWT_SECRET_KEY")
if not jwt_secret:
    raise RuntimeError("JWT_SECRET_KEY not set — add it to your .env file.")

app.config["JWT_SECRET_KEY"] = jwt_secret
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=1)

jwt = JWTManager(app)

# Initialise DB (creates table + seeds default admin if needed)
init_db()


# ── Password helpers ──────────────────────────────────────────────────────────

def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _check_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def _send_verification_email(recipient_email: str, code: str) -> bool:
    """Send verification code via Gmail SMTP. Returns True if successful."""
    smtp_email = os.environ.get("SMTP_EMAIL")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    
    if not smtp_email or not smtp_password:
        print(f"[email] SMTP not configured. Verification code for {recipient_email}: {code}")
        return False
    
    try:
        msg = MIMEText(f"Your IT Jobs PH verification code is: {code}\n\nThis code expires in 10 minutes.")
        msg['Subject'] = "Your Verification Code - IT Jobs PH"
        msg['From'] = smtp_email
        msg['To'] = recipient_email
        
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
        print(f"[email] Verification code sent to {recipient_email}")
        return True
    except Exception as e:
        print(f"[email] Failed to send email to {recipient_email}: {e}")
        return False

def _generate_verification_code() -> str:
    """Generate a random 6-digit verification code."""
    import random
    return str(random.randint(100000, 999999))


def _send_test_email(recipient_email: str) -> tuple[bool, str]:
    """Send a simple SMTP connectivity test email."""
    smtp_email = os.environ.get("SMTP_EMAIL")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    if not smtp_email or not smtp_password:
        return False, "SMTP_EMAIL/SMTP_PASSWORD are not configured."

    try:
        msg = MIMEText(
            "This is a test email from IT Jobs PH.\n\n"
            "If you received this, your Gmail SMTP setup is working."
        )
        msg["Subject"] = "IT Jobs PH - SMTP Test"
        msg["From"] = smtp_email
        msg["To"] = recipient_email

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(smtp_email, smtp_password)
            server.send_message(msg)

        return True, f"Test email sent to {recipient_email}."
    except Exception as e:
        return False, f"SMTP test failed: {e}"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    user = get_user(username)

    # Same error for missing user vs wrong password (prevents user enumeration)
    if user is None or not _check_password(password, user["password"]):
        return jsonify({"error": "Incorrect username or password."}), 401

    if not user.get("is_verified", 1): # Failsafe back to 1 for older local dev accounts
        return jsonify({"error": "Account not verified. Please check your email."}), 401

    # [DISABLED] 2FA check on login
    # if user.get("two_fa_secret"):
    #     otp_token = data.get("otp")
    #     if not otp_token:
    #         return jsonify({
    #             "requires_2fa": True,
    #             "message": "2FA token required."
    #         }), 401
            
    #     totp = pyotp.TOTP(user["two_fa_secret"])
    #     if not totp.verify(otp_token):
    #         return jsonify({"error": "Invalid 2FA token."}), 401

    token = create_access_token(
        identity=user["username"], # Ensure we use the exact username found in DB
        additional_claims={"role": user["role"]},
    )
    return jsonify({"token": token, "role": user["role"], "username": user["username"]}), 200


@app.route("/auth/send-verification-code", methods=["POST"])
def send_verification_code():
    """Send a verification code to an email address."""
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()
    
    if not email:
        return jsonify({"error": "Email is required."}), 400
    
    import re
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"error": "Invalid email address format."}), 400
    
    # Check if email is already registered
    user = get_user(email)
    if user is not None:
        return jsonify({"error": "This email is already registered."}), 409
    
    # Generate and save code
    code = _generate_verification_code()
    save_verification_code(email, code)
    
    # Send email
    _send_verification_email(email, code)
    
    return jsonify({
        "message": "Verification code sent to your email.",
        "email": email
    }), 200


@app.route("/auth/test-email", methods=["POST"])
def test_email():
    """Send a test email to validate SMTP settings quickly."""
    data = request.get_json(silent=True) or {}
    recipient = (data.get("email") or os.environ.get("SMTP_EMAIL") or "").strip().lower()

    if not recipient:
        return jsonify({"error": "Email is required (body.email or SMTP_EMAIL)."}), 400

    import re
    if not re.match(r"[^@]+@[^@]+\.[^@]+", recipient):
        return jsonify({"error": "Invalid email address format."}), 400

    ok, message = _send_test_email(recipient)
    if not ok:
        return jsonify({"error": message}), 500

    return jsonify({"message": message, "email": recipient}), 200

@app.route("/auth/verify-code", methods=["POST"])
def verify_code():
    """Verify that the user has the correct code for their email."""
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    
    if not email or not code:
        return jsonify({"error": "Email and code are required."}), 400
    
    if verify_email_code(email, code):
        return jsonify({
            "message": "Email verified. You can now create your account.",
            "email": email
        }), 200
    else:
        return jsonify({"error": "Invalid or expired verification code."}), 401

@app.route("/auth/register", methods=["POST"])
def register():
    """Create a new account. Email must already be verified."""
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not username or not password:
        return jsonify({"error": "Email, username, and password are required."}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters."}), 400
    
    # Password validation
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters long."}), 400
    import re
    if not re.search(r"\d", password):
        return jsonify({"error": "Password must contain at least one number."}), 400
    if not re.search(r"[a-zA-Z]", password):
        return jsonify({"error": "Password must contain at least one letter."}), 400

    # Create user as verified (email was already verified)
    ok, err = create_user(username, _hash_password(password), role="user", email=email)
    if not ok:
        return jsonify({"error": err}), 409

    # Mark as verified since they already verified their email
    with _get_conn() as conn:
        conn.execute("UPDATE users SET is_verified = 1 WHERE username = ?", (username,))
        conn.commit()

    token = create_access_token(
        identity=username,
        additional_claims={"role": "user"},
    )
    return jsonify({
        "token":    token,
        "role":     "user",
        "username": username,
        "message":  "Account created successfully!",
    }), 201


@app.route("/auth/verify", methods=["GET"])
@jwt_required()
def verify():
    username = get_jwt_identity()
    user = get_user(username)

    if user is None:
        return jsonify({"error": "User no longer exists."}), 401

    # Always return freshest role from DB (not just what's in the token)
    return jsonify({
        "username": username, 
        "role": user["role"], 
        "email": user.get("email") or "",
        "has_2fa": bool(user.get("two_fa_secret")),
        "valid": True
    }), 200

@app.route("/auth/enable-2fa", methods=["POST"])
@jwt_required()
def enable_2fa():
    """Generate a secret and return provisioning URI for authenticator app"""
    username = get_jwt_identity()
    user = get_user(username)
    if not user:
        return jsonify({"error": "User not found."}), 404
        
    secret = pyotp.random_base32()
    # Add temporary unconfirmed secret. You could use a separate temp table or session cache.
    # For simplicity, we assign it directly - see verify_2fa step below
    set_2fa_secret(username, secret)
    
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=username, issuer_name="IT Jobs PH")
    
    return jsonify({
        "secret": secret,
        "provisioning_uri": provisioning_uri
    }), 200

@app.route("/auth/disable-2fa", methods=["POST"])
@jwt_required()
def disable_2fa():
    """Remove 2FA requirement"""
    username = get_jwt_identity()
    data = request.get_json() or {}
    password = data.get("password", "")
    
    user = get_user(username)
    if not user or not _check_password(password, user["password"]):
        return jsonify({"error": "Invalid password."}), 401
        
    set_2fa_secret(username, None)
    return jsonify({"message": "2FA disabled successfully."}), 200

@app.route("/auth/me", methods=["PUT"])
@jwt_required()
def update_profile():
    username = get_jwt_identity()
    data = request.get_json()
    email = data.get("email")
    if email:
        import re
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return jsonify({"error": "Invalid email address format."}), 400
        update_email(username, email)
        return jsonify({"message": "Profile updated successfully", "email": email}), 200
    return jsonify({"error": "No valid fields to update"}), 400


@app.route("/auth/users", methods=["GET"])
@jwt_required()
def list_all_users():
    """Admin only — list all users and their roles."""
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"error": "Admin access required."}), 403

    return jsonify({"users": list_users()}), 200


@app.route("/auth/promote", methods=["POST"])
@jwt_required()
def promote():
    """Admin only — promote or demote a user.
    Body: { "username": "sean", "role": "admin" }
    """
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"error": "Admin access required."}), 403

    data = request.get_json()
    target = (data.get("username") or "").strip().lower()
    new_role = data.get("role", "user")

    if new_role not in ("admin", "user"):
        return jsonify({"error": "Role must be 'admin' or 'user'."}), 400

    if not get_user(target):
        return jsonify({"error": f"User '{target}' not found."}), 404

    set_role(target, new_role)
    return jsonify({
        "message":  f"{target} is now {new_role}.",
        "username": target,
        "role":     new_role,
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "IT Jobs PH API"}), 200


if __name__ == "__main__":
    print("Starting IT Jobs PH Flask API on http://localhost:5050")
    app.run(port=5050, debug=True)