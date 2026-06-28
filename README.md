# Gombe Desertification & Afforestation Digital Twin — Version 3

Version 3 converts the platform into an immersive Earth-intelligence command centre while preserving the existing Sentinel-2, Global Forest Watch, OpenWeather, cellular-automata, LGA explorer and Green Wall planning services.

## Main services

| Service | Route |
|---|---|
| Immersive live twin | `/` |
| Gombe LGA explorer | `/areas` |
| Weather and sky service | `/weather` |
| Sentinel-2 NDVI service | `/satellite` |
| Cellular simulation lab | `/simulation` |
| Green Wall planner | `/planner` |
| Evidence and limitations | `/evidence` |

## Version 3 command-centre features

### Immersive full-state scene

- Full Gombe State boundary with all 11 LGA outlines and labels.
- Northern-focus highlighting for Dukku, Funakaye, Gombe, Kwami and Nafada.
- 3D terrain and optional globe projection.
- Natural background imagery used only as geographic context.
- Sentinel-2 NDVI ground texture clipped to the northern analysis geometry.
- Cellular desert-pressure texture updated without reloading the scene.
- Procedural Three.js trees with trunks, multiple branches, health-sensitive crowns and live wind sway.
- State, north, first-person, split ground/sky, reset and fullscreen views.

### Default orbit and cloud-flow follow

Auto-orbit is enabled when the page opens. When reported cloud cover is at least 35%, the camera follows a slowly moving wind-driven cloud-flow target. This target uses the current cloud-cover percentage, wind speed and wind direction; it is a visual navigation aid and not a detection of one physical cloud object.

### Live sky

- Sun follows the provider sunrise-to-sunset cycle.
- Moon and twinkling stars appear outside the daylight interval.
- Cloud density responds to cloud cover.
- Cloud drift and tree motion respond to wind direction and speed.
- Rain streaks respond to current rainfall and weather code.
- Thunder flashes appear for thunderstorm weather codes.
- Haze strength responds to reported visibility.

### Provider weather layers

The backend proxies the following OpenWeather map layers without exposing the API key in the browser:

- `clouds_new`
- `precipitation_new`
- `temp_new`

Transparent tiles are returned in demonstration mode, so the interface continues to work without credentials.

### Forecast and analytical panels

- Current weather and sky status.
- Animated circular sky dome.
- Environment status indicators.
- NDVI sparkline and satellite statistics.
- Live weather-flow visualisation.
- Forecast temperature and humidity trend.
- Animated wind-flow panel.
- Evidence-based events and advisories.
- Forecast rainfall chart.
- Global Forest Watch annual loss context.
- Green Wall model-health donut.
- Live vegetation/desert-pressure trajectory.

The advisory engine uses current source values and model outputs. It does not issue certified weather, fire, land-management or emergency warnings.

## Data meaning

- Sentinel-2 NDVI is a spectral greenness indicator, not a direct tree count or desertification measurement.
- Global Forest Watch tree-cover loss is contextual evidence and does not establish the cause or permanence of land degradation.
- OpenWeather current and forecast data drive atmospheric visualisation and bounded simulation forcing.
- Weather map tiles are provider products; the animated wind paths and cloud-flow target are visual interpretations.
- Procedural trees and cellular desert pressure are scenario-model outputs rather than observations of individual trees or a measured desert boundary.
- Background imagery is geographic context and is not claimed to be the latest Sentinel acquisition.

## Environment configuration

Copy the example file:

```powershell
Copy-Item .env.example .env
```

Configure credentials:

```dotenv
COPERNICUS_CLIENT_ID=your_client_id
COPERNICUS_CLIENT_SECRET=your_client_secret

GFW_API_KEY=your_gfw_api_key
GFW_ORIGIN=http://localhost

OPENWEATHER_API_KEY=your_openweather_key
```

The OpenWeather endpoints have defaults:

```dotenv
OPENWEATHER_CURRENT_URL=https://api.openweathermap.org/data/2.5/weather
OPENWEATHER_FORECAST_URL=https://api.openweathermap.org/data/2.5/forecast
OPENWEATHER_TILE_URL=https://tile.openweathermap.org/map/{layer}/{z}/{x}/{y}.png
```

## Run locally

```powershell
cd A:\gombe_desertification_afforestation_twin_v3_command_centre

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
Copy-Item .env.example .env

python -m pytest -q
python run.py
```

Open:

```text
http://127.0.0.1:8000
```

Perform a hard refresh after replacing an older version:

```text
Ctrl + F5
```

## Render deployment

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Add credentials under **Render → Service → Environment**. Never commit `.env`.

## Updating an existing Git repository

```powershell
git status
git add -A
git commit -m "Add immersive command centre live sky and cloud-follow orbit"
git pull origin main --rebase
git push origin main
```

## Main APIs

- `GET /api/snapshot`
- `GET /api/weather`
- `GET /api/weather/forecast`
- `GET /api/weather/tiles/{layer}/{z}/{x}/{y}.png`
- `GET /api/ndvi/grid`
- `GET /api/ndvi/texture.png`
- `GET /api/simulation/texture.png`
- `GET /api/simulation/trees`
- `GET /api/history`
- `GET /api/lgas`
- `GET /api/northern-lgas`
- `GET /api/areas/{slug}`
- `WS /ws/live`

## Validation

The project includes automated checks for:

- configuration parsing;
- Sentinel demonstration data;
- cellular simulation;
- texture generation and geographic masking;
- Gombe boundaries and northern-focus geometry;
- planner draft non-persistence;
- weather observations and forecast fallback;
- command-centre controls;
- forecast and weather-tile routes;
- HTML ID uniqueness;
- standard social-preview dimensions.
