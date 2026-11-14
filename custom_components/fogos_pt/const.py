"""Constants for the Fogos.pt integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "fogos_pt"
ATTRIBUTION: Final = "Dados fornecidos por Fogos.pt"

API_BASE: Final = "https://api.fogos.pt"
API_KEY_HEADER: Final = "X-API-Key"
API_KEY_URL: Final = "https://fogos.pt/pt/api"
INCIDENT_URL: Final = "https://fogos.pt/fogo/{id}"

CONF_DISTRICTS: Final = "districts"
CONF_CONCELHOS: Final = "concelhos"
CONF_FREGUESIAS: Final = "freguesias"
CONF_WARNING_AREAS: Final = "warning_areas"
CONF_KINDS: Final = "kinds"
CONF_SEISMIC_REGION: Final = "seismic_region"
CONF_SEISMIC_NEAR_SELECTION: Final = "seismic_near_selection"
CONF_MIN_MAGNITUDE: Final = "min_magnitude"
CONF_RADIUS: Final = "radius"

# Selected municipalities / parishes are stored with their parents, joined by
# SEPARATOR ("Porto|Amarante", "Porto|Amarante|Telões"): the same municipality
# name exists in two districts (Calheta).
SEPARATOR: Final = "|"

KIND_FIRE: Final = "fire"
KIND_URBAN_FIRE: Final = "urban_fire"
KIND_TRANSPORT_FIRE: Final = "transport_fire"
KIND_OTHER_FIRE: Final = "other_fire"
KIND_FMA: Final = "fma"
KIND_OTHER: Final = "other"
# The API's `kind` (camelCase) → ours (translation keys must be snake_case).
API_KINDS: Final = {"urbanFire": "urban_fire", "transportFire": "transport_fire", "otherFire": "other_fire"}
KINDS: Final = [KIND_FIRE, KIND_URBAN_FIRE, KIND_TRANSPORT_FIRE, KIND_OTHER_FIRE, KIND_FMA, KIND_OTHER]
FIRE_KINDS: Final = {KIND_FIRE, KIND_URBAN_FIRE, KIND_TRANSPORT_FIRE, KIND_OTHER_FIRE}
DEFAULT_KINDS: Final = [KIND_FIRE]

# naturezaCode lists from fogosapi (app/Models/Incident.php), for responses
# without `kind`.
NATUREZA_FIRE: Final = {"3101", "3103", "3105", "3111", "3109", "4335"}
NATUREZA_URBAN_FIRE: Final = {str(code) for code in range(2101, 2130, 2)}
NATUREZA_TRANSPORT_FIRE: Final = {"2301", "2303", "2305", "2307"}
NATUREZA_OTHER_FIRE: Final = {"3201", "3203", "2201", "2203", "3107"}
NATUREZA_FMA: Final = {
    "3315", "3317", "3301", "4305", "3309", "2419", "3313", "3319", "3321", "3329", "4329", "4339",
}

SEISMIC_REGION_NONE: Final = "none"
SEISMIC_REGION_ALL: Final = "all"
SEISMIC_REGIONS: Final = [SEISMIC_REGION_ALL, "continente", "acores", "madeira", SEISMIC_REGION_NONE]
DEFAULT_SEISMIC_REGION: Final = SEISMIC_REGION_ALL
DEFAULT_MIN_MAGNITUDE: Final = 2.5
DEFAULT_RADIUS: Final = 0

WARNING_LEVELS: Final = {"green": 0, "yellow": 1, "orange": 2, "red": 3}

INCIDENTS_INTERVAL: Final = timedelta(seconds=60)
WARNINGS_INTERVAL: Final = timedelta(minutes=5)
SEISMIC_INTERVAL: Final = timedelta(minutes=2)

# Most items kept in a sensor's list attribute (the state machine limits size).
MAX_ATTRIBUTE_ITEMS: Final = 50

EVENT_NEW_INCIDENT: Final = f"{DOMAIN}_new_incident"
EVENT_INCIDENT_STATUS_CHANGED: Final = f"{DOMAIN}_incident_status_changed"
EVENT_INCIDENT_ENDED: Final = f"{DOMAIN}_incident_ended"
EVENT_NEW_WARNING: Final = f"{DOMAIN}_new_warning"
EVENT_NEW_EARTHQUAKE: Final = f"{DOMAIN}_new_earthquake"
