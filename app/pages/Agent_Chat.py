# app/pages/Agent_Chat.py
import os, sys

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)  # load .env regardless of cwd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as st

# ---------------- LLM wrapper (no tools, chat only) ----------------
SYSTEM_PROMPT = (
    "You are a helpful investment research chatbot. "
    "Answer clearly and professionally. Do NOT give financial advice or make buy/sell recommendations. "
    "If the user asks for advice, provide information and risks instead."
)

class ChatLLM:
    def __init__(self):
        self.backend = "offline"
        self.model = "offline"
        self.client = None
        self.init_error = None

        be   = (os.getenv("LLM_BACKEND") or "").lower()
        gkey = os.getenv("GOOGLE_API_KEY")
        okey = os.getenv("OPENAI_API_KEY")

        # -------- GEMINI: auto-detect best model for THIS key ----------
        if (be == "gemini" or (be == "" and gkey and not okey)) and gkey:
            try:
                import google.generativeai as genai
                genai.configure(api_key=gkey)

                # 1) Optional user override (if set in .env) gets first try
                override = (os.getenv("GEMINI_MODEL") or "").strip()
                candidates = []
                if override:
                    candidates.append(override)

                # 2) Ask API what models this key can use, prefer 1.5/pro/flash (descending)
                try:
                    models = list(genai.list_models())
                except Exception as e:
                    models = []
                    self.init_error = f"list_models failed: {e!r}"

                usable = [
                    m.name for m in models
                    if "generateContent" in getattr(m, "supported_generation_methods", [])
                ]

                def rank(name: str) -> tuple:
                    # Lower tuple sorts earlier (better)
                    is_15   = "1.5"  in name
                    is_pro  = "pro"  in name
                    is_flash= "flash" in name
                    # prefer 1.5 + pro, then 1.5 + flash, then pro, then flash, then others
                    return (
                        0 if is_15 else 1,
                        0 if is_pro else (1 if is_flash else 2),
                        name,  # tie-breaker stable
                    )

                usable_sorted = sorted(usable, key=rank)
                # Only add to candidates if not already overridden
                for mid in usable_sorted:
                    if mid not in candidates:
                        candidates.append(mid)

                # 3) Final safety fallbacks if list_models gave nothing
                if not candidates:
                    candidates = [
                        # v1beta legacy text often available on free keys:
                        "models/gemini-pro",
                        # common newer ids (may or may not exist on v1beta):
                        "models/gemini-1.5-flash",
                        "models/gemini-1.5-pro",
                        "gemini-1.5-flash",
                        "gemini-1.5-pro",
                    ]

                chosen, last_err = None, None
                for mid in candidates:
                    try:
                        self.client = genai.GenerativeModel(mid, system_instruction=SYSTEM_PROMPT)
                        chosen = mid
                        break
                    except Exception as e:
                        last_err = e

                if self.client is None:
                    raise last_err or RuntimeError("No supported Gemini model available to this API key.")

                self.backend, self.model = "gemini", chosen

            except Exception as e:
                self.init_error = f"Gemini init failed: {e!r}"

        # -------- OPENAI (optional fallback) ----------
        if self.client is None and ((be == "openai") or (be == "" and okey)):
            try:
                from openai import OpenAI
                self.client = OpenAI()
                self.backend, self.model = "openai", "gpt-4o-mini"
            except Exception as e:
                self.init_error = f"OpenAI init failed: {e!r}"

    def generate(self, messages):
        user_text = messages[-1]["content"]
        if self.backend == "gemini" and self.client is not None:
            try:
                # v1beta-style ids look like "models/…": use generate_content (stateless)
                if str(self.model).startswith("models/"):
                    resp = self.client.generate_content(user_text)
                else:
                    # v1 alias ids (no prefix): chat API is fine
                    resp = self.client.start_chat(history=[]).send_message(user_text)
                return (getattr(resp, "text", None) or "").strip() or "…"
            except Exception as e:
                return f"Gemini call failed: {e!r}"
        if self.backend == "openai" and self.client is not None:
            msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
            resp = self.client.chat.completions.create(model=self.model, temperature=0.2, messages=msgs)
            return resp.choices[0].message.content or "…"
        return (
            "I'm currently running in offline mode (no API key detected or init failed). "
            "Set GOOGLE_API_KEY (LLM_BACKEND=gemini) or OPENAI_API_KEY.\n\n"
            "Your question was:\n" + user_text
        )

# ---------------- UI ----------------
st.set_page_config(page_title="Agent Chat", page_icon="🤖", layout="wide")
st.title("Agent Chat")

# Show backend status
llm = st.session_state.get("llm")
if llm is None:
    llm = ChatLLM()
    st.session_state.llm = llm

# with st.sidebar.expander("LLM status", expanded=True):
#     st.write(f"LLM_BACKEND: **{os.getenv('LLM_BACKEND','(unset)')}**")
#     st.write(f"GOOGLE_API_KEY set: **{bool(os.getenv('GOOGLE_API_KEY'))}**")
#     st.write(f"Active backend: **{llm.backend}**")
#     st.write(f"Model: **{llm.model}**")
#     if getattr(llm, "init_error", None):
#         st.error(llm.init_error)

# Chat history
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hi! Ask me anything about companies, metrics, filings, or market concepts. (Educational only—no financial advice.)"}]

# Render history
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# Input
prompt = st.chat_input("Ask a question (e.g., 'Explain ROA vs ROE', 'What does PE mean?', 'News about AAPL?')")
if prompt:
    # append user
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # build messages for LLM (keep last ~20 for brevity)
    recent = st.session_state.messages[-20:]
    # ensure first message isn't a system role for Gemini path (system already set in model)
    msgs = [m for m in recent if m["role"] in ("user", "assistant")]
    reply = llm.generate(msgs)

    # append assistant
    st.session_state.messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.markdown(reply)
