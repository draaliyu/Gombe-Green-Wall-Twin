# Northern Gombe Desertification & Afforestation (Great Green Wall) Twin

A standalone FastAPI and WebGL digital twin for exploring vegetation condition, desertification pressure and simulated afforestation barriers across northern Gombe State, Nigeria.

The platform combines:

- **Copernicus Data Space Sentinel-2 L2A** red and near-infrared bands to calculate cloud-masked NDVI;
- **Global Forest Watch Data API** tree-cover-loss context;
- a continuous-state **cellular automata model** for desert spread, vegetation recovery and planted barrier growth/withering;
- **MapLibre GL JS 3D terrain** with a dynamic sand-to-grass texture;
- procedural **Three.js 3D tree instances** whose height and colour change with model health;
- scheduled background source refreshes and one-second WebSocket state streaming;
- a click-to-design Great Green Wall corridor planner;
- evidence and limitation panels that separate observations, context, interpretation and simulation.

## Important scientific distinction

- NDVI is a spectral greenness indicator. It is not a direct measurement of desertification, biomass, soil fertility or tree count.
- Global Forest Watch tree-cover loss is contextual forest-change evidence. It does not establish the cause or permanence of land degradation.
- Cellular-automata outputs are scenario experiments, not operational forecasts.
- 3D trees are visualisations of model state, not an inventory of real trees.
- The initial tree belt in demo mode is synthetic and exists only to demonstrate growth and withering behaviour.

## Service pages

| Service | Route | Purpose |
|---|---|---|
| Live Twin | `/` | 3D terrain, dynamic texture, tree growth and live interpretation |
| Satellite NDVI | `/satellite` | NDVI map, histogram, cloud-free coverage and display classes |
| Simulation Lab | `/simulation` | Cellular automata controls and trajectory chart |
| Green Wall Planner | `/planner` | Draw and submit simulated planting corridors |
| Evidence | `/evidence` | Provenance, methodology, current statements and limitations |

## Live and demonstration modes

The project starts immediately without credentials.

- Without Copernicus credentials, it produces a deterministic, clearly labelled demonstration NDVI surface.
- Without a Global Forest Watch API key, it displays a clearly labelled demonstration forest-change series.
- When credentials are configured, the corresponding source switches to `LIVE`.
- If only one external source is live, the overall platform reports `MIXED` mode.

No demonstration value is presented as a measured observation.

## Project structure

```text
gombe_desertification_afforestation_twin/
├── app/
│   ├── config.py
│   ├── main.py
│   ├── models.py
│   ├── services/
│   │   ├── boundary.py
│   │   ├── cellular.py
│   │   ├── gfw.py
│   │   ├── insights.py
│   │   ├── runtime.py
│   │   ├── sentinel.py
│   │   └── texture.py
│   └── static/
│       ├── index.html
│       ├── satellite.html
│       ├── simulation.html
│       ├── planner.html
│       ├── evidence.html
│       ├── css/styles.css
│       └── js/
│           ├── common.js
│           ├── trees3d.js
│           ├── twin.js
│           ├── satellite.js
│           ├── simulation.js
│           ├── planner.js
│           └── evidence.js
├── data/
├── tests/
├── .env.example
├── Dockerfile
├── Procfile
├── requirements.txt
└── run.py
```

## Run locally on Windows

```powershell
cd A:\gombe_desertification_afforestation_twin

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

## Copernicus Data Space setup

The Sentinel Hub Process API uses OAuth2 client credentials.

1. Create or sign in to a Copernicus Data Space account.
2. Open the Sentinel Hub dashboard.
3. Create an OAuth client using the **Client Credentials** grant.
4. Copy the client ID and secret into `.env`:

```dotenv
COPERNICUS_CLIENT_ID=your_client_id
COPERNICUS_CLIENT_SECRET=your_client_secret
COPERNICUS_TOKEN_URL=https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token
COPERNICUS_PROCESS_URL=https://sh.dataspace.copernicus.eu/process/v1
```

The application requests Sentinel-2 L2A data and calculates:

```text
NDVI = (B08 - B04) / (B08 + B04)
```

The SCL band is used to exclude no-data, cloud shadow, cloud, cirrus and snow/ice classes. The request uses the least-cloudy mosaic within the configured lookback window.

The app reports the **retrieval time and observation window**, not an invented exact acquisition time.

## Global Forest Watch setup

The GFW Data API requires an API key for dataset queries.

```dotenv
GFW_API_KEY=your_gfw_api_key
GFW_DATASET=umd_tree_cover_loss
GFW_DATASET_VERSION=latest
```

If the key has a domain allowlist, add the deployed origin:

```dotenv
GFW_ORIGIN=https://your-app.onrender.com
```

The backend queries the UMD tree-cover-loss dataset for the northern Gombe analysis polygon and groups mapped loss area by year.

## Analysis area and refresh schedule

```dotenv
AOI_BBOX=[10.55,10.20,11.85,11.55]
SENTINEL_LOOKBACK_DAYS=35
SENTINEL_MAX_CLOUD_PERCENT=35
SATELLITE_REFRESH_SECONDS=21600
GFW_REFRESH_SECONDS=43200
SIMULATION_INTERVAL_SECONDS=1
BROADCAST_INTERVAL_SECONDS=1
```

`AOI_BBOX` is ordered as:

```text
west,south,east,north
```

A scheduled Sentinel refresh updates the NDVI array and ground texture in place. The MapLibre image source calls `updateImage`, so the 3D scene is not reloaded.

## Cellular automata model

Every grid cell stores continuous values for:

- vegetation condition;
- desert pressure;
- tree-barrier strength;
- moisture support;
- assimilated NDVI baseline.

The model exposes scenario controls for:

- aridity pressure;
- grazing pressure;
- rainfall support;
- restoration effort;
- barrier maintenance;
- desert spread rate;
- vegetation growth rate.

These are assumptions. They are shown explicitly and are never described as API measurements.

## Great Green Wall planner

On `/planner`:

1. Click or tap two or more points inside the northern Gombe AOI.
2. Select a model corridor width.
3. Choose **Plant in simulation**.
4. The line is rasterised into cellular-automata barrier cells.
5. The live twin receives the new tree instances and simulation texture through WebSocket/version updates.

## API endpoints

- `GET /api/health`
- `GET /api/snapshot`
- `GET /api/boundary`
- `GET /api/locations`
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
- `POST /api/planner/corridor`
- `DELETE /api/planner/corridors`
- `WS /ws/live`

## Deploy on Render

Create a separate GitHub repository for this project.

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Add credentials through **Render → Environment**, never through GitHub.

The free Render filesystem is ephemeral. `data/history.json` is therefore temporary on a free web service. Use a persistent disk or external database for durable history.

## Docker

```powershell
docker compose up --build
```

## Testing

```powershell
python -m pytest -q
```

JavaScript syntax can be checked with:

```powershell
Get-ChildItem app\static\js\*.js | ForEach-Object { node --check $_.FullName }
```


