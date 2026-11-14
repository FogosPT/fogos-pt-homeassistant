"""Location selection, incident kinds and distances (no Home Assistant imports)."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping

from .const import (
    API_KINDS,
    CONF_CONCELHOS,
    CONF_DISTRICTS,
    CONF_FREGUESIAS,
    KIND_FIRE,
    KIND_FMA,
    KIND_OTHER,
    KIND_OTHER_FIRE,
    KIND_TRANSPORT_FIRE,
    KIND_URBAN_FIRE,
    KINDS,
    NATUREZA_FIRE,
    NATUREZA_FMA,
    NATUREZA_OTHER_FIRE,
    NATUREZA_TRANSPORT_FIRE,
    NATUREZA_URBAN_FIRE,
    SEPARATOR,
)


def key(name: Any) -> str:
    """Case-insensitive comparison key (the API stores "Vila Nova De Gaia")."""
    return str(name or "").strip().casefold()


def join(*parts: str) -> str:
    return SEPARATOR.join(parts)


def split(value: str) -> list[str]:
    return value.split(SEPARATOR)


@dataclass(frozen=True)
class Selection:
    """Districts, municipalities and parishes chosen by the user.

    A district with chosen municipalities stands for those municipalities only,
    and a municipality with chosen parishes for those parishes only.
    """

    districts: tuple[str, ...] = ()
    concelhos: tuple[tuple[str, str], ...] = ()
    freguesias: tuple[tuple[str, str, str], ...] = ()
    _keys: dict[str, set] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> Selection:
        concelhos = tuple(
            (parts[0], parts[1]) for value in options.get(CONF_CONCELHOS, []) if len(parts := split(value)) == 2
        )
        freguesias = tuple(
            (parts[0], parts[1], parts[2])
            for value in options.get(CONF_FREGUESIAS, [])
            if len(parts := split(value)) == 3
        )
        return cls(tuple(options.get(CONF_DISTRICTS, [])), concelhos, freguesias)

    @property
    def is_empty(self) -> bool:
        return not (self.districts or self.concelhos or self.freguesias)

    def _effective(self) -> tuple[list[str], list[tuple[str, str]], list[tuple[str, str, str]]]:
        refined_districts = {key(d) for d, _ in self.concelhos} | {key(d) for d, _, _ in self.freguesias}
        refined_concelhos = {(key(d), key(c)) for d, c, _ in self.freguesias}

        districts = [d for d in self.districts if key(d) not in refined_districts]
        concelhos = [(d, c) for d, c in self.concelhos if (key(d), key(c)) not in refined_concelhos]
        return districts, concelhos, list(self.freguesias)

    def query(self) -> dict[str, list[str]]:
        """The most specific level of each branch, as API filter params."""
        districts, concelhos, freguesias = self._effective()
        return {
            "district": list(dict.fromkeys(districts)),
            "concelho": list(dict.fromkeys(c for _, c in concelhos)),
            "freguesia": list(dict.fromkeys(f for _, _, f in freguesias)),
        }

    def matches(self, incident: Mapping[str, Any]) -> bool:
        """Whether an incident is in the selection (the API filter is by name
        only, so a municipality name shared by two districts matches both)."""
        if self.is_empty:
            return True
        if not self._keys:
            districts, concelhos, freguesias = self._effective()
            self._keys["d"] = {key(d) for d in districts}
            self._keys["c"] = {(key(d), key(c)) for d, c in concelhos}
            self._keys["f"] = {(key(d), key(c), key(f)) for d, c, f in freguesias}

        d, c, f = key(incident.get("district")), key(incident.get("concelho")), key(incident.get("freguesia"))
        return d in self._keys["d"] or (d, c) in self._keys["c"] or (d, c, f) in self._keys["f"]


def incident_kind(incident: Mapping[str, Any]) -> str:
    """The incident category, from `kind` or else from `naturezaCode`."""
    kind = incident.get("kind")
    kind = API_KINDS.get(kind, kind)
    if kind in KINDS:
        return kind

    code = str(incident.get("naturezaCode") or "")
    if incident.get("isFire") or code in NATUREZA_FIRE:
        return KIND_FIRE
    if code in NATUREZA_URBAN_FIRE:
        return KIND_URBAN_FIRE
    if code in NATUREZA_TRANSPORT_FIRE:
        return KIND_TRANSPORT_FIRE
    if code in NATUREZA_OTHER_FIRE:
        return KIND_OTHER_FIRE
    if code in NATUREZA_FMA:
        return KIND_FMA
    return KIND_OTHER


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
