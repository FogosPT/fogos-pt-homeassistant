"""The notification blueprints are valid automation blueprints."""

from pathlib import Path

import pytest
from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.util.yaml.loader import load_yaml

BLUEPRINTS = sorted((Path(__file__).parent.parent / "blueprints" / "automation" / "fogos_pt").glob("*.yaml"))


@pytest.mark.parametrize("path", BLUEPRINTS, ids=lambda p: p.name)
def test_blueprint_is_valid(path: Path) -> None:
    blueprint = Blueprint(load_yaml(path), expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)

    assert "notify_device" in blueprint.inputs
    assert blueprint.data["triggers"][0]["event_type"].startswith("fogos_pt_")


def test_there_are_three_blueprints() -> None:
    assert [p.name for p in BLUEPRINTS] == ["novo_aviso.yaml", "novo_incidente.yaml", "novo_sismo.yaml"]
