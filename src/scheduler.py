import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from . import database, polymarket, reports
from .filter import score_market


def ingest():
    """Fetch markets from Polymarket and upsert into the DB."""
    markets = polymarket.fetch_markets()
    n = database.insert_markets(markets)
    print(f"ingest: stored {n} markets")
    return n


def filter_new(limit: int = 300):
    """Score markets that don't have a signal yet."""
    pending = database.get_unfiltered_markets(limit)
    scored = 0
    for m in pending:
        try:
            database.insert_signal(score_market(m))
            scored += 1
        except Exception as e:  # ponytail: skip a bad market, don't kill the batch
            print(f"  skip {m['market_id']}: {e}")
    print(f"filter: scored {scored}/{len(pending)} markets")
    return scored


def pipeline():
    ingest()
    filter_new(40)  # bounded so a 2-min tick finishes; backlog clears over successive ticks


def main():
    if "--once" in sys.argv:
        ingest()
        filter_new(400)  # manual run: big catch-up
        reports.generate_report()
        return

    sched = BlockingScheduler()
    # ponytail: max_instances=1 (default) means a slow run just skips the next tick, no overlap.
    # Hourly is plenty for a daily-brief product; 2-min polling was ~7k Gamma requests/day for nothing.
    sched.add_job(pipeline, "interval", hours=1, next_run_time=datetime.now())
    sched.add_job(reports.generate_report, "cron", hour=23)  # nightly brief
    print("scheduler started: ingest+filter hourly, report nightly. Ctrl-C to stop.")
    sched.start()


if __name__ == "__main__":
    main()
