"""Config, options and reauth flows."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.fogos_pt.const import DOMAIN


async def test_full_flow(hass: HomeAssistant, fake_api) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": " secret "})
    assert result["step_id"] == "districts"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"districts": ["Ilha Da Madeira", "Porto"]}
    )
    assert result["step_id"] == "concelhos"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"concelhos": ["Ilha Da Madeira|Funchal"]}
    )
    assert result["step_id"] == "freguesias"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"freguesias": []})
    assert result["step_id"] == "warnings"
    schema_default = {str(k): k.default() for k in result["data_schema"].schema}
    assert sorted(schema_default["warning_areas"]) == ["MCS", "MRM", "PTO"]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"warning_areas": ["MCS", "PTO"]})
    assert result["step_id"] == "filters"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "kinds": ["fire"],
            "seismic_region": "none",
            "min_magnitude": 3,
            "radius": 0,
            "seismic_near_selection": False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Fogos.pt — Ilha Da Madeira, Porto, Funchal"
    assert result["data"] == {"api_key": "secret"}
    assert result["options"]["concelhos"] == ["Ilha Da Madeira|Funchal"]
    assert result["options"]["warning_areas"] == ["MCS", "PTO"]


async def test_invalid_key(hass: HomeAssistant, fake_api) -> None:
    fake_api.status = 401
    fake_api.register()

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "bad"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_unreachable(hass: HomeAssistant, fake_api) -> None:
    fake_api.status = 500
    fake_api.register()

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "x"})

    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow_changes_locations(hass: HomeAssistant, fake_api, config_entry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["step_id"] == "districts"

    result = await hass.config_entries.options.async_configure(result["flow_id"], {"districts": ["Porto"]})
    assert result["step_id"] == "concelhos"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"concelhos": []})
    assert result["step_id"] == "warnings"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"warning_areas": ["PTO"]})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "kinds": ["fire"],
            "seismic_region": "all",
            "min_magnitude": 2,
            "radius": 100,
            "seismic_near_selection": False,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options["districts"] == ["Porto"]
    # Braga's municipality was dropped with its district.
    assert config_entry.options["concelhos"] == []
    assert config_entry.title == "Fogos.pt — Porto"


async def test_reauth(hass: HomeAssistant, fake_api, config_entry) -> None:
    config_entry.add_to_hass(hass)

    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "new-key"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data["api_key"] == "new-key"
