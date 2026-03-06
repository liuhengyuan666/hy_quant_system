from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from scheduler.jobs import calc_indicators_job, export_signals_job, generate_signals_job, update_market_job


def start_scheduler() -> None:
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(update_market_job, trigger=CronTrigger(hour=8, minute=30), id="update_market", replace_existing=True)
    scheduler.add_job(calc_indicators_job, trigger=CronTrigger(hour=15, minute=30), id="calc_indicators", replace_existing=True)
    scheduler.add_job(generate_signals_job, trigger=CronTrigger(hour=15, minute=35), id="generate_signals", replace_existing=True)
    scheduler.add_job(export_signals_job, trigger=CronTrigger(hour=15, minute=40), id="export_signals", replace_existing=True)
    scheduler.start()


if __name__ == "__main__":
    start_scheduler()
