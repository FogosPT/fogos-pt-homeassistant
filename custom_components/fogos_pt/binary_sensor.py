"""Binary sensors: a fire in the selected locations, an orange/red warning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import FIRE_KINDS, WARNING_LEVELS
from .coordinator import FogosConfigEntry, FogosCoordinator
from .entity import FogosEntity
from .selection import incident_kind

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class FogosBinarySensorDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[FogosCoordinator], bool]


FIRE_ACTIVE = FogosBinarySensorDescription(
    key="fire_active",
    device_class=BinarySensorDeviceClass.SAFETY,
    is_on_fn=lambda c: any(incident_kind(i) in FIRE_KINDS for i in (c.data or {}).values()),
)

SEVERE_WARNING = FogosBinarySensorDescription(
    key="severe_warning",
    device_class=BinarySensorDeviceClass.SAFETY,
    is_on_fn=lambda c: any(
        WARNING_LEVELS.get(str(w.get("awarenessLevelID")), 0) >= WARNING_LEVELS["orange"] for w in c.data or []
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: FogosConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    data = entry.runtime_data
    entities = [FogosBinarySensor(data.incidents, entry, FIRE_ACTIVE)]
    if data.warnings.areas:
        entities.append(FogosBinarySensor(data.warnings, entry, SEVERE_WARNING))
    async_add_entities(entities)


class FogosBinarySensor(FogosEntity, BinarySensorEntity):
    entity_description: FogosBinarySensorDescription

    def __init__(
        self, coordinator: FogosCoordinator, entry: FogosConfigEntry, description: FogosBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on_fn(self.coordinator)
