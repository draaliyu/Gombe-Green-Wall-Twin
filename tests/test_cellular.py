from app.config import Settings
from app.services.cellular import DesertificationAutomaton
from app.services.sentinel import generate_demo_ndvi


def test_corridor_creates_barrier_cells() -> None:
    settings = Settings(_env_file=None, simulation_grid_width=48, simulation_grid_height=36)
    ndvi, valid = generate_demo_ndvi(48, 36, 4106)
    model = DesertificationAutomaton(settings)
    model.initialise_from_ndvi(ndvi, valid)
    before = model.metrics().barrier_fraction
    changed = model.plant_corridor([(10.7, 10.8), (11.6, 10.8)], settings.aoi_bbox, width_cells=2)
    after = model.metrics().barrier_fraction
    assert changed > 0
    assert after > before


def test_model_advances_when_running() -> None:
    settings = Settings(_env_file=None, simulation_grid_width=48, simulation_grid_height=36)
    ndvi, valid = generate_demo_ndvi(48, 36, 4106)
    model = DesertificationAutomaton(settings)
    model.initialise_from_ndvi(ndvi, valid)
    model.step()
    assert model.metrics().tick >= 1
