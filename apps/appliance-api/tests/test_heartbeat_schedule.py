import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from appliance import main
from appliance.db import Base

JOB = "bliss-license-heartbeat"


@pytest.fixture
def scheduler(monkeypatch):
    fresh = BackgroundScheduler(daemon=True)
    monkeypatch.setattr(main, "scheduler", fresh)
    monkeypatch.setattr(main.settings, "app_env", "production")
    monkeypatch.setattr(main.settings, "heartbeat_interval_hours", 24)
    yield fresh
    if fresh.running:
        fresh.shutdown(wait=False)


def seconds_until(job):
    return (job.next_run_time - datetime.now(UTC)).total_seconds()


def test_first_heartbeat_is_scheduled_shortly_after_startup(scheduler, monkeypatch):
    monkeypatch.setattr(main.settings, "heartbeat_startup_delay_seconds", 30)
    main.start_heartbeat_scheduler()
    job = scheduler.get_job(JOB)
    assert 20 <= seconds_until(job) <= 31
    assert job.trigger.interval == timedelta(hours=24)


def test_startup_heartbeat_runs_and_then_recurs_on_the_interval(scheduler, monkeypatch):
    ran = threading.Event()
    monkeypatch.setattr(main, "automatic_license_heartbeat", ran.set)
    monkeypatch.setattr(main.settings, "heartbeat_startup_delay_seconds", 0)
    main.start_heartbeat_scheduler()
    assert ran.wait(10), "startup heartbeat did not run"
    remaining = seconds_until(scheduler.get_job(JOB))
    assert timedelta(hours=23, minutes=59).total_seconds() <= remaining <= timedelta(hours=24).total_seconds()


def test_heartbeat_disabled_in_tests_and_when_interval_is_zero(scheduler, monkeypatch):
    monkeypatch.setattr(main.settings, "heartbeat_interval_hours", 0)
    main.start_heartbeat_scheduler()
    assert scheduler.get_job(JOB) is None


def test_unreachable_agent_or_licensing_server_never_raises(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))

    class Unreachable:
        def heartbeat(self, *args):
            raise httpx.ConnectError("license agent or Bliss unreachable")

    monkeypatch.setattr(main, "license_agent", Unreachable)
    main.automatic_license_heartbeat()
    engine.dispose()
