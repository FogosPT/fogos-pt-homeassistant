# CLAUDE.md

Home Assistant custom integration (HACS) `fogos_pt` for the Fogos.pt API (`https://api.fogos.pt`, header `X-API-Key`, validated at Cloudflare). Server side lives in `../fogosapi` (endpoints `v2/incidents/locations`, `v2/warnings/ipma/areas` and the `district`/`concelho`/`freguesia` filters were added there for this integration).

## Commands

No local Python 3.13 — tests run in docker:

```bash
# once (image with pytest-homeassistant-custom-component)
printf 'FROM python:3.13\nCOPY requirements_test.txt /tmp/\nRUN pip install -q -r /tmp/requirements_test.txt\n' | docker build -t fogos-ha-test -f - .
docker run --rm -v "$PWD":/app -w /app fogos-ha-test python -m pytest -q -p no:cacheprovider
# hassfest (amd64 only)
docker run --rm --platform linux/amd64 -v "$PWD:/github/workspace" ghcr.io/home-assistant/hassfest
```

## Layout / invariants

- `api.py` (aiohttp client, splits long location lists over several requests), `selection.py` (no HA imports: selection → query params, exact client-side match, kind fallback), `coordinator.py` (3 coordinators; events only after the first successful refresh), `config_flow.py` (steps shared by config + options flow via `_SelectionSteps`).
- Selected municipalities/parishes are stored as `District|Concelho[|Freguesia]` (a municipality name exists in two districts: Calheta).
- Kinds are snake_case (translation keys must be); the API's camelCase `kind` is mapped in `API_KINDS`.
- `strings.json` = `translations/en.json`; keep `translations/pt.json` in sync.
- Bump `manifest.json` `version` before tagging `vX.Y.Z` (the release workflow checks it).
