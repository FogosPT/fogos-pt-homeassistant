"""The Fogos.pt integration: incidents, IPMA warnings and earthquakes."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FogosApi
from .const import CONF_SEISMIC_REGION, DEFAULT_SEISMIC_REGION, SEISMIC_REGION_NONE
from .coordinator import (
    FogosConfigEntry,
    FogosData,
    FogosCoordinator,
    IncidentsCoordinator,
    SeismicCoordinator,
    WarningsCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.GEO_LOCATION, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: FogosConfigEntry) -> bool:
    api = FogosApi(async_get_clientsession(hass), entry.data[CONF_API_KEY])

    incidents = IncidentsCoordinator(hass, entry, api)
    warnings = WarningsCoordinator(hass, entry, api)
    seismic = None
    if entry.options.get(CONF_SEISMIC_REGION, DEFAULT_SEISMIC_REGION) != SEISMIC_REGION_NONE:
        seismic = SeismicCoordinator(hass, entry, api)

    # Incidents are required (and also catch a rejected API key). Warnings and
    # earthquakes are best-effort: a down IPMA or seismic endpoint must not
    # take the fire sensors with it.
    await incidents.async_config_entry_first_refresh()
    await _async_optional_first_refresh(warnings)
    await _async_optional_first_refresh(seismic)

    entry.runtime_data = FogosData(api, incidents, warnings, seismic)
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_optional_first_refresh(coordinator: FogosCoordinator | None) -> None:
    if coordinator is None:
        return
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except ConfigEntryNotReady as err:
        _LOGGER.warning("Fogos.pt %s unavailable at startup: %s", coordinator.name, err)


async def async_unload_entry(hass: HomeAssistant, entry: FogosConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: FogosConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
