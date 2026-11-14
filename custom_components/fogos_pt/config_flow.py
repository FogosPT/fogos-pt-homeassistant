"""Config and options flows: API key, then locations, warning areas and filters."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import FogosApi, FogosApiError, FogosAuthError
from .const import (
    API_KEY_URL,
    CONF_CONCELHOS,
    CONF_DISTRICTS,
    CONF_FREGUESIAS,
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
    KINDS,
    SEISMIC_REGIONS,
)
from .selection import Selection, join, key, split

_LOGGER = logging.getLogger(__name__)

PLACEHOLDERS = {"api_url": API_KEY_URL}


def _multi(options: list[SelectOptionDict], translation_key: str | None = None) -> SelectSelector:
    config = SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.DROPDOWN, sort=False)
    if translation_key is not None:
        config["translation_key"] = translation_key
    return SelectSelector(config)


def default_warning_areas(areas: list[dict[str, Any]], selection: Selection) -> list[str]:
    """Areas covering the selected districts (islands included) and municipalities."""
    districts = {key(d) for d in selection.districts}
    districts |= {key(d) for d, _ in selection.concelhos} | {key(d) for d, _, _ in selection.freguesias}
    concelhos = {key(c) for _, c in selection.concelhos} | {key(c) for _, c, _ in selection.freguesias}

    codes = []
    for area in areas:
        area_districts = {key(d) for d in area.get("districts", [])}
        area_concelhos = {key(c) for c in area.get("concelhos", [])}
        if not area_districts & districts:
            continue
        # Madeira island: only the coast of the chosen municipalities (+ MRM,
        # which has no `concelhos` and covers the whole island).
        if area_concelhos and concelhos and not area_concelhos & concelhos:
            continue
        codes.append(area["code"])
    return codes


def build_title(selection: Selection) -> str:
    names = list(selection.districts)
    names += [c for _, c in selection.concelhos if c not in names]
    if not names:
        return "Fogos.pt"
    title = ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
    return f"Fogos.pt — {title}"


class _SelectionSteps:
    """Steps shared by the config and options flows.

    Needs self._api (set before `async_step_districts`), self._options (the
    options being built; existing values are the defaults) and `_async_finish`.
    """

    _api: FogosApi
    _options: dict[str, Any]
    _tree: list[dict[str, Any]] | None = None
    _areas: list[dict[str, Any]] | None = None

    async def _async_load(self) -> str | None:
        """Load locations and areas; the error key on failure."""
        try:
            if self._tree is None:
                self._tree = await self._api.locations()
            if self._areas is None:
                self._areas = await self._api.warning_areas()
        except FogosAuthError:
            return "invalid_auth"
        except FogosApiError:
            _LOGGER.debug("Fogos.pt API unreachable", exc_info=True)
            return "cannot_connect"
        return None

    def _set(self, conf: str, value: list[str]) -> None:
        """Store a location choice; a new choice re-suggests the warning areas."""
        if sorted(value) != sorted(self._options.get(conf, [])):
            self._options.pop(CONF_WARNING_AREAS, None)
        self._options[conf] = value

    def _districts(self) -> list[dict[str, Any]]:
        chosen = {key(d) for d in self._options.get(CONF_DISTRICTS, [])}
        return [d for d in self._tree or [] if key(d["district"]) in chosen]

    async def async_step_districts(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._set(CONF_DISTRICTS, user_input.get(CONF_DISTRICTS, []))
            chosen = {key(d) for d in self._options[CONF_DISTRICTS]}
            # Drop municipalities / parishes of districts no longer chosen.
            for conf in (CONF_CONCELHOS, CONF_FREGUESIAS):
                self._options[conf] = [v for v in self._options.get(conf, []) if key(split(v)[0]) in chosen]
            if not self._options[CONF_DISTRICTS]:
                return await self.async_step_warnings()
            return await self.async_step_concelhos()

        options = [SelectOptionDict(value=d["district"], label=d["district"]) for d in self._tree or []]
        return self.async_show_form(
            step_id="districts",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DISTRICTS, default=self._options.get(CONF_DISTRICTS, [])
                    ): _multi(options),
                }
            ),
        )

    async def async_step_concelhos(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._set(CONF_CONCELHOS, user_input.get(CONF_CONCELHOS, []))
            chosen = set(self._options[CONF_CONCELHOS])
            self._options[CONF_FREGUESIAS] = [
                v for v in self._options.get(CONF_FREGUESIAS, []) if join(*split(v)[:2]) in chosen
            ]
            if not chosen:
                return await self.async_step_warnings()
            return await self.async_step_freguesias()

        options = [
            SelectOptionDict(value=join(d["district"], c["concelho"]), label=f"{c['concelho']} ({d['district']})")
            for d in self._districts()
            for c in d["concelhos"]
        ]
        return self.async_show_form(
            step_id="concelhos",
            data_schema=vol.Schema(
                {vol.Optional(CONF_CONCELHOS, default=self._options.get(CONF_CONCELHOS, [])): _multi(options)}
            ),
        )

    async def async_step_freguesias(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._options[CONF_FREGUESIAS] = user_input.get(CONF_FREGUESIAS, [])
            return await self.async_step_warnings()

        chosen = set(self._options.get(CONF_CONCELHOS, []))
        options = [
            SelectOptionDict(value=join(d["district"], c["concelho"], f), label=f"{f} ({c['concelho']})")
            for d in self._districts()
            for c in d["concelhos"]
            if join(d["district"], c["concelho"]) in chosen
            for f in c.get("freguesias", [])
        ]
        if not options:
            return await self.async_step_warnings()
        return self.async_show_form(
            step_id="freguesias",
            data_schema=vol.Schema(
                {vol.Optional(CONF_FREGUESIAS, default=self._options.get(CONF_FREGUESIAS, [])): _multi(options)}
            ),
        )

    async def async_step_warnings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._options[CONF_WARNING_AREAS] = user_input.get(CONF_WARNING_AREAS, [])
            return await self.async_step_filters()

        areas = self._areas or []
        default = self._options.get(CONF_WARNING_AREAS)
        if default is None:
            default = default_warning_areas(areas, Selection.from_options(self._options))
        options = [SelectOptionDict(value=a["code"], label=f"{a['name']} ({a['code']})") for a in areas]
        return self.async_show_form(
            step_id="warnings",
            data_schema=vol.Schema({vol.Optional(CONF_WARNING_AREAS, default=default): _multi(options)}),
        )

    async def async_step_filters(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._options.update(user_input)
            return self._async_finish()

        o = self._options
        schema = vol.Schema(
            {
                vol.Required(CONF_KINDS, default=o.get(CONF_KINDS, DEFAULT_KINDS)): _multi(
                    [SelectOptionDict(value=k, label=k) for k in KINDS], translation_key=CONF_KINDS
                ),
                vol.Required(
                    CONF_SEISMIC_REGION, default=o.get(CONF_SEISMIC_REGION, DEFAULT_SEISMIC_REGION)
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=SEISMIC_REGIONS,
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key=CONF_SEISMIC_REGION,
                    )
                ),
                vol.Required(
                    CONF_MIN_MAGNITUDE, default=o.get(CONF_MIN_MAGNITUDE, DEFAULT_MIN_MAGNITUDE)
                ): NumberSelector(NumberSelectorConfig(min=0, max=9, step=0.1, mode=NumberSelectorMode.BOX)),
                vol.Required(CONF_RADIUS, default=o.get(CONF_RADIUS, DEFAULT_RADIUS)): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=2000, step=1, unit_of_measurement="km", mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_SEISMIC_NEAR_SELECTION, default=o.get(CONF_SEISMIC_NEAR_SELECTION, False)
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="filters", data_schema=schema)

    def _async_finish(self) -> ConfigFlowResult:
        raise NotImplementedError


API_KEY_SCHEMA = vol.Schema(
    {vol.Required(CONF_API_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
)


class FogosConfigFlow(_SelectionSteps, ConfigFlow, domain=DOMAIN):
    """Several entries may exist (e.g. home and a second house)."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str | None = None
        self._options = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY].strip()
            self._api = FogosApi(async_get_clientsession(self.hass), self._api_key)
            if (error := await self._async_load()) is None:
                return await self.async_step_districts()
            errors["base"] = error

        return self.async_show_form(
            step_id="user", data_schema=API_KEY_SCHEMA, errors=errors, description_placeholders=PLACEHOLDERS
        )

    def _async_finish(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title=build_title(Selection.from_options(self._options)),
            data={CONF_API_KEY: self._api_key},
            options=self._options,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            self._api = FogosApi(async_get_clientsession(self.hass), api_key)
            self._tree = self._areas = None
            if (error := await self._async_load()) is None:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_API_KEY: api_key}
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=API_KEY_SCHEMA,
            errors=errors,
            description_placeholders=PLACEHOLDERS,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> FogosOptionsFlow:
        return FogosOptionsFlow()


class FogosOptionsFlow(_SelectionSteps, OptionsFlow):
    """Change locations, warning areas and filters (not the API key)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self._options = dict(self.config_entry.options)
        self._api = FogosApi(async_get_clientsession(self.hass), self.config_entry.data[CONF_API_KEY])
        if (error := await self._async_load()) is not None:
            return self.async_abort(reason=error)
        return await self.async_step_districts()

    def _async_finish(self) -> ConfigFlowResult:
        self.hass.config_entries.async_update_entry(
            self.config_entry, title=build_title(Selection.from_options(self._options))
        )
        return self.async_create_entry(data=self._options)
