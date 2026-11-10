"""Coordinator for the Desman Lock integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import DesmanLockApiClient, DesmanLockApiError
from .bluetooth import DesmanBluetoothLock
from .const import (
    DEFAULT_UNLOCK_HOLD_SECONDS,
    DOMAIN,
    LOG_TYPE_ACTION,
    LOG_TYPE_ALARM,
    LOG_TYPE_OPEN_DOOR,
)
from .exceptions import DesmanLockAuthError
from .helpers import (
    AUTO_LOCK_TEXT,
    latest_open_time_record,
    parse_log_datetime,
    resolve_lock_state,
)

_LOGGER = logging.getLogger(__name__)


class DesmanLockDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Desman Lock data update coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: DesmanLockApiClient,
        lock_id: str,
        scan_interval: int,
        unlock_hold_seconds: int = DEFAULT_UNLOCK_HOLD_SECONDS,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.lock_id = lock_id
        self.bluetooth = DesmanBluetoothLock(hass, api, {}, {}, {})
        self.unlock_hold_seconds = max(0, int(unlock_hold_seconds))
        self.last_unlock_at: datetime | None = None
        self._unlock_hold_cancel: Callable[[], None] | None = None
        self._log_hold_cancel: Callable[[], None] | None = None

    @property
    def lock_state(self) -> tuple[bool | None, str]:
        """Return (is_locked, source) for the lock state binary sensor.

        The cloud has no real-time bolt state, so the newest open-door /
        auto-lock log entry is the only authoritative source. A successful
        Bluetooth unlock is reflected immediately for ``unlock_hold_seconds``;
        afterwards the lock is assumed to have auto-locked unless the cloud
        already reports otherwise.
        """
        return resolve_lock_state(
            self.data.get("records") if self.data else None,
            self.last_unlock_at,
            self.unlock_hold_seconds,
            dt_util.utcnow(),
            local_now=dt_util.now().replace(tzinfo=None),
        )

    def mark_unlocked(self) -> None:
        """Record a successful unlock and refresh state listeners immediately."""
        self.last_unlock_at = dt_util.utcnow()
        self.async_update_listeners()
        self._schedule_hold_expiry()

    @callback
    def _schedule_hold_expiry(self) -> None:
        """Re-evaluate the optimistic state when the hold window expires."""
        self.cancel_unlock_hold()
        if self.unlock_hold_seconds <= 0 or self.last_unlock_at is None:
            return
        self._unlock_hold_cancel = async_call_later(
            self.hass, self.unlock_hold_seconds, self._handle_hold_expired
        )

    @callback
    def _handle_hold_expired(self, _now: datetime) -> None:
        """Refresh listeners after the optimistic unlock window."""
        self._unlock_hold_cancel = None
        self.async_update_listeners()

    @callback
    def cancel_unlock_hold(self) -> None:
        """Cancel a pending optimistic-state timer."""
        if self._unlock_hold_cancel is not None:
            self._unlock_hold_cancel()
            self._unlock_hold_cancel = None

    def _schedule_log_hold_expiry(self, records: list[dict] | None) -> None:
        """Refresh listeners when a cloud unlock event leaves its hold window.

        The coordinator only polls the cloud every few minutes, so without this
        timer the entity would keep showing "unlocked" long after the lock has
        auto-locked itself.
        """
        self.cancel_log_hold()
        if self.unlock_hold_seconds <= 0:
            return
        record = latest_open_time_record(records)
        if not record:
            return
        if (
            record.get("logType") == AUTO_LOCK_TEXT
            or record.get("content") == AUTO_LOCK_TEXT
        ):
            return
        logged_at = parse_log_datetime(record.get("datetime"))
        if logged_at is None:
            return
        elapsed = (
            dt_util.now().replace(tzinfo=None) - logged_at
        ).total_seconds()
        # A log timestamp far in the future means the HA timezone does not
        # match the lock's; time-based inference is disabled in that case.
        if elapsed < -300:
            return
        remaining = self.unlock_hold_seconds - elapsed
        if remaining <= 0:
            return
        self._log_hold_cancel = async_call_later(
            self.hass, remaining, self._handle_log_hold_expired
        )

    @callback
    def _handle_log_hold_expired(self, _now: datetime) -> None:
        """Refresh listeners after a cloud unlock event has expired."""
        self._log_hold_cancel = None
        self.async_update_listeners()

    @callback
    def cancel_log_hold(self) -> None:
        """Cancel a pending cloud-log hold timer."""
        if self._log_hold_cancel is not None:
            self._log_hold_cancel()
            self._log_hold_cancel = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest data from DSM cloud."""
        try:
            previous_data = self.data or {}
            locks = await self.api.async_lock_list()
            locks = locks or previous_data.get("locks") or []
            selected_lock = _merge_current_with_previous(
                self._select_lock(locks),
                previous_data.get("lock") or {},
            )
            lock_id = self.lock_id
            detail: dict[str, Any] = {}
            detail_config: dict[str, Any] = {}
            open_records: list[dict[str, Any]] = []
            alarm_records: list[dict[str, Any]] = []
            action_records: list[dict[str, Any]] = []
            detail = await self.api.async_lock_detail(lock_id)
            try:
                detail_config = await self.api.async_lock_detail_and_config(lock_id)
            except DesmanLockAuthError:
                raise
            except DesmanLockApiError as err:
                _LOGGER.debug("Failed to fetch lock detailAndConfig: %s", err)
            battery_curve: dict[str, Any] = {}
            try:
                battery_curve = await self.api.async_lock_battery_curve(lock_id)
            except DesmanLockAuthError:
                raise
            except DesmanLockApiError as err:
                _LOGGER.debug("Failed to fetch lock battery curve: %s", err)
            for record_type, previous_key in (
                (LOG_TYPE_OPEN_DOOR, "records"),
                (LOG_TYPE_ALARM, "alarm_records"),
                (LOG_TYPE_ACTION, "action_records"),
            ):
                try:
                    records = await self.api.async_open_door_records(
                        lock_id, record_type=record_type
                    )
                except DesmanLockAuthError:
                    raise
                except DesmanLockApiError as err:
                    _LOGGER.debug("Failed to fetch record type %s: %s", record_type, err)
                    records = previous_data.get(previous_key) or []
                if record_type == LOG_TYPE_OPEN_DOOR:
                    open_records = records
                elif record_type == LOG_TYPE_ALARM:
                    alarm_records = records
                else:
                    action_records = records
            detail = _merge_current_with_previous(
                detail,
                previous_data.get("detail") or {},
            )
            detail_config = _merge_current_with_previous(
                detail_config,
                previous_data.get("detail_config") or {},
            )
            battery_curve = _merge_current_with_previous(
                battery_curve,
                previous_data.get("battery_curve") or {},
            )
            last_open = _last_open_record(open_records) or previous_data.get("last_open") or {}
            last_alarm = _last_alarm_record(alarm_records) or previous_data.get("last_alarm") or {}
            last_action = (
                _last_action_record(action_records)
                or previous_data.get("last_action")
                or {}
            )
            last_alarm_snapshot = _last_record_with_picture(
                alarm_records, LOG_TYPE_ALARM
            ) or previous_data.get("last_alarm_snapshot") or {}
            self.bluetooth.update_data(selected_lock, detail, detail_config)
            result = {
                "locks": locks,
                "lock": selected_lock,
                "lock_id": lock_id,
                "detail": detail,
                "detail_config": detail_config,
                "battery_curve": battery_curve,
                "records": open_records,
                "alarm_records": alarm_records,
                "action_records": action_records,
                "last_open": last_open,
                "last_alarm": last_alarm,
                "last_action": last_action,
                "last_alarm_snapshot": last_alarm_snapshot,
            }
            self._schedule_log_hold_expiry(open_records)
            return result
        except DesmanLockAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DesmanLockApiError as err:
            raise UpdateFailed(str(err)) from err

    def _select_lock(self, locks: list[dict[str, Any]]) -> dict[str, Any]:
        """Select the configured lock."""
        for lock in locks:
            if str(lock.get("lockId")) == str(self.lock_id):
                return lock
        return {}


def _merge_current_with_previous(
    current: dict[str, Any],
    previous: dict[str, Any],
) -> dict[str, Any]:
    """Fill missing current fields from the previous successful payload."""
    if not current:
        return dict(previous)
    if not previous:
        return dict(current)

    merged = dict(previous)
    for key, value in current.items():
        previous_value = previous.get(key)
        if isinstance(value, dict) and isinstance(previous_value, dict):
            merged[key] = _merge_current_with_previous(value, previous_value)
        elif value not in (None, ""):
            merged[key] = value
    return merged


def _last_open_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten latest open door record detail."""
    return _last_record(records, LOG_TYPE_OPEN_DOOR)


def _last_alarm_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten latest alarm record detail."""
    return _last_record(records, LOG_TYPE_ALARM)


def _last_action_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten latest action record detail."""
    return _last_record(records, LOG_TYPE_ACTION)


def _last_record(records: list[dict[str, Any]], log_type_int: int) -> dict[str, Any]:
    """Return the first matching detail from the newest-first API response."""
    for day in records:
        day = day or {}
        for detail in day.get("logDetails") or []:
            if str(detail.get("logTypeInt")) != str(log_type_int):
                continue
            result = dict(detail)
            log_date = day.get("logDate")
            log_time = detail.get("logTime")
            if log_date and log_time:
                result["datetime"] = f"{log_date} {log_time}"
            elif log_date:
                result["datetime"] = log_date
            result["dayTag"] = day.get("dayTag")
            result["weekTag"] = day.get("weekTag")
            return result
    return {}


def _last_record_with_picture(
    records: list[dict[str, Any]], log_type_int: int
) -> dict[str, Any]:
    """Return the newest matching record that contains a picture ID."""
    for day in records:
        day = day or {}
        for detail in day.get("logDetails") or []:
            if str(detail.get("logTypeInt")) != str(log_type_int):
                continue
            if not detail.get("pic"):
                continue
            result = dict(detail)
            log_date = day.get("logDate")
            log_time = detail.get("logTime")
            if log_date and log_time:
                result["datetime"] = f"{log_date} {log_time}"
            elif log_date:
                result["datetime"] = log_date
            result["dayTag"] = day.get("dayTag")
            result["weekTag"] = day.get("weekTag")
            return result
    return {}
