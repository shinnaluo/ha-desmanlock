"""Binary sensor platform for Desman Lock."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DesmanLockDataUpdateCoordinator
from .entity import DesmanLockEntity, entity_identity, entity_unique_id
from .helpers import (
    latest_open_time_record,
    latest_open_user,
    parse_log_datetime,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Desman Lock lock-state binary sensor."""
    coordinator: DesmanLockDataUpdateCoordinator = entry.runtime_data
    async_add_entities([DesmanLockStateBinarySensor(coordinator)])


class DesmanLockStateBinarySensor(DesmanLockEntity, BinarySensorEntity):
    """Report whether the door is unlocked (on) or locked (off)."""

    _attr_device_class = BinarySensorDeviceClass.LOCK
    _attr_translation_key = "lock_state"

    def __init__(self, coordinator: DesmanLockDataUpdateCoordinator) -> None:
        """Initialize the state sensor."""
        super().__init__(coordinator)
        identity = entity_identity(self.lock_id, "lock_state")
        self.entity_id = f"binary_sensor.{identity}"
        self._attr_unique_id = entity_unique_id(self.lock_id, "lock_state")

    @property
    def is_on(self) -> bool | None:
        """Return True when unlocked, False when locked, None when unknown."""
        is_locked, _ = self.coordinator.lock_state
        if is_locked is None:
            return None
        return not is_locked

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the evidence behind the inferred state."""
        is_locked, source = self.coordinator.lock_state
        last_open = latest_open_time_record(self.coordinator.data.get("records"))
        lock = self.lock_data
        detail = self.detail_data
        if is_locked is None:
            state = "unknown"
        else:
            state = "locked" if is_locked else "unlocked"

        hold = self.coordinator.unlock_hold_seconds
        expires_at: str | None = None
        if hold > 0 and source == "cloud_unlock_recent":
            logged = parse_log_datetime(last_open.get("datetime"))
            if logged is not None:
                expires_at = (logged + timedelta(seconds=hold)).isoformat()
        elif hold > 0 and source == "unlock_in_progress":
            local_unlock = self.coordinator.last_unlock_at
            if local_unlock is not None:
                expires_at = (local_unlock + timedelta(seconds=hold)).isoformat()

        return {
            "lock_state": state,
            "state_source": source,
            "open_user": latest_open_user(self.coordinator.data.get("records")),
            "open_content": last_open.get("content"),
            "open_log_type": last_open.get("logType"),
            "open_time": last_open.get("datetime"),
            "lock_mac": detail.get("lockMac") or lock.get("lockMac"),
            "last_unlock_at": (
                self.coordinator.last_unlock_at.isoformat()
                if self.coordinator.last_unlock_at
                else None
            ),
            "unlock_hold_seconds": self.coordinator.unlock_hold_seconds,
            "state_expires_at": expires_at,
            "state_is_inferred": True,
        }
