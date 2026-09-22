"""Sensor-платформа: числові й текстові показники плати СтрумОК.

Перелік і джерела полів — точно за §2 спільного контракту
`docs/HOME-ASSISTANT-DEVICE-INTEGRATION.md`. Значення дістають чисті
функції з `parser.py`; коли поля в `/api` немає, `value_fn` повертає
``None`` і HA сам показує сенсор як `unavailable` — жодного винятку.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import parser
from .const import DOMAIN
from .coordinator import StrumokDataUpdateCoordinator
from .entity import StrumokEntity


@dataclass(frozen=True, kw_only=True)
class StrumokSensorEntityDescription(SensorEntityDescription):
    """Опис сенсора + функція, що дістає значення з `coordinator.data`."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSOR_DESCRIPTIONS: tuple[StrumokSensorEntityDescription, ...] = (
    StrumokSensorEntityDescription(
        key="charging_state",
        translation_key="charging_state",
        value_fn=parser.charging_state,
    ),
    StrumokSensorEntityDescription(
        key="charging_current",
        translation_key="charging_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=parser.charging_current_a,
    ),
    StrumokSensorEntityDescription(
        key="charging_power",
        translation_key="charging_power",
        # 🔴 Одиниця НЕ підтверджена емпірично — детальне обґрунтування й
        # застереження в docstring `parser.charging_power`. kW обрано як
        # найбільш імовірний варіант для побутової зарядки; підлягає
        # звірці на живій платі.
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=parser.charging_power,
    ),
    StrumokSensorEntityDescription(
        key="home_battery_soc",
        translation_key="home_battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=parser.home_battery_soc,
    ),
    StrumokSensorEntityDescription(
        key="pv_power",
        translation_key="pv_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=parser.pv_power_w,
    ),
    StrumokSensorEntityDescription(
        key="battery_power",
        translation_key="battery_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=parser.battery_power_w,
    ),
    StrumokSensorEntityDescription(
        key="grid_power",
        translation_key="grid_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=parser.grid_power_w,
    ),
    StrumokSensorEntityDescription(
        key="load_power",
        translation_key="load_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=parser.load_power_w,
    ),
    StrumokSensorEntityDescription(
        key="wifi_rssi",
        translation_key="wifi_rssi",
        # Конвенція dBm не написана явно в коді прошивки — типова для RSSI,
        # позначено як припущення (контракт §2).
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=parser.wifi_rssi,
    ),
    StrumokSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=parser.uptime_seconds,
    ),
    StrumokSensorEntityDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=parser.firmware_version,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: StrumokDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        StrumokSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    )


class StrumokSensor(StrumokEntity, CoordinatorEntity[StrumokDataUpdateCoordinator], SensorEntity):
    """Один READ-ONLY сенсор плати СтрумОК."""

    entity_description: StrumokSensorEntityDescription

    def __init__(
        self,
        coordinator: StrumokDataUpdateCoordinator,
        description: StrumokSensorEntityDescription,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        StrumokEntity.__init__(self, coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._entity_prefix}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None
