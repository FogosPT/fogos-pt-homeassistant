"""The Fogos.pt integration: incidents, IPMA warnings and earthquakes."""

from __future__ import annotations

from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FogosApi
from .const import CONF_SEISMIC_REGION, DEFAULT_SEISMIC_REGION, SEISMIC_REGION_NONE
from .coordinator import (
    FogosConfigEntry,
    FogosData,
    IncidentsCoordinator,
    SeismicCoordinator,
    WarningsCoordinator,
)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.GEO_LOCATION, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: FogosConfigEntry) -> bool:
    api = FogosApi(async_get_clientsession(hass), entry.data[CONF_API_KEY])

    incidents = IncidentsCoordinator(hass, entry, api)
    warnings = WarningsCoordinator(hass, entry, api)
    seismic = None
    if entry.options.get(CONF_SEISMIC_REGION, DEFAULT_SEISMIC_REGION) != SEISMIC_REGION_NONE:
        seismic = SeismicCoordinator(hass, entry, api)

    for coordinator in (incidents, warnings, seismic):
        if coordinator is not None:
            await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = FogosData(api, incidents, warnings, seismic)
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FogosConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: FogosConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
