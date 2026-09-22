"""Binary_sensor-платформа: булеві прапорці плати СтрумОК.

Перелік і джерела полів — §2 спільного контракту
`docs/HOME-ASSISTANT-DEVICE-INTEGRATION.md`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import parser
from .const import DOMAIN
from .coordinator import StrumokDataUpdateCoordinator
from .entity import StrumokEntity


@dataclass(frozen=True, kw_only=True)
class StrumokBinarySensorEntityDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[StrumokBinarySensorEntityDescription, ...] = (
    StrumokBinarySensorEntityDescription(
        key="charging_allowed",
        translation_key="charging_allowed",
        value_fn=parser.charging_allowed,
    ),
    StrumokBinarySensorEntityDescription(
        key="car_connected",
        translation_key="car_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=parser.car_connected,
    ),
    StrumokBinarySensorEntityDescription(
        key="wifi_online",
        translation_key="wifi_online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=parser.wifi_online,
    ),
    StrumokBinarySensorEntityDescription(
        key="inverter_bus_connected",
        translation_key="inverter_bus_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=parser.inverter_bus_connected,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: StrumokDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        StrumokBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class StrumokBinarySensor(
    StrumokEntity, CoordinatorEntity[StrumokDataUpdateCoordinator], BinarySensorEntity
):
    """Один READ-ONLY binary_sensor плати СтрумОК."""

    entity_description: StrumokBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: StrumokDataUpdateCoordinator,
        description: StrumokBinarySensorEntityDescription,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        StrumokEntity.__init__(self, coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._entity_prefix}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def available(self) -> bool:
        return super().available and self.is_on is not None
