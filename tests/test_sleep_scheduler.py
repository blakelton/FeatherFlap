from datetime import datetime

from featherflap.runtime.sleep import SleepScheduler


def make_dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2024, 1, 1, hour=hour, minute=minute)


def test_sleep_scheduler_daytime_window() -> None:
    scheduler = SleepScheduler([{ "start": "09:00", "end": "11:00" }])
    assert scheduler.is_sleep_time(make_dt(10, 0))
    assert not scheduler.is_sleep_time(make_dt(8, 59))
    assert not scheduler.is_sleep_time(make_dt(11, 0))


def test_sleep_scheduler_overnight_window() -> None:
    scheduler = SleepScheduler([{ "start": "22:00", "end": "06:00" }])
    assert scheduler.is_sleep_time(make_dt(23, 0))
    assert scheduler.is_sleep_time(make_dt(1, 30))
    assert not scheduler.is_sleep_time(make_dt(7, 0))
