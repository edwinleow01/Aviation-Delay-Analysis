"""The app works from small aggregate tables; these tests check they reproduce the report."""

import pandas as pd
import pytest

from aviation_delays import aggregates, data, metrics
from synthetic import make_raw


def test_aggregates_match_full_frame_metrics():
    af = data.analysis_frame(data.clean(make_raw(20_000, seed=4)))
    t = aggregates.build(af)

    carriers = aggregates.entity_table(t["by_airport"], "carrier")
    full = metrics.group_metrics(af, "carrier").join(metrics.mix_adjusted(af, "carrier", "origin")["adj_index"])
    full.index = full.index.astype(str)
    pd.testing.assert_series_equal(carriers["index"], full["index"].loc[carriers.index], check_names=False, check_dtype=False, rtol=1e-4)
    pd.testing.assert_series_equal(carriers["adj_index"], full["adj_index"].loc[carriers.index], check_names=False, check_dtype=False, rtol=1e-4)

    band = aggregates.band_table(t["by_time"], "NK")
    full_band = metrics.excess_by_band(af, "NK")
    assert band["excess_hours_per_year"].to_numpy() == pytest.approx(full_band["excess_hours_per_year"].to_numpy(), rel=1e-4)
    assert aggregates.what_if(t["by_time"], "NK", list(band.index), 0.5) == pytest.approx(
        band["excess_hours_per_year"].clip(lower=0).sum() / 2
    )


@pytest.mark.skipif(not (aggregates.AGG_DIR / "by_time.csv").exists(), reason="app aggregates not built")
def test_committed_aggregates_reproduce_the_report():
    """Mini test case: the app's numbers are the report's numbers (BTS 2024-25)."""
    t = aggregates.load()
    carriers = aggregates.entity_table(t["by_airport"], "carrier", min_flights=50_000)
    assert sorted(carriers.index[carriers["flagged"]]) == ["AA", "OO"]
    assert carriers.loc["OO", "min_per_flight"] == pytest.approx(8.02, abs=0.01)
    assert carriers.loc["AA", "adj_index"] == pytest.approx(1.33, abs=0.01)

    airports = aggregates.entity_table(t["by_airport"], "origin", min_flights=20_000)
    assert sorted(airports.index[airports["flagged"]]) == ["DSM", "DTW", "MSN"]

    first_wave = sum(aggregates.what_if(t["by_time"], c, ["<09:00"]) for c in ("OO", "AA"))
    assert round(first_wave, -2) == 20_600
