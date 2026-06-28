# Gombe Desertification & Afforestation Intelligence Twin — Version 5

Version 5 preserves the Version 4 immersive command centre and all temporal, drought, radar, restoration, carbon, risk, field and prediction services, while adding a dedicated live digital twin for every Local Government Area in Gombe State.

The application contains **11 LGA-scoped service modules** inside one FastAPI deployment. This gives each LGA an isolated page, route, API namespace, WebSocket stream, satellite cache, environmental textures and local scenario laboratory without requiring eleven separate Render services.

The platform remains evidence-aware: satellite observations, provider weather, external context, local interpolation and scenario-derived values are labelled separately. It works without credentials using clearly labelled deterministic demonstration data.

## Eleven dedicated LGA twins

| Local government | Dedicated route |
|---|---|
| Akko | `/lga/akko` |
| Balanga | `/lga/balanga` |
| Billiri | `/lga/billiri` |
| Dukku | `/lga/dukku` |
| Funakaye | `/lga/funakaye` |
| Gombe | `/lga/gombe` |
| Kaltungo | `/lga/kaltungo` |
| Kwami | `/lga/kwami` |
| Nafada | `/lga/nafada` |
| Shongom | `/lga/shongom` |
| Yamaltu/Deba | `/lga/yamaltu-deba` |

Dukku, Funakaye, Gombe, Kwami and Nafada retain the brighter **northern-focus** classification used by the Great Green Wall analysis. The remaining LGAs receive the same local-twin capabilities and are explicitly identified as wider Gombe State LGAs.

## What each LGA twin contains

Every LGA page has its own:

- exact administrative boundary and fitted local 3D map;
- on-demand LGA-scoped Sentinel-2 NDVI mosaic;
- live or demonstration weather at the LGA centroid;
- provider weather forecast;
- animated sun, moon, stars, clouds, rain and wind-responsive sky;
- automatic orbit and cloud-flow camera tracking;
- procedural trees driven by local vegetation condition;
- NDVI, land-state, land-cover, suitability and combined-risk layers;
- vegetation, desert-pressure, moisture and restoration indicators;
- local rainfall and drought context;
- local NASA FIRMS thermal-anomaly context;
- local project-registry and field-observation records;
- carbon and ecosystem-service screening;
- local timeline and weather charts;
- evidence-grounded interpretations, provenance and limitations;
- alerts and environmental events;
- interactive local scenario laboratory;
- previous/next LGA navigation and a complete LGA directory.

The LGA selector and directory make it possible to move between all eleven twins without losing the state-level command centre.

## LGA service architecture

Each LGA has a dedicated service namespace:

```text
/lga/{slug}
/api/lga-twins/{slug}/snapshot
/api/lga-twins/{slug}/boundary
/api/lga-twins/{slug}/textures/{layer}.png
/api/lga-twins/{slug}/scenario
/api/lga-twins/{slug}/projects
/api/lga-twins/{slug}/field-observations
/ws/lga/{slug}
```

An administrator can force an LGA-specific Sentinel-2 refresh with:

```text
POST /api/admin/lga-twins/{slug}/refresh-satellite
```

This action uses the same protected bearer-token workflow as the other Version 4 administrator functions.

### Environmental texture layers

The local texture endpoint accepts:

- `ndvi` — Sentinel-2 greenness;
- `simulation` — vegetation, desert pressure and committed barriers;
- `landcover` — transparent derived land-cover screening;
- `suitability` — local restoration-opportunity screening;
- `risk` — fire, wind erosion, runoff and infiltration attention.

All textures are masked to the selected LGA boundary. Neighbouring LGAs are not painted by the local raster.

## Local scenario laboratory

Every LGA page can run an independent experiment using:

- aridity pressure;
- grazing pressure;
- rainfall support;
- restoration effort;
- barrier maintenance;
- experiment duration.

The service returns vegetation, desert-pressure and barrier trajectories plus net changes. These are **scenario experiments**, not operational forecasts.

## Existing state-wide services retained

| Service | Route | Purpose |
|---|---|---|
| Immersive Live Twin | `/` | Full-state 3D terrain, live sky, vegetation, weather and command-centre metrics |
| LGA Twin Directory | `/areas` | Select any of the 11 dedicated local twins |
| Service Portal | `/services` | Navigation to every platform service |
| Weather & Sky | `/weather` | Live sun/moon/stars, cloud movement, rainfall, wind and forecast context |
| Sentinel-2 NDVI | `/satellite` | Satellite greenness, valid coverage and texture interpretation |
| Temporal Intelligence | `/timeline` | Seasonal playback, change detection and protected Sentinel-2 backfill |
| Rainfall & Drought | `/drought` | 7/30/90/365-day rainfall, dry spells, onset and moisture balance |
| Land-Cover Intelligence | `/landcover` | Environmental class probabilities and confidence |
| Sentinel-1 Radar | `/radar` | Cloud-independent VV/VH/RVI evidence |
| Cellular Simulation | `/simulation` | Transparent desertification/restoration scenarios |
| Restoration Intelligence | `/restoration` | Suitability screening and route optimisation |
| Green Wall Planner | `/planner` | Draw and commit scenario corridors |
| Carbon & Ecosystems | `/ecosystems` | Biomass/carbon screening and ecosystem indicators |
| Risk Intelligence | `/risks` | Fire, erosion, runoff, infiltration and exposure layers |
| Scenario Workspace | `/scenarios` | Compare restoration, drought, grazing, maintenance and fire scenarios |
| Field Verification | `/field` | Geotagged observations and review workflow |
| Project Registry | `/projects` | Restoration projects, planting targets and inspections |
| Explainable Prediction | `/predictions` | Protected model retraining, forecasts and feature importance |
| Satellite-to-Ground Compare | `/compare` | Synchronized satellite, classification and immersive views |
| Evidence & Limitations | `/evidence` | Source provenance, assumptions and caveats |

## Source interpretation

### Sentinel-2

With Copernicus credentials, each LGA requests a cloud-masked Sentinel-2 Level-2A mosaic for its own bounding box. NDVI is calculated from B08 and B04. A failed, cloudy or unavailable request falls back to a deterministic LGA-specific surface labelled `demo`.

### Weather

OpenWeather current conditions and forecast are requested at the LGA centroid. The animated sky and camera respond to reported cloud cover, rain, wind, visibility, sunrise and sunset. Animated clouds represent wind-driven atmospheric visualisation, not the tracked boundary of a physical cloud.

### Rainfall and drought

Open-Meteo historical/reanalysis context is requested per LGA centroid and cached separately. If unavailable, the platform uses labelled fallback context. Screening values are not official drought declarations.

### Fire and heat

NASA FIRMS detections are filtered to the LGA or nearby context. A thermal anomaly does not establish its cause, size, permanence or land damage.

### Land cover, risk and suitability

Unless an external validated dataset is configured, these are transparent screening interpretations derived from NDVI, weather, rainfall, terrain-gradient proxies, model state and thermal context. They are not cadastral, ecological or engineering surveys.

### Carbon

LGA carbon and ecosystem values are wide-uncertainty screening estimates. They are not certified biomass inventories or carbon-credit calculations.

## Project structure

```text
gombe_desertification_afforestation_twin/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── services/
│   │   ├── lga_twins.py          # Version 5 LGA-scoped service facade
│   │   ├── enhanced_runtime.py
│   │   ├── sentinel.py
│   │   ├── rainfall.py
│   │   ├── weather.py
│   │   ├── intelligence.py
│   │   ├── prediction.py
│   │   └── ...
│   └── static/
│       ├── lga-twin.html         # reusable dedicated LGA interface
│       ├── areas.html            # LGA twin directory
│       ├── index.html            # state command centre
│       ├── css/styles.css
│       └── js/
│           ├── lga-twin.js
│           ├── areas.js
│           ├── twin.js
│           └── ...
├── tests/
├── .env.example
├── Procfile
├── Dockerfile
├── requirements.txt
└── run.py
```

## Credentials

Copy the template:

```powershell
Copy-Item .env.example .env
```

### Copernicus Data Space

```dotenv
COPERNICUS_CLIENT_ID=your_client_id
COPERNICUS_CLIENT_SECRET=your_client_secret
COPERNICUS_TOKEN_URL=https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token
COPERNICUS_PROCESS_URL=https://sh.dataspace.copernicus.eu/process/v1
```

These credentials support both state-level and on-demand LGA-level Sentinel-2 processing, plus optional Sentinel-1 radar.

### Global Forest Watch

```dotenv
GFW_API_KEY=your_api_key
GFW_ORIGIN=http://localhost
GFW_DATASET=umd_tree_cover_loss
GFW_DATASET_VERSION=latest
```

For Render, use the exact public origin:

```dotenv
GFW_ORIGIN=https://your-service.onrender.com
```

### OpenWeather

```dotenv
OPENWEATHER_API_KEY=your_key
OPENWEATHER_CURRENT_URL=https://api.openweathermap.org/data/2.5/weather
OPENWEATHER_FORECAST_URL=https://api.openweathermap.org/data/2.5/forecast
OPENWEATHER_TILE_URL=https://tile.openweathermap.org/map/{layer}/{z}/{x}/{y}.png
```

### NASA FIRMS

```dotenv
NASA_FIRMS_MAP_KEY=your_map_key
NASA_FIRMS_SOURCE=VIIRS_SNPP_NRT
```

### Protected administration

There is no default password. Configure one only in `.env` or Render:

```dotenv
ADMIN_PASSWORD=your-long-private-password
```

The preferred method is a SHA-256 hash:

```powershell
python -c "import getpass,hashlib; print(hashlib.sha256(getpass.getpass('Admin password: ').encode()).hexdigest())"
```

Then configure:

```dotenv
ADMIN_PASSWORD=
ADMIN_PASSWORD_SHA256=generated_hash
```

Never commit `.env`, access tokens, API keys or passwords.

## Run locally

```powershell
cd A:\gombe_desertification_afforestation_twin

python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m pytest -q
python run.py
```

Open the directory:

```text
http://127.0.0.1:8000/areas
```

Or open a dedicated local twin directly:

```text
http://127.0.0.1:8000/lga/dukku
```

Perform a hard browser refresh after replacing an earlier version:

```text
Ctrl + F5
```

## Upgrade an existing Version 4 repository

Back up the environment file:

```powershell
cd A:\gombe_desertification_afforestation_twin
Copy-Item .env A:\green_wall_env_backup.txt -Force
```

Extract Version 5:

```powershell
Expand-Archive `
    A:\gombe_desertification_afforestation_twin_v5_lga_microservices.zip `
    -DestinationPath A:\green_wall_v5_update `
    -Force
```

Copy the update while preserving `.git`, `.env` and `.venv`:

```powershell
robocopy `
    A:\green_wall_v5_update\gombe_desertification_afforestation_twin_v5_lga_microservices `
    A:\gombe_desertification_afforestation_twin `
    /E `
    /XD .git .venv `
    /XF .env
```

Restore the environment file:

```powershell
Copy-Item `
    A:\green_wall_env_backup.txt `
    A:\gombe_desertification_afforestation_twin\.env `
    -Force
```

## Push to GitHub

```powershell
cd A:\gombe_desertification_afforestation_twin

git status
git add -A
git commit -m "Add dedicated digital twins for all eleven Gombe LGAs"
git pull origin main --rebase
git push origin main
```

Render will redeploy automatically when automatic deployment is enabled.

## Render deployment

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

One Render service hosts the state twin and all eleven LGA twins. This avoids eleven idle services while retaining separate routes, APIs, WebSockets and caches.

## Persistence note

Field records, projects, timeline history and trained models use local storage by default. Render Free uses an ephemeral filesystem, so durable public deployment requires a managed database or persistent disk. Committed scenario barriers also reset when the server restarts unless they are stored externally.

## Testing

```powershell
python -m pytest -q
```

Version 5 tests verify:

- all 11 Gombe LGAs;
- the LGA page and API namespaces;
- the dedicated LGA WebSocket;
- all five local environmental textures;
- LGA selector and navigation controls;
- local scenario experiments;
- JavaScript syntax;
- unique HTML IDs;
- all pre-existing Version 4 intelligence services.

## Operational notice

This is a research, education and planning-support platform. It is not a cadastral system, certified forest inventory, official drought declaration, emergency warning service, carbon-credit verifier or substitute for field surveys, local government records, community consultation and professional ecological assessment.
