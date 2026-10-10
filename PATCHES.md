# Maintained patches

## Request-scoped date sweep coverage

Based on upstream `881aee5ff4321e81ea2157cb44be94ce6a21dc1b`.

The date sweep could return prices after failed fetches while MCP reported only
success. `DateSearchCoverage` is an optional caller-owned argument to
`SearchDates.search()`, reset on every call and populated before collection can
raise. No coverage state is kept on the search client or globally. Use a separate
coverage instance for each concurrent request.

MCP date responses add `coverage` and successful responses add `warnings`.
Coverage lists ISO departure dates in sweep order: `candidate_dates`,
`attempted_dates`, `priced_dates`, `empty_dates`, `failed_dates`, and
`unattempted_dates`. `complete` means all candidates were attempted without a
final failure. Empty means no matching priced itinerary after filtering.
Underlying fetch retries produce one final outcome per date. Past dates and
circuit-breaker skips are unattempted. Coverage describes the sweep, not exhaustive
Google Flights inventory or a guarantee of globally cheapest fares. MCP result
limits and price sorting do not change sweep coverage. Validation errors before
a sweep retain their existing response; sweep errors include coverage.

Covering tests: `tests/search/test_date_coverage.py` checks captured-page partial
MCP success, complete priced/empty sweeps, all failures, caller metadata reuse,
and circuit-breaker skips. Existing offline search/MCP tests protect legacy
success, empty, retry, filtering and error behavior. This upstream version has no
maximum-duration sweep budget, so no budget subsystem was added.

Remove this patch once upstream exposes equivalent request-scoped coverage and
MCP partial-result warnings; migrate personal-mcp's consumer and immutable pin
before removing it.
