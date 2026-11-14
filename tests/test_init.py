"""Setup, entities, requests and the events used for notifications."""

from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from .conftest import incident, quake, warning


def _state(hass: HomeAssistant, entity_id: str):
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state


async def _setup(hass, config_entry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def _tick(hass, minutes: int = 10) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=minutes))
    await hass.async_block_till_done()


async def test_entities_and_server_side_filters(hass: HomeAssistant, fake_api, config_entry) -> None:
    fake_api.incidents[:] = [
        incident("1", man=30),
        incident("2", district="Braga", concelho="Guimarães", kind="fma", natureza="Queda de árvore"),
        # Filtered out on the client: kind not chosen, municipality not chosen.
        incident("3", kind="urbanFire"),
        incident("4", district="Braga", concelho="Barcelos"),
    ]
    fake_api.warnings[:] = [warning("PTO", "orange"), warning("BRG", "yellow", "Precipitação")]
    fake_api.quakes[:] = [
        quake("q1", 3.1, "2026-11-14T08:00:00Z"),
        quake("q2", 2.0, "2026-11-14T09:00:00Z"),  # below the minimum
        quake("q3", None, "2026-11-14T10:00:00Z"),  # provisional
    ]
    fake_api.register()

    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    requests = {str(url.path): url.query for _, url, _, _ in fake_api.mock.mock_calls}
    assert requests["/v2/incidents/active"] == {
        "all": "1",
        "limit": "1000",
        "district": "Porto",
        "concelho": "Guimarães",
    }
    assert requests["/v2/warnings/ipma"] == {"area": "PTO,BRG"}
    assert requests["/v2/seismic/events/latest"] == {"region": "continente"}

    fires = _state(hass, "sensor.fogos_pt_porto_braga_active_fires")
    assert fires.state == "1"
    assert fires.attributes["incidents"][0]["url"] == "https://fogos.pt/fogo/1"
    assert _state(hass, "sensor.fogos_pt_porto_braga_other_active_incidents").state == "1"
    assert _state(hass, "sensor.fogos_pt_porto_braga_personnel").state == "50"
    assert _state(hass, "sensor.fogos_pt_porto_braga_ipma_warnings").state == "2"
    assert _state(hass, "sensor.fogos_pt_porto_braga_highest_warning_level").state == "orange"
    assert _state(hass, "binary_sensor.fogos_pt_porto_braga_orange_or_red_warning").state == "on"
    assert _state(hass, "binary_sensor.fogos_pt_porto_braga_fire_in_the_area").state == "on"

    last = _state(hass, "sensor.fogos_pt_porto_braga_last_earthquake")
    assert last.state == "3.1"
    assert last.attributes["count_7d"] == 1

    geo = [s for s in hass.states.async_all("geo_location") if s.attributes.get("source") == "fogos_pt"]
    assert len(geo) == 3  # two incidents and one earthquake


async def test_events_fire_for_changes_only(hass: HomeAssistant, fake_api, config_entry) -> None:
    fake_api.incidents[:] = [incident("1"), incident("2", statusCode=4, status="Despacho")]
    fake_api.warnings[:] = [warning("PTO", "yellow")]
    fake_api.quakes[:] = [quake("q1", 3.0, "2026-11-14T08:00:00Z")]
    fake_api.register()

    new_incident = async_capture_events(hass, "fogos_pt_new_incident")
    status = async_capture_events(hass, "fogos_pt_incident_status_changed")
    ended = async_capture_events(hass, "fogos_pt_incident_ended")
    new_warning = async_capture_events(hass, "fogos_pt_new_warning")
    new_quake = async_capture_events(hass, "fogos_pt_new_earthquake")

    await _setup(hass, config_entry)
    # Nothing is "new" on start-up.
    assert not (new_incident or status or ended or new_warning or new_quake)

    fake_api.incidents[:] = [incident("2", statusCode=5, status="Em Curso"), incident("5", location="Fridão")]
    fake_api.warnings[:] = [warning("PTO", "red"), warning("BRG")]
    fake_api.quakes[:] = [quake("q2", 3.4, "2026-11-14T09:00:00Z"), quake("q1", 3.0, "2026-11-14T08:00:00Z")]
    fake_api.register()
    await _tick(hass)

    assert [e.data["id"] for e in new_incident] == ["5"]
    assert new_incident[0].data["location"] == "Fridão"
    assert new_incident[0].data["entry_id"] == config_entry.entry_id
    assert [(e.data["id"], e.data["previous_status"]) for e in status] == [("2", "Despacho")]
    assert [e.data["id"] for e in ended] == ["1"]
    assert sorted((e.data["area"], e.data["level"]) for e in new_warning) == [("BRG", "yellow"), ("PTO", "red")]
    assert [e.data["id"] for e in new_quake] == ["q2"]

    geo_ids = {s.attributes["id"] for s in hass.states.async_all("geo_location")}
    assert geo_ids == {"2", "5", "q1", "q2"}


async def test_rejected_key_starts_reauth(hass: HomeAssistant, fake_api, config_entry) -> None:
    fake_api.status = 403
    fake_api.register()

    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_unload(hass: HomeAssistant, fake_api, config_entry) -> None:
    await _setup(hass, config_entry)

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.NOT_LOADED
