# Deploy — get a stable HTTPS URL (≈10 min, no laptop needed)

The local `streamlit run` + cloudflared tunnel dies whenever the Mac sleeps.
This deploys the dashboard to **Streamlit Community Cloud** (free) with a fixed
HTTPS URL, and runs the scanner on a **GitHub Actions cron** so data stays fresh
without your machine. Everything is code-ready; these steps need *your* logins.

## 1. Push to GitHub
```bash
cd ~/Desktop/Job-Applications/polymarket-signal-analyser
gh repo create polymarket-signal-analyser --private --source=. --push
# or: create the repo on github.com, then:
#   git remote add origin git@github.com:<you>/polymarket-signal-analyser.git
#   git push -u origin main
```
`.env` and `.streamlit/secrets.toml` are gitignored — secrets never leave your machine.

## 2. Deploy the dashboard
1. Go to [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub.
2. **New app** → pick the repo → branch `main` → main file `app.py` → **Deploy**.
3. App → **Settings → Secrets** → paste the three keys (see
   `.streamlit/secrets.toml.example` for the format).
4. It builds and gives you a permanent `https://<name>.streamlit.app` URL.

## 3. Keep data fresh (GitHub Actions)
The scanner can't run inside the Streamlit app (web hosts don't keep background
loops). `.github/workflows/scan.yml` already runs the pipeline every 30 min.
Enable it:
1. Repo → **Settings → Secrets and variables → Actions → New repository secret** —
   add `SUPABASE_URL`, `SUPABASE_KEY`, `OPENAI_API_KEY`.
2. Repo → **Actions** tab → enable workflows. First run: **Run workflow** on `scan`.

That's it — dashboard live 24/7, data refreshing every 30 min, laptop off.

> Local dev still works as before: `streamlit run app.py` + `python -m src.scheduler`.
