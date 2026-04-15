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
    Login screen UI — identical to what you had, now backed by Flask API calls.
    """
    if not _check_flask_running():
        st.error(
            "Auth server is not running.\n\n"
            "Open a second terminal and run: `python flask_api.py`"
        )
        st.stop()

    st.markdown("""
        <div style="text-align:center; padding: 3rem 0 1rem;">
            <h1 style="font-size:2.2rem; font-weight:700; margin-bottom:0.25rem;">
                IT Jobs PH
            </h1>
            <p style="color:#6b7280; font-size:1rem;">
                Explore 525 IT job listings across the Philippines
            </p>
        </div>
    """, unsafe_allow_html=True)

    col_l, col_center, col_r = st.columns([1, 2, 1])

    with col_center:

        # ── Guest access ──────────────────────────────────────────────────────
        with st.container(border=True):
            st.markdown("#### Continue as guest")
            st.caption("Full access to dashboard, matcher, and AI chatbot — no login required.")
            if st.button("Enter as guest", use_container_width=True):
                st.session_state.role = "guest"
                st.session_state.username = "Guest"
                st.rerun()

        st.write("")

        # ── Login / Register tabs ─────────────────────────────────────────────
        with st.container(border=True):
            tab_login, tab_register = st.tabs(["Log in", "Create an account"])

            # ── LOGIN TAB ─────────────────────────────────────────────────────
            with tab_login:
                st.markdown("#### Account login")
                with st.form("login_form", clear_on_submit=False):
                    username = st.text_input("Username or Email", placeholder="admin")
                    password = st.text_input("Password", type="password", placeholder="••••••••")
                    
                    submitted = st.form_submit_button("Log in", use_container_width=True)

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
                                # Store the JWT token — this is what future requests use
                                st.session_state.jwt_token = data["token"]
                                st.session_state.role = data["role"]
                                st.session_state.username = data["username"]
                                st.session_state.login_error = ""
                                if data.get("role") == "admin":
                                    st.success("Logged in successfully as admin. Redirecting...")
                                else:
                                    st.success("Logged in successfully. Redirecting...")
                                import time; time.sleep(0.5)
                                verify_token()
                                st.rerun()
                            else:
                                st.session_state.login_error = data.get("error", "Login failed. Please check your credentials.")
                                import time; time.sleep(0.5)
                                st.rerun()

            # ── REGISTER TAB ──────────────────────────────────────────────────
            with tab_register:
                st.markdown("#### Register")
                pending_signup = st.session_state.get("pending_signup")

                if pending_signup:
                    email_value = pending_signup.get("email", "")
                    email_parts = email_value.split("@")
                    masked_email = email_value
                    if len(email_parts) == 2 and len(email_parts[0]) > 2:
                        local = email_parts[0]
                        masked_email = f"{local[:2]}{'*' * max(2, len(local) - 2)}@{email_parts[1]}"

                    st.markdown("##### Verify your email address")
                    st.caption(f"A verification code has been sent to {masked_email}")
                    st.caption("Enter the 6-digit code below to continue.")

                    digit_cols = st.columns(6)
                    digits = []
                    for i, col in enumerate(digit_cols):
                        with col:
                            val = st.text_input(
                                f"Digit {i+1}",
                                max_chars=1,
                                key=f"verify_digit_{i}",
                                label_visibility="collapsed",
                                placeholder="0",
                            )
                            digits.append(val.strip())

                    code_input = "".join(digits)

                    verify_btn = st.button("Verify", use_container_width=True, type="primary")
                    action_col1, action_col2 = st.columns(2)
                    with action_col1:
                        resend_btn = st.button("Resend code", use_container_width=True)
                    with action_col2:
                        change_email_btn = st.button("Change email", use_container_width=True)

                    if verify_btn:
                        if len(code_input) != 6 or not code_input.isdigit():
                            st.error("Please enter the full 6-digit verification code.")
                        else:
                            with st.spinner("Verifying code..."):
                                data, verify_code = _api_call(
                                    "POST", "/auth/verify-code",
                                    json={"email": pending_signup["email"], "code": code_input}
                                )
                                if verify_code == 200:
                                    reg_data, reg_code = _api_call(
                                        "POST", "/auth/register",
                                        json={
                                            "email": pending_signup["email"],
                                            "username": pending_signup["username"],
                                            "password": pending_signup["password"],
                                        }
                                    )
                                    if reg_code == 201:
                                        st.session_state.jwt_token = reg_data.get("token")
                                        st.session_state.role = reg_data.get("role")
                                        st.session_state.username = reg_data.get("username")
                                        st.session_state.pending_signup = None
                                        for i in range(6):
                                            st.session_state.pop(f"verify_digit_{i}", None)
                                        st.success("Account created successfully! Logging in...")
                                        import time; time.sleep(0.5)
                                        verify_token()
                                        st.rerun()
                                    else:
                                        st.error(reg_data.get("error", "Registration failed after code verification."))
                                else:
                                    st.error(data.get("error", "Invalid or expired verification code."))

                    if resend_btn:
                        with st.spinner("Resending verification code..."):
                            data, resend_code = _api_call(
                                "POST", "/auth/send-verification-code",
                                json={"email": pending_signup["email"]}
                            )
                            if resend_code == 200:
                                st.success("A new verification code has been sent.")
                            else:
                                st.error(data.get("error", "Failed to resend code."))

                    if change_email_btn:
                        st.session_state.pending_signup = None
                        for i in range(6):
                            st.session_state.pop(f"verify_digit_{i}", None)
                        st.rerun()

                else:
                    with st.form("register_form", clear_on_submit=True):
                        new_email = st.text_input("Email Address", placeholder="user@example.com")
                        new_username = st.text_input("Username", placeholder="MyUsername")
                        new_password = st.text_input("Password", type="password", placeholder="••••••••")
                        confirm_password = st.text_input("Confirm password", type="password", placeholder="••••••••")
                        reg_submitted = st.form_submit_button("Continue", use_container_width=True, type="primary")

                    if reg_submitted:
                        new_email_clean = new_email.strip().lower()
                        new_username_clean = new_username.strip()

                        if not new_email_clean or not new_username_clean or not new_password:
                            st.error("Please fill out all fields.")
                        elif not re.match(r"[^@]+@[^@]+\.[^@]+", new_email_clean):
                            st.warning("Please enter a valid email address.")
                        elif len(new_username_clean) < 3:
                            st.warning("Username must be at least 3 characters long.")
                        elif not new_username_clean.isalnum():
                            st.warning("Username can only contain letters and numbers.")
                        elif len(new_password) < 8:
                            st.warning("Password must be at least 8 characters long.")
                        elif not re.search(r"\d", new_password):
                            st.warning("Password must contain at least one number.")
                        elif not re.search(r"[a-zA-Z]", new_password):
                            st.warning("Password must contain at least one letter.")
                        elif new_password != confirm_password:
                            st.error("Passwords do not match.")
                        else:
                            with st.spinner("Sending verification code..."):
                                data, code = _api_call(
                                    "POST", "/auth/send-verification-code",
                                    json={"email": new_email_clean}
                                )
                                if code == 200:
                                    st.session_state.pending_signup = {
                                        "email": new_email_clean,
                                        "username": new_username_clean,
                                        "password": new_password,
                                    }
                                    st.rerun()
                                else:
                                    st.error(data.get("error", "Failed to send verification code."))

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