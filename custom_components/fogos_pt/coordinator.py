"""Data update coordinators: poll the API and fire events for what changed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FogosApi, FogosApiError, FogosAuthError
from .const import (
    CONF_KINDS,
    CONF_MIN_MAGNITUDE,
    CONF_RADIUS,
    CONF_SEISMIC_NEAR_SELECTION,
    CONF_SEISMIC_REGION,
    CONF_WARNING_AREAS,
    DEFAULT_KINDS,
    DEFAULT_MIN_MAGNITUDE,
    DEFAULT_RADIUS,
    DEFAULT_SEISMIC_REGION,
    DOMAIN,
    EVENT_INCIDENT_ENDED,
    EVENT_INCIDENT_STATUS_CHANGED,
    EVENT_NEW_EARTHQUAKE,
    EVENT_NEW_INCIDENT,
    EVENT_NEW_WARNING,
    FIRE_KINDS,
    INCIDENT_URL,
    INCIDENTS_INTERVAL,
    SEISMIC_INTERVAL,
    SEISMIC_REGION_ALL,
    WARNING_LEVELS,
    WARNINGS_INTERVAL,
)
from .selection import Selection, as_float, distance_km, incident_kind

_LOGGER = logging.getLogger(__name__)


@dataclass
class FogosData:
    """What a config entry keeps in `entry.runtime_data`."""

    api: FogosApi
    incidents: IncidentsCoordinator
    warnings: WarningsCoordinator
    seismic: SeismicCoordinator | None


type FogosConfigEntry = ConfigEntry[FogosData]


class FogosCoordinator[T](DataUpdateCoordinator[T]):
    """Shared error handling; `_initialized` is False until the first refresh
    succeeded, so nothing already there on start-up is reported as new."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: FogosApi, name: str, interval: timedelta) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} {name}", update_interval=interval)
        self.api = api
        self._initialized = False

    async def _async_update_data(self) -> T:
        try:
            data = await self._fetch()
        except FogosAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FogosApiError as err:
            raise UpdateFailed(str(err)) from err

        if self._initialized:
            self._fire_changes(data)
        self._initialized = True
        return data

    async def _fetch(self) -> T:
        raise NotImplementedError

    def _fire_changes(self, data: T) -> None:
        """Fire events for the differences between self.data and data."""

    def _fire(self, event_type: str, payload: dict[str, Any]) -> None:
        self.hass.bus.async_fire(event_type, {"entry_id": self.config_entry.entry_id, **payload})


def incident_payload(incident: dict[str, Any]) -> dict[str, Any]:
    """The fields of an incident sent with events and in attributes."""
    return {
        "id": str(incident.get("id")),
        "kind": incident_kind(incident),
        "is_fire": incident_kind(incident) in FIRE_KINDS,
        "natureza": incident.get("natureza"),
        "status": incident.get("status"),
        "status_code": incident.get("statusCode"),
        "district": incident.get("district"),
        "concelho": incident.get("concelho"),
        "freguesia": incident.get("freguesia"),
        "location": incident.get("location"),
        "latitude": as_float(incident.get("lat")),
        "longitude": as_float(incident.get("lng")),
        "man": incident.get("man") or 0,
        "terrain": incident.get("terrain") or 0,
        "aerial": incident.get("aerial") or 0,
        "important": bool(incident.get("important")),
        "date": incident.get("date"),
        "hour": incident.get("hour"),
        "url": INCIDENT_URL.format(id=incident.get("id")),
    }


class IncidentsCoordinator(FogosCoordinator[dict[str, dict[str, Any]]]):
    """Active incidents in the selected locations and kinds, by id."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: FogosApi) -> None:
        super().__init__(hass, entry, api, "incidents", INCIDENTS_INTERVAL)
        self.selection = Selection.from_options(entry.options)
        self.kinds = set(entry.options.get(CONF_KINDS, DEFAULT_KINDS))

    async def _fetch(self) -> dict[str, dict[str, Any]]:
        rows = await self.api.active_incidents(self.selection.query())
        return {
            str(row.get("id")): row
            for row in rows
            if incident_kind(row) in self.kinds and self.selection.matches(row)
        }

    def _fire_changes(self, data: dict[str, dict[str, Any]]) -> None:
        old = self.data or {}
        for incident_id, incident in data.items():
            previous = old.get(incident_id)
            if previous is None:
                self._fire(EVENT_NEW_INCIDENT, incident_payload(incident))
            elif previous.get("statusCode") != incident.get("statusCode"):
                self._fire(
                    EVENT_INCIDENT_STATUS_CHANGED,
                    {**incident_payload(incident), "previous_status": previous.get("status")},
                )
        for incident_id in old.keys() - data.keys():
            self._fire(EVENT_INCIDENT_ENDED, incident_payload(old[incident_id]))


def warning_key(warning: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(warning.get("idAreaAviso")),
        str(warning.get("awarenessTypeName")),
        str(warning.get("startTime")),
    )


def warning_payload(warning: dict[str, Any], area_names: dict[str, str]) -> dict[str, Any]:
    area = str(warning.get("idAreaAviso"))
    return {
        "area": area,
        "area_name": area_names.get(area, area),
        "type": warning.get("awarenessTypeName"),
        "level": warning.get("awarenessLevelID"),
        "text": warning.get("text"),
        "start": warning.get("startTime"),
        "end": warning.get("endTime"),
    }


class WarningsCoordinator(FogosCoordinator[list[dict[str, Any]]]):
    """Active IPMA warnings of the selected areas."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: FogosApi) -> None:
        super().__init__(hass, entry, api, "warnings", WARNINGS_INTERVAL)
        self.areas: list[str] = list(entry.options.get(CONF_WARNING_AREAS, []))
        self.area_names: dict[str, str] = {}

    async def _fetch(self) -> list[dict[str, Any]]:
        if not self.areas:
            return []
        if not self.area_names:
            try:
                self.area_names = {a["code"]: a["name"] for a in await self.api.warning_areas()}
            except FogosApiError:
                _LOGGER.debug("Could not load the IPMA area names")
        return await self.api.ipma_warnings(self.areas)

    def _fire_changes(self, data: list[dict[str, Any]]) -> None:
        """A warning window not seen before, or one whose level went up."""
        old = {warning_key(w): w for w in self.data or []}
        for warning in data:
            previous = old.get(warning_key(warning))
            level = WARNING_LEVELS.get(str(warning.get("awarenessLevelID")), 0)
            if previous is None or level > WARNING_LEVELS.get(str(previous.get("awarenessLevelID")), 0):
                self._fire(EVENT_NEW_WARNING, warning_payload(warning, self.area_names))


def quake_payload(quake: dict[str, Any], distance: float | None) -> dict[str, Any]:
    nearest = quake.get("nearest") or {}
    return {
        "id": str(quake.get("id")),
        "magnitude": quake.get("magnitude"),
        "time": quake.get("time"),
        "depth": quake.get("depth"),
        "place": quake.get("place"),
        "region": quake.get("region"),
        "felt": bool(quake.get("felt")),
        "nearest": nearest.get("name"),
        "nearest_municipality": nearest.get("municipality"),
        "nearest_km": nearest.get("km"),
        "latitude": as_float(quake.get("lat")),
        "longitude": as_float(quake.get("lon")),
        "distance_km": round(distance, 1) if distance is not None else None,
    }


class SeismicCoordinator(FogosCoordinator[list[dict[str, Any]]]):
    """Earthquakes of the last 7 days above the minimum magnitude, newest first."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: FogosApi) -> None:
        super().__init__(hass, entry, api, "seismic", SEISMIC_INTERVAL)
        options = entry.options
        region = options.get(CONF_SEISMIC_REGION, DEFAULT_SEISMIC_REGION)
        self.region = None if region == SEISMIC_REGION_ALL else region
        self.min_magnitude = float(options.get(CONF_MIN_MAGNITUDE, DEFAULT_MIN_MAGNITUDE))
        self.radius = float(options.get(CONF_RADIUS, DEFAULT_RADIUS) or 0)
        selection = Selection.from_options(options)
        self.locations = selection.query() if options.get(CONF_SEISMIC_NEAR_SELECTION) else None

    def distance(self, quake: dict[str, Any]) -> float | None:
        lat, lon = as_float(quake.get("lat")), as_float(quake.get("lon"))
        if lat is None or lon is None:
            return None
        return distance_km(self.hass.config.latitude, self.hass.config.longitude, lat, lon)

    async def _fetch(self) -> list[dict[str, Any]]:
        rows = await self.api.latest_earthquakes(self.region, self.locations)
        out = []
        for quake in rows:
            magnitude = as_float(quake.get("magnitude"))
            # Provisional events have no magnitude yet; they come back later.
            if magnitude is None or magnitude < self.min_magnitude:
                continue
            distance = self.distance(quake)
            if self.radius and (distance is None or distance > self.radius):
                continue
            out.append(quake)
        out.sort(key=lambda q: str(q.get("time")), reverse=True)
        return out

    def _fire_changes(self, data: list[dict[str, Any]]) -> None:
        seen = {str(q.get("id")) for q in self.data or []}
        for quake in reversed(data):
            if str(quake.get("id")) not in seen:
                self._fire(EVENT_NEW_EARTHQUAKE, quake_payload(quake, self.distance(quake)))
