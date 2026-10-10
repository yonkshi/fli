"""Coverage contracts with offline captured search pages."""

from pathlib import Path

import pytest

from fli.mcp.server import DateSearchParams, _execute_date_search
from fli.search import SearchDates
from fli.search._wire import iter_wrb_chunks
from fli.search.exceptions import SearchTimeoutError
from tests.search._pages import as_search_page


@pytest.fixture
def page_transport(monkeypatch):
    page = as_search_page(
        next(
            iter_wrb_chunks(
                (
                    Path(__file__).parent / "fixtures" / "flight_search_jfk_lax_oneway_usd.bin"
                ).read_text()
            )
        )
    )
    monkeypatch.setattr("fli.search.dates.page_url", lambda token, *args: token)
    monkeypatch.setattr("fli.search.dates.build_tfs", lambda filters, travel_dates: travel_dates[0])

    def fetch(client, day):
        if day == "2026-12-02":
            raise SearchTimeoutError("fixture timeout")
        from fli.search._tfs import extract_payload

        return extract_payload(page)

    monkeypatch.setattr("fli.search.dates.fetch_payload", fetch)
    return fetch


def test_mcp_partial_sweep_exposes_incomplete_coverage(page_transport):
    response = _execute_date_search(
        DateSearchParams(
            origin="JFK",
            destination="LAX",
            start_date="2026-12-01",
            end_date="2026-12-02",
            is_round_trip=False,
        )
    )
    assert response["success"] is True
    assert response["count"] == 1
    assert response["coverage"]["complete"] is False
    assert response["coverage"]["attempted_dates"] == ["2026-12-01", "2026-12-02"]
    assert response["coverage"]["priced_dates"] == ["2026-12-01"]
    assert response["coverage"]["failed_dates"] == ["2026-12-02"]
    assert response["warnings"]


@pytest.mark.parametrize(
    "mode,complete,priced,empty,failed",
    [
        ("priced", True, ["2026-12-01", "2026-12-02"], [], []),
        ("empty", True, [], ["2026-12-01", "2026-12-02"], []),
        ("failed", False, [], [], ["2026-12-01", "2026-12-02"]),
    ],
)
def test_coverage_records_final_outcomes_and_resets(
    monkeypatch, mode, complete, priced, empty, failed
):
    from fli.models import Airport, DateSearchFilters, FlightSegment, PassengerInfo
    from fli.search import DateSearchCoverage
    from fli.search.dates import DatePrice, _DateOutcome
    from fli.search.exceptions import SearchClientError

    filters = DateSearchFilters(
        passenger_info=PassengerInfo(adults=1),
        flight_segments=[
            FlightSegment(
                departure_airport=[[Airport.JFK, 0]],
                arrival_airport=[[Airport.LAX, 0]],
                travel_date="2026-12-01",
            )
        ],
        from_date="2026-12-01",
        to_date="2026-12-02",
    )
    search = SearchDates()
    coverage = DateSearchCoverage(failed_dates=["stale"], complete=True)

    def outcome(filters, day, **kwargs):
        if mode == "failed":
            return _DateOutcome(failure="timeout")
        if mode == "empty":
            return _DateOutcome(rows_before_filters=0)
        return _DateOutcome(price=DatePrice(date=(day,), price=100))

    monkeypatch.setattr(search, "_price_one_date", outcome)
    for _ in range(2):
        if mode == "failed":
            with pytest.raises(SearchClientError):
                search.search(filters, coverage=coverage)
        else:
            result = search.search(filters, coverage=coverage)
            assert (result is None) == (mode == "empty")
        assert coverage.complete is complete
        assert coverage.priced_dates == priced
        assert coverage.empty_dates == empty
        assert coverage.failed_dates == failed
        assert coverage.attempted_dates == ["2026-12-01", "2026-12-02"]


def test_breaker_unattempted_dates_cannot_claim_complete(monkeypatch):
    from fli.models import Airport, DateSearchFilters, FlightSegment, PassengerInfo
    from fli.search import DateSearchCoverage
    from fli.search.exceptions import SearchParseError

    monkeypatch.setattr(
        "fli.search.dates.parallel_map", lambda fn, tasks: [fn(task) for task in tasks]
    )
    monkeypatch.setattr("fli.search.dates.fetch_payload", lambda *args: None)
    filters = DateSearchFilters(
        passenger_info=PassengerInfo(adults=1),
        flight_segments=[
            FlightSegment(
                departure_airport=[[Airport.JFK, 0]],
                arrival_airport=[[Airport.LAX, 0]],
                travel_date="2026-12-01",
            )
        ],
        from_date="2026-12-01",
        to_date="2026-12-07",
    )
    coverage = DateSearchCoverage()
    with pytest.raises(SearchParseError):
        SearchDates().search(filters, coverage=coverage)
    assert coverage.complete is False
    assert coverage.failed_dates == [
        "2026-12-01",
        "2026-12-02",
        "2026-12-03",
        "2026-12-04",
        "2026-12-05",
    ]
    assert coverage.unattempted_dates == ["2026-12-06", "2026-12-07"]
