"""Спільна база сутностей: пристрій (плата) + unique_id + динамічне додавання.

`identifiers = {("strumok", <dev>)}`, `manufacturer = "СтрумОК"`,
`model = "Зарядна станція СтрумОК"`, `sw_version = fw` — за §2
`docs/HOME-ASSISTANT-DEVICE-INTEGRATION.md`. unique_id — `strumok_<slug(dev)>_<key>`,
як і в 0.1.0 (змінювати не можна: сутності користувачів осиротіли б).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import parser
from .const import DOMAIN, MANUFACTURER, MODEL, PENDING_COMMAND_S
from .coordinator import StrumokConfigEntry, StrumokDataUpdateCoordinator

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slug(dev: str) -> str:
    return _NON_ALNUM.sub("", dev.lower())


class StrumokEntity(CoordinatorEntity[StrumokDataUpdateCoordinator]):
    """Сутність плати СтрумОК з описом пристрою."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: StrumokDataUpdateCoordinator, description: EntityDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        data = coordinator.data or {}
        dev = coordinator.device_id
        self._attr_unique_id = f"strumok_{_slug(dev)}_{description.key}"
        mac = parser.mac_from_device_id(dev)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev)},
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=dev,
            serial_number=dev,
            sw_version=parser.firmware_version(data),
            configuration_url=coordinator.client.panel_url,
        )

    @property
    def data(self) -> dict[str, Any]:
        return self.coordinator.data or {}


class StrumokCommandEntity(StrumokEntity):
    """Сутність керування з оптимістичним станом після команди.

    Плата ставить команду в чергу й застосовує її за такт-два, тож найближче
    опитування може ще показати старе значення. Щоб перемикач не «відскакував»,
    тримаємо надіслане значення, доки плата його не підтвердить або не мине
    `PENDING_COMMAND_S`.
    """

    _pending: Any = None
    _pending_until: float = 0.0

    def _reported(self) -> Any:
        raise NotImplementedError

    def _current(self) -> Any:
        reported = self._reported()
        if self._pending is not None and time.monotonic() < self._pending_until:
            if reported == self._pending:
                self._pending = None
            else:
                return self._pending
        self._pending = None
        return reported

    def _set_pending(self, value: Any) -> None:
        self._pending = value
        self._pending_until = time.monotonic() + PENDING_COMMAND_S
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.control_available


def async_setup_dynamic_entities(
    entry: StrumokConfigEntry,
    add_entities: Callable[[Iterable[Entity]], None],
    candidates: Callable[[StrumokDataUpdateCoordinator], Iterable[tuple[str, Callable[[], Entity]]]],
) -> None:
    """Додати сутності зараз і ті, що зʼявляться пізніше (нове поле, OTA з командами).

    `candidates` повертає пари (ключ, фабрика) лише для тих сутностей, які плата
    зараз підтримує; кожен ключ додається один раз за життя запису.
    """
    coordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[Entity] = []
        for key, factory in candidates(coordinator):
            if key in added:
                continue
            added.add(key)
            new.append(factory())
        if new:
            add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))
