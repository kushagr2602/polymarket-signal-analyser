"""MCP server exposing the signal database to any MCP client (Claude Desktop, ADK, etc.).

Run:  python3 -m src.mcp_server          (stdio transport)

Claude Desktop config:
  {"mcpServers": {"polymarket-signals": {
      "command": "python3", "args": ["-m", "src.mcp_server"],
      "cwd": "<path to this repo>"}}}

Same three read-only tools the in-app agent uses (src/agent.py) — one
implementation, two front-ends: the internal loop and the open protocol.
"""
from mcp.server.fastmcp import FastMCP

from . import agent

mcp = FastMCP("polymarket-signals")


@mcp.tool()
def query_signals(min_score: int = 5, ticker: str = "", keyword: str = "", limit: int = 15) -> list[dict]:
    """Search LLM-scored prediction-market signals (question, score 0-10, sector,
    tickers, implied probability, volume, reasoning). Filter by min_score,
    ticker (e.g. IREN), or a keyword in the market question."""
    return agent.query_signals(min_score=min_score, ticker=ticker, keyword=keyword, limit=limit)


@mcp.tool()
def portfolio_exposure() -> dict:
    """Per-ticker summary: active signal count and peak relevance score for each watchlist holding."""
    return agent.portfolio_exposure()


@mcp.tool()
def get_latest_brief() -> str:
    """The most recent daily analyst brief (markdown)."""
    return agent.get_latest_brief()


if __name__ == "__main__":
    mcp.run()  # stdio
