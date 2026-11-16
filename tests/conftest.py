"""Fixtures: API payloads and a mocked Fogos.pt API."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.fogos_pt.const import (
    CONF_CONCELHOS,
    CONF_DISTRICTS,
    CONF_FREGUESIAS,
    CONF_KINDS,
    CONF_MIN_MAGNITUDE,
    CONF_RADIUS,
    CONF_SEISMIC_NEAR_SELECTION,
    CONF_SEISMIC_REGION,
    CONF_WARNING_AREAS,
    DOMAIN,
)

API = "https://api.fogos.pt"

LOCATIONS = [
    {
        "district": "Braga",
        "concelhos": [
            {"concelho": "Guimarães", "dico": "0308", "freguesias": ["Azurém", "Creixomil"]},
            {"concelho": "Barcelos", "dico": "0302", "freguesias": ["Areias"]},
        ],
    },
    {
        "district": "Ilha Da Madeira",
        "concelhos": [{"concelho": "Funchal", "dico": "3103", "freguesias": ["Sé"]}],
    },
    {
        "district": "Porto",
        "concelhos": [{"concelho": "Amarante", "dico": "1301", "freguesias": ["Telões"]}],
    },
]

AREAS = [
    {"code": "BRG", "name": "Braga", "region": "continente", "districts": ["Braga"], "concelhos": []},
    {"code": "PTO", "name": "Porto", "region": "continente", "districts": ["Porto"], "concelhos": []},
    {
        "code": "MCN",
        "name": "Madeira - Costa Norte",
        "region": "madeira",
        "districts": ["Ilha da Madeira"],
        "concelhos": ["Porto Moniz", "São Vicente", "Santana"],
    },
    {
        "code": "MCS",
        "name": "Madeira - Costa Sul",
        "region": "madeira",
        "districts": ["Ilha da Madeira"],
        "concelhos": ["Funchal", "Calheta"],
    },
    {
        "code": "MRM",
        "name": "Madeira - Regiões Montanhosas",
        "region": "madeira",
        "districts": ["Ilha da Madeira"],
        "concelhos": [],
    },
]


def incident(incident_id: str, **fields: Any) -> dict[str, Any]:
    return {
        "id": incident_id,
        "district": "Porto",
        "concelho": "Amarante",
        "freguesia": "Telões",
        "location": "Telões",
        "natureza": "Mato",
        "naturezaCode": "3103",
        "kind": "fire",
        "status": "Em Curso",
        "statusCode": 5,
        "lat": 41.27,
        "lng": -8.08,
        "man": 20,
        "terrain": 5,
        "aerial": 1,
        "date": "14-11-2026",
        "hour": "10:00",
        **fields,
    }


def warning(area: str, level: str = "yellow", kind: str = "Vento") -> dict[str, Any]:
    return {
        "text": f"{kind} em {area}",
        "awarenessTypeName": kind,
        "idAreaAviso": area,
        "awarenessLevelID": level,
        "startTime": "2026-11-14T09:00:00",
        "endTime": "2026-11-14T21:00:00",
    }


def quake(quake_id: str, magnitude: float | None, time: str, **fields: Any) -> dict[str, Any]:
    return {
        "id": quake_id,
        "time": time,
        "lat": 41.3,
        "lon": -8.1,
        "depth": 10,
        "magnitude": magnitude,
        "place": "Amarante",
        "region": "continente",
        "felt": False,
        "nearest": {"name": "Telões", "municipality": "Amarante", "kind": "f", "km": 2.0, "bearing": "N"},
        **fields,
    }


OPTIONS = {
    CONF_DISTRICTS: ["Porto", "Braga"],
    CONF_CONCELHOS: ["Braga|Guimarães"],
    CONF_FREGUESIAS: [],
    CONF_WARNING_AREAS: ["PTO", "BRG"],
    CONF_KINDS: ["fire", "fma"],
    CONF_SEISMIC_REGION: "continente",
    CONF_MIN_MAGNITUDE: 2.5,
    CONF_RADIUS: 0,
    CONF_SEISMIC_NEAR_SELECTION: False,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN, title="Fogos.pt — Porto, Braga", data={"api_key": "secret"}, options=OPTIONS
    )


class FakeApi:
    """Mutable API payloads served through aioclient_mock."""

    def __init__(self, mock: AiohttpClientMocker) -> None:
        self.mock = mock
        self.incidents: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.quakes: list[dict[str, Any]] = []
        self.status = 200
        self.status_for: dict[str, int] = {}
        self.register()

    def _status(self, path: str) -> int:
        return self.status_for.get(path, self.status)

    def register(self) -> None:
        self.mock.clear_requests()
        self.mock._mocks.clear()
        self.mock.get(
            f"{API}/v2/incidents/locations",
            status=self._status("/v2/incidents/locations"),
            json={"success": True, "data": LOCATIONS},
        )
        self.mock.get(
            f"{API}/v2/warnings/ipma/areas",
            status=self._status("/v2/warnings/ipma/areas"),
            json={"success": True, "data": AREAS},
        )
        self.mock.get(
            f"{API}/v2/incidents/active",
            status=self._status("/v2/incidents/active"),
            json={"success": True, "data": self.incidents},
        )
        self.mock.get(f"{API}/v2/warnings/ipma", status=self._status("/v2/warnings/ipma"), json=self.warnings)
        self.mock.get(
            f"{API}/v2/seismic/events/latest",
            status=self._status("/v2/seismic/events/latest"),
            json={"success": True, "data": self.quakes},
        )


@pytest.fixture
def fake_api(aioclient_mock: AiohttpClientMocker) -> FakeApi:
    return FakeApi(aioclient_mock)
