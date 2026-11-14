"""Diagnostics (the API key is redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from .coordinator import FogosConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: FogosConfigEntry) -> dict[str, Any]:
    data = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), {CONF_API_KEY}),
            "options": dict(entry.options),
        },
        "query": data.incidents.selection.query(),
        "incidents": len(data.incidents.data or {}),
        "warnings": len(data.warnings.data or []),
        "earthquakes": len(data.seismic.data or []) if data.seismic else None,
    }
