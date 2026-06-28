from __future__ import annotations

from app.models import GFWSnapshot, InsightItem, SatelliteSnapshot, SimulationMetrics, WeatherSnapshot


def build_insights(
    satellite: SatelliteSnapshot,
    gfw: GFWSnapshot,
    weather: WeatherSnapshot,
    simulation: SimulationMetrics,
) -> list[InsightItem]:
    stats = satellite.stats
    items: list[InsightItem] = []

    if stats.mean < 0.18:
        vegetation_text = "The available NDVI mosaic has low average spectral greenness across the northern analysis area."
    elif stats.mean < 0.32:
        vegetation_text = "The available NDVI mosaic indicates predominantly sparse to moderate greenness."
    else:
        vegetation_text = "The available NDVI mosaic indicates moderate or stronger greenness across much of the valid area."
    items.append(InsightItem(
        kind="observation",
        title="Satellite vegetation condition",
        body=(
            f"{vegetation_text} Mean NDVI is {stats.mean:.2f}; "
            f"{stats.bare_fraction * 100:.1f}% of valid pixels are below the display threshold of 0.15."
        ),
        evidence=[
            satellite.source_name,
            f"Valid-pixel coverage: {stats.valid_fraction * 100:.1f}%",
            f"Observation window: {satellite.observation_window_start.date()} to {satellite.observation_window_end.date()}",
        ],
        confidence="high" if satellite.mode == "live" and stats.valid_fraction >= 0.65 else "medium",
    ))

    moisture_support = "stronger" if weather.rain_1h_mm > 0 or weather.humidity_percent >= 65 else "weaker" if weather.humidity_percent < 35 else "mixed"
    items.append(InsightItem(
        kind="weather",
        title="Current atmospheric forcing",
        body=(
            f"Moisture support is currently {moisture_support}: temperature {weather.temperature_c:.1f}°C, "
            f"humidity {weather.humidity_percent:.0f}%, rain {weather.rain_1h_mm:.1f} mm in the reported hour, "
            f"and wind {weather.wind_speed_mps:.1f} m/s from {weather.wind_direction_cardinal}. "
            "The cellular model uses these values only as a bounded short-term forcing signal."
        ),
        evidence=[weather.note, f"Weather mode: {weather.mode}", f"Condition: {weather.condition}"],
        confidence="high" if weather.mode == "live" else "low",
    ))

    if gfw.mode == "live":
        forest_body = (
            f"Global Forest Watch reports {gfw.cumulative_loss_ha:.1f} ha of tree-cover loss in the queried recent-year series. "
            "This is contextual historical evidence and does not identify desertification cause or permanence."
        )
        confidence = "high"
    else:
        forest_body = (
            "Global Forest Watch is in demonstration mode. The loss series is illustrative and must not be used as evidence of observed forest loss."
        )
        confidence = "low"
    items.append(InsightItem(
        kind="external",
        title="Forest-change context",
        body=forest_body,
        evidence=[f"Dataset: {gfw.dataset}", f"Mode: {gfw.mode}", gfw.note],
        confidence=confidence,
    ))

    direction = "expanding" if simulation.desert_change > 0.002 else "contracting" if simulation.desert_change < -0.002 else "approximately stable"
    items.append(InsightItem(
        kind="simulation",
        title="Scenario trajectory",
        body=(
            f"Under the current assumptions and live weather forcing, the simulated high-desert fraction is {simulation.desert_fraction * 100:.1f}% "
            f"and is {direction} over the latest model step. Tree-barrier health averages {simulation.mean_tree_health * 100:.1f}%."
        ),
        evidence=[
            f"Simulation tick: {simulation.tick}",
            f"Barrier footprint: {simulation.barrier_fraction * 100:.2f}% of cells",
            f"Weather moisture forcing: {simulation.weather_moisture_forcing * 100:.1f}%",
            f"Weather heat stress: {simulation.weather_heat_stress * 100:.1f}%",
        ],
        confidence="not-applicable",
    ))

    if stats.bare_fraction > 0.40 and simulation.desert_fraction > 0.35:
        items.append(InsightItem(
            kind="interpretation",
            title="Priority-screening signal",
            body=(
                "Low satellite greenness and a large simulated desert-pressure footprint overlap in the current screen. "
                "This identifies a possible field-verification priority; it does not prove active desert encroachment."
            ),
            evidence=["Sentinel-2 NDVI", "Cellular-automata scenario output", "Current weather forcing"],
            confidence="medium",
        ))

    items.append(InsightItem(
        kind="limitation",
        title="What the twin cannot conclude",
        body=(
            "NDVI measures spectral greenness, not land-degradation cause. Tree-cover loss can result from several disturbances. "
            "The animated trees are procedural model symbols rather than mapped individual trees, and the cellular automaton is a scenario model rather than an operational forecast."
        ),
        evidence=["Source provenance and model assumptions are shown on each service page."],
        confidence="not-applicable",
    ))
    return items
