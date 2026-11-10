"""Shared helper functions for the Desman Lock integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .const import LOG_TYPE_OPEN_DOOR

AUTO_LOCK_TEXT = "自动上锁"
DOORBELL_RING_TEXT = "按响了门铃"


def extract_open_user(content: str | None) -> str | None:
    """Extract opener name from DSM log content."""
    if not content or content == AUTO_LOCK_TEXT or DOORBELL_RING_TEXT in content:
        return None
    if content == "密码开锁":
        return content
    if "【" in content and "】" in content:
        return content.split("【", 1)[1].split("】", 1)[0]
    return content


def latest_open_user(records: list[dict] | None) -> str | None:
    """Return the latest opener by scanning open-door records newest-first."""
    return latest_open_user_record(records).get("user")


def latest_open_time_record(records: list[dict] | None) -> dict[str, Any]:
    """Return the latest open-door record, excluding doorbell rings."""
    for day in records or []:
        day = day or {}
        for detail in day.get("logDetails") or []:
            if str(detail.get("logTypeInt")) != str(LOG_TYPE_OPEN_DOOR):
                continue
            if DOORBELL_RING_TEXT in str(detail.get("content") or ""):
                continue
            return _record_with_datetime(day, detail)
    return {}


def latest_open_user_record(records: list[dict] | None) -> dict[str, Any]:
    """Return the latest opener and the matching open-door record."""
    for day in records or []:
        day = day or {}
        for detail in day.get("logDetails") or []:
            if str(detail.get("logTypeInt")) != str(LOG_TYPE_OPEN_DOOR):
                continue
            user = extract_open_user(detail.get("content"))
            if user:
                return _record_with_datetime(day, detail, user)
    return {}


def _record_with_datetime(
    day: dict[str, Any],
    detail: dict[str, Any],
    user: str | None = None,
) -> dict[str, Any]:
    """Return a flattened open-door detail enriched with datetime."""
    result = dict(detail)
    log_date = day.get("logDate")
    log_time = detail.get("logTime")
    if log_date and log_time:
        result["datetime"] = f"{log_date} {log_time}"
    elif log_date:
        result["datetime"] = log_date
    result["dayTag"] = day.get("dayTag")
    result["weekTag"] = day.get("weekTag")
    if user is not None:
        result["user"] = user
    return result


_LOG_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")

# Cloud log timestamps are local wall-clock strings. A gap larger than this
# means the HA timezone does not match the lock's, so time-based inference
# must be disabled rather than silently producing a wrong state.
_MAX_CLOCK_SKEW_SECONDS = 300


def parse_log_datetime(value: Any) -> datetime | None:
    """Parse a cloud ``logDate logTime`` string into a naive local datetime."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in _LOG_TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def cloud_lock_state(
    records: list[dict] | None,
    *,
    local_now: datetime | None = None,
    unlock_hold_seconds: int = 0,
) -> tuple[bool | None, str]:
    """Return (is_locked, source) inferred from the newest open-door record.

    A plain unlock record is an *event*, not a persistent state: Desman locks
    re-lock themselves within seconds. It therefore only counts as unlocked
    for ``unlock_hold_seconds`` after the logged time, after which the lock is
    assumed to have auto-locked. An explicit ``自动上锁`` record is authoritative.
    When the log timestamp cannot be compared to the local clock, the legacy
    behaviour is kept and reported as a distinct source.
    """
    record = latest_open_time_record(records)
    log_type = record.get("logType")
    content = record.get("content")
    if log_type == AUTO_LOCK_TEXT or content == AUTO_LOCK_TEXT:
        return True, "cloud_auto_lock"
    if not (log_type or content):
        return None, "unknown"

    if local_now is None or unlock_hold_seconds <= 0:
        return False, "cloud_record"

    logged_at = parse_log_datetime(record.get("datetime"))
    if logged_at is None:
        return False, "cloud_record_undated"

    elapsed = (local_now - logged_at).total_seconds()
    if elapsed < -_MAX_CLOCK_SKEW_SECONDS:
        return False, "cloud_record_time_mismatch"
    if elapsed < unlock_hold_seconds:
        return False, "cloud_unlock_recent"
    return True, "cloud_unlock_expired"


def resolve_lock_state(
    records: list[dict] | None,
    last_unlock_at: datetime | None,
    unlock_hold_seconds: int,
    now: datetime,
    local_now: datetime | None = None,
) -> tuple[bool | None, str]:
    """Resolve (is_locked, source) from cloud records and a local unlock.

    Pure function so the state inference can be tested without Home Assistant.
    ``now`` is a UTC-aware clock used for the local (button) unlock window;
    ``local_now`` is a naive local wall clock matching the cloud log format.
    ``unlock_hold_seconds <= 0`` disables both optimistic windows.
    """
    cloud, source = cloud_lock_state(
        records,
        local_now=local_now,
        unlock_hold_seconds=unlock_hold_seconds,
    )
    if last_unlock_at is not None and unlock_hold_seconds > 0:
        elapsed = (now - last_unlock_at).total_seconds()
        if elapsed < unlock_hold_seconds:
            return False, "unlock_in_progress"
        if cloud is False:
            return True, "auto_lock_timeout"
    return cloud, source
