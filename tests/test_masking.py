from io import BytesIO

import numpy as np
from PIL import Image

from app.services.texture import mask_texture_to_features, simulation_to_texture


def test_texture_is_transparent_outside_polygon() -> None:
    texture = simulation_to_texture(
        np.full((8, 8), 0.6, dtype=np.float32),
        np.full((8, 8), 0.2, dtype=np.float32),
        np.zeros((8, 8), dtype=np.float32),
        width=100,
        height=100,
    )
    geometry = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [[[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75], [0.25, 0.25]]]},
        }],
    }
    masked = mask_texture_to_features(texture, geometry, (0.0, 0.0, 1.0, 1.0))
    image = Image.open(BytesIO(masked)).convert("RGBA")
    assert image.getpixel((5, 5))[3] == 0
    assert image.getpixel((50, 50))[3] > 0
