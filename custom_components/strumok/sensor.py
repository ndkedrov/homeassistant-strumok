"""Sensor-платформа: числові й текстові показники плати СтрумОК.

Перелік і джерела — §2 `docs/HOME-ASSISTANT-DEVICE-INTEGRATION.md` + енергія
сесії (HA-FULL-CONTRACT §3). Коли поля в `/api` немає, `value_fn` повертає
``None`` і сенсор стає `unavailable` — без винятку. Енергія сесії створюється
лише тоді, коли плата її віддає (і зʼявляється сама після OTA, без перезапуску).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant

from . import parser
from .coordinator import StrumokConfigEntry, StrumokDataUpdateCoordinator
from .entity import StrumokEntity, async_setup_dynamic_entities

if TYPE_CHECKING:
    # AddConfigEntryEntitiesCallback зʼявився в HA 2025.3; лише для типів,
    # щоб компонент вантажився й на 2025.2 (мінімум у hacs.json).
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

# Сенсори лише читають дані координатора — обмежувати паралельність нема чого.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class StrumokSensorEntityDescription(SensorEntityDescription):
    """Опис сенсора + звідки брати значення і чи плата його взагалі віддає."""

    value_fn: Callable[[dict[str, Any]], Any]
    # None — сенсор є завжди (як у 0.1.0); інакше — лише коли плата віддає поле.
    exists_fn: Callable[[dict[str, Any]], bool] | None = None


SENSOR_DESCRIPTIONS: tuple[StrumokSensorEntityDescription, ...] = (
    StrumokSensorEntityDescription(
        key="charging_state",
        translation_key="charging_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(parser.CHARGING_STATES),
        value_fn=parser.charging_state_enum,
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
        # Вт, не кВт: звірено в прошивці (див. parser.charging_power).
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=parser.charging_power,
    ),
    StrumokSensorEntityDescription(
        key="charging_session_energy",
        translation_key="charging_session_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        # Нова сесія починається з нуля — HA сприймає спад як скидання лічильника.
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=parser.charging_session_energy_kwh,
        exists_fn=lambda data: parser.charging_session_energy_kwh(data) is not None,
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
    # Стан мережі з якістю (STR-762): немає / нестабільна / норма і причина.
    # Лише коли плата його віддає — стара прошивка сутностей не плодить.
    StrumokSensorEntityDescription(
        key="grid_state",
        translation_key="grid_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(parser.GRID_STATES),
        value_fn=parser.grid_state,
        exists_fn=parser.has_grid_state,
    ),
    StrumokSensorEntityDescription(
        key="grid_state_reason",
        translation_key="grid_state_reason",
        device_class=SensorDeviceClass.ENUM,
        options=list(parser.GRID_STATE_REASONS),
        value_fn=parser.grid_state_reason,
        exists_fn=parser.has_grid_state,
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
    entry: StrumokConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    def candidates(coordinator: StrumokDataUpdateCoordinator):
        data = coordinator.data or {}
        for description in SENSOR_DESCRIPTIONS:
            if description.exists_fn is None or description.exists_fn(data):
                yield description.key, (
                    lambda d=description: StrumokSensor(coordinator, d)
                )

    async_setup_dynamic_entities(entry, async_add_entities, candidates)


class StrumokSensor(StrumokEntity, SensorEntity):
    """Один сенсор плати СтрумОК (лише читання)."""

    entity_description: StrumokSensorEntityDescription

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.data)

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None
