"""Every LLM call goes through chat() — the one place models are chosen.

Two roles, because the cost profiles differ:
  score  one call per market (hundreds per scan)         → cheap, fast
  smart  agent, daily brief, news read-through, ticker suggestions (a handful of calls) → best judgment

Override any of these in .env:  SCORE_MODEL, SMART_MODEL, SCORE_EFFORT, SMART_EFFORT
(effort = the reasoning-effort setting of the gpt-6 family: none|low|medium|high|xhigh|max).

If the configured model is unknown to your key, or rejects the effort setting, chat() degrades — same model
without effort, then FALLBACK — instead of taking the app down. `python -m src.llm` shows what actually answers.
"""
import os

import openai
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
# None on a keyless checkout (CI / fresh clone) so imports and offline tests still work
client = OpenAI() if os.getenv("OPENAI_API_KEY") else None

FALLBACK = "gpt-4o-mini"
# ponytail: defaults from OpenAI's model docs (gpt-6-luna $0.10/$0.50 per 1M tok, gpt-6.1-sol $2/$10, gpt-6-astra $10/$50).
# Scoring on Sol costs roughly $1 per 300-market rescan; drop SCORE_MODEL to gpt-6-luna for cents. Astra only on the few analyst calls.
ROLES = {
    "score": (os.getenv("SCORE_MODEL", "gpt-6.1-sol"), os.getenv("SCORE_EFFORT", "low")),
    "smart": (os.getenv("SMART_MODEL", "gpt-6-astra"), os.getenv("SMART_EFFORT", "medium")),
}
_ok: dict[str, int] = {}  # role → index of the first attempt that worked, so a bad model isn't retried every call


def _attempts(role: str) -> list[tuple[str, str]]:
    model, effort = ROLES[role]
    seen, out = set(), []
    for a in ((model, effort), (model, ""), (FALLBACK, "")):
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def active(role: str) -> str:
    """The model currently answering for this role (the configured one until a call has had to degrade)."""
    att = _attempts(role)
    return att[min(_ok.get(role, 0), len(att) - 1)][0]


def chat(role: str, **kw):
    """client.chat.completions.create with the role's model; kw = messages, tools, response_format, ..."""
    att, last = _attempts(role), None
    for i in range(_ok.get(role, 0), len(att)):
        model, effort = att[i]
        try:
            r = client.chat.completions.create(model=model, **({"reasoning_effort": effort} if effort else {}), **kw)
            _ok[role] = i
            return r
        except (openai.NotFoundError, openai.PermissionDeniedError, openai.BadRequestError) as e:
            last = e  # unknown model / no access / unsupported parameter → try the next, safer attempt
    raise last


if __name__ == "__main__":
    # Offline: the attempt ladder never repeats itself and always ends on the fallback.
    for role in ROLES:
        att = _attempts(role)
        assert att[-1] == (FALLBACK, "") and len(att) == len(set(att)), att
    if client is None:
        print("no OPENAI_API_KEY — offline checks passed, skipping the live check")
    else:
        for role, (model, effort) in ROLES.items():
            r = chat(role, messages=[{"role": "user", "content": 'Reply with JSON {"ok": true}.'}],
                     response_format={"type": "json_object"})
            note = "" if active(role) == model else f"  ← configured {model} was refused, using the fallback"
            print(f"{role:5} configured {model} (effort {effort or '-'}) → answered by {r.model}{note}")
