import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from . import config, database, polymarket, reports, views
from .filter import score_market


def ingest():
    """Fetch markets from Polymarket and upsert into the DB."""
    markets = polymarket.fetch_markets(queries=polymarket.topics(config.get_watchlist()))
    n = database.insert_markets(markets)
    print(f"ingest: stored {n} markets")
    return n


SNAPSHOT_EVERY_H = 6  # ~4 rows a day: plenty for weekly trends and day-over-day movers, tiny for a free database


def snapshot():
    """Save sector heat + market odds so the dashboard can show trends. Throttled; never breaks a scan."""
    try:
        recent = database.get_snapshots(days=1)
        if recent and (datetime.now(timezone.utc) - views._ts(recent[-1]["taken_at"])).total_seconds() < SNAPSHOT_EVERY_H * 3600 - 600:
            return
        database.insert_snapshot(views.snapshot(views.to_rows(database.get_signals(min_score=5))))
        print("snapshot: saved")
    except Exception as e:  # most likely the table doesn't exist yet
        print(f"snapshot: skipped ({str(e)[:80]}) — run the snapshots SQL in schema.sql to enable trends")


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


import os
import tempfile

RESCAN_LOCK = os.path.join(tempfile.gettempdir(), "pmsa_rescore.lock")


def rescore(limit: int = 300):
    """Re-score the top markets by volume against the CURRENT watchlist (upsert, overwrites).
    A lockfile prevents overlapping rescans (double-click / double-cost)."""
    open(RESCAN_LOCK, "w").close()
    try:
        ingest()  # refresh prices first
        markets = database._all_rows("markets", "*", order="volume_usd")[:limit]
        scored = 0
        for m in markets:
            try:
                database.upsert_signal(score_market(m))
                scored += 1
            except Exception as e:
                print(f"  skip {m['market_id']}: {e}")
        print(f"rescore: scored {scored}/{len(markets)} against current watchlist")
        reports.generate_report()
        snapshot()
        return scored
    finally:
        try:
            os.remove(RESCAN_LOCK)
        except OSError:
            pass


def pipeline():
    ingest()
    filter_new(40)  # bounded so a 2-min tick finishes; backlog clears over successive ticks
    snapshot()


def main():
    if "--once" in sys.argv:
        ingest()
        filter_new(400)  # manual run: big catch-up
        reports.generate_report()
        snapshot()
        return
    if "--rescore" in sys.argv:
        rescore()
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
