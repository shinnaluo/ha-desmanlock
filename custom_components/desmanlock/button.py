"""Button platform for Desman Lock."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DesmanLockDataUpdateCoordinator
from .entity import DesmanLockEntity, entity_identity, entity_unique_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Desman Lock unlock button."""
    coordinator: DesmanLockDataUpdateCoordinator = entry.runtime_data
    async_add_entities([DesmanUnlockButton(coordinator)])


class DesmanUnlockButton(DesmanLockEntity, ButtonEntity):
    """Unlock-only button: Desman locks expose no active lock command."""

    _attr_translation_key = "unlock"
    _attr_icon = "mdi:lock-open-variant"

    def __init__(self, coordinator: DesmanLockDataUpdateCoordinator) -> None:
        """Initialize the unlock button."""
        super().__init__(coordinator)
        identity = entity_identity(self.lock_id, "unlock")
        self.entity_id = f"button.{identity}"
        self._attr_unique_id = entity_unique_id(self.lock_id, "unlock")

    async def async_press(self) -> None:
        """Unlock the door over Bluetooth."""
        _LOGGER.debug("Unlock button pressed for Desman lock %s", self.lock_id)
        await self.coordinator.bluetooth.async_unlock()
        # Reflect the successful unlock immediately instead of waiting for the
        # next cloud poll (5 minutes by default).
        self.coordinator.mark_unlocked()
        _LOGGER.debug("Bluetooth unlock completed for Desman lock %s", self.lock_id)
        await self.coordinator.async_request_refresh()
