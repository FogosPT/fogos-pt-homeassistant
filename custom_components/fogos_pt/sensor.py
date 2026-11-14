"""Sensors: incident counts, resources, IPMA warnings and the last earthquake."""

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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import FIRE_KINDS, MAX_ATTRIBUTE_ITEMS, WARNING_LEVELS
from .coordinator import FogosConfigEntry, FogosCoordinator, incident_payload, quake_payload, warning_payload
from .entity import FogosEntity
from .selection import incident_kind

PARALLEL_UPDATES = 0


def _incidents(coordinator: FogosCoordinator, fires: bool) -> list[dict[str, Any]]:
    rows = [i for i in (coordinator.data or {}).values() if (incident_kind(i) in FIRE_KINDS) == fires]
    return sorted(rows, key=lambda i: (i.get("man") or 0), reverse=True)


def _incident_attributes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "incidents": [incident_payload(i) for i in rows[:MAX_ATTRIBUTE_ITEMS]],
        "man": sum(i.get("man") or 0 for i in rows),
        "terrain": sum(i.get("terrain") or 0 for i in rows),
        "aerial": sum(i.get("aerial") or 0 for i in rows),
    }


def _sum(field: str) -> Callable[[FogosCoordinator], int]:
    return lambda c: sum(i.get(field) or 0 for i in (c.data or {}).values())


def _max_level(coordinator: FogosCoordinator) -> str:
    levels = [str(w.get("awarenessLevelID")) for w in coordinator.data or []]
    return max(levels, key=lambda lvl: WARNING_LEVELS.get(lvl, 0), default="green")


@dataclass(frozen=True, kw_only=True)
class FogosSensorDescription(SensorEntityDescription):
    value_fn: Callable[[FogosCoordinator], Any]
    attributes_fn: Callable[[FogosCoordinator], dict[str, Any]] | None = None


INCIDENT_SENSORS = (
    FogosSensorDescription(
        key="active_fires",
        native_unit_of_measurement="incêndios",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: len(_incidents(c, True)),
        attributes_fn=lambda c: _incident_attributes(_incidents(c, True)),
    ),
    FogosSensorDescription(
        key="other_incidents",
        native_unit_of_measurement="ocorrências",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: len(_incidents(c, False)),
        attributes_fn=lambda c: _incident_attributes(_incidents(c, False)),
    ),
    FogosSensorDescription(
        key="man",
        native_unit_of_measurement="operacionais",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_sum("man"),
    ),
    FogosSensorDescription(
        key="terrain",
        native_unit_of_measurement="veículos",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_sum("terrain"),
    ),
    FogosSensorDescription(
        key="aerial",
        native_unit_of_measurement="meios aéreos",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_sum("aerial"),
    ),
)

WARNING_SENSORS = (
    FogosSensorDescription(
        key="warnings",
        native_unit_of_measurement="avisos",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: len(c.data or []),
        attributes_fn=lambda c: {
            "max_level": _max_level(c),
            "warnings": [warning_payload(w, c.area_names) for w in (c.data or [])[:MAX_ATTRIBUTE_ITEMS]],
        },
    ),
    FogosSensorDescription(
        key="warning_level",
        device_class=SensorDeviceClass.ENUM,
        options=list(WARNING_LEVELS),
        value_fn=_max_level,
    ),
)

SEISMIC_SENSORS = (
    FogosSensorDescription(
        key="last_earthquake",
        native_unit_of_measurement="M",
        suggested_display_precision=1,
        value_fn=lambda c: c.data[0].get("magnitude") if c.data else None,
        attributes_fn=lambda c: (
            {
                **quake_payload(c.data[0], c.distance(c.data[0])),
                "count_7d": len(c.data),
            }
            if c.data
            else {"count_7d": 0}
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: FogosConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    data = entry.runtime_data
    entities: list[FogosSensor] = [FogosSensor(data.incidents, entry, d) for d in INCIDENT_SENSORS]
    if data.warnings.areas:
        entities += [FogosSensor(data.warnings, entry, d) for d in WARNING_SENSORS]
    if data.seismic is not None:
        entities += [FogosSensor(data.seismic, entry, d) for d in SEISMIC_SENSORS]
    async_add_entities(entities)


class FogosSensor(FogosEntity, SensorEntity):
    entity_description: FogosSensorDescription

    def __init__(self, coordinator: FogosCoordinator, entry: FogosConfigEntry, description: FogosSensorDescription) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator)
