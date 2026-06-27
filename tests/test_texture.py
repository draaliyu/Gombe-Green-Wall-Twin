import numpy as np

from app.services.texture import ndvi_to_texture, simulation_to_texture


def test_textures_are_png() -> None:
    grid = np.full((12, 16), 0.3, dtype=np.float32)
    valid = np.ones_like(grid, dtype=bool)
    assert ndvi_to_texture(grid, valid).startswith(b"\x89PNG")
    assert simulation_to_texture(grid, 1 - grid, np.zeros_like(grid)).startswith(b"\x89PNG")
