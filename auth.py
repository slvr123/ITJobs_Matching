import requests
import streamlit as st
import re

# ── Flask API config ──────────────────────────────────────────────────────────
# This is the address of your Flask server (flask_api.py).
# Both Streamlit and Flask run on your machine — they talk over localhost.
# Streamlit runs on :8501, Flask runs on :5050.
API_BASE = "http://localhost:5050"


def _api_call(method: str, endpoint: str, **kwargs):
    """
    Helper that wraps requests calls with a clean error response.
    Returns (data_dict, status_code) or ({"error": "..."}, 0) on network failure.

    This is why the Flask separation matters: if the API is down, we get a
    clear error instead of a cryptic Python exception crashing the app.
    """
    try:
        response = requests.request(
            method,
            f"{API_BASE}{endpoint}",
            timeout=5,  # fail fast if Flask isn't running
            **kwargs
        )
        return response.json(), response.status_code
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot connect to auth server. Is Flask running? (python flask_api.py)"}, 0
    except requests.exceptions.Timeout:
        return {"error": "Auth server timed out."}, 0
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}, 0


def _check_flask_running() -> bool:
    """Ping the Flask health endpoint to check if it's up."""
    data, code = _api_call("GET", "/health")
    return code == 200


def init_session():
    """
    Initialise session state keys.

    We now store three things in session_state:
    - role: "guest", "admin", "user", or None
    - jwt_token: the raw JWT string from Flask
    - username: the logged-in username (for display)
    """
    for key, default in [
        ("role", None),
        ("jwt_token", None),
        ("username", None),
        ("email", ""),
        ("has_2fa", False),
        ("pending_signup", None),
        ("login_error", ""),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default


def verify_token() -> bool:
    """
    Call Flask /auth/verify to check if the stored JWT is still valid.
    Called on every page load — if the token expired, the user gets logged out.

    This is the key JWT benefit: the server decides if the session is valid,
    not just "does this browser tab have a variable set".
    """
    if not st.session_state.get("jwt_token"):
        return False

    data, code = _api_call(
        "GET", "/auth/verify",
        headers={"Authorization": f"Bearer {st.session_state.jwt_token}"}
    )

    if code == 200:
        # Refresh role and username from the token in case they changed
        st.session_state.role = data.get("role", "user")
        st.session_state.username = data.get("username")
        st.session_state.email = data.get("email", "")
        st.session_state.has_2fa = data.get("has_2fa", False)
        return True

    # Token expired or invalid — clear session
    logout(rerun=False)
    return False


def login_screen():
    """
    Compact card-based login screen with blue/white theme and Helvetica branding.
    """
    if not _check_flask_running():
        st.error(
            "Auth server is not running.\n\n"
            "Open a second terminal and run: `python flask_api.py`"
        )
        st.stop()

    # ── Theme & global styles ─────────────────────────────────────────────────
    # Palette: #1d4ed8 (primary blue), #3b82f6 (mid blue), #93c5fd (light blue),
    #          #ffffff (white), #f0f6ff (off-white bg)
    st.markdown("""
    <style>
    /* Full-page background */
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #f0f6ff 0%, #e8f0fe 100%);
    }
    [data-testid="stHeader"] { background: transparent; }

    /* Hide default block padding on login page */
    .login-wrap .block-container { padding-top: 0 !important; }

    /* Card */
    .login-card {
        background: #ffffff;
        border: 1px solid #bfdbfe;
        border-radius: 14px;
        padding: 2rem 2rem 1.5rem;
        box-shadow: 0 4px 24px rgba(29,78,216,0.08);
        max-width: 420px;
        margin: 0 auto;
    }

    /* Title */
    .login-title {
        font-family: Helvetica, Arial, sans-serif;
        font-size: 1.9rem;
        font-weight: 800;
        color: #1d4ed8;
        letter-spacing: -0.5px;
        margin-bottom: 0;
        text-align: center;
    }
    .login-subtitle {
        color: #6b7280;
        font-size: 0.82rem;
        text-align: center;
        margin-top: 2px;
        margin-bottom: 1.2rem;
    }

    /* Divider text */
    .or-divider {
        display: flex; align-items: center; gap: 8px;
        color: #9ca3af; font-size: 0.78rem; margin: 0.75rem 0;
    }
    .or-divider::before, .or-divider::after {
        content: ""; flex: 1; height: 1px; background: #e5e7eb;
    }

    /* Guest button override */
    div[data-testid="stButton"] button[kind="secondary"] {
        border: 1.5px solid #3b82f6 !important;
        color: #1d4ed8 !important;
        background: #f0f6ff !important;
        border-radius: 8px !important;
        font-size: 0.85rem !important;
    }
    div[data-testid="stButton"] button[kind="secondary"]:hover {
        background: #dbeafe !important;
    }

    /* Primary button */
    div[data-testid="stButton"] button[kind="primary"],
    div[data-testid="stFormSubmitButton"] button {
        background: #1d4ed8 !important;
        border: none !important;
        border-radius: 8px !important;
        font-size: 0.88rem !important;
        font-weight: 600 !important;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover,
    div[data-testid="stFormSubmitButton"] button:hover {
        background: #1e40af !important;
    }

    /* Input fields */
    div[data-testid="stTextInput"] input {
        border-radius: 8px !important;
        border: 1.5px solid #bfdbfe !important;
        font-size: 0.88rem !important;
        padding: 0.45rem 0.75rem !important;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: #3b82f6 !important;
        box-shadow: 0 0 0 3px rgba(59,130,246,0.15) !important;
    }

    /* OTP tiles */
    .otp-tile input {
        text-align: center !important;
        font-size: 1.3rem !important;
        font-weight: 700 !important;
        color: #1d4ed8 !important;
        border: 2px solid #93c5fd !important;
        border-radius: 10px !important;
        padding: 0.5rem 0 !important;
        background: #f0f6ff !important;
    }
    .otp-tile input:focus {
        border-color: #1d4ed8 !important;
        box-shadow: 0 0 0 3px rgba(29,78,216,0.15) !important;
        background: #ffffff !important;
    }

    /* OTP tiles */
    .otp-tile input {
        text-align: center !important;
        font-size: 1.3rem !important;
        font-weight: 700 !important;
        color: #1d4ed8 !important;
        border: 2px solid #93c5fd !important;
        border-radius: 10px !important;
        padding: 0.5rem 0 !important;
        background: #f0f6ff !important;
        width: 100% !important;
        height: 50px !important;
    }
    .otp-tile input:focus {
        border-color: #1d4ed8 !important;
        box-shadow: 0 0 0 3px rgba(29,78,216,0.15) !important;
        background: #ffffff !important;
    }

    /* OTP tiles */
    .otp-tile input {
        text-align: center !important;
        font-size: 1.3rem !important;
        font-weight: 700 !important;
        color: #1d4ed8 !important;
        border: 2px solid #93c5fd !important;
        border-radius: 10px !important;
        padding: 0.5rem 0 !important;
        background: #f0f6ff !important;
        width: 100% !important;
        height: 50px !important;
    }
    .otp-tile input:focus {
        border-color: #1d4ed8 !important;
        box-shadow: 0 0 0 3px rgba(29,78,216,0.15) !important;
        background: #ffffff !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 0; border-bottom: 2px solid #bfdbfe; }
    .stTabs [data-baseweb="tab"] {
        font-size: 0.88rem !important;
        font-weight: 600 !important;
        color: #6b7280 !important;
        padding: 0.5rem 1.2rem !important;
        border-radius: 0 !important;
        background: transparent !important;
    }
    .stTabs [aria-selected="true"] {
        color: #1d4ed8 !important;
        border-bottom: 2px solid #1d4ed8 !important;
    }

    /* Labels */
    div[data-testid="stTextInput"] label {
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        color: #374151 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Layout ────────────────────────────────────────────────────────────────
    st.markdown("<div style='height:3.5rem'></div>", unsafe_allow_html=True)
    col_l, col_center, col_r = st.columns([1, 1.6, 1])

    with col_center:
        # Title
        st.markdown("""
            <div class="login-title">GitHiredPH</div>
            <div class="login-subtitle">525 IT job listings across the Philippines</div>
        """, unsafe_allow_html=True)

        # ── Guest access ──────────────────────────────────────────────────────
        if st.button("Continue as Guest", use_container_width=True):
            st.session_state.role = "guest"
            st.session_state.username = "Guest"
            st.rerun()

        st.markdown('<div class="or-divider">or sign in to your account</div>', unsafe_allow_html=True)

        # ── Login / Register card ─────────────────────────────────────────────
        with st.container(border=True):
            tab_login, tab_register = st.tabs(["Log in", "Create account"])

            # ── LOGIN TAB ─────────────────────────────────────────────────────
            with tab_login:
                with st.form("login_form", clear_on_submit=False):
                    username = st.text_input("Username or Email", placeholder="admin")
                    password = st.text_input("Password", type="password", placeholder="••••••••")
                    submitted = st.form_submit_button("Log in", use_container_width=True, type="primary")

                if st.session_state.login_error:
                    st.error(st.session_state.login_error)

                if submitted:
                    if not username.strip() or not password.strip():
                        st.error("Please enter both username/email and password.")
                    else:
                        with st.spinner("Logging in..."):
                            data, code = _api_call(
                                "POST", "/auth/login",
                                json={"username": username, "password": password}
                            )
                            if code == 200:
                                st.session_state.jwt_token = data["token"]
                                st.session_state.role = data["role"]
                                st.session_state.username = data["username"]
                                st.session_state.login_error = ""
                                import time; time.sleep(0.4)
                                verify_token()
                                st.rerun()
                            else:
                                st.session_state.login_error = data.get("error", "Login failed.")
                                import time; time.sleep(0.4)
                                st.rerun()

            # ── REGISTER TAB ──────────────────────────────────────────────────
            with tab_register:
                pending_signup = st.session_state.get("pending_signup")

                if pending_signup:
                    # ── OTP verification ──────────────────────────────────────
                    email_value = pending_signup.get("email", "")
                    email_parts = email_value.split("@")
                    masked_email = email_value
                    if len(email_parts) == 2 and len(email_parts[0]) > 2:
                        local = email_parts[0]
                        masked_email = f"{local[:2]}{'*' * max(2, len(local)-2)}@{email_parts[1]}"

                    st.markdown(f"**Check your inbox**")
                    st.caption(f"We sent a 6-digit code to **{masked_email}**.")

                    # Single hidden text input (accepts paste)
                    raw_code = st.text_input(
                        "Verification code",
                        max_chars=6,
                        placeholder="Enter or paste 6-digit code",
                        key="otp_input",
                        label_visibility="collapsed",
                    )

                    # Filter to only digits
                    code_clean = "".join([c for c in raw_code if c.isdigit()])[:6]

                    # Display as visual tiles
                    tiles_html = "<div style='display:flex;gap:10px;justify-content:center;margin:12px 0;'>"
                    for i in range(6):
                        char = code_clean[i] if i < len(code_clean) else ""
                        filled = char != ""
                        bg = "#3d5a80" if filled else "#e0fbfc"
                        color = "#ffffff" if filled else "#98c1d9"
                        border = "#3d5a80" if filled else "#98c1d9"
                        display_char = char if filled else "•"
                        tiles_html += (
                            f"<div style='width:48px;height:56px;border:2px solid {border};"
                            f"border-radius:12px;background:{bg};display:flex;"
                            f"align-items:center;justify-content:center;"
                            f"font-size:1.6rem;font-weight:700;color:{color};'>{display_char}</div>"
                        )
                    tiles_html += "</div>"
                    st.markdown(tiles_html, unsafe_allow_html=True)

                    code_input = code_clean

                    verify_btn = st.button("Verify & Create Account", use_container_width=True, type="primary")
                    c1, c2 = st.columns(2)
                    with c1:
                        resend_btn = st.button("Resend code", use_container_width=True)
                    with c2:
                        change_email_btn = st.button("Change email", use_container_width=True)

                    if verify_btn:
                        if len(code_input) != 6:
                            st.error("Enter the full 6-digit code.")
                        else:
                            with st.spinner("Verifying..."):
                                data, verify_code = _api_call(
                                    "POST", "/auth/verify-code",
                                    json={"email": pending_signup["email"], "code": code_input}
                                )
                                if verify_code == 200:
                                    reg_data, reg_code = _api_call(
                                        "POST", "/auth/register",
                                        json={
                                            "email":    pending_signup["email"],
                                            "username": pending_signup["username"],
                                            "password": pending_signup["password"],
                                        }
                                    )
                                    if reg_code == 201:
                                        st.session_state.jwt_token = reg_data.get("token")
                                        st.session_state.role      = reg_data.get("role")
                                        st.session_state.username  = reg_data.get("username")
                                        st.session_state.pending_signup = None
                                        st.session_state.pop("otp_input", None)
                                        st.success("Account created! Logging in...")
                                        import time; time.sleep(0.4)
                                        verify_token()
                                        st.rerun()
                                    else:
                                        st.error(reg_data.get("error", "Registration failed."))
                                else:
                                    st.error(data.get("error", "Invalid or expired code."))

                    if resend_btn:
                        with st.spinner("Resending..."):
                            data, resend_code = _api_call(
                                "POST", "/auth/send-verification-code",
                                json={"email": pending_signup["email"]}
                            )
                            if resend_code == 200:
                                st.success("New code sent.")
                            else:
                                st.error(data.get("error", "Failed to resend."))

                    if change_email_btn:
                        st.session_state.pending_signup = None
                        st.session_state.pop("otp_input", None)
                        st.rerun()

                else:
                    # ── Registration form ─────────────────────────────────────
                    with st.form("register_form", clear_on_submit=True):
                        new_email    = st.text_input("Email", placeholder="you@example.com")
                        new_username = st.text_input("Username", placeholder="MyUsername")
                        new_password = st.text_input("Password", type="password", placeholder="Min 8 chars, 1 number")
                        confirm_pw   = st.text_input("Confirm password", type="password", placeholder="••••••••")
                        reg_submitted = st.form_submit_button("Continue", use_container_width=True, type="primary")

                    if reg_submitted:
                        new_email_clean    = new_email.strip().lower()
                        new_username_clean = new_username.strip()

                        if not new_email_clean or not new_username_clean or not new_password:
                            st.error("Please fill out all fields.")
                        elif not re.match(r"[^@]+@[^@]+\.[^@]+", new_email_clean):
                            st.warning("Enter a valid email address.")
                        elif len(new_username_clean) < 3:
                            st.warning("Username must be at least 3 characters.")
                        elif not new_username_clean.isalnum():
                            st.warning("Username can only contain letters and numbers.")
                        elif len(new_password) < 8:
                            st.warning("Password must be at least 8 characters.")
                        elif not re.search(r"\d", new_password):
                            st.warning("Password must contain at least one number.")
                        elif not re.search(r"[a-zA-Z]", new_password):
                            st.warning("Password must contain at least one letter.")
                        elif new_password != confirm_pw:
                            st.error("Passwords do not match.")
                        else:
                            with st.spinner("Sending verification code..."):
                                data, code = _api_call(
                                    "POST", "/auth/send-verification-code",
                                    json={"email": new_email_clean}
                                )
                                if code == 200:
                                    st.session_state.pending_signup = {
                                        "email":    new_email_clean,
                                        "username": new_username_clean,
                                        "password": new_password,
                                    }
                                    st.rerun()
                                else:
                                    st.error(data.get("error", "Failed to send code."))

    return False


def logout(rerun: bool = True):
    """Clear session state and return to login screen."""
    for key in ["role", "jwt_token", "username", "login_error", "chat_history",
                "gemini_history", "system_prompt"]:
        st.session_state.pop(key, None)
    if rerun:
        st.rerun()


def require_auth():
    """
    Call this at the top of app.py — same interface as before.

    New behaviour:
    1. If no role in session → show login screen
    2. If role exists but token present → verify token with Flask on every load
       (catches expired tokens automatically)
    3. Returns role so app.py knows what to show
    """
    init_session()

    # Guest has no token — skip verification
    if st.session_state.role == "guest":
        return "guest"

    # Has a token — verify it's still valid with Flask
    if st.session_state.jwt_token:
        if verify_token():
            return st.session_state.role
        # verify_token() already cleared session if invalid

    # No valid session → show login
    login_screen()
    st.stop()