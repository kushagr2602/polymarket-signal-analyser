"""MCP server exposing My Financial Scanner to any MCP client (Claude Desktop, Claude Code, etc.).

Run:  python3 -m src.mcp_server          (stdio transport)

Claude Desktop config:
  {"mcpServers": {"financial-scanner": {
      "command": "python3", "args": ["-m", "src.mcp_server"],
      "cwd": "<path to this repo>"}}}

The same read-only tools the in-app agent uses (src/agent.py) — one implementation,
two front-ends. stdio runs on your machine only, so the portfolio tool is included.
"""
from mcp.server.fastmcp import FastMCP

from . import agent

mcp = FastMCP("financial-scanner")


@mcp.tool()
def query_signals(min_score: int = 5, ticker: str = "", keyword: str = "", limit: int = 15, min_impact: int = 0) -> list[dict]:
    """Search LLM-scored prediction-market signals (question, watchlist score 0-10, market impact 0-10,
    sector, tickers, implied probability, volume, reasoning, plain-English angle). Filter by min_score,
    ticker (e.g. NVDA), a keyword in the question, or min_impact=7 for the big market-moving bets."""
    return agent.query_signals(min_score=min_score, ticker=ticker, keyword=keyword, limit=limit, min_impact=min_impact)


@mcp.tool()
def portfolio_exposure() -> dict:
    """Per-ticker summary: active signal count and peak relevance score for each watchlist holding."""
    return agent.portfolio_exposure()


@mcp.tool()
def get_latest_brief() -> str:
    """The most recent daily analyst brief (markdown)."""
    return agent.get_latest_brief()


@mcp.tool()
def screen_instruments(kind: str = "etf", group: str = "", sort: str = "score", query: str = "", limit: int = 10) -> list[dict]:
    """Ranked European-listed ETFs, stocks or funds (kind: etf|stock|fund). Score 0-100 vs same-kind peers,
    with a plain-English why. sort: score|growth|r1y|calm. query: words in name/ticker/theme."""
    return agent.screen_instruments(kind=kind, group=group, sort=sort, query=query, limit=limit)


@mcp.tool()
def get_instrument(ticker: str) -> dict:
    """Full read-out for any Yahoo symbol (e.g. VWCE.DE, ENR.DE, KO): score, returns, risk, worst fall,
    plain-English cards and similar funds. Symbols outside the ranked list are scored against peers."""
    return agent.get_instrument(ticker)


@mcp.tool()
def search_markets(query: str) -> list[dict]:
    """Find stocks/ETFs/funds by company or fund name ("siemens energy", "bit capital") → tickers."""
    return agent.search_markets(query)


@mcp.tool()
def compare_instruments(tickers: list[str]) -> dict:
    """Side-by-side for 2-4 symbols: score, growth, last 12 months, risk, worst fall, and correlation."""
    return agent.compare_instruments(tickers)


@mcp.tool()
def get_my_portfolio() -> dict:
    """The user's own holdings from data/trades.json: weights, gains, overlap and concentration notes."""
    return agent.get_my_portfolio()


if __name__ == "__main__":
    mcp.run()  # stdio
