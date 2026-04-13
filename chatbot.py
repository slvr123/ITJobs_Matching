import os
import re
import json
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
from matcher import match_jobs

# ── Gemini client ─────────────────────────────────────────────────────────────
# Reads GEMINI_API_KEY from your environment.
# Get a free key at: https://aistudio.google.com
# Set it before running:
#   Mac/Linux:  export GEMINI_API_KEY="AIza..."
#   Windows:    $env:GEMINI_API_KEY = "AIza..."
#
# Free tier limits (no credit card needed):
#   - 1,500 requests per day
#   - 1,000,000 tokens per minute
#   - Completely free forever on gemini-2.0-flash

MODEL = "gemini-2.0-flash"


def _get_client():
    """
    Create the Gemini client lazily — only when the user actually opens the
    chat tab. This way a missing API key doesn't crash the whole app on startup.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            api_key = ""
            
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def _build_system_prompt(df: pd.DataFrame) -> str:
    """
    Build a data-aware system prompt from live dataset statistics.
    Injecting real numbers here means the AI answers factually from your
    actual CSV instead of making things up.
    """
    total = len(df)
    level_counts   = df["level"].value_counts().to_dict()
    mode_counts    = df["mode"].value_counts().to_dict()
    type_counts    = df["type"].value_counts().to_dict()
    edu_counts     = df["education_level"].value_counts().to_dict()

    salary_by_level = (
        df.groupby("level")["salary_mid"].median().round(0).astype(int).to_dict()
    )
    exp_by_level = (
        df.groupby("level")["work_experience_years"].median().round(1).to_dict()
    )
    top_specs = df["tech_specialisation"].value_counts().head(20).to_dict()
    spec_salary = (
        df.groupby("tech_specialisation")["salary_mid"]
        .agg(["median", "min", "max"]).round(0).astype(int)
        .sort_values("median", ascending=False).head(15)
        .to_dict("index")
    )

    return f"""You are JobBot — an AI assistant for the IT Jobs PH dashboard, \
a data science project analyzing {total} IT job listings in the Philippines.

Your two core abilities:
1. Answer questions about the dataset (salary, demand, experience, trends)
2. Find matching jobs when someone describes what they're looking for

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATASET FACTS (use these — do not invent numbers)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total listings: {total} | Country: Philippines only

Experience levels: {json.dumps(level_counts)}
Work modes:        {json.dumps(mode_counts)}
Job types:         {json.dumps(type_counts)}
Education:         {json.dumps(edu_counts)}

Median monthly salary by level (PHP):
{json.dumps(salary_by_level, indent=2)}

Avg experience required by level (years):
{json.dumps(exp_by_level, indent=2)}

Top 20 specialisations (name: job count):
{json.dumps(top_specs, indent=2)}

Salary by top specialisation (PHP/month — median | min | max):
{json.dumps(spec_salary, indent=2)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TRIGGERING JOB MATCHING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When the user wants job recommendations, extract their profile and output
ONLY this JSON block on its own line (nothing else on that line):

[MATCH]{{"skill_query":"...","level":[],"mode":[],"job_type":[],"exp_years":0,"salary_min":0,"salary_max":500000,"top_n":5}}[/MATCH]

Rules:
- skill_query: user's skills as a comma-separated string
- level: e.g. ["Middle","Senior"] — [] means any level
- mode: e.g. ["Remote","Hybrid"] — [] means any mode
- job_type: e.g. ["Full Time"] — [] means any type
- exp_years: float years of experience
- salary_min / salary_max: PHP/month integers (default 0 / 500000)
- top_n: 3–10

After the [MATCH] block add one short sentence like "Here are your best matches!"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BEHAVIOUR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Be concise and friendly. Keep replies under ~150 words unless detail is needed.
- Format salaries as "PHP X,XXX/month".
- If asked about something not in the dataset (company names, job links), say so.
- Never invent listings or salary figures not in the data above.
"""


def _parse_match_command(text: str):
    """Extract and parse the [MATCH]...[/MATCH] JSON block from the AI reply."""
    match = re.search(r"\[MATCH\](.*?)\[/MATCH\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            return None
    return None


def _clean_response(text: str) -> str:
    """Strip the [MATCH] block from the text shown to the user."""
    return re.sub(r"\[MATCH\].*?\[/MATCH\]", "", text, flags=re.DOTALL).strip()


def _render_match_results(results_df):
    """Render matched job cards inside the chat bubble."""
    if results_df is None or results_df.empty:
        st.warning("No matching jobs found. Try broadening your criteria.")
        return

    st.markdown(f"**Found {len(results_df)} matching jobs:**")
    for _, row in results_df.iterrows():
        score = int(row["match_pct"])
        badge = (
            f"🟢 {score}% match" if score >= 70 else
            f"🟡 {score}% match" if score >= 45 else
            f"🔴 {score}% match"
        )
        exp_req = (
            f"{row['work_experience_years']:.0f} yrs"
            if pd.notna(row["work_experience_years"]) else "Not specified"
        )
        with st.container(border=True):
            col_title, col_badge = st.columns([4, 1])
            with col_title:
                st.markdown(f"**{row['tech_specialisation']}** · {row['level']}")
            with col_badge:
                st.markdown(badge)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.caption(f"🏠 {row['mode']}")
                st.caption(f"📋 {row['type']}")
            with col2:
                st.caption(f"💰 PHP {row['salary_from']:,.0f} – {row['salary_to']:,.0f}/mo")
                st.caption(f"⏳ {exp_req} required")
            with col3:
                st.caption(f"🎓 {row['education_level']}")


def init_chat(df: pd.DataFrame):
    """
    Initialise session state for the chat.

    Gemini's API is also stateless — it has no memory between calls.
    We store the full conversation as a list of {"role", "parts"} dicts
    (Gemini's format) and send the whole list every API call.

    We also cache the system prompt so it's only built once per session,
    not on every message.
    """
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []   # for display (role + content + match_results)
    if "gemini_history" not in st.session_state:
        st.session_state.gemini_history = []  # for API calls (role + parts)
    if "system_prompt" not in st.session_state:
        st.session_state.system_prompt = _build_system_prompt(df)


def render_chat(df: pd.DataFrame):
    """
    Main chat UI. Called from the Chat tab in app.py.

    How the Gemini API call works:
      - We pass the system prompt as a separate `system_instruction` field
        (Gemini separates system prompt from conversation history)
      - We send the full gemini_history list so the model sees prior turns
      - The response comes back as response.text
    """
    init_chat(df)

    client = _get_client()

    # ── API key check ─────────────────────────────────────────────────────────
    if client is None:
        st.warning(
            "**GEMINI_API_KEY not set.**\n\n"
            "1. Get a free key at [aistudio.google.com](https://aistudio.google.com) — no credit card needed\n"
            "2. In your terminal, run: `export GEMINI_API_KEY=\"AIza...\"`\n"
            "3. Restart Streamlit"
        )
        return

    # ── Replay chat history ───────────────────────────────────────────────────
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("match_results") is not None:
                _render_match_results(msg["match_results"])

    # ── User input ────────────────────────────────────────────────────────────
    user_input = st.chat_input("Ask about IT jobs in the Philippines…")

    if user_input:
        with st.chat_message("user"):
            st.markdown(user_input)

        # Add to both history lists
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
            "match_results": None,
        })
        st.session_state.gemini_history.append({
            "role": "user",
            "parts": [{"text": user_input}],
        })

        # ── Call Gemini API ───────────────────────────────────────────────────
        # Key difference from Anthropic: Gemini takes system_instruction
        # separately from the conversation contents.
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    response = client.models.generate_content(
                        model=MODEL,
                        contents=st.session_state.gemini_history,
                        config=types.GenerateContentConfig(
                            system_instruction=st.session_state.system_prompt,
                            max_output_tokens=1024,
                            temperature=0.3,   # lower = more factual, less creative
                        ),
                    )
                    raw_reply = response.text

                except Exception as e:
                    raw_reply = (
                        f"Sorry, something went wrong: `{e}`\n\n"
                        "Check that your GEMINI_API_KEY is valid and you have internet access."
                    )

        # ── Parse and display ─────────────────────────────────────────────────
        match_params   = _parse_match_command(raw_reply)
        clean_reply    = _clean_response(raw_reply)
        match_results_df = None

        with st.chat_message("assistant"):
            st.markdown(clean_reply)

            if match_params:
                with st.spinner("Running job matcher…"):
                    try:
                        match_results_df = match_jobs(
                            df=df,
                            skill_query=match_params.get("skill_query", ""),
                            level=match_params.get("level", []),
                            mode=match_params.get("mode", []),
                            job_type=match_params.get("job_type", []),
                            exp_years=float(match_params.get("exp_years", 3)),
                            salary_min=float(match_params.get("salary_min", 0)),
                            salary_max=float(match_params.get("salary_max", 500_000)),
                            top_n=int(match_params.get("top_n", 5)),
                        )
                        _render_match_results(match_results_df)
                    except Exception as e:
                        st.warning(f"Matcher error: {e}")

        # Store in display history
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": clean_reply,
            "match_results": match_results_df,
        })

        # Store in Gemini history (API format — no match_results here)
        st.session_state.gemini_history.append({
            "role": "model",   # Gemini uses "model" not "assistant"
            "parts": [{"text": raw_reply}],
        })