import html
import json
import os
import re
import uuid
from pathlib import Path
from shutil import which

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".ENV")

SAMPLE_MEETING_PATH = ROOT / "assets" / "sample_meeting.json"
ALLOWED_EMAILS = {
    entry.strip().lower()
    for entry in os.getenv("ASTRA_ALLOWED_EMAILS", "").split(",")
    if entry.strip()
}


import auth_server
from core.llm import OLLAMA_BASE_URL, OLLAMA_MODEL, installed_models
from core.progress import ProgressTracker, format_eta
from core.rag_engine import ask_question
from core.transcriber import WHISPER_MODEL
from main import print_progress, run_pipeline
from utils.audio_processor import cleanup_files
from utils.superbase_client import create_supabase_client

st.set_page_config(
    page_title="Astra — Never Lose the Thread.",
    page_icon="A",
    layout="wide",
    initial_sidebar_state="expanded",
)

boot_label = "Signing you out" if st.session_state.get("pending_redirect") else "Opening your workspace"
boot_placeholder = st.empty()
boot_placeholder.markdown(
    f"""
    <style>
    .astra-boot {{
        position: fixed; inset: 0; z-index: 999;
        display: flex; align-items: center; justify-content: center;
        background: #e9ebee;
    }}
    .astra-boot-card {{ width: min(420px, calc(100% - 3rem)); }}
    .astra-boot-bar {{ height: 2px; background: #7c2f39; margin-bottom: 1.4rem; }}
    .astra-boot-label {{
        color: #6b7684; font-family: 'IBM Plex Mono', ui-monospace, monospace;
        font-size: 0.68rem; letter-spacing: 0.12em; text-transform: uppercase;
    }}
    .astra-boot-line {{
        height: 0.9rem; margin-top: 1rem;
        background: linear-gradient(90deg, #d2d7de 25%, #fdfdfc 50%, #d2d7de 75%);
        background-size: 200% 100%;
        animation: astra-boot-shimmer 1.3s ease-in-out infinite;
    }}
    .astra-boot-line.short {{ width: 36%; }}
    .astra-boot-line.medium {{ width: 64%; }}
    .astra-boot-line.long {{ width: 88%; }}
    @keyframes astra-boot-shimmer {{
        from {{ background-position: 200% 0; }}
        to {{ background-position: -200% 0; }}
    }}
    @media (prefers-reduced-motion: reduce) {{ .astra-boot-line {{ animation: none; }} }}
    </style>
    <div class="astra-boot">
        <div class="astra-boot-card">
            <div class="astra-boot-bar"></div>
            <div class="astra-boot-label">{boot_label}</div>
            <div class="astra-boot-line short"></div>
            <div class="astra-boot-line long"></div>
            <div class="astra-boot-line medium"></div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


def redirect(url: str) -> None:
    components.html(
        f"<script>window.top.location.replace({json.dumps(url)});</script>",
        height=0,
    )


def get_supabase():
    client = st.session_state.get("supabase")
    if client is None:
        client = create_supabase_client()
        st.session_state.supabase = client
    return client


def restore_auth_session() -> bool:
    access_token = st.query_params.get("access_token")
    refresh_token = st.query_params.get("refresh_token")
    if not access_token or not refresh_token:
        return False

    try:
        auth_response = get_supabase().auth.set_session(access_token, refresh_token)
    except Exception as error:
        st.session_state.auth_error = str(error)
        st.query_params.clear()
        return False

    if not auth_response.user:
        st.session_state.auth_error = "Supabase did not return a user for this session."
        st.query_params.clear()
        return False

    st.session_state.user = auth_response.user
    st.session_state.session = auth_response.session
    st.query_params.clear()
    return True


def enforce_allowlist() -> None:
    if not ALLOWED_EMAILS:
        return
    if current_user_email().lower() in ALLOWED_EMAILS:
        return

    boot_placeholder.empty()
    st.error("This account is not on the allowlist for this Astra instance.")
    st.link_button("Sign in with another account", auth_server.LOGOUT_URL)
    st.stop()


def require_authentication() -> None:
    pending = st.session_state.pop("pending_redirect", None)
    if pending:
        redirect(pending)
        st.stop()

    if st.session_state.get("user"):
        enforce_allowlist()
        return

    if restore_auth_session():
        st.rerun()

    error = st.session_state.pop("auth_error", None)
    if error:
        boot_placeholder.empty()
        st.error(f"Authentication could not be completed: {error}")
        st.link_button("Back to sign in", auth_server.LOGIN_URL)
        st.stop()

    redirect(auth_server.LOGIN_URL)
    st.stop()


def sign_out() -> None:
    client = st.session_state.get("supabase")
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    st.session_state.clear()
    st.session_state.pending_redirect = auth_server.LOGOUT_URL
    st.rerun()


def current_user_email() -> str:
    user = st.session_state.get("user")
    return getattr(user, "email", None) or "Signed in"


demo_mode = st.query_params.get("demo") == "1"

if not demo_mode:
    require_authentication()

boot_placeholder.empty()

STYLES = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Instrument+Sans:wght@400;500;600;700&display=swap');

:root {
    --ink: #161a20;
    --ink-soft: #39424e;
    --slate: #6b7684;
    --paper: #e9ebee;
    --panel: #fdfdfc;
    --line: #d2d7de;
    --line-soft: #e3e7eb;
    --signal: #7c2f39;
    --signal-deep: #5d222a;
    --signal-tint: #f1e7e8;
    --ok: #2f6b4f;
}

html, body, [data-testid="stAppViewContainer"], .stApp {
    background: var(--paper);
    background-image:
        radial-gradient(ellipse 52% 18% at 12% 9%, rgba(255, 255, 255, 0.66), transparent 72%),
        radial-gradient(ellipse 58% 22% at 88% 88%, rgba(255, 255, 255, 0.58), transparent 72%),
        radial-gradient(ellipse 35% 13% at 76% 17%, rgba(255, 255, 255, 0.35), transparent 70%),
        radial-gradient(ellipse at 86% 4%, rgba(124, 47, 57, 0.035), transparent 42%);
    color: var(--ink);
    font-family: 'Instrument Sans', system-ui, -apple-system, sans-serif;
}

header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

.astra-boot { display: none !important; }

.block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1320px; }

h1, h2, h3, h4 {
    font-family: 'Instrument Sans', sans-serif;
    color: var(--ink);
    letter-spacing: -0.02em;
    font-weight: 600;
}
p, li, label, .stMarkdown { color: var(--ink-soft); }

/* ---------- utility type ---------- */
.mono {
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--slate);
}

/* ---------- masthead ---------- */
.masthead { padding: 0 0 1.1rem; }
.masthead .kicker { display: flex; align-items: center; gap: 0.55rem; margin-bottom: 1.4rem; }
.masthead .kicker::before {
    content: ""; width: 9px; height: 9px; background: var(--signal); display: inline-block;
}
.masthead h1 {
    font-size: clamp(2.1rem, 4.4vw, 3.35rem);
    line-height: 1.03;
    margin: 0;
    max-width: 18ch;
    font-weight: 600;
}
.masthead p {
    color: var(--slate);
    font-size: 1.02rem;
    line-height: 1.6;
    max-width: 56ch;
    margin: 1rem 0 0;
}

/* signature: a timeline ruler, ticks every 8px, tall tick every 40px */
.ruler {
    height: 26px;
    margin: 1.6rem 0 1.9rem;
    border-bottom: 1px solid var(--line);
    background-image:
        repeating-linear-gradient(90deg, var(--line) 0 1px, transparent 1px 40px),
        repeating-linear-gradient(90deg, var(--line-soft) 0 1px, transparent 1px 8px);
    background-size: 100% 14px, 100% 7px;
    background-position: left bottom, left bottom;
    background-repeat: repeat-x;
    position: relative;
}
.ruler::after {
    content: ""; position: absolute; left: 0; bottom: 0; width: 2px; height: 22px; background: var(--signal);
}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { background: var(--panel); border-right: 1px solid var(--line); }
[data-testid="stSidebar"] .block-container { padding-top: 2rem; }
[data-testid="stSidebar"] h2 { font-size: 1.05rem; margin-bottom: 0.2rem; }
[data-testid="stSidebar"] hr { border-color: var(--line-soft); margin: 1.4rem 0; }

/* ---------- record header ---------- */
.record { border-top: 2px solid var(--ink); padding-top: 0.9rem; margin-bottom: 1.4rem; }
.record h2 { font-size: 1.75rem; line-height: 1.15; margin: 0.5rem 0 0.75rem; }
.slug { font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; color: var(--slate); letter-spacing: 0.06em; }
.slug b { color: var(--signal); font-weight: 500; }

/* ---------- metrics ---------- */
[data-testid="stMetric"] {
    background: var(--panel);
    border: 1px solid var(--line);
    padding: 0.85rem 1rem 0.9rem;
}
[data-testid="stMetricLabel"] p {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.66rem !important;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--slate);
}
[data-testid="stMetricValue"] {
    font-family: 'Instrument Sans', sans-serif;
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--ink);
}

/* ---------- tabs ---------- */
.stTabs [data-baseweb="tab-list"] { gap: 0; border-bottom: 1px solid var(--line); background: transparent; }
.stTabs [data-baseweb="tab"] {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--slate);
    padding: 0.7rem 1.05rem;
    background: transparent;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--ink); }
.stTabs [aria-selected="true"] { color: var(--ink); box-shadow: inset 0 -2px 0 var(--signal); }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { background: transparent; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 1.3rem; }

/* ---------- controls ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: 2px;
    font-family: 'Instrument Sans', sans-serif;
    font-weight: 500;
    letter-spacing: 0.01em;
    border: 1px solid var(--line);
    background: var(--panel);
    color: var(--ink);
    transition: background 120ms ease, border-color 120ms ease;
}
.stButton > button:hover, .stDownloadButton > button:hover { border-color: var(--ink); color: var(--ink); background: #fff; }
.stFormSubmitButton > button, .stButton > button[kind="primary"] {
    background: var(--signal) !important; border-color: var(--signal) !important; color: #fff !important; font-weight: 600;
}
.stFormSubmitButton > button:hover, .stButton > button[kind="primary"]:hover {
    background: var(--signal-deep) !important; border-color: var(--signal-deep) !important; color: #fff !important;
}
[data-testid="stFormSubmitButton"] button,
[data-testid="stBaseButton-primary"] {
    background: var(--signal) !important;
    border-color: var(--signal) !important;
    color: #fff !important;
}
[data-testid="stFormSubmitButton"] button:hover,
[data-testid="stBaseButton-primary"]:hover {
    background: var(--signal-deep) !important;
    border-color: var(--signal-deep) !important;
    color: #fff !important;
}
[data-testid="stFormSubmitButton"] button,
[data-testid="stFormSubmitButton"] button *,
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primary"] * {
    color: #fff !important;
}
.st-key-sign_out_button button {
    background: var(--signal) !important;
    border-color: var(--signal) !important;
    color: #fff !important;
    font-weight: 600;
}
.st-key-sign_out_button button:hover {
    background: var(--signal-deep) !important;
    border-color: var(--signal-deep) !important;
    color: #fff !important;
}
.st-key-sign_out_button button,
.st-key-sign_out_button button * {
    color: #fff !important;
}
.stTextInput input, .stTextArea textarea, [data-baseweb="select"] > div {
    border-radius: 2px !important;
    border-color: var(--line) !important;
    background: var(--panel) !important;
    font-family: 'Instrument Sans', sans-serif;
}
.stTextInput input:focus, [data-baseweb="select"] > div:focus-within { border-color: var(--signal) !important; box-shadow: none !important; }
[data-testid="stSidebar"] [data-testid="stTextInput"] { margin-bottom: 0.75rem; }
[data-testid="stSidebar"] [data-testid="stTextInput"] input {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
[data-testid="stSidebar"] [data-testid="InputInstructions"] {
    position: static !important;
    height: auto !important;
    min-height: 1.1rem;
    margin-top: 0.35rem;
    overflow: visible !important;
    line-height: 1.3 !important;
}
[data-testid="stSidebar"] [data-testid="InputInstructions"] p {
    margin: 0;
    white-space: normal;
}
[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] { margin-top: 0.9rem; }
[data-testid="stFileUploaderDropzone"] {
    background: #f6f7f8; border: 1px dashed var(--line); border-radius: 2px;
}
[data-testid="stFileUploaderDropzone"] button { border-radius: 2px; }
[data-testid="stWidgetLabel"] p {
    font-family: 'IBM Plex Mono', monospace; font-size: 0.66rem !important;
    letter-spacing: 0.1em; text-transform: uppercase; color: var(--slate);
}

/* ---------- status rows ---------- */
.status { display: flex; align-items: flex-start; gap: 0.6rem; padding: 0.5rem 0; border-bottom: 1px solid var(--line-soft); }
.status:last-child { border-bottom: none; }
.status .dot { width: 7px; height: 7px; margin-top: 0.42rem; flex: 0 0 7px; }
.status .dot.on { background: var(--ok); }
.status .dot.off { background: var(--signal); }
.status .txt { font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; line-height: 1.5; color: var(--ink-soft); }
.status .txt span { display: block; color: var(--slate); font-size: 0.68rem; margin-top: 0.15rem; }

/* ---------- transcript ---------- */
.stTextArea textarea {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.8rem !important;
    line-height: 1.85 !important;
    color: var(--ink-soft) !important;
}

/* ---------- chat ---------- */
.panel-head { border-top: 2px solid var(--ink); padding-top: 0.9rem; margin-bottom: 0.9rem; }
.panel-head h3 { font-size: 1.05rem; margin: 0.45rem 0 0.35rem; }
.panel-head p { color: var(--slate); font-size: 0.85rem; margin: 0; }
[data-testid="stChatMessage"] {
    background: transparent;
    padding: 0.7rem 0;
    gap: 0.65rem;
    border-bottom: 1px solid var(--line-soft);
}
[data-testid="stChatMessage"]:last-of-type { border-bottom: none; }
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] {
    width: 1.8rem !important;
    height: 1.8rem !important;
    min-width: 1.8rem !important;
    border-radius: 50% !important;
}
[data-testid="stChatMessageAvatarUser"] svg,
[data-testid="stChatMessageAvatarAssistant"] svg {
    width: 1rem !important;
    height: 1rem !important;
}
[data-testid="stChatMessageContent"] {
    max-width: 42rem;
    color: var(--ink-soft);
    font-size: 0.92rem;
    line-height: 1.6;
}
[data-testid="stChatMessageContent"] p { margin: 0; }
[data-testid="stChatInput"] {
    margin-top: 1rem;
    border-radius: 2px;
    border-color: var(--line);
    background: var(--panel);
}
[data-testid="stChatInput"] textarea {
    font-family: 'Instrument Sans', sans-serif;
    font-size: 0.92rem;
}
.prompts { list-style: none; padding: 0; margin: 1.1rem 0 0; }
.prompts li {
    font-family: 'IBM Plex Mono', monospace; font-size: 0.74rem; color: var(--slate);
    padding: 0.5rem 0 0.5rem 1.1rem; border-top: 1px solid var(--line-soft); position: relative;
}
.prompts li::before { content: "?"; position: absolute; left: 0; color: var(--signal); }

/* ---------- empty state ---------- */
.empty { border: 1px solid var(--line); background: var(--panel); padding: 2.4rem 2rem; max-width: 640px; }
.empty h3 { margin: 0.6rem 0 0.5rem; font-size: 1.3rem; }
.empty p { color: var(--slate); margin: 0; line-height: 1.65; }

/* ---------- workspace header ---------- */
.workspace-head { padding: 0 0 0.9rem; margin-bottom: 1.4rem; border-bottom: 1px solid var(--line); }
.workspace-head .kicker { display: flex; align-items: center; gap: 0.55rem; margin: 0; }
.workspace-head .kicker::before {
    content: ""; width: 9px; height: 9px; background: var(--signal); display: inline-block;
}

@media (max-width: 640px) {
    .masthead h1 { font-size: 2rem; }
    .block-container { padding-top: 1.4rem; }
}
@media (prefers-reduced-motion: reduce) {
    * { transition: none !important; animation: none !important; }
}
</style>
"""

st.markdown(STYLES, unsafe_allow_html=True)

BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+")


def count_items(text: str) -> int:
    if not text:
        return 0
    return sum(1 for line in text.splitlines() if BULLET.match(line))


def reading_minutes(word_count: int) -> int:
    return max(1, round(word_count / 180))


def reset_workspace() -> None:
    st.session_state.pop("result", None)
    st.session_state.pop("messages", None)
    st.rerun()


def save_upload(uploaded_file) -> str:
    upload_dir = ROOT / "downloads"
    upload_dir.mkdir(exist_ok=True)
    suffix = Path(uploaded_file.name).suffix or ".audio"
    target = upload_dir / f"streamlit_upload_{uuid.uuid4().hex}{suffix}"
    target.write_bytes(uploaded_file.getbuffer())
    return str(target)


@st.cache_data(ttl=15, show_spinner=False)
def ollama_models() -> list:
    return installed_models()


def status_row(label: str, detail: str, ok: bool) -> str:
    state = "on" if ok else "off"
    return (
        f'<div class="status"><div class="dot {state}"></div>'
        f'<div class="txt">{label}<span>{detail}</span></div></div>'
    )


def render_analysis(result: dict) -> None:
    title = result.get("title") or "Untitled meeting"
    transcript = result.get("transcript", "")
    action_items = result.get("action_items", "")
    decisions = result.get("key_decisions", "")
    words = len(transcript.split())
    language = st.session_state.get("language", "english")
    source = st.session_state.get("source_label", "Recording")

    st.markdown(
        f'<div class="record">'
        f'<div class="slug"><b>REC</b> &nbsp;·&nbsp; {html.escape(source)} '
        f"&nbsp;·&nbsp; {html.escape(language.upper())}</div>"
        f"<h2>{html.escape(title)}</h2></div>",
        unsafe_allow_html=True,
    )

    columns = st.columns(3)
    columns[0].metric("Transcript words", f"{words:,}")
    columns[1].metric("Read time", f"{reading_minutes(words)} min")
    columns[2].metric("Action items", count_items(action_items) or "—")

    tabs = st.tabs(["Summary", "Actions", "Decisions", "Questions", "Transcript"])
    with tabs[0]:
        st.markdown(result.get("summary") or "No summary was produced for this recording.")
    with tabs[1]:
        st.markdown(action_items or "No action items were assigned in this meeting.")
    with tabs[2]:
        st.markdown(decisions or "Nothing was decided on the record.")
    with tabs[3]:
        st.markdown(result.get("open_questions") or "No questions were left open.")
    with tabs[4]:
        st.text_area("Transcript", transcript, height=460, label_visibility="collapsed")
        st.download_button(
            "Download transcript",
            data=transcript,
            file_name="astra_transcript.txt",
            mime="text/plain",
            use_container_width=True,
        )


def load_sample_meeting() -> dict:
    return json.loads(SAMPLE_MEETING_PATH.read_text(encoding="utf-8"))


def render_chat(locked: bool = False) -> None:
    st.markdown(
        '<div class="panel-head"><div class="mono">Follow up</div>'
        "<h3>Ask about this meeting</h3>"
        "<p>Every answer is drawn from the transcript above.</p></div>",
        unsafe_allow_html=True,
    )

    if locked:
        st.markdown(
            '<ul class="prompts">'
            "<li>What did we agree to ship first?</li>"
            "<li>Who owns the follow-ups, and by when?</li>"
            "<li>What was left unresolved?</li>"
            "</ul>",
            unsafe_allow_html=True,
        )
        st.link_button(
            "Sign in to ask questions",
            auth_server.LOGIN_URL,
            type="primary",
            use_container_width=True,
        )
        return

    rag_chain = st.session_state.get("result", {}).get("rag_chain")
    if rag_chain is None:
        st.info("The follow-up assistant is unavailable for this transcript.")
        return

    messages = st.session_state.setdefault("messages", [])
    if not messages:
        st.markdown(
            '<ul class="prompts">'
            "<li>What did we agree to ship first?</li>"
            "<li>Who owns the follow-ups, and by when?</li>"
            "<li>What was left unresolved?</li>"
            "</ul>",
            unsafe_allow_html=True,
        )

    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Ask a question about the meeting")
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Thinking through the transcript..."):
                try:
                    answer = ask_question(rag_chain, question)
                except Exception as error:
                    st.error(f"That question could not be answered: {error}")
                    return
            st.markdown(answer)
        messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": answer})


MASTHEAD = (
    '<div class="masthead">'
    '<div class="kicker mono">Astra — Never Lose the Thread.</div>'
    "<h1>Read the meeting in two minutes.</h1>"
    "<p>Bring a recording or a YouTube link. Astra writes the transcript, pulls out the decisions "
    "and the action items, and then answers whatever you still need to know.</p>"
    "</div>"
    '<div class="ruler"></div>'
)

WORKSPACE_HEAD = (
    '<div class="workspace-head">'
    '<div class="kicker mono">Astra — Never Lose the Thread.</div>'
    "</div>"
)


@st.dialog("Sign out of Astra?")
def confirm_sign_out():
    st.write("Your workspace will be cleared and you will return to the sign-in page.")
    confirm, cancel = st.columns(2)
    if confirm.button("Sign out", type="primary", use_container_width=True):
        sign_out()
    if cancel.button("Stay signed in", use_container_width=True):
        st.rerun()


submitted = False
source_mode = "Upload file"
uploaded_file = None
source_url = ""
language = "english"

if demo_mode:
    with st.sidebar:
        st.markdown('<div class="mono">Sample meeting</div>', unsafe_allow_html=True)
        st.markdown("## You are viewing a demo")
        st.markdown(
            "This is a saved meeting record so you can see the output without signing up. "
            "Transcription, analysis, and the follow-up assistant all run locally on the "
            "machine hosting Astra."
        )
        st.link_button(
            "Sign in to run your own",
            auth_server.LOGIN_URL,
            type="primary",
            use_container_width=True,
        )
        st.link_button("Create an account", auth_server.SIGNUP_URL, use_container_width=True)

    sample = load_sample_meeting()
    st.session_state.language = sample.get("language", "english")
    st.session_state.source_label = sample.get("source_label", "Sample recording")

    st.markdown(WORKSPACE_HEAD, unsafe_allow_html=True)
    left_column, right_column = st.columns([1.45, 1], gap="large")
    with left_column:
        render_analysis(sample)
    with right_column:
        render_chat(locked=True)
    st.stop()

with st.sidebar:
    st.markdown('<div class="mono">Step 01</div>', unsafe_allow_html=True)
    st.markdown("## New meeting")
    source_mode = st.radio("Source", ["Upload file", "YouTube URL"], horizontal=True)
    language = st.selectbox("Transcription language", ["english", "hinglish"])

    with st.form("meeting_form"):
        uploaded_file = None
        source_url = ""
        if source_mode == "Upload file":
            uploaded_file = st.file_uploader(
                "Recording",
                type=["wav", "mp3", "m4a", "mp4", "webm", "ogg", "flac"],
                help="FFmpeg is required for anything other than WAV.",
            )
        else:
            source_url = st.text_input("YouTube URL", placeholder="")
        submitted = st.form_submit_button(
            "Transcribe meeting", type="primary", use_container_width=True
        )

    if st.session_state.get("result") and st.button("Start another meeting", use_container_width=True):
        reset_workspace()

    st.markdown("---")
    st.markdown('<div class="mono">Environment</div>', unsafe_allow_html=True)

    models = ollama_models()
    reachable = bool(models)
    model_ready = any(name.startswith(OLLAMA_MODEL.split(":")[0]) for name in models)
    has_ffmpeg = which("ffmpeg") is not None

    rows = [
        status_row(
            "Ollama running" if reachable else "Ollama unreachable",
            f"Serving at {OLLAMA_BASE_URL}" if reachable else f"Start it with 'ollama serve' at {OLLAMA_BASE_URL}",
            reachable,
        ),
        status_row(
            f"Model {OLLAMA_MODEL}" if model_ready else f"Model {OLLAMA_MODEL} missing",
            "Pulled and ready" if model_ready else f"Run 'ollama pull {OLLAMA_MODEL}'",
            model_ready,
        ),
        status_row(
            "FFmpeg" if has_ffmpeg else "FFmpeg missing",
            "Found on PATH" if has_ffmpeg else "Needed for anything other than WAV",
            has_ffmpeg,
        ),
        status_row(
            f"Whisper {WHISPER_MODEL}",
            "Transcription runs locally on this machine",
            True,
        ),
    ]
    st.markdown("".join(rows), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(
        f'<div class="mono">Signed in</div>'
        f'<div class="slug">{html.escape(current_user_email())}</div>',
        unsafe_allow_html=True,
    )
    if st.button("Sign out", key="sign_out_button", use_container_width=True):
        confirm_sign_out()

if submitted:
    if source_mode == "Upload file" and uploaded_file is None:
        st.sidebar.error("Pick an audio or video file to continue.")
    elif source_mode == "YouTube URL" and not source_url.strip():
        st.sidebar.error("Paste a YouTube URL to continue.")
    else:
        source = save_upload(uploaded_file) if uploaded_file else source_url.strip()
        st.session_state.language = language
        st.session_state.source_label = uploaded_file.name if uploaded_file else "YouTube"
        st.session_state.pop("messages", None)
        tracker = ProgressTracker(skip_download=uploaded_file is not None)

        def update_pipeline_progress(progress: dict) -> None:
            print_progress(progress)
            reading = tracker.update(progress)
            if reading is None:
                return

            fraction, label, eta = reading
            detail = tracker.detail(progress)
            headline = f"{label} · {detail}" if detail else label

            status.update(label=headline, expanded=True)
            pipeline_progress.progress(
                fraction,
                text=f"{headline} — {round(fraction * 100)}% · {format_eta(eta)}",
            )

        with st.status("Building your meeting record...", expanded=True) as status:
            pipeline_progress = st.progress(0.0, text="Starting meeting pipeline...")
            try:
                result = run_pipeline(source, language, progress_callback=update_pipeline_progress)
                st.session_state.result = result
                pipeline_progress.progress(1.0, text="Meeting record ready")
                status.update(label="Meeting record ready", state="complete", expanded=False)
            except Exception as error:
                status.update(label="Transcription stopped", state="error", expanded=True)
                st.error(str(error))
                st.info(
                    "Check that Ollama is running and FFmpeg is installed. "
                    "The terminal log has the full traceback."
                )
            finally:
                if uploaded_file:
                    cleanup_files([source])

if st.session_state.get("result"):
    st.markdown(WORKSPACE_HEAD, unsafe_allow_html=True)
    left_column, right_column = st.columns([1.45, 1], gap="large")
    with left_column:
        render_analysis(st.session_state.result)
    with right_column:
        render_chat()
else:
    st.markdown(MASTHEAD, unsafe_allow_html=True)
    st.markdown(
        '<div class="empty"><div class="mono">No meeting loaded</div>'
        "<h3>Start with a recording or a link.</h3>"
        "<p>Choose a source in the left panel and run it. The brief, the full transcript, "
        "and the follow-up assistant all appear here.</p></div>",
        unsafe_allow_html=True,
    )