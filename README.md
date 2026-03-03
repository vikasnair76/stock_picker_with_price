## Agentic Stock Picker (Educational)

Research assistant + factor screener + chat for stocks, built with Streamlit.
It combines a rules-based screener (momentum/value/quality), quick back-of-the-envelope metrics, and an optional LLM chat (“Agent Chat”) for educational Q&A. Not financial advice.

✨ Features

Screener: rank arbitrary tickers by:

Momentum (126-day total return)

Value (1 / trailing PE)

Quality (ROA)

Optional live price column

Agent Chat (two modes):

Chat-only: a simple Gemini/OpenAI Q&A chatbot with compliance prompt

Agentic (optional): tool-calling runtime (prices, indicators, fundamentals, news, scoring)

NSE/US friendly: supports tickers like TCS.NS, INFY.NS, AAPL, MSFT

No hard-coding: user enters any tickers, UI enforces their choices

LLM backends: Gemini (Google AI Studio) or OpenAI, with robust fallbacks   

Clear disclaimers and reproducible outputs (CSV download, metric cards)

⚠️ This app is for education only. It does not provide investment advice.
