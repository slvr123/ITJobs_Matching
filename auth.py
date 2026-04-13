import requests
import streamlit as st

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
                username = st.text_input("Username", placeholder="admin", key="login_user")
                password = st.text_input("Password", type="password", placeholder="••••••••", key="login_pass")

                if st.session_state.login_error:
                    st.error(st.session_state.login_error)

                if st.button("Log in", use_container_width=True):
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
                        st.rerun()
                    else:
                        st.session_state.login_error = data.get("error", "Login failed.")
                        st.rerun()

            # ── REGISTER TAB ──────────────────────────────────────────────────
            with tab_register:
                st.markdown("#### Register")
                new_username = st.text_input("New username", key="reg_user")
                new_password = st.text_input("New password", type="password", key="reg_pass")
                confirm_password = st.text_input("Confirm password", type="password", key="reg_conf")

                if st.button("Create account", use_container_width=True, type="primary"):
                    if new_password != confirm_password:
                        st.error("Passwords do not match.")
                    else:
                        data, code = _api_call(
                            "POST", "/auth/register",
                            json={"username": new_username, "password": new_password}
                        )

                        if code == 201:
                            # Auto-login after registration
                            st.session_state.jwt_token = data["token"]
                            st.session_state.role = data["role"]
                            st.session_state.username = data["username"]
                            st.session_state.login_error = ""
                            st.success(data.get("message", "Account created!"))
                            st.rerun()
                        else:
                            st.error(data.get("error", "Registration failed."))

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