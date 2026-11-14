"""Geolocation events: one per active incident and per earthquake, for the map
card and for zone-based automations. Created and removed as the data changes
(not in the entity registry)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.location import distance as ha_distance

from .const import ATTRIBUTION, DOMAIN, FIRE_KINDS
from .coordinator import FogosConfigEntry, FogosCoordinator, incident_payload, quake_payload
from .selection import as_float, incident_kind

SOURCE = DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: FogosConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    data = entry.runtime_data

    incidents = GeoManager(hass, data.incidents, async_add_entities, _incident_items)
    entry.async_on_unload(incidents.start())

    if data.seismic is not None:
        quakes = GeoManager(hass, data.seismic, async_add_entities, _quake_items)
        entry.async_on_unload(quakes.start())


def _incident_items(coordinator: FogosCoordinator) -> dict[str, dict[str, Any]]:
    items = {}
    for incident_id, incident in (coordinator.data or {}).items():
        payload = incident_payload(incident)
        if payload["latitude"] is None or payload["longitude"] is None:
            continue
        icon = "mdi:fire" if incident_kind(incident) in FIRE_KINDS else "mdi:alert-circle"
        name = f"{payload['natureza'] or 'Ocorrência'} — {payload['location'] or payload['concelho']}"
        items[f"incident_{incident_id}"] = {"name": name, "icon": icon, "attributes": payload}
    return items


def _quake_items(coordinator: FogosCoordinator) -> dict[str, dict[str, Any]]:
    items = {}
    for quake in coordinator.data or []:
        payload = quake_payload(quake, coordinator.distance(quake))
        if payload["latitude"] is None or payload["longitude"] is None:
            continue
        name = f"Sismo M{payload['magnitude']} — {payload['nearest'] or payload['place'] or ''}".rstrip(" —")
        items[f"quake_{payload['id']}"] = {"name": name, "icon": "mdi:pulse", "attributes": payload}
    return items


class GeoManager:
    """Keeps one FogosGeoEvent per item of a coordinator's data."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: FogosCoordinator,
        async_add_entities: AddConfigEntryEntitiesCallback,
        items_fn: Callable[[FogosCoordinator], dict[str, dict[str, Any]]],
    ) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.async_add_entities = async_add_entities
        self.items_fn = items_fn
        self.entities: dict[str, FogosGeoEvent] = {}

    def start(self) -> Callable[[], None]:
        self._update()
        return self.coordinator.async_add_listener(self._update)

    @callback
    def _update(self) -> None:
        items = self.items_fn(self.coordinator)

        new = []
        for item_id, item in items.items():
            if (entity := self.entities.get(item_id)) is not None:
                entity.set_item(item)
                if entity.hass is not None:
                    entity.async_write_ha_state()
            else:
                entity = FogosGeoEvent(item)
                self.entities[item_id] = entity
                new.append(entity)
        if new:
            self.async_add_entities(new)

        for item_id in list(self.entities.keys() - items.keys()):
            entity = self.entities.pop(item_id)
            if entity.hass is not None:
                self.hass.async_create_task(entity.async_remove(force_remove=True))


class FogosGeoEvent(GeolocationEvent):
    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False
    _attr_source = SOURCE
    _attr_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, item: dict[str, Any]) -> None:
        self._item = item

    def set_item(self, item: dict[str, Any]) -> None:
        self._item = item

    @property
    def name(self) -> str:
        return self._item["name"]

    @property
    def icon(self) -> str:
        return self._item["icon"]

    @property
    def latitude(self) -> float | None:
        return as_float(self._item["attributes"].get("latitude"))

    @property
    def longitude(self) -> float | None:
        return as_float(self._item["attributes"].get("longitude"))

    @property
    def distance(self) -> float | None:
        if self.hass is None or self.latitude is None or self.longitude is None:
            return None
        meters = ha_distance(self.hass.config.latitude, self.hass.config.longitude, self.latitude, self.longitude)
        return round(meters / 1000, 1) if meters is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {k: v for k, v in self._item["attributes"].items() if k not in ("latitude", "longitude")}
