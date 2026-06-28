# Gombe Desertification & Afforestation Digital Twin — Version 2.0

A responsive FastAPI, MapLibre and Three.js environmental digital twin for exploring vegetation condition, desertification pressure, current weather and afforestation scenarios across **the complete Gombe State boundary**, with a clearly highlighted **northern Gombe focus**.

The northern analysis focus contains:

- Dukku
- Funakaye
- Gombe
- Kwami
- Nafada

All eleven Gombe State local government areas remain visible and selectable for geographic context:

- Akko
- Balanga
- Billiri
- Dukku
- Funakaye
- Gombe
- Kaltungo
- Kwami
- Nafada
- Shongom
- Yamaltu/Deba

## Version 2.0 improvements

### Complete Gombe State and clear northern focus

- The main twin initially fits the complete Gombe State boundary.
- The state boundary is drawn with a strong luminous outline.
- Every LGA has a boundary, centre marker and label.
- Northern-focus LGAs use brighter outlines and a separate focus tint.
- **State** and **North** controls switch between the complete state and northern analysis extent.
- Satellite and cellular-model textures are clipped to the northern LGA geometry, so the old rectangular overlay no longer covers neighbouring states.
- The LGA Explorer provides a dedicated selection panel for all eleven LGAs.

### Live weather and sky scene

The new Weather & Sky service and main-twin atmosphere respond to current OpenWeather values when an API key is configured:

- temperature and feels-like temperature;
- humidity;
- pressure;
- wind speed, gust and direction;
- cloud cover;
- one-hour rainfall;
- visibility;
- weather condition;
- sunrise, sunset and daylight state.

The live visual layer includes:

- a visible sun during reported daylight;
- a moon and twinkling stars outside the reported daylight period;
- clouds whose visible population follows reported cloud cover;
- cloud drift and wind streamlines driven by reported wind speed and direction;
- rain streaks when rainfall or a rain weather code is reported;
- a visibility haze when reported visibility is reduced.

These are animated visual representations of current observations. They are not Doppler radar or a complete state-wide numerical weather field.

### More natural 3D vegetation

- The previous synthetic demonstration shelterbelt has been removed.
- Natural vegetation candidates are derived from the cellular vegetation state assimilated from NDVI.
- Planned trees appear only after a corridor is explicitly committed.
- Procedural trees use trunks, branches and multi-lobed crowns rather than flat white symbols.
- Height, crown size and colour respond to modelled vegetation health.
- Tree crowns and branches sway continuously according to the current wind speed and direction.
- The tree renderer is instanced for improved performance.

The 3D trees are a visualisation of model state. They are not detections or an inventory of individual real trees.

### Improved Green Wall Planner

- Draft points exist only in the current browser page.
- A refresh, page reopen or successful submission clears the draft automatically.
- Draft points cannot be placed outside the highlighted northern-focus LGAs.
- A committed corridor is clearly distinguished from an unsaved draft.
- Committed barriers remain only in the running in-memory scenario.
- Dedicated controls remove all committed barriers or reset the entire simulation.
- Server restart/redeployment also clears the in-memory intervention scenario.

### Live progressive cellular simulation

Current weather contributes bounded atmospheric forcing to the scenario:

- recent rain and humidity contribute to moisture support;
- high temperature and wind contribute to heat/drying stress;
- weather forcing affects vegetation growth, desert pressure, moisture and planted-tree health progressively;
- the simulation can be paused, resumed and accelerated;
- updated textures and trees are streamed without reloading the MapLibre scene.

Weather forcing is not direct soil moisture, evapotranspiration or drought measurement. It is a transparent model input.

## Service pages

| Service | Route | Function |
|---|---|---|
| Live Twin | `/` | Full-state 3D context, northern NDVI/model textures, live sky, wind-blown trees and LGA inspection |
| LGA Explorer | `/areas` | Select any of the eleven LGAs and inspect local satellite, weather and simulation evidence |
| Weather & Sky | `/weather` | Animated daylight, night sky, clouds, rainfall, wind and model-weather forcing |
| Satellite NDVI | `/satellite` | Cloud-masked Sentinel-2 NDVI, vegetation classes, coverage and histogram |
| Simulation Lab | `/simulation` | Pause/run the cellular model and change explicit scenario assumptions |
| Green Wall Planner | `/planner` | Draw temporary drafts and commit/remove afforestation corridors |
| Evidence | `/evidence` | Data provenance, interpretation boundaries, assumptions and limitations |

## Data-source roles

### Copernicus Data Space Sentinel-2

The backend requests Sentinel-2 Level-2A data through the Sentinel Hub Process API and calculates:

```text
NDVI = (B08 - B04) / (B08 + B04)
```

The Scene Classification Layer is used to exclude no-data, cloud shadow, cloud, cirrus and snow/ice classes. The platform reports the observation window and retrieval time instead of inventing a precise scene time.

### Global Forest Watch

The Global Forest Watch Data API provides UMD tree-cover-loss context for the northern analysis area. Tree-cover loss is not automatically interpreted as desertification because it does not establish the cause, permanence or final land-cover state.

### OpenWeather

OpenWeather current weather drives the live sky and bounded simulation forcing. When no key is configured, the project uses deterministic animated demonstration weather and labels it **DEMO**.

### geoBoundaries

Gombe State and LGA boundaries are fetched at startup. If the external geometry source is unavailable, the app uses labelled approximate fallback geometry so the interface continues to run.

## Scientific interpretation rules

The platform deliberately separates:

- **Observation:** Sentinel-2 NDVI and current weather values when live credentials work.
- **External context:** Global Forest Watch tree-cover-loss information.
- **Simulation:** cellular desert pressure, vegetation recovery and planted barriers.
- **Interpretation:** cautious statements based on the available evidence.
- **Limitation:** what the available data cannot establish.

Important distinctions:

- NDVI indicates spectral greenness; it is not a direct tree count, soil-fertility value or proof of desertification.
- Low NDVI may indicate sparse vegetation, bare soil, harvested land, built surfaces, seasonal senescence or cloud-quality effects.
- Weather modifies the scenario but does not replace soil, rainfall-gauge, groundwater, grazing or field-survival data.
- 3D trees represent modelled vegetation/tree-barrier state and are not mapped individual trees.
- Green Wall corridors are scenario interventions, not approved land-allocation or planting plans.

## Project structure

```text
gombe_desertification_afforestation_twin_v2_dynamic/
├── app/
│   ├── config.py
│   ├── main.py
│   ├── models.py
│   ├── services/
│   │   ├── boundary.py
│   │   ├── cellular.py
│   │   ├── geometry.py
│   │   ├── gfw.py
│   │   ├── insights.py
│   │   ├── runtime.py
│   │   ├── sentinel.py
│   │   ├── texture.py
│   │   └── weather.py
│   └── static/
│       ├── index.html
│       ├── areas.html
│       ├── weather.html
│       ├── satellite.html
│       ├── simulation.html
│       ├── planner.html
│       ├── evidence.html
│       ├── css/styles.css
│       └── js/
│           ├── common.js
│           ├── areas.js
│           ├── weather.js
│           ├── sky.js
│           ├── trees3d.js
│           ├── twin.js
│           ├── satellite.js
│           ├── simulation.js
│           ├── planner.js
│           └── evidence.js
├── tests/
├── .env.example
├── Dockerfile
├── Procfile
├── requirements.txt
└── run.py
```

## Run locally on Windows

```powershell
cd A:\gombe_desertification_afforestation_twin_v2_dynamic

python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
python run.py
```

Open:

```text
http://127.0.0.1:8000
```

Useful routes:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/areas
http://127.0.0.1:8000/weather
http://127.0.0.1:8000/planner
```

## Environment variables

```dotenv
# Copernicus Data Space / Sentinel Hub OAuth2
COPERNICUS_CLIENT_ID=
COPERNICUS_CLIENT_SECRET=
COPERNICUS_TOKEN_URL=https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token
COPERNICUS_PROCESS_URL=https://sh.dataspace.copernicus.eu/process/v1

# Global Forest Watch
GFW_API_KEY=
GFW_ORIGIN=http://localhost
GFW_DATASET=umd_tree_cover_loss
GFW_DATASET_VERSION=latest

# Current weather
OPENWEATHER_API_KEY=
OPENWEATHER_CURRENT_URL=https://api.openweathermap.org/data/2.5/weather
WEATHER_REFRESH_SECONDS=300
WEATHER_CACHE_SECONDS=240

# Northern Sentinel/model grid: west,south,east,north
AOI_BBOX=[10.55,10.20,11.85,11.55]
SENTINEL_LOOKBACK_DAYS=35
SENTINEL_MAX_CLOUD_PERCENT=35
SATELLITE_REFRESH_SECONDS=21600
GFW_REFRESH_SECONDS=43200

# Cellular simulation
SIMULATION_INTERVAL_SECONDS=1
BROADCAST_INTERVAL_SECONDS=1
SIMULATION_GRID_WIDTH=96
SIMULATION_GRID_HEIGHT=72
RANDOM_SEED=4106
DEBUG=false
```

The app works in clearly labelled demonstration mode if credentials are absent.

## Scheduled updates

Default schedules are:

- weather: every 5 minutes;
- Sentinel-2 NDVI: every 6 hours;
- Global Forest Watch context: every 12 hours;
- cellular simulation: every second;
- WebSocket live frame: every second.

Sentinel observations themselves update according to satellite acquisition and cloud availability; a six-hour API check does not imply a new cloud-free satellite scene every six hours.

## Key API endpoints

### Geography and areas

- `GET /api/boundary`
- `GET /api/lgas`
- `GET /api/northern-lgas`
- `GET /api/locations`
- `GET /api/areas`
- `GET /api/areas/{slug}`

### Live state

- `GET /api/health`
- `GET /api/snapshot`
- `GET /api/weather`
- `POST /api/weather/refresh`
- `WS /ws/live`

### Satellite and model

- `GET /api/ndvi/grid`
- `GET /api/ndvi/texture.png`
- `GET /api/simulation/texture.png`
- `GET /api/simulation/trees`
- `GET /api/history`
- `GET /api/methodology`
- `POST /api/simulation/scenario`
- `POST /api/simulation/run`
- `POST /api/simulation/speed`
- `POST /api/simulation/reset`

### Planner

- `POST /api/planner/corridor`
- `DELETE /api/planner/corridors`

## Deploy on Render

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Add secrets only in **Render → Environment**. Never commit `.env`.

The free Render filesystem is ephemeral. Runtime history and committed scenario interventions are lost after restart, spin-down or redeployment. Use persistent storage or an external database when durable scenario history is required.

## Push the upgrade to GitHub

After copying Version 2 over the existing independent project while preserving `.git` and `.env`:

```powershell
git status
git add -A
git commit -m "Add full Gombe geography live weather dynamic vegetation and improved planner"
git pull origin main --rebase
git push origin main
```

## Testing

```powershell
python -m pytest -q
```

JavaScript syntax:

```powershell
Get-ChildItem app\static\js\*.js | ForEach-Object { node --check $_.FullName }
```


