"""Client for the Fogos.pt API (https://api.fogos.pt)."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlencode

import aiohttp

from .const import API_BASE, API_KEY_HEADER

TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)
USER_AGENT = "HomeAssistant-FogosPT/0.1 (+https://github.com/FogosPT/fogos-pt-homeassistant)"

# Longest query string sent in one request; longer location lists are split
# over several requests and the results merged.
MAX_QUERY_LENGTH = 1500

LEVELS = ("district", "concelho", "freguesia")


class FogosApiError(Exception):
    """The API could not be reached or answered with an error."""


class FogosAuthError(FogosApiError):
    """The API key was rejected."""


class FogosApi:
    """Thin async wrapper around the endpoints the integration uses."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str, base_url: str = API_BASE) -> None:
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        url = f"{self._base_url}/{path.lstrip('/')}"
        headers = {API_KEY_HEADER: self._api_key, "User-Agent": USER_AGENT, "Accept": "application/json"}
        try:
            async with self._session.get(url, params=params or None, headers=headers, timeout=TIMEOUT) as resp:
                if resp.status in (401, 403):
                    raise FogosAuthError(f"API key rejected ({resp.status})")
                if resp.status >= 400:
                    raise FogosApiError(f"{path}: HTTP {resp.status}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise FogosApiError(f"{path}: {err}") from err

    async def locations(self) -> list[dict[str, Any]]:
        """District → concelhos → freguesias tree seen on incidents."""
        return (await self._get("v2/incidents/locations")).get("data", [])

    async def warning_areas(self) -> list[dict[str, Any]]:
        """The IPMA warning areas."""
        return (await self._get("v2/warnings/ipma/areas")).get("data", [])

    async def active_incidents(self, locations: dict[str, list[str]]) -> list[dict[str, Any]]:
        """Active incidents of every kind in the given locations (all when empty)."""
        rows: dict[str, dict[str, Any]] = {}
        for params in batch_location_params(locations, {"all": "1", "limit": "1000"}):
            for incident in (await self._get("v2/incidents/active", params)).get("data", []):
                rows[str(incident.get("id"))] = incident
        return list(rows.values())

    async def ipma_warnings(self, areas: list[str]) -> list[dict[str, Any]]:
        """Active IPMA warnings of the given areas (all when empty)."""
        params = {"area": ",".join(areas)} if areas else None
        data = await self._get("v2/warnings/ipma", params)
        return data if isinstance(data, list) else []

    async def latest_earthquakes(
        self, region: str | None, locations: dict[str, list[str]] | None = None
    ) -> list[dict[str, Any]]:
        """Earthquakes of the last 7 days, optionally near the given locations."""
        base = {"region": region} if region else {}
        rows: dict[str, dict[str, Any]] = {}
        for params in batch_location_params(locations or {}, base):
            for quake in (await self._get("v2/seismic/events/latest", params)).get("data", []):
                rows[str(quake.get("id"))] = quake
        return list(rows.values())


def batch_location_params(locations: dict[str, list[str]], base: dict[str, str]) -> list[dict[str, str]]:
    """Query params for `locations`, split so each query string stays short.

    Names are joined with `|` (parish names contain commas). With no
    locations a single request with only `base` is made.
    """
    items = [(level, name) for level in LEVELS for name in locations.get(level, []) if name]
    if not items:
        return [dict(base)]

    batches: list[dict[str, str]] = []
    current: dict[str, list[str]] = {}

    def params_of(group: dict[str, list[str]]) -> dict[str, str]:
        return {**base, **{level: "|".join(names) for level, names in group.items()}}

    for level, name in items:
        candidate = {k: list(v) for k, v in current.items()}
        candidate.setdefault(level, []).append(name)
        if current and len(urlencode(params_of(candidate))) > MAX_QUERY_LENGTH:
            batches.append(params_of(current))
            current = {level: [name]}
        else:
            current = candidate
    batches.append(params_of(current))

    return batches
