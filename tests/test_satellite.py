from datetime import datetime, timezone

import numpy as np

from app.services.sentinel import calculate_stats, generate_demo_ndvi


def test_demo_ndvi_is_reproducible() -> None:
    now = datetime(2026, 6, 27, tzinfo=timezone.utc)
    first, first_valid = generate_demo_ndvi(32, 24, 4106, now)
    second, second_valid = generate_demo_ndvi(32, 24, 4106, now)
    assert np.allclose(first, second)
    assert np.array_equal(first_valid, second_valid)
    assert first.shape == (24, 32)


def test_ndvi_statistics_sum_to_valid_classes() -> None:
    ndvi = np.array([[-0.1, 0.2], [0.4, 0.7]], dtype=np.float32)
    valid = np.ones_like(ndvi, dtype=bool)
    stats = calculate_stats(ndvi, valid)
    total = stats.bare_fraction + stats.sparse_fraction + stats.moderate_fraction + stats.dense_fraction
    assert abs(total - 1.0) < 1e-6
