"""Binary_sensor-платформа: булеві прапорці плати СтрумОК.

Перелік і джерела полів — §2 `docs/HOME-ASSISTANT-DEVICE-INTEGRATION.md`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from . import parser
from .coordinator import StrumokConfigEntry
from .entity import StrumokEntity

if TYPE_CHECKING:
    # AddConfigEntryEntitiesCallback зʼявився в HA 2025.3; лише для типів,
    # щоб компонент вантажився й на 2025.2 (мінімум у hacs.json).
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

PARALLEL_UPDATES = 0


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
        key="grid_present",
        translation_key="grid_present",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=parser.grid_present,
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
    entry: StrumokConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        StrumokBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class StrumokBinarySensor(StrumokEntity, BinarySensorEntity):
    """Один binary_sensor плати СтрумОК (лише читання)."""

    entity_description: StrumokBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.data)

    @property
    def available(self) -> bool:
        return super().available and self.is_on is not None
