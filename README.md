# FortyGuard Product Evaluation — Automation Demo

A clean, **FortyGuard-only** automation built for the Automation Internship
product evaluation. It demonstrates real, end-to-end use of the FortyGuard
**Temperature API** and documents the **Dashboard** and **Temperature MCP**
alongside it.

> **One data provider.** No Open-Meteo, no Nominatim/OpenStreetMap geocoding,
> no third-party temperature source. The area of interest is a fixed GeoJSON
> polygon (or one you paste), and every temperature comes from the FortyGuard
> heatmap grid.

## What it does

1. (optional) reads your account plan/credits via `GET /v1/system/fetch-api-key-usage`.
2. submits a **single-hour** heatmap (`filter_type: 1` + `start_time`) over a
   small Downtown Phoenix AOI and polls `/v1/status/{activity_id}` until
   completed. The hourly basis is important: `env_params` is point-in-time.
3. extracts the **explicit area mean** from `stats_data.temperature_stats.mean`
   (falling back to a mean of per-tile `average_temperature` only when the
   statistics block is absent).
4. for each sample point, sources a **per-point temperature from the nearest
   heatmap tile** — `env_params` requires a `temperature` in Celsius, so this
   reads the most representative value from the heatmap grid rather than using
   a single area mean for every point.
5. submits `env_params` at those points (same date **and** hour) and polls until
   completed.
6. archives every completed result locally (identical requests are served from
   disk for free — results are deterministic), renders the heatmap, and writes a
   provenance-bearing summary.

## Project layout

```
fortyguard/            # the package (FortyGuard-only)
  config.py            # endpoints, granularity, plan ceilings, Phoenix AOI
  client.py            # submit / poll / env_params / usage
  parsing.py           # exact heatmap + env_params response parsing
  geo.py               # geodesic area, point-in-polygon, nearest tile
  archive.py           # local result cache (avoid re-billing)
  visualization.py     # local-only tile heatmap (matplotlib, no basemap)
cli.py                 # terminal pipeline
app.py                 # Streamlit UI (FortyGuard-only)
mcp/                   # MCP demo: README, config example, tools_list smoke test
tests/                 # pytest (parser + geo, no network)
```

## Setup

```bash
cd fortyguard-product-eval
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then set FORTYGUARD_API_KEY
```

## Run the terminal pipeline

```bash
# full pipeline: heatmap -> mean -> nearest-tile env_params (1 point)
python cli.py --yes

# choose the local hour (env_params is hourly; default 14:00)
python cli.py --time 14:00 --yes

# heatmap only (skip env_params)
python cli.py --temperature-only --yes

# also print account plan/credits first
python cli.py --usage --yes
```

The first run performs one heatmap request and one env_params request at the
AOI centre — a deliberately minimal, credit-conscious test. Increase sampling
gradually:

```bash
python cli.py --max-points 5 --yes
```

The script refuses more than 25 points and stops if the AOI exceeds the Basic
10 sq mi cap.

## Run the UI

```bash
streamlit run app.py
```

## Run the tests (no network, no credits)

```bash
pytest -q
```

## Plan limits (Basic vs Pro)

From the [official pricing page](https://www.fortyguard.com/api-pricing):

| Capability | Basic | Pro |
|---|---|---|
| Included credits / month | 1,000,000 | 5,000,000 |
| Heatmap generation | up to 10 mi² | up to 50 mi² |
| Environmental parameters | up to 3 user-selected | full access |
| Satellite / Street View segmentation | — | ✓ |
| Heat Intelligence | — | 2 of 5 |

This project stays inside Basic: the default AOI is ~0.08 sq mi and the default
selection is 3 environmental parameters. Your account's actual access is always
authoritative — call `python cli.py --usage` to check it.

## Honest caveats (the reviewer will appreciate these)

- **Empty heatmaps still cost credits.** A completed request can return
  `n_cells: 0` (out-of-coverage, sub-minimum AOI, or a date with no data) and
  is charged in full. This project detects and reports that instead of silently
  substituting a temperature.
- **`temperature` is Celsius** and is a required `env_params` input. This project
  sources it from the nearest heatmap tile, not a guessed value.
- **Failed tasks are not charged.** Per the docs, tasks that fail during
  processing (status `Failed`) do not consume credits; a *completed* empty result
  (`n_cells: 0`) is a different case and should be checked against your plan.
- **No external fallback.** If the heatmap carries no usable temperature, the
  pipeline fails closed rather than inventing or importing a value.
- The heatmap PNG is drawn from the returned tile polygons with no basemap, so
  no third-party map tiles are fetched.
