import os
from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from matcher import load_data, match_jobs, build_clusters, apply_privacy_threshold, PRIVACY_THRESHOLD
from auth import require_auth, logout
from chatbot import render_chat

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GitHiredPH",
    layout="wide",
)

# ── Auth & Role ───────────────────────────────────────────────────────────────
role = require_auth()

# ── Initialize session state ──────────────────────────────────────────────────
if "current_tab" not in st.session_state:
    st.session_state.current_tab = "Dashboard"

# ── Theme ─────────────────────────────────────────────────────────────────────
current_is_dark = False
if os.path.exists(".streamlit/config.toml"):
    with open(".streamlit/config.toml", "r", encoding="utf-8") as f:
        current_is_dark = 'base="dark"' in f.read()

card_bg = "#1f2937" if current_is_dark else "#ffffff"
border_col = "#374151" if current_is_dark else "#e5e7eb"

# ── Custom CSS with palette + dark mode support ───────────────────────────────
# Palette: #3d5a80 (dark blue), #98c1d9 (sky blue), #e0fbfc (light cyan),
#          #ee6c4d (coral), #293241 (charcoal)

_dark = current_is_dark

# Dynamic palette values
_bg         = "#1a2332" if _dark else "linear-gradient(135deg, #f8fafb 0%, #e0fbfc 100%)"
_sidebar_bg = "linear-gradient(180deg, #0d1b2a 0%, #0a1520 100%)" if _dark else "linear-gradient(180deg, #3d5a80 0%, #293241 100%)"
_container_border = "#2a4a6b" if _dark else "#98c1d9"
_text       = "#e0fbfc" if _dark else "#293241"
_subtext    = "#98c1d9" if _dark else "#6b7280"
_metric_bg  = "linear-gradient(135deg, #0d2137 0%, #1a2e42 100%)" if _dark else "linear-gradient(135deg, #e0fbfc 0%, #f8fafb 100%)"
_metric_val = "#98c1d9" if _dark else "#3d5a80"
_input_border = "#2a4a6b" if _dark else "#98c1d9"
_page_bg    = f"background: #1a2332;" if _dark else f"background: linear-gradient(135deg, #f8fafb 0%, #e0fbfc 100%);"

st.markdown(f"""
<style>
    /* Root colors */
    :root {{
        --primary: #3d5a80;
        --secondary: #98c1d9;
        --accent: #ee6c4d;
        --light: #e0fbfc;
        --dark: #293241;
    }}

    /* Page background */
    [data-testid="stAppViewContainer"] {{
        {_page_bg}
    }}
    [data-testid="stHeader"] {{ background: transparent; height: 0 !important; }}

    /* Compact main block */
    .block-container {{
        padding-top: 1.2rem !important;
        padding-bottom: 1rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }}

    /* Main content text */
    .main .block-container, [data-testid="stMainBlockContainer"] {{
        color: {_text} !important;
    }}

    p, h1, h2, h3, h4, h5, h6, label, span {{
        color: {_text};
    }}

    /* Tighten vertical spacing — not too tight */
    [data-testid="stVerticalBlock"] {{
        gap: 0.6rem !important;
    }}

    /* Headings */
    h1 {{ font-size: 1.5rem !important; margin: 0 0 0.3rem 0 !important; }}
    h2 {{ font-size: 1.2rem !important; margin: 0 0 0.25rem 0 !important; }}
    h3 {{ font-size: 1rem !important; margin: 0 0 0.2rem 0 !important; }}

    /* Captions */
    [data-testid="stCaptionContainer"] p {{
        font-size: 0.78rem !important;
        margin: 0 !important;
    }}

    /* Dividers */
    hr {{
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, {_container_border}, transparent);
        margin: 0.6rem 0 !important;
    }}

    /* Content area */
    .content-area {{
        margin-left: 240px;
        flex: 1;
        padding: 1rem;
    }}

    /* Sidebar — fixed height, no scroll, compact */
    [data-testid="stSidebar"] {{
        background: {_sidebar_bg};
        height: 100vh !important;
        overflow: hidden !important;
        display: flex !important;
        flex-direction: column !important;
    }}

    [data-testid="stSidebar"] > div:first-child {{
        height: 100vh !important;
        overflow: hidden !important;
        display: flex !important;
        flex-direction: column !important;
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
    }}

    /* Squish all sidebar elements */
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] .stButton,
    [data-testid="stSidebar"] .stSelectbox,
    [data-testid="stSidebar"] .stMultiSelect,
    [data-testid="stSidebar"] .stSlider,
    [data-testid="stSidebar"] .stToggle {{
        margin-bottom: 0 !important;
        margin-top: 0 !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }}

    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
        gap: 0.2rem !important;
    }}

    [data-testid="stSidebar"] label {{
        font-size: 0.75rem !important;
        margin-bottom: 0 !important;
    }}

    [data-testid="stSidebar"] button {{
        padding-top: 0.3rem !important;
        padding-bottom: 0.3rem !important;
        min-height: 0 !important;
        font-size: 0.92rem !important;
    }}

    [data-testid="stSidebar"] hr {{
        margin: 0.3rem 0 !important;
    }}

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{
        color: #e0fbfc;
    }}

    [data-testid="stSidebar"] button {{
        background: rgba(255,255,255,0.1) !important;
        border: 1px solid rgba(152,193,217,0.3) !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.92rem !important;
        transition: all 0.2s ease !important;
        margin-bottom: 4px !important;
    }}

    [data-testid="stSidebar"] button p {{
        color: #293241 !important;
        font-weight: 600 !important;
        font-size: 0.92rem !important;
    }}

    [data-testid="stSidebar"] button:hover {{
        background: rgba(238,108,77,0.25) !important;
        border-color: #ee6c4d !important;
    }}

    [data-testid="stSidebar"] button:hover p {{
        color: #ffffff !important;
    }}

    [data-testid="stSidebar"] button:disabled,
    [data-testid="stSidebar"] button[disabled] {{
        background: rgba(238,108,77,0.2) !important;
        border-left: 3px solid #ee6c4d !important;
        border-color: rgba(238,108,77,0.5) !important;
        opacity: 1 !important;
        cursor: default !important;
    }}

    [data-testid="stSidebar"] button:disabled p,
    [data-testid="stSidebar"] button[disabled] p {{
        color: #ee6c4d !important;
        font-weight: 700 !important;
    }}

    [data-testid="stSidebar"] h3 {{
        color: #e0fbfc;
        font-weight: 700;
        font-size: 0.95rem;
    }}

    [data-testid="stSidebar"] [data-testid="stDivider"] {{
        border-color: rgba(152,193,217,0.3) !important;
    }}

    /* Container cards */
    .e1rw0b1u4 {{
        background: {'rgba(13,27,42,0.6)' if _dark else 'transparent'} !important;
        border: 1px solid {_container_border} !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 8px rgba(61,90,128,0.07) !important;
        padding: 1rem !important;
        margin-bottom: 0.6rem !important;
    }}

    /* Metric cards */
    [data-testid="metric-container"] {{
        background: {_metric_bg};
        border: 1px solid {_container_border};
        border-radius: 8px;
        padding: 0.8rem 1rem;
        box-shadow: 0 1px 4px rgba(61,90,128,0.06);
    }}

    [data-testid="metric-container"] [data-testid="stMetricValue"] {{
        color: {_metric_val};
        font-weight: 700;
        font-size: 1.3rem !important;
    }}

    [data-testid="metric-container"] [data-testid="stMetricLabel"] {{
        color: {_text};
        font-weight: 600;
        font-size: 0.8rem !important;
    }}

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0;
        border-bottom: 2px solid #98c1d9;
    }}

    .stTabs [data-baseweb="tab"] {{
        font-size: 0.9rem;
        font-weight: 600;
        color: #3d5a80;
        padding: 0.6rem 1.2rem;
        border-radius: 0;
        background: transparent;
    }}

    .stTabs [aria-selected="true"] {{
        color: #ee6c4d;
        border-bottom: 3px solid #ee6c4d;
    }}

    /* Buttons */
    div[data-testid="stButton"] button {{
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease;
    }}

    div[data-testid="stButton"] button[kind="primary"] {{
        background: #3d5a80 !important;
        border: none !important;
    }}

    div[data-testid="stButton"] button[kind="primary"]:hover {{
        background: #293241 !important;
    }}

    div[data-testid="stButton"] button[kind="secondary"] {{
        border: 1.5px solid #98c1d9 !important;
        color: #3d5a80 !important;
        background: #e0fbfc !important;
    }}

    div[data-testid="stButton"] button[kind="secondary"]:hover {{
        background: #98c1d9 !important;
    }}

    /* Inputs */
    div[data-testid="stTextInput"] input,
    div[data-testid="stSelectbox"] select {{
        border: 1.5px solid {_input_border} !important;
        border-radius: 8px !important;
        color: {_text} !important;
        background: {'#0d1b2a' if _dark else '#ffffff'} !important;
    }}

    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stSelectbox"] select:focus {{
        border-color: #ee6c4d !important;
        box-shadow: 0 0 0 3px rgba(238,108,77,0.1) !important;
    }}

    /* Privacy warning — red */
    [data-testid="stAlert"][data-baseweb="notification"] {{
        background: {'#2d0a0a' if _dark else '#fff0f0'} !important;
        border: 1.5px solid #e53e3e !important;
        border-radius: 8px !important;
        color: {'#fc8181' if _dark else '#c53030'} !important;
    }}

    [data-testid="stAlert"] p {{
        color: {'#fc8181' if _dark else '#c53030'} !important;
    }}

    /* Multiselect tags — orange */
    [data-testid="stSidebar"] [data-testid="stMultiSelect"] span[data-baseweb="tag"] {{
        background: #ee6c4d !important;
        color: #ffffff !important;
        border-radius: 4px !important;
    }}

    [data-testid="stSidebar"] [data-testid="stMultiSelect"] span[data-baseweb="tag"] span {{
        color: #ffffff !important;
    }}

    /* Dark Mode toggle label — always light cyan, readable on dark sidebar */
    [data-testid="stSidebar"] .stToggle p,
    [data-testid="stSidebar"] .stToggle label {{
        color: #e0fbfc !important;
        font-size: 0.82rem !important;
    }}
    {'[data-testid="stDataFrame"] { background: #0d1b2a !important; color: #e0fbfc !important; }' if _dark else ''}

    /* Multiselect tags — orange */
    [data-testid="stSidebar"] span[data-baseweb="tag"] {{
        background: #ee6c4d !important;
        color: #ffffff !important;
        border-radius: 4px !important;
    }}

    [data-testid="stSidebar"] span[data-baseweb="tag"] span {{
        color: #ffffff !important;
    }}

    /* Slider — orange track and thumb, readable labels */
    [data-testid="stSidebar"] [data-testid="stSlider"] div[data-baseweb="slider"] div[role="slider"] {{
        background: #ee6c4d !important;
        border-color: #ee6c4d !important;
    }}

    [data-testid="stSidebar"] [data-testid="stSlider"] div[data-baseweb="slider"] div[class*="Track"] div {{
        background: #ee6c4d !important;
    }}

    [data-testid="stSidebar"] [data-testid="stSlider"] p,
    [data-testid="stSidebar"] [data-testid="stSlider"] span,
    [data-testid="stSidebar"] [data-testid="stSlider"] div {{
        color: #e0fbfc !important;
    }}

    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{
        color: #e0fbfc !important;
        font-size: 0.8rem !important;
    }}

    /* Expanders */
    .streamlit-expanderHeader {{
        background: #e0fbfc;
        border: 1px solid #98c1d9;
        border-radius: 8px;
        color: #3d5a80;
        font-weight: 600;
    }}

    /* Divider */
    hr {{
        border: none;
        height: 2px;
        background: linear-gradient(90deg, transparent, #98c1d9, transparent);
        margin: 1.5rem 0;
    }}

    /* Scrollbar */
    ::-webkit-scrollbar {{
        width: 8px;
    }}
    ::-webkit-scrollbar-track {{
        background: #e0fbfc;
    }}
    ::-webkit-scrollbar-thumb {{
        background: #98c1d9;
        border-radius: 4px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
        background: #3d5a80;
    }}

    /* Match cards */
    .match-card {{
        background: #ffffff;
        border: 1.5px solid #98c1d9;
        border-radius: 10px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(61,90,128,0.06);
    }}

    .score-badge {{
        display: inline-block;
        padding: 6px 12px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
    }}

    .score-high   {{ background: #d1fae5; color: #065f46; }}
    .score-medium {{ background: #fef3c7; color: #92400e; }}
    .score-low    {{ background: #fee2e2; color: #991b1b; }}
</style>
""", unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_data
def get_data():
    return load_data("itjob_header_cleaned.csv")

@st.cache_data
def get_clustered_data():
    """
    Build K-Means + hierarchical clusters once and cache the result.
    This also trains the global _KMEANS_MODEL used by match_jobs() for the
    cluster boost — so we call it at startup, not lazily.
    """
    raw = load_data("itjob_header_cleaned.csv")
    return build_clusters(raw, n_clusters=8)

df = get_data()
clustered_df = get_clustered_data()  # trains models as a side-effect

def extract_cv_text(uploaded_file) -> str:
    if not uploaded_file:
        return ""
    
    text = ""
    file_type = uploaded_file.name.split(".")[-1].lower()
    
    try:
        if file_type == "pdf":
            reader = PyPDF2.PdfReader(uploaded_file)
            for page in reader.pages:
                text += page.extract_text() + " "
        elif file_type == "docx":
            doc = docx.Document(uploaded_file)
            for para in doc.paragraphs:
                text += para.text + " "
        elif file_type == "txt":
            text = uploaded_file.getvalue().decode("utf-8")
    except Exception as e:
        st.error(f"Error reading file: {e}")
        
    return text.strip()

# ── Sidebar Navigation (using Streamlit's native sidebar) ────────────────────
with st.sidebar:
    # Add Font Awesome icons
    st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    """, unsafe_allow_html=True)
    
    # GitHiredPH with light blue font
    st.markdown("""
    <div style="text-align:center; padding:0.6rem 0 0.6rem 0; border-bottom:1px solid rgba(152,193,217,0.3); margin-bottom:0.6rem;">
        <div style="font-family:Helvetica,Arial,sans-serif; font-size:1.9rem; font-weight:900;
                    color:#98c1d9; letter-spacing:-0.5px;">
            GitHiredPH
        </div>
        <div style="font-size:0.65rem; color:rgba(224,251,252,0.5); margin-top:1px;">IT Jobs Philippines</div>
    </div>
    """, unsafe_allow_html=True)

    # Navigation buttons
    current = st.session_state.current_tab

    nav_items_list = [
        ("Dashboard",   "nav_dashboard"),
        ("Job Matcher", "nav_matcher"),
        ("AI Chatbot",  "nav_chat"),
    ]
    if role == "admin":
        nav_items_list.append(("Admin Panel", "nav_admin"))

    for label, key in nav_items_list:
        is_active = current == label
        if is_active:
            st.button(label, key=key, use_container_width=True, disabled=True)
        else:
            if st.button(label, key=key, use_container_width=True):
                st.session_state.current_tab = label
                st.rerun()

    st.divider()

    # Global filters in sidebar
    st.markdown('<div style="color:#98c1d9; font-size:0.8rem; font-weight:700; margin-bottom:6px;">FILTERS</div>', unsafe_allow_html=True)

    all_levels = sorted(df["level"].dropna().unique().tolist())
    selected_levels = st.multiselect("Experience level", options=all_levels, default=all_levels)

    all_modes = sorted(df["mode"].dropna().unique().tolist())
    selected_modes = st.multiselect("Work mode", options=all_modes, default=all_modes)

    all_types = sorted(df["type"].dropna().unique().tolist())
    selected_types = st.multiselect("Job type", options=all_types, default=["Full Time"])

    salary_range = st.slider("Salary (PHP/mo)", min_value=0, max_value=500_000,
                              value=(20_000, 200_000), step=5_000, format="PHP %d")

    st.divider()

    # User info
    if role == "admin":
        st.markdown(f'<div style="color:#e0fbfc; font-size:0.85rem; padding:0.3rem 0;">&#9679; {st.session_state.get("username","Admin")} <span style="color:#ee6c4d; font-size:0.75rem;">[admin]</span></div>', unsafe_allow_html=True)
    elif role == "user":
        st.markdown(f'<div style="color:#e0fbfc; font-size:0.85rem; padding:0.3rem 0;">&#9679; {st.session_state.get("username","User")}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="color:#98c1d9; font-size:0.85rem; padding:0.3rem 0;">&#9679; Guest</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    if role == "guest":
        if st.button("Log in", use_container_width=True, key="login_btn"):
            logout()
    else:
        if st.button("Log out", use_container_width=True, key="logout_btn"):
            logout()

    st.divider()
    theme_toggle = st.toggle("Dark Mode", value=current_is_dark)

# ── Theme toggle handler ───────────────────────────────────────────────────────
if theme_toggle != current_is_dark:
    os.makedirs(".streamlit", exist_ok=True)
    config_content = (
        '[theme]\nbase="dark"\nprimaryColor="#ee6c4d"\nbackgroundColor="#1a2332"\nsecondaryBackgroundColor="#0d1b2a"\ntextColor="#e0fbfc"\n'
        if theme_toggle else
        '[theme]\nbase="light"\nprimaryColor="#3d5a80"\nbackgroundColor="#f8fafb"\nsecondaryBackgroundColor="#e0fbfc"\ntextColor="#293241"\n'
    )
    with open(".streamlit/config.toml", "w", encoding="utf-8") as f:
        f.write(config_content)
    import time; time.sleep(0.3)
    st.rerun()

# ── Main header ───────────────────────────────────────────────────────────────
page_icons = {
    "Dashboard":   "▣",
    "Job Matcher": "◎",
    "AI Chatbot":  "◈",
    "Admin Panel": "◧",
}
current_page = st.session_state.current_tab
page_icon = page_icons.get(current_page, "▣")
st.markdown(
    f'<div style="font-family:Helvetica,Arial,sans-serif;font-size:1.9rem;font-weight:800;color:#3d5a80;margin-bottom:0.2rem;">'
    f'{page_icon} {current_page}</div>',
    unsafe_allow_html=True
)
st.caption("525 listings · Philippines | Streamlit · scikit-learn · Plotly · Groq AI")
st.divider()

# ── Apply filters ─────────────────────────────────────────────────────────────
filtered_df = df.copy()
if selected_levels:
    filtered_df = filtered_df[filtered_df["level"].isin(selected_levels)]
if selected_modes:
    filtered_df = filtered_df[filtered_df["mode"].isin(selected_modes)]
if selected_types:
    filtered_df = filtered_df[filtered_df["type"].isin(selected_types)]
filtered_df = filtered_df[
    (filtered_df["salary_mid"] >= salary_range[0]) &
    (filtered_df["salary_mid"] <= salary_range[1])
]

# ── Page routing ───────────────────────────────────────────────────────────────
show_dashboard = st.session_state.current_tab == "Dashboard"
show_matcher   = st.session_state.current_tab == "Job Matcher"
show_chat      = st.session_state.current_tab == "AI Chatbot"
show_admin     = st.session_state.current_tab == "Admin Panel" and role == "admin"


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if show_dashboard:
    # ── Metrics ───────────────────────────────────────────────────────────────
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader("IT Job Market Overview")
        st.caption(f"Showing {len(filtered_df):,} of {len(df):,} listings based on your filters")
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a: st.metric("Total listings", f"{len(filtered_df):,}")
        with col_b: st.metric("Median salary", f"PHP {filtered_df['salary_mid'].median():,.0f}/mo")
        with col_c:
            remote_pct = filtered_df["mode"].isin(["Remote", "Hybrid"]).sum() / max(len(filtered_df), 1) * 100
            st.metric("Remote / hybrid", f"{remote_pct:.0f}%")
        with col_d:
            top_spec = filtered_df["tech_specialisation"].value_counts().index[0] if len(filtered_df) > 0 else "-"
            st.metric("Top specialisation", top_spec)

    level_order = ["Junior", "Middle", "Senior", "Lead"]

    # ── Privacy threshold check ───────────────────────────────────────────────
    # Suppress salary data for experience levels with fewer than PRIVACY_THRESHOLD jobs
    privacy_df = apply_privacy_threshold(filtered_df, group_col="level", salary_col="salary_mid")
    suppressed_levels = privacy_df[privacy_df["privacy_suppressed"]]["level"].unique().tolist()
    if suppressed_levels:
        st.error(
            f"**🔒 Privacy Notice:** Salary data for **{', '.join(suppressed_levels)}** "
            f"has been suppressed — fewer than {PRIVACY_THRESHOLD} listings in this group. "
            f"Displaying exact figures could allow re-identification of individuals. "
            f"(Philippine Data Privacy Act of 2012)"
        )

    # ── Salary + Work mode ────────────────────────────────────────────────────
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        col_left, col_right = st.columns([3, 2])
        with col_left:
            st.markdown("**Salary range by experience level**")
            # Only plot levels that passed the privacy threshold
            safe_levels = [l for l in level_order if l not in suppressed_levels]
            plot_salary_df = privacy_df[privacy_df["level"].isin(safe_levels)].dropna(subset=["salary_mid"])
            if plot_salary_df.empty:
                st.info("Insufficient data to display salary chart with current filters.")
            else:
                fig_box = px.box(
                    plot_salary_df,
                    x="level", y="salary_mid", category_orders={"level": safe_levels}, color="level",
                    color_discrete_sequence=["#3d5a80", "#98c1d9", "#ee6c4d", "#e0fbfc"],
                    labels={"salary_mid": "Monthly salary (PHP)", "level": "Level"}, points="outliers"
                )
                fig_box.update_layout(showlegend=False, yaxis_tickformat=",.0f", margin=dict(t=15, b=15, l=8, r=8))
                st.plotly_chart(fig_box, use_container_width=True)
        with col_right:
            st.markdown("**Work mode**")
            mode_counts = filtered_df["mode"].value_counts().reset_index()
            mode_counts.columns = ["mode", "count"]
            fig_donut = px.pie(mode_counts, names="mode", values="count", hole=0.55,
                               color_discrete_sequence=["#3d5a80", "#98c1d9", "#ee6c4d"])
            fig_donut.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2),
                                     margin=dict(t=15, b=30, l=8, r=8))
            fig_donut.update_traces(textinfo="percent+label")
            st.plotly_chart(fig_donut, use_container_width=True)

    # ── Specialisations + Experience ──────────────────────────────────────────
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        col_left2, col_right2 = st.columns([2, 3])
        with col_left2:
            st.markdown("**Top 15 specialisations**")
            top_specs = filtered_df["tech_specialisation"].value_counts().head(15).reset_index()
            top_specs.columns = ["specialisation", "count"]
            fig_bar = px.bar(top_specs, x="count", y="specialisation", orientation="h", color="count",
                             color_continuous_scale=["#e0fbfc", "#98c1d9", "#3d5a80"],
                             labels={"count": "Listings", "specialisation": ""})
            fig_bar.update_layout(showlegend=False, coloraxis_showscale=False,
                                  yaxis=dict(autorange="reversed"), margin=dict(t=15, b=15, l=8, r=8))
            st.plotly_chart(fig_bar, use_container_width=True)
        with col_right2:
            st.markdown("**Experience required by level**")
            fig_violin = px.violin(
                filtered_df[filtered_df["level"].isin(safe_levels)],
                x="level", y="work_experience_years", category_orders={"level": safe_levels}, color="level",
                color_discrete_sequence=["#3d5a80", "#98c1d9", "#ee6c4d", "#e0fbfc"],
                box=True, points="outliers",
                labels={"work_experience_years": "Years required", "level": "Level"}
            )
            fig_violin.update_layout(showlegend=False, margin=dict(t=15, b=15, l=8, r=8))
            st.plotly_chart(fig_violin, use_container_width=True)

    # ── Education ─────────────────────────────────────────────────────────────
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("**Education requirements**")
        edu_counts = filtered_df["education_level"].value_counts().reset_index()
        edu_counts.columns = ["education", "count"]
        fig_edu = px.bar(edu_counts, x="education", y="count", color="education",
                         color_discrete_sequence=["#3d5a80", "#98c1d9", "#ee6c4d", "#e0fbfc", "#293241"],
                         labels={"count": "Listings", "education": "Education level"})
        fig_edu.update_layout(showlegend=False, margin=dict(t=15, b=15, l=8, r=8))
        st.plotly_chart(fig_edu, use_container_width=True)
        with st.expander("View raw data", expanded=False):
            st.dataframe(
                filtered_df[["tech_specialisation", "level", "mode", "type",
                              "salary_from", "salary_to", "work_experience_years", "education_level"]],
                use_container_width=True, hide_index=True
            )

    # ── Clustering ────────────────────────────────────────────────────────────
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader("Job Market Clusters")
        st.caption("Jobs grouped by skill similarity, salary band, and experience level using K-Means (8 clusters) and Hierarchical (Ward linkage) clustering.")

        cluster_tab1, cluster_tab2 = st.tabs(["K-Means Clusters", "Hierarchical Clusters"])

        with cluster_tab1:
            st.markdown("**K-Means cluster map** — each dot is a job, coloured by cluster")
            plot_df = filtered_df.copy()
            plot_df = plot_df.merge(
                clustered_df[["jobid", "kmeans_cluster", "kmeans_label", "pca_x", "pca_y"]],
                on="jobid", how="left"
            ).dropna(subset=["pca_x", "pca_y"])
            if not plot_df.empty:
                fig_scatter = px.scatter(
                    plot_df, x="pca_x", y="pca_y", color="kmeans_label",
                    hover_data={"tech_specialisation": True, "level": True, "salary_mid": ":,.0f", "pca_x": False, "pca_y": False},
                    labels={"pca_x": "PCA 1", "pca_y": "PCA 2", "kmeans_label": "Cluster"},
                    color_discrete_sequence=["#3d5a80","#98c1d9","#ee6c4d","#e0fbfc","#293241","#5b8db8","#f4a07a","#b0d9e8"],
                    opacity=0.75,
                )
                fig_scatter.update_traces(marker=dict(size=6))
                fig_scatter.update_layout(legend=dict(orientation="v", x=1.01, y=1), margin=dict(t=15, b=15, l=8, r=8), height=360)
                st.plotly_chart(fig_scatter, use_container_width=True)

                # Apply privacy threshold to cluster summary
                cluster_privacy_df = apply_privacy_threshold(plot_df, group_col="kmeans_label", salary_col="salary_mid")
                suppressed_clusters = cluster_privacy_df[cluster_privacy_df["privacy_suppressed"]]["kmeans_label"].unique().tolist()

                cluster_summary = (
                    plot_df.groupby("kmeans_label")
                    .agg(Jobs=("jobid","count"), Median_Salary=("salary_mid","median"), Avg_Exp=("work_experience_years","mean"))
                    .rename(columns={"Median_Salary":"Median Salary (PHP)","Avg_Exp":"Avg Exp (yrs)"})
                    .sort_values("Jobs", ascending=False).reset_index().rename(columns={"kmeans_label":"Cluster"})
                )

                # Suppress salary for small clusters
                def format_salary(row):
                    if row["Cluster"] in suppressed_clusters:
                        return f"🔒 Suppressed (n < {PRIVACY_THRESHOLD})"
                    return f"PHP {row['Median Salary (PHP)']:,.0f}"

                cluster_summary["Median Salary (PHP)"] = cluster_summary.apply(format_salary, axis=1)
                cluster_summary["Avg Exp (yrs)"] = cluster_summary["Avg Exp (yrs)"].map("{:.1f}".format)

                if suppressed_clusters:
                    st.caption(f"🔒 Salary suppressed for {len(suppressed_clusters)} cluster(s) with fewer than {PRIVACY_THRESHOLD} listings.")

                st.dataframe(cluster_summary, use_container_width=True, hide_index=True)
            else:
                st.info("No cluster data available for the current filter selection.")

        with cluster_tab2:
            st.markdown("**Hierarchical cluster map** — Ward linkage, cut at 8 clusters")
            plot_df2 = filtered_df.copy()
            plot_df2 = plot_df2.merge(
                clustered_df[["jobid", "hier_cluster", "pca_x", "pca_y"]],
                on="jobid", how="left"
            ).dropna(subset=["pca_x", "pca_y"])
            if not plot_df2.empty:
                plot_df2["hier_cluster"] = "Cluster " + plot_df2["hier_cluster"].astype(int).astype(str)
                fig_hier = px.scatter(
                    plot_df2, x="pca_x", y="pca_y", color="hier_cluster",
                    hover_data={"tech_specialisation": True, "level": True, "salary_mid": ":,.0f", "pca_x": False, "pca_y": False},
                    labels={"pca_x": "PCA 1", "pca_y": "PCA 2", "hier_cluster": "Cluster"},
                    color_discrete_sequence=["#3d5a80","#98c1d9","#ee6c4d","#e0fbfc","#293241","#5b8db8","#f4a07a","#b0d9e8"],
                    opacity=0.75,
                )
                fig_hier.update_traces(marker=dict(size=6))
                fig_hier.update_layout(legend=dict(orientation="v", x=1.01, y=1), margin=dict(t=15, b=15, l=8, r=8), height=360)
                st.plotly_chart(fig_hier, use_container_width=True)
                link_matrix = clustered_df.attrs.get("linkage_matrix")
                if link_matrix is not None:
                    st.markdown("**Dendrogram** — top 30 merges (Ward linkage)")
                    import plotly.figure_factory as ff
                    n = len(link_matrix)
                    last_n = 30
                    truncated = link_matrix[n - last_n:]
                    try:
                        fig_dendro = ff.create_dendrogram(
                            truncated[:, :2], orientation="bottom",
                            labels=[str(i) for i in range(last_n + 1)],
                            color_threshold=truncated[:, 2].mean(),
                        )
                        fig_dendro.update_layout(xaxis=dict(showticklabels=False),
                                                 yaxis=dict(title="Merge distance (Ward)"),
                                                 margin=dict(t=15, b=15, l=30, r=8), height=280)
                        st.plotly_chart(fig_dendro, use_container_width=True)
                    except Exception:
                        merge_distances = link_matrix[n - last_n:, 2]
                        fig_fallback = px.bar(x=list(range(1, last_n + 1)), y=merge_distances,
                                              labels={"x": "Merge step", "y": "Ward distance"},
                                              color=merge_distances, color_continuous_scale=["#e0fbfc","#98c1d9","#3d5a80"])
                        fig_fallback.update_layout(coloraxis_showscale=False, margin=dict(t=15, b=15, l=8, r=8), height=240)
                        st.plotly_chart(fig_fallback, use_container_width=True)
            else:
                st.info("No cluster data available for the current filter selection.")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — JOB MATCHER
# ══════════════════════════════════════════════════════════════════════════════
if show_matcher:
    st.subheader("Job Matcher")
    st.caption("Rank jobs based on your profile.")

    st.markdown("**1. Upload your CV/Resume (Optional)**")
    uploaded_cv = st.file_uploader("Upload PDF, DOCX or TXT", type=["pdf", "docx", "txt"])
    has_cv = uploaded_cv is not None

    with st.form("matcher_form"):
        st.markdown("**2. Or enter details manually**")
        
        col1, col2 = st.columns(2)
        with col1:
            user_skills   = st.text_input("Skills / keywords", placeholder="e.g. Python, data analysis, SQL", disabled=has_cv)
            user_level    = st.selectbox("Your experience level", options=["Any"] + all_levels, disabled=has_cv)
            user_mode     = st.selectbox("Preferred work mode", options=["Any"] + all_modes, disabled=has_cv)
            user_type     = st.selectbox("Job type preference", options=["Any"] + all_types, disabled=has_cv)
        with col2:
            user_exp        = st.slider("Years of experience", min_value=0.0, max_value=15.0, value=3.0, step=0.5, format="%.1f yrs", disabled=has_cv)
            user_salary_min = st.number_input("Min salary (PHP/month)", min_value=0, max_value=500_000, value=40_000, step=5_000, disabled=has_cv)
            user_salary_max = st.number_input("Max salary (PHP/month)", min_value=0, max_value=500_000, value=120_000, step=5_000, disabled=has_cv)

        submitted = st.form_submit_button("Find Matches", use_container_width=True)

    if submitted:
        # Extract CV text if a file is uploaded
        cv_text = ""
        if uploaded_cv is not None:
            cv_text = extract_cv_text(uploaded_cv)
            with st.expander("🛠️ Debug: Extracted CV Text", expanded=False):
                st.text(cv_text)
            
        # Combine user skills and CV text for the final query
        combined_skills = cv_text if has_cv else user_skills.strip()
        
        level_filter = [] if (user_level == "Any" or has_cv) else [user_level]
        mode_filter  = [] if (user_mode  == "Any" or has_cv) else [user_mode]
        type_filter  = [] if (user_type  == "Any" or has_cv) else [user_type]
        
        # Override experience and salary for pure CV search
        search_exp = 3.0 if has_cv else user_exp
        search_sal_min = 0 if has_cv else user_salary_min
        search_sal_max = 500_000 if has_cv else user_salary_max

        with st.spinner("Running matching engine..."):
            results = match_jobs(df=df, skill_query=combined_skills, level=level_filter, mode=mode_filter,
                                 job_type=type_filter, exp_years=search_exp,
                                 salary_min=search_sal_min, salary_max=search_sal_max, top_n=len(df))
                                 
        # --- Strict Filtering ---
        # 1. If terms were specified, the skill score MUST be greater than 2.0 (ensuring at least some direct overlap)
        if combined_skills:
            results = results[results["skill_score"] > 2.0]
            
        # 2. Cut off completely irrelevant matches that are riding on free points from "Any" salary/exp filters
        results = results[results["match_pct"] >= 45]

        if results.empty:
            st.warning("No jobs matched enough criteria. Try adding more skills or lowering your constraints.")
        else:
            st.success(f"Successfully matched {len(results)} jobs.")

            # Top N results for charts to avoid clutter
            chart_n = min(15, len(results))
            results_chart = results.head(chart_n).copy()

            st.markdown(f"**Match Score Breakdown (Top {chart_n})**")
            fig_scores = px.bar(
                results_chart, x="match_pct",
                y=results_chart.index.astype(str) + ". " + results_chart["tech_specialisation"] + " (" + results_chart["level"] + ")",
                orientation="h", color="match_pct",
                color_continuous_scale=["#f87171", "#fbbf24", "#34d399"], range_color=[0, 100],
                labels={"match_pct": "Match %", "y": ""}, text="match_pct"
            )
            fig_scores.update_traces(texttemplate="%{text}%", textposition="outside")
            fig_scores.update_layout(coloraxis_showscale=False, yaxis=dict(autorange="reversed"),
                                      xaxis=dict(range=[0, 115]), margin=dict(t=15, b=15, l=8, r=8),
                                      height=max(260, len(results_chart) * 36))
            st.plotly_chart(fig_scores, use_container_width=True)

            st.markdown(f"**Score Analysis (Top {chart_n})**")
            results_long = results_chart.copy()
            results_long["label"] = results_long["tech_specialisation"] + " (" + results_long["level"] + ")"
            fig_stacked = go.Figure()
            fig_stacked.add_trace(go.Bar(name="Skill match (max 55)", y=results_long["label"], x=results_long["skill_score"].round(1), orientation="h", marker_color="#3b82f6"))
            fig_stacked.add_trace(go.Bar(name="Salary fit (max 25)",  y=results_long["label"], x=results_long["salary_score"].round(1), orientation="h", marker_color="#10b981"))
            fig_stacked.add_trace(go.Bar(name="Experience fit (max 15)", y=results_long["label"], x=results_long["exp_score"].round(1), orientation="h", marker_color="#f59e0b"))
            fig_stacked.add_trace(go.Bar(name="Cluster boost (max 5)", y=results_long["label"], x=results_long["cluster_boost"].round(1), orientation="h", marker_color="#8b5cf6"))
            fig_stacked.update_layout(barmode="stack", legend=dict(orientation="h", yanchor="bottom", y=1.02),
                                       yaxis=dict(autorange="reversed"), xaxis=dict(title="Score breakdown", range=[0, 100]),
                                       margin=dict(t=40, b=15, l=8, r=8), height=max(260, len(results_chart) * 36))
            st.plotly_chart(fig_stacked, use_container_width=True)

            st.markdown("**Matched Job Listings**")
            for _, row in results.iterrows():
                score = int(row["match_pct"])
                badge_class = "score-high" if score >= 70 else "score-medium" if score >= 45 else "score-low"
                exp_req = f"{row['work_experience_years']:.0f} yrs" if pd.notna(row["work_experience_years"]) else "Not specified"
                st.markdown(f"""
                <div class="match-card">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                        <strong style="font-size:1.05rem;">{row['tech_specialisation']}</strong>
                        <span class="score-badge {badge_class}">{score}% Match</span>
                    </div>
                    <div style="display:flex; gap:20px; flex-wrap:wrap; font-size:0.85rem;">
                        <span><strong>Level:</strong> {row['level']}</span>
                        <span><strong>Mode:</strong> {row['mode']}</span>
                        <span><strong>Type:</strong> {row['type']}</span>
                        <span><strong>Salary:</strong> PHP {row['salary_from']:,.0f} – {row['salary_to']:,.0f}/mo</span>
                        <span><strong>Education:</strong> {row['education_level']}</span>
                        <span><strong>Exp Required:</strong> {exp_req}</span>
                    </div>
                </div>""", unsafe_allow_html=True)

            st.divider()
            csv_out = results.drop(columns=["skill_score", "salary_score", "exp_score", "cluster_boost"], errors="ignore").to_csv(index=False)
            st.download_button("Download Results (CSV)", data=csv_out, file_name="matched_jobs.csv", mime="text/csv")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 3 — AI CHATBOT
# ══════════════════════════════════════════════════════════════════════════════
if show_chat:

    MAX_CHATS = 5

    # ── Init multi-chat session state ─────────────────────────────────────────
    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = {
            "chat_1": {"title": "Chat 1", "history": [], "api_history": []}
        }
    if "active_chat" not in st.session_state:
        st.session_state.active_chat = "chat_1"
    if "chat_counter" not in st.session_state:
        st.session_state.chat_counter = 1

    sessions = st.session_state.chat_sessions
    active   = st.session_state.active_chat

    # Ensure active chat still exists (could have been deleted)
    if active not in sessions:
        st.session_state.active_chat = list(sessions.keys())[0]
        active = st.session_state.active_chat

    # ── Chat session sidebar panel ────────────────────────────────────────────
    col_main, col_history = st.columns([3, 1])

    with col_history:
        with st.container(border=True):
            st.markdown("**Chat Sessions**")

            # New chat button
            if len(sessions) < MAX_CHATS:
                if st.button("+ New Chat", use_container_width=True, type="primary"):
                    st.session_state.chat_counter += 1
                    new_key = f"chat_{st.session_state.chat_counter}"
                    new_num = st.session_state.chat_counter
                    sessions[new_key] = {
                        "title": f"Chat {new_num}",
                        "history": [],
                        "api_history": []
                    }
                    st.session_state.active_chat = new_key
                    # Reset system prompt so new chat gets fresh context
                    st.session_state.pop("system_prompt", None)
                    st.rerun()
            else:
                st.caption(f"Max {MAX_CHATS} chats reached.")

            st.divider()

            # List all chats
            for key, session in list(sessions.items()):
                is_active = key == active
                msg_count = len(session["history"])

                # Auto-title from first user message
                if msg_count > 0 and session["title"].startswith("Chat "):
                    first_msg = session["history"][0].get("content", "")
                    session["title"] = first_msg[:28] + "…" if len(first_msg) > 28 else first_msg

                label = f"{'▶ ' if is_active else ''}{session['title']}"
                col_btn, col_del = st.columns([4, 1])
                with col_btn:
                    if st.button(label, key=f"select_{key}", use_container_width=True,
                                 disabled=is_active):
                        st.session_state.active_chat = key
                        st.session_state.pop("system_prompt", None)
                        st.rerun()
                with col_del:
                    if st.button("✕", key=f"del_{key}", use_container_width=True):
                        del sessions[key]
                        if not sessions:
                            st.session_state.chat_counter += 1
                            new_key = f"chat_{st.session_state.chat_counter}"
                            sessions[new_key] = {"title": f"Chat {st.session_state.chat_counter}", "history": [], "api_history": []}
                        st.session_state.active_chat = list(sessions.keys())[0]
                        st.session_state.pop("system_prompt", None)
                        st.rerun()

                st.caption(f"{msg_count // 2} message{'s' if msg_count // 2 != 1 else ''}")

    # ── Active chat area ──────────────────────────────────────────────────────
    with col_main:
        active_session = sessions[active]

        st.subheader(f"AI Job Assistant — {active_session['title']}")
        st.caption("Ask about salaries, job demand, or say 'find me a job' to get matched via chat.")

        st.markdown("**Try asking:**")
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            if st.button("What's the average salary for a Senior Python developer?", use_container_width=True, key="q1"):
                st.session_state.gemini_trigger = "What's the average salary for a Senior Python developer?"
                st.rerun()
        with col_s2:
            if st.button("Find me remote jobs for someone with 3 years of Java experience", use_container_width=True, key="q2"):
                st.session_state.gemini_trigger = "Find me remote jobs for someone with 3 years of Java experience"
                st.rerun()
        with col_s3:
            if st.button("Which IT specialisations are most in demand?", use_container_width=True, key="q3"):
                st.session_state.gemini_trigger = "Which IT specialisations are most in demand?"
                st.rerun()

        st.divider()

        # Wire the active session's history into the keys render_chat expects
        st.session_state.chat_history    = active_session["history"]
        st.session_state.gemini_history  = active_session["api_history"]

        render_chat(df)

        # Write back (render_chat mutates session_state keys directly)
        active_session["history"]     = st.session_state.chat_history
        active_session["api_history"] = st.session_state.gemini_history


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 4 — ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════════════
if show_admin:
        st.subheader("Admin Panel")
        st.caption("Only visible to logged-in admins.")

        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Total rows", len(df))
        with col2: st.metric("Unique specialisations", df["tech_specialisation"].nunique())
        with col3: st.metric("Avg salary (mid)", f"PHP {df['salary_mid'].mean():,.0f}")
        with col4: st.metric("Missing exp data", int(df["work_experience_years"].isna().sum()))

        st.divider()

        st.markdown("**Full dataset (unfiltered)**")
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ Download full dataset (CSV)",
            data=df.to_csv(index=False),
            file_name="itjobs_full.csv",
            mime="text/csv",
        )

        st.divider()

        st.markdown("**Salary outlier inspector**")
        threshold = st.slider("Show jobs with salary_mid above:", 0, 500_000, 200_000,
                              step=10_000, format="PHP %d")
        outliers = df[df["salary_mid"] > threshold].sort_values("salary_mid", ascending=False)
        st.caption(f"{len(outliers)} listings above threshold")
        st.dataframe(
            outliers[["jobid", "tech_specialisation", "level", "salary_from", "salary_to", "salary_mid"]],
            use_container_width=True, hide_index=True
        )

