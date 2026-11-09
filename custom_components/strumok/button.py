"""Button `phase_reset`: скинути вирок автопілота про фазу зарядки.

`POST /api/evse/cmd {"phase_reset": true}` — та сама дія, що `evse phase reset`
у консолі плати і `eveus/auto/phase-reset` на сервері: після неї плата заново
міряє, на якій фазі зарядка (див. `evse.cpp`, «СКИНУТИ ВИРОК ПРО ФАЗУ»).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from .coordinator import StrumokConfigEntry, StrumokDataUpdateCoordinator
from .entity import StrumokEntity, async_setup_dynamic_entities

PARALLEL_UPDATES = 1

PHASE_RESET = ButtonEntityDescription(
    key="phase_reset",
    translation_key="phase_reset",
    entity_category=EntityCategory.CONFIG,
)

if TYPE_CHECKING:
    # AddConfigEntryEntitiesCallback зʼявився в HA 2025.3; лише для типів,
    # щоб компонент вантажився й на 2025.2 (мінімум у hacs.json).
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StrumokConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    def candidates(coordinator: StrumokDataUpdateCoordinator):
        if coordinator.control_available:
            yield PHASE_RESET.key, lambda: StrumokPhaseResetButton(coordinator, PHASE_RESET)

    async_setup_dynamic_entities(entry, async_add_entities, candidates)


class StrumokPhaseResetButton(StrumokEntity, ButtonEntity):
    """Скидання вироку про фазу."""

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.control_available

    async def async_press(self) -> None:
        await self.coordinator.async_command({"phase_reset": True})
