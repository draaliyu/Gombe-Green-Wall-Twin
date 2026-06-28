# Gombe Desertification & Afforestation Intelligence Twin — Version 4

Version 4 extends the immersive Gombe command centre into a multi-service restoration-intelligence platform. It combines Earth-observation evidence, weather and rainfall context, scenario modelling, field verification, project monitoring, intervention screening, explainable forecasting and cinematic ground/sky visualisation in one FastAPI deployment.

The application continues to run without credentials using clearly labelled demonstration or derived data. Live and external products are never silently substituted for modelled values.

## Service portal

| Service | Route | Purpose |
|---|---|---|
| Immersive Live Twin | `/` | Full-state 3D terrain, live sky, vegetation, wind, weather and command-centre metrics |
| Service Portal | `/services` | Navigation to every analytical service |
| Gombe LGA Explorer | `/areas` | Evidence and model summaries for all 11 LGAs |
| Weather & Sky | `/weather` | Live sun/moon/stars, cloud movement, rainfall, wind and forecast context |
| Sentinel-2 NDVI | `/satellite` | Satellite greenness, quality coverage and texture interpretation |
| Temporal Intelligence | `/timeline` | Seasonal playback, change detection and protected Sentinel-2 backfill |
| Rainfall & Drought | `/drought` | 7/30/90/365-day rainfall, dry spells, onset and moisture balance |
| Land-Cover Intelligence | `/landcover` | Nine-class land-cover probabilities and confidence |
| Sentinel-1 Radar | `/radar` | Cloud-independent VV/VH/RVI structural and moisture evidence |
| Cellular Simulation | `/simulation` | Transparent desertification/restoration cellular-automata scenarios |
| Restoration Intelligence | `/restoration` | Suitability screening, route optimisation and intervention comparison |
| Green Wall Planner | `/planner` | Draw and commit temporary scenario corridors |
| Carbon & Ecosystems | `/ecosystems` | Biomass/carbon screening and ecosystem-service indicators |
| Risk Intelligence | `/risks` | Fire, erosion, runoff, infiltration and exposure layers |
| Scenario Workspace | `/scenarios` | Baseline, restoration, drought, grazing, maintenance and fire comparisons |
| Field Verification | `/field` | Geotagged field observations and review workflow |
| Project Registry | `/projects` | Restoration projects, planting targets and inspections |
| Explainable Prediction | `/predictions` | Protected model retraining, forecasts, uncertainty and feature importance |
| Satellite-to-Ground Compare | `/compare` | Synchronized satellite, classified and immersive model views |
| Evidence & Limitations | `/evidence` | Source provenance, assumptions and scientific caveats |

## Version 4 capabilities

### 1. Time travel and seasonal change

- Monthly NDVI, vegetation, desert pressure and rainfall playback.
- Wet-season versus dry-season comparison.
- Year-on-year greening, browning or stable/seasonal classification.
- Before/after swipe visualisation.
- Protected Sentinel-2 historical backfill for administrators.
- Transparent fallback reconstruction when a true historical satellite archive has not yet been collected.

The fallback timeline is labelled `derived`; it is not presented as historical satellite observation.

### 2. Rainfall and drought intelligence

Open-Meteo historical/reanalysis data are used without an API key when the service is reachable. The page reports:

- 7-, 30-, 90- and 365-day rainfall totals;
- consecutive dry days;
- monthly rainfall history;
- approximate rainy-season onset;
- rainfall support and water-balance screens;
- vegetation-response interpretation;
- current source mode and retrieval time.

These indicators are screening metrics and are not official drought declarations.

### 3. Land-cover intelligence beyond NDVI

The platform supports nine classes:

- water;
- trees;
- grass;
- flooded vegetation;
- crops;
- shrub/scrub;
- built area;
- bare ground;
- snow/ice.

When `DYNAMIC_WORLD_STATS_URL` is configured, externally prepared Dynamic World statistics can be supplied. Otherwise, the platform produces a clearly labelled `derived` probability layer using NDVI, Sentinel-1 RVI and scenario state. The derived layer is not represented as a Google Dynamic World observation.

### 4. Cloud-independent Sentinel-1 evidence

The radar service uses Sentinel-1 GRD through the Copernicus Sentinel Hub Process API and provides:

- VV backscatter;
- VH backscatter;
- Radar Vegetation Index proxy;
- a radar evidence texture;
- interpretation of structural/moisture change;
- an explicit source and limitation notice.

This complements Sentinel-2 during cloudy periods. Radar response is not a direct soil-moisture measurement without calibration.

### 5. Restoration suitability and route optimisation

The suitability engine combines transparent weighted screens for:

- current vegetation and desert pressure;
- modelled moisture support;
- settlement/access proximity;
- terrain-gradient proxy;
- 90-day rainfall support;
- avoidance of nearby thermal anomalies.

The route optimiser proposes three alternatives:

- maximum restoration benefit;
- lowest maintenance burden;
- balanced protection route.

Each route includes coordinates, length, mean suitability and an explanation. These are planning screens only. They do not determine land tenure, consent, soil chemistry, groundwater, planting species, cost or legal feasibility.

### 6. Species and restoration lifecycle

Configurable species profiles provide example planning attributes for drought tolerance, establishment requirements and ecological/livelihood value. The cellular simulation represents:

- seedling establishment;
- barrier growth;
- stress;
- maintenance;
- grazing pressure;
- drought mortality;
- fire disturbance;
- recovery and replanting scenarios.

Species profiles must be validated by local forestry, soil and community experts before operational use.

### 7. Biomass, carbon and ecosystem services

The ecosystem service reports:

- above-ground biomass screen;
- carbon-stock screen;
- projected annual carbon gain;
- uncertainty range;
- water-retention support;
- wind-erosion protection;
- soil-retention support;
- habitat-connectivity support;
- shade and shelter support.

Optional GEDI context can be supplied through `GEDI_CONTEXT_URL` or reference values. Without it, values remain modelled screening estimates. They are not certified carbon-credit calculations.

### 8. Fire, erosion, runoff and infiltration risk

NASA FIRMS thermal anomalies can be integrated with current model state. The risk service visualises:

- nearby thermal anomalies;
- vegetation/fire exposure;
- wind-aligned risk context;
- erosion pressure;
- runoff potential;
- infiltration support;
- combined attention score.

A FIRMS detection is a satellite thermal anomaly and does not by itself establish the cause, land damage or active wildfire status.

### 9. Field verification and project registry

Authorised users can create geotagged field observations with:

- observer;
- coordinates and LGA;
- observation type;
- tree count;
- survival percentage;
- species and condition;
- notes and optional photo URL;
- review status: pending, verified, rejected or needs review.

Restoration projects can record:

- project name and organisation;
- LGA and geometry;
- target/planted trees;
- species;
- funding source and manager;
- status;
- inspections, survival, maintenance, grazing and fire damage.

Local records are stored in SQLite by default.

### 10. Explainable forecasting

A compact ridge-regression model predicts the next monthly mean NDVI from:

- seasonal terms;
- rainfall;
- lagged NDVI;
- lagged desert pressure;
- lagged vegetation fraction.

The service reports:

- validation MAE, RMSE and R²;
- forecast intervals;
- feature importance;
- training mode;
- sample count;
- limitations.

Retraining is administrator-protected. A model trained on derived/demo history is explicitly labelled experimental and must not be treated as an operational land forecast.

### 11. Immersive visualisation

The live command centre retains and extends:

- full Gombe State and northern-focus views;
- all 11 LGA boundaries and labels;
- 3D terrain and globe modes;
- automatic orbit enabled on load;
- wind-driven cloud-follow camera target;
- sun movement during daytime;
- moon and stars at night;
- moving cloud layers, rain, thunder and haze;
- procedural trees with wind sway and health-sensitive growth;
- first-person and split satellite/ground views;
- event-focused cinematic camera;
- mobile economy rendering and reduced-motion support.

Cloud tracking follows a modelled wind-driven cloud-flow target; it does not track one physically identified cloud object.

## Data provenance vocabulary

Every analytical service uses explicit labels:

- **Observed** — directly returned by an external provider or collected field record.
- **External evidence** — externally prepared context, such as supplied Dynamic World or GEDI statistics.
- **Recorded** — observations/model frames saved by this deployment.
- **Derived** — calculated from available observations using disclosed rules.
- **Interpolated** — spatial estimate between contributing observations.
- **Forecast** — provider or trained-model future value.
- **Scenario** — user-controlled cellular-model output.
- **Demonstration** — deterministic fallback used when credentials or network access are unavailable.

## Main data sources

- Copernicus Data Space Sentinel Hub Process API: Sentinel-2 L2A NDVI and Sentinel-1 GRD.
- Global Forest Watch Data API: tree-cover-loss context.
- OpenWeather: current weather, forecast and map layers.
- Open-Meteo Historical Weather API: rainfall history/reanalysis.
- NASA FIRMS Area API: recent satellite thermal anomalies.
- Optional externally prepared Dynamic World statistics.
- Optional GEDI biomass context.
- Field and project records created through this deployment.

Official documentation:

- Copernicus Process API: https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process.html
- Sentinel-1 GRD: https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html
- Dynamic World: https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1
- Open-Meteo Historical API: https://open-meteo.com/en/docs/historical-weather-api
- NASA FIRMS Area API: https://firms.modaps.eosdis.nasa.gov/api/area/
- GEDI L4A biomass: https://daac.ornl.gov/GEDI/guides/GEDI_L4A_AGB_Density_V2_1.html

## Project structure

```text
gombe_desertification_afforestation_twin_v4_intelligence/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── services/
│   │   ├── enhanced_runtime.py
│   │   ├── intelligence.py
│   │   ├── rainfall.py
│   │   ├── radar.py
│   │   ├── fires.py
│   │   ├── prediction.py
│   │   ├── security.py
│   │   ├── store.py
│   │   └── ...
│   └── static/
│       ├── index.html
│       ├── services.html
│       ├── timeline.html
│       ├── drought.html
│       ├── landcover.html
│       ├── radar.html
│       ├── restoration.html
│       ├── ecosystems.html
│       ├── risks.html
│       ├── scenarios.html
│       ├── field.html
│       ├── projects.html
│       ├── predictions.html
│       ├── compare.html
│       ├── css/styles.css
│       └── js/intelligence.js
├── data/
├── tests/
├── .env.example
├── requirements.txt
├── Procfile
├── Dockerfile
└── run.py
```

## Run locally on Windows

```powershell
cd A:\gombe_desertification_afforestation_twin_v4_intelligence

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

The platform starts in labelled demonstration/derived mode when credentials are blank.

## Live credentials

Copy `.env.example` to `.env`, then configure the services you need.

### Copernicus Sentinel-2 and Sentinel-1

```dotenv
COPERNICUS_CLIENT_ID=your_client_id
COPERNICUS_CLIENT_SECRET=your_client_secret
```

### Global Forest Watch

```dotenv
GFW_API_KEY=your_api_key
GFW_ORIGIN=http://localhost
```

For Render, use the exact deployed origin:

```dotenv
GFW_ORIGIN=https://your-service.onrender.com
```

### OpenWeather

```dotenv
OPENWEATHER_API_KEY=your_api_key
```

### NASA FIRMS

```dotenv
NASA_FIRMS_MAP_KEY=your_map_key
```

### Optional Dynamic World and GEDI evidence

The application does not directly authenticate to Google Earth Engine. Supply an endpoint that returns prepared statistics for the study area:

```dotenv
DYNAMIC_WORLD_STATS_URL=https://your-secure-service.example/dynamic-world
DYNAMIC_WORLD_BEARER_TOKEN=optional_token

GEDI_CONTEXT_URL=https://your-secure-service.example/gedi-context
GEDI_BEARER_TOKEN=optional_token
```

Alternatively, enter a validated GEDI reference context:

```dotenv
GEDI_REFERENCE_AGBD_MG_HA=0
GEDI_REFERENCE_UNCERTAINTY_MG_HA=0
```

## Administrator protection

There is no default administrator password. Set either a plaintext environment secret or a SHA-256 hash.

Plaintext:

```dotenv
ADMIN_PASSWORD=your-long-private-password
```

Preferred hash generation:

```powershell
python -c "import getpass,hashlib; print(hashlib.sha256(getpass.getpass('Admin password: ').encode()).hexdigest())"
```

Then set:

```dotenv
ADMIN_PASSWORD=
ADMIN_PASSWORD_SHA256=generated_lowercase_hash
```

Administrator authentication protects:

- model retraining;
- Sentinel-2 temporal backfill;
- field-observation review status;
- project/inspection creation.

The browser receives a short-lived bearer token after successful login. Never place the password in source code or GitHub.

## API summary

### Existing twin APIs

- `GET /api/health`
- `GET /api/snapshot`
- `GET /api/boundary`
- `GET /api/lgas`
- `GET /api/northern-lgas`
- `GET /api/areas`
- `GET /api/weather`
- `GET /api/weather/forecast`
- `GET /api/ndvi/grid`
- `GET /api/ndvi/texture.png`
- `GET /api/simulation/texture.png`
- `GET /api/simulation/trees`
- `POST /api/simulation/scenario`
- `POST /api/planner/corridor`

### Version 4 intelligence APIs

- `GET /api/intelligence/summary`
- `GET /api/temporal`
- `GET /api/rainfall`
- `GET /api/radar`
- `GET /api/radar/texture.png`
- `GET /api/landcover`
- `GET /api/landcover/texture.png`
- `GET /api/suitability`
- `GET /api/suitability/texture.png`
- `POST /api/suitability/routes`
- `GET /api/carbon`
- `GET /api/risks`
- `GET /api/risks/texture.png`
- `GET /api/fires`
- `GET /api/scenarios`
- `GET /api/alerts`
- `GET /api/predictions/status`
- `GET /api/predictions/forecast`
- `GET/POST /api/field/observations`
- `GET/POST /api/projects`
- `POST /api/projects/{project_id}/inspections`
- `GET /api/species-profiles`

### Protected APIs

- `POST /api/admin/login`
- `POST /api/admin/logout`
- `POST /api/admin/predictions/retrain`
- `POST /api/admin/temporal/backfill`

## Deployment on Render

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Add credentials only under **Render → Environment**. Do not upload `.env`.

### Persistence warning

The default SQLite database, recorded history and trained model are stored under `data/`. Render Free services use an ephemeral filesystem, so these files may be lost when the service restarts, redeploys or spins down. For durable field records, projects, inspections, timeline archives and trained models, use a persistent disk or migrate the store to an external managed database/object store.

## Updating an existing Git repository

Preserve `.git`, `.env` and `.venv` while copying the Version 4 files, then run:

```powershell
git status
git add -A
git commit -m "Add temporal restoration and field intelligence platform"
git pull origin main --rebase
git push origin main
```

## Testing

```powershell
python -m pytest -q
```

The Version 4 test suite checks configuration, satellite processing, cellular simulation, geographic masking, weather, command-centre behaviour, intelligence pages, route optimisation, prediction training, API routes, unique HTML IDs and planner draft persistence rules.

## Scientific and operational notice

This is a research, education and scenario-screening platform. It does not replace field survey, official land administration, meteorological warnings, forestry assessment, environmental impact assessment, emergency management, certified carbon accounting or community consultation. Decisions about planting, species, land tenure, water, grazing, fire management and maintenance require local evidence and authorised expert review.
