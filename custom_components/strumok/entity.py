"""Спільна базова сутність: описує ПРИСТРІЙ (плату), не окремий сенсор.

`identifiers`, `manufacturer`, `model`, `sw_version` — точно за §2
контракту `docs/HOME-ASSISTANT-DEVICE-INTEGRATION.md`:
``identifiers = {("strumok", <dev>)}``, ``manufacturer = "СтрумОК"``,
``model = "Зарядна станція СтрумОК"``, ``sw_version = <fw з /api>``.
"""

from __future__ import annotations

import re

from homeassistant.helpers.entity import DeviceInfo, Entity

from . import parser
from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import StrumokDataUpdateCoordinator

# Контракт §2: "Іменування: strumok_<dev>_<key> де <dev> — поле dev з /api
# ..., нижній регістр, без спецсимволів". Той самий префікс використовує
# паралельний напрям STR-459 (MQTT discovery/topics) — навмисно тримати
# формат ідентичним між обома шляхами.
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slug(dev: str) -> str:
    return _NON_ALNUM.sub("", dev.lower())


class StrumokEntity(Entity):
    """Домішка з `device_info`, спільна для sensor і binary_sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: StrumokDataUpdateCoordinator) -> None:
        data = coordinator.data or {}
        # `dev` МАЄ бути в кожній відповіді `/api` (перше поле в прикладі
        # контракту) — але `async_config_entry_first_refresh()` гарантує
        # хоча б одне успішне опитування до створення сутностей
        # (`__init__.py::async_setup_entry`), тому запасний варіант (хост)
        # практично не використовується — лишається лише як запобіжник,
        # щоб не впасти, якщо плата раптом віддасть `/api` без поля `dev`.
        self._device_id = parser.device_id(data) or coordinator.host
        # unique_id-префікс за контрактом §2: strumok_<dev>_<key>.
        self._entity_prefix = f"strumok_{_slug(self._device_id)}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=parser.firmware_version(data),
            name=self._device_id,
        )
