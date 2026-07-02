from . import database
from .filter import client, MODEL

SYSTEM = """You are the BIT Capital Signal Desk assistant. Answer ONLY from the CONTEXT below —
scored Polymarket signals and the latest daily brief.
- Be specific: cite relevance scores, tickers, implied probabilities and volumes where they help.
- If the answer isn't in the context, say so plainly. Never invent markets, numbers, or holdings.
- Analyst tone: tight, concrete, no filler."""


def _retrieve(question: str, k: int = 120) -> str:
    """Rank stored signals by keyword overlap with the question, then conviction. Context-stuff the top k.
    ponytail: keyword rank, not embeddings — corpus is a few hundred rows. Swap to pgvector if it grows past ~5k."""
    db = database.get_client()
    sigs = database.get_signals(min_score=1)  # deduped, expired dropped — same clean path as the dashboard
    terms = {w for w in question.lower().split() if len(w) > 3}

    def rank(s):
        m = s.get("markets") or {}
        blob = " ".join([m.get("question", ""), s.get("sector") or "",
                         " ".join(s.get("affected_tickers") or []), s.get("reasoning") or ""]).lower()
        return (sum(t in blob for t in terms), s["relevance_score"])

    top = sorted(sigs, key=rank, reverse=True)[:k]
    lines = []
    for s in top:
        m = s.get("markets") or {}
        lines.append(
            f"- [{s['relevance_score']}/10 · {s.get('sector') or '—'} · "
            f"{','.join(s.get('affected_tickers') or []) or 'no ticker'}] {m.get('question','')} "
            f"(prob {m.get('probability')}, vol ${m.get('volume_usd'):,.0f}): {s.get('reasoning','')}"
        )
    rep = db.table("reports").select("content").order("report_date", desc=True).limit(1).execute().data
    brief = rep[0]["content"] if rep else "(no brief yet)"
    return "SIGNALS:\n" + "\n".join(lines) + f"\n\nLATEST DAILY BRIEF:\n{brief}"


def answer(question: str, history: list[dict] | None = None) -> str:
    msgs = [{"role": "system", "content": SYSTEM + "\n\nCONTEXT:\n" + _retrieve(question)}]
    msgs += history or []
    msgs.append({"role": "user", "content": question})
    return client.chat.completions.create(model=MODEL, messages=msgs).choices[0].message.content


if __name__ == "__main__":
    a = answer("Which Bitcoin markets matter for IREN and how bullish are they?")
    assert a and len(a) > 20, a
    print(a)
