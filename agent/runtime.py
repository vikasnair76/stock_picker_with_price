# agent/runtime.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Callable, List, Optional, Tuple
import json, os, re, importlib
from dotenv import load_dotenv
load_dotenv() 

backend = os.getenv("LLM_BACKEND", "(unset)")
google_key = bool(os.getenv("GOOGLE_API_KEY"))
openai_key = bool(os.getenv("OPENAI_API_KEY"))



# ---------- prompts ----------
try:
    from .prompts import SYSTEM_PROMPT
except Exception:
    SYSTEM_PROMPT = (
        "You are an agentic investment research assistant. "
        "You do NOT give financial advice. Prefer calling tools."
    )

ToolFn = Callable[[Dict[str, Any]], Dict[str, Any]]

# ---------- tools registry ----------
def _lazy_import(path: str, name: str) -> ToolFn:
    mod = importlib.import_module(path)
    fn = getattr(mod, name, None)
    if fn is None:
        raise ImportError(f"{name} not found in {path}")
    return fn

def _build_registry() -> Dict[str, ToolFn]:
    return {
        "fetch_prices":   _lazy_import("agent.tools.prices", "fetch_prices"),
        "indicators":     _lazy_import("agent.tools.prices", "compute_indicators"),
        "fundamentals":   _lazy_import("agent.tools.fundamentals", "get_fundamentals"),
        "news":           _lazy_import("agent.tools.news", "get_news"),
        "score_universe": _lazy_import("agent.tools.scoring", "score_universe"),
        # "backtest":    _lazy_import("agent.tools.backtest", "run_backtest"),
    }

# ---------- LLM backends ----------
@dataclass
class AgentMessage:
    role: str
    content: str
    tool_name: str = ""
    tool_args: Optional[Dict[str, Any]] = None

TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,5})?\b")

def extract_tickers(text: str) -> List[str]:
    if not text:
        return []
    seen, out = set(), []
    for m in TICKER_RE.findall(text.upper()):
        if m not in seen:
            seen.add(m); out.append(m)
    return out

def infer_suffix(tickers: List[str]) -> Optional[str]:
    return ".NS" if any(t.endswith(".NS") for t in tickers) else None

class _LLM:
    """Small wrapper that can be OpenAI, Gemini, or None (offline)."""
    def __init__(self):
        self.backend = os.getenv("LLM_BACKEND", "").lower()
        self.model_name = "offline"
        self.client = None

        if self.backend == "gemini" and os.getenv("GOOGLE_API_KEY"):
            try:
                import google.generativeai as genai
                genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
                self.client = genai.GenerativeModel("gemini-1.5-pro", system_instruction=SYSTEM_PROMPT)
                self.model_name = "gemini-1.5-pro"
                return
            except Exception:
                # fall through to try OpenAI or offline
                pass

        if os.getenv("OPENAI_API_KEY"):
            try:
                from openai import OpenAI
                self.client = OpenAI()
                self.backend = "openai"
                self.model_name = "gpt-4o-mini"
                return
            except Exception:
                pass

        # offline
        self.backend = "offline"

    def generate(self, messages: List[Dict[str, str]]) -> str:
        if self.backend == "gemini" and self.client is not None:
            chat = self.client.start_chat(history=[])
            # send the last user message (Gemini chat can be simple)
            text = messages[-1]["content"]
            resp = chat.send_message(text)
            return resp.text or ""
        if self.backend == "openai" and self.client is not None:
            resp = self.client.chat.completions.create(
                model=self.model_name, temperature=0.2, messages=messages
            )
            return resp.choices[0].message.content or ""
        # OFFLINE: produce a minimal plan without hardcoded tickers
        user_text = messages[-1]["content"]
        user_tickers = extract_tickers(user_text)
        if user_tickers:
            return (
                "I will rank the provided universe with `score_universe` and summarize.\n"
                f"```tool:score_universe {{\"tickers\": {json.dumps(user_tickers)} }}```"
            )
        return (
            "Please provide a list of tickers (e.g., 'AAPL, MSFT, NVDA, TSLA') "
            "or a market/sector so I can propose a concrete list. "
            "I will then call `score_universe`."
        )

# ---------- Agent ----------
class Agent:
    def __init__(self, system_prompt: str = SYSTEM_PROMPT):
        self.history: List[AgentMessage] = [AgentMessage("system", system_prompt)]
        self.registry: Dict[str, ToolFn] = _build_registry()
        self.llm = _LLM()

    @staticmethod
    def _parse_tool_call(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        m = re.search(r"```tool:(\w+)\s*(\{.*?\})\s*```", text, flags=re.S)
        if not m:
            return None
        name = m.group(1)
        try:
            args = json.loads(m.group(2))
        except Exception:
            args = {}
        return name, args

    def _enforce_user_tickers(self, tool_name: str, args: Dict[str, Any], user_text: str) -> Dict[str, Any]:
        """If user provided symbols, force score_universe to use them; also set suffix."""
        if tool_name != "score_universe":
            return args
        user_tickers = extract_tickers(user_text)
        if user_tickers:
            args = dict(args or {})
            args["tickers"] = user_tickers
            args.setdefault("default_suffix", infer_suffix(user_tickers))
        return args

    def step(self, user_text: str) -> Dict[str, Any]:
        # 1) get model output
        self.history.append(AgentMessage("user", user_text))
        messages = [{"role": m.role, "content": m.content} for m in self.history]
        thought = self.llm.generate(messages)

        # 2) parse and (if needed) enforce user tickers
        tool_call = self._parse_tool_call(thought)
        if tool_call:
            name, args = tool_call
            args = self._enforce_user_tickers(name, args or {}, user_text)
            if name in self.registry:
                try:
                    result = self.registry[name](args)
                except Exception as e:
                    result = {"error": f"Tool `{name}` failed: {e!r}"}
                self.history.append(AgentMessage("tool", json.dumps(result)[:2000], tool_name=name, tool_args=args))
                return {
                    "thought": thought,
                    "tool_name": name,
                    "tool_result": result,
                    "backend": self.llm.model_name,
                }

        # 3) no tool call — just return the model text
        return {"thought": thought, "backend": self.llm.model_name}
