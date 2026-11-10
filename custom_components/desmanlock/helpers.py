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


def cloud_lock_state(records: list[dict] | None) -> bool | None:
    """Infer the lock state from the newest open-door record.

    Return True when locked, False when unlocked, and None when the cloud has
    not reported any usable record yet. This is the same inference the former
    lock entity used, kept here so the state sensor and the cloud stay in sync.
    """
    record = latest_open_time_record(records)
    log_type = record.get("logType")
    content = record.get("content")
    if log_type == AUTO_LOCK_TEXT or content == AUTO_LOCK_TEXT:
        return True
    if log_type or content:
        return False
    return None


def resolve_lock_state(
    records: list[dict] | None,
    last_unlock_at: datetime | None,
    unlock_hold_seconds: int,
    now: datetime,
) -> tuple[bool | None, str]:
    """Resolve (is_locked, source) from cloud records and a local unlock.

    Pure function so the state inference can be tested without Home Assistant.
    ``unlock_hold_seconds <= 0`` disables the optimistic window entirely.
    """
    cloud = cloud_lock_state(records)
    if last_unlock_at is not None and unlock_hold_seconds > 0:
        elapsed = (now - last_unlock_at).total_seconds()
        if elapsed < unlock_hold_seconds:
            return False, "unlock_in_progress"
        if cloud is False:
            return True, "auto_lock_timeout"
    return cloud, "cloud_record"
