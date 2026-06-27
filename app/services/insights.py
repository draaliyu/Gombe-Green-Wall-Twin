from __future__ import annotations

from app.models import GFWSnapshot, InsightItem, SatelliteSnapshot, SimulationMetrics


def build_insights(
    satellite: SatelliteSnapshot,
    gfw: GFWSnapshot,
    simulation: SimulationMetrics,
) -> list[InsightItem]:
    stats = satellite.stats
    items: list[InsightItem] = []

    if stats.mean < 0.18:
        vegetation_text = "The current NDVI mosaic has low average greenness across the analysis window."
    elif stats.mean < 0.32:
        vegetation_text = "The current NDVI mosaic indicates predominantly sparse to moderate greenness."
    else:
        vegetation_text = "The current NDVI mosaic indicates moderate or stronger greenness across much of the valid area."
    items.append(InsightItem(
        kind="observation",
        title="Satellite vegetation condition",
        body=(
            f"{vegetation_text} Mean NDVI is {stats.mean:.2f}; "
            f"{stats.bare_fraction * 100:.1f}% of valid pixels are below the visual bare/sparse threshold of 0.15."
        ),
        evidence=[
            satellite.source_name,
            f"Valid-pixel coverage: {stats.valid_fraction * 100:.1f}%",
            f"Observation window: {satellite.observation_window_start.date()} to {satellite.observation_window_end.date()}",
        ],
        confidence="high" if satellite.mode == "live" and stats.valid_fraction >= 0.65 else "medium",
    ))

    if gfw.mode == "live":
        forest_body = (
            f"Global Forest Watch reports {gfw.cumulative_loss_ha:.1f} ha of tree-cover loss in the queried recent-year series. "
            "This is a forest-change indicator and should not be interpreted automatically as desertification."
        )
        confidence = "high"
    else:
        forest_body = (
            "Global Forest Watch is currently in demonstration mode. The displayed loss series is illustrative and must not be used as evidence of observed forest loss."
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
            f"Under the current scenario settings, the simulated high-desert fraction is {simulation.desert_fraction * 100:.1f}% "
            f"and is {direction} over the latest model step. Tree-barrier health averages {simulation.mean_tree_health * 100:.1f}%."
        ),
        evidence=[
            f"Simulation tick: {simulation.tick}",
            f"Barrier footprint: {simulation.barrier_fraction * 100:.2f}% of cells",
            f"Desert-front cells: {simulation.desert_front_cells}",
        ],
        confidence="not-applicable",
    ))

    if stats.bare_fraction > 0.40 and simulation.desert_fraction > 0.35:
        items.append(InsightItem(
            kind="interpretation",
            title="Priority-screening signal",
            body=(
                "Low satellite greenness and a large simulated desert-risk footprint overlap in the current screen. "
                "This identifies an area for field verification and restoration planning; it does not prove active desert encroachment."
            ),
            evidence=["Sentinel-2 NDVI", "Cellular-automata scenario output"],
            confidence="medium",
        ))

    items.append(InsightItem(
        kind="limitation",
        title="What the twin cannot conclude",
        body=(
            "NDVI measures spectral greenness, not land degradation cause. Tree-cover loss can result from several disturbances. "
            "The cellular automaton is a scenario model, not an operational forecast, and should be calibrated with field observations before decision use."
        ),
        evidence=["Source provenance and model parameters are shown on every service page."],
        confidence="not-applicable",
    ))
    return items
