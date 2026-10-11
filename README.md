# Samish River Outlook

[Live field-planning page](https://jdinneen.github.io/samish-river-outlook/)

Buildless HTML, CSS and JavaScript. Each browser requests the public USGS Burlington
gauge, NOAA SMRW1 forecast, two NWS precipitation grid points, and Bellingham tide
predictions. No runtime dependencies, tracking, accounts, backend or automated alerts.
GitHub Pages serves this repository's main branch at the existing address.
The deployed release receipt is `version.json`; it records the public release label
and SHA-256 content hashes for the four runtime assets.

Version 3 separates observations, forecasts and retrospective research. It removes
the previous probability/action labels and inferred crest status. It adds:

- a browser-profile saved-forecast check that can show when the gauge is materially
  above a National Oceanic and Atmospheric Administration (NOAA) path captured
  3–36 hours earlier and is still rising;
- a clearly labeled experimental comparison against the confirmed seasonal 24-hour rise
  numbers, while leaving the agency's unconfirmed starting-value method explicit;
- same-window forecast-revision context, forecast-high/tide pairing, and links to
  separate rainfall observations plus the University of Washington and AccuWeather
  forecast views Jason already uses;
- a direct Washington State Department of Health commercial-closure link and an
  explicit statement that the page does not ingest official open/closed status;
- copyable and downloadable field snapshots, source clocks, missing/stale-feed
  handling, accessible data tables, keyboard tabs, and mobile/dark layouts.

## Meaning and limits

- USGS measurements are provisional. Direct USGS values take precedence at matching
  timestamps; the NOAA gauge copy is a fallback. Older-than-two-hour readings are
  labeled stale.
- NOAA forecasts are shown without alignment to the latest gauge. More-than-48-hour
  issue age, missing issue clocks, unsupported gaps and expired coverage withhold
  the forecast. The chart never extrapolates beyond supplied support. An available
  forecast high is not a confirmed crest or a validated sampling window.
- The seasonal screen is a transparent planning calculation, not the Department of
  Health formula. It uses one constant gauge alignment, a strictly earlier rolling
  24-hour low, and the confirmed seasonal numbers: 400 cubic feet per second (cfs)
  in November–February, 200 cfs in March–April, and 100 cfs in May–October. It
  withholds a result when gauge or forecast coverage is incomplete.
- The saved-forecast check stores the first capture of each NOAA issue in that
  browser for up to 14 days. “Outpacing” requires the unrounded later gauge value
  to be at least 10% of the seasonal rise number above the saved, gauge-aligned
  path and a positive measured change over 2.5–3.5 hours. This unvalidated line is
  a prompt to re-check conditions, not a closure, dispatch, or all-clear rule.
  Clearing browser data clears the history. The page refreshes only while its tab
  is visible, and history does not transfer between browser profiles.
- Rain is a mean of two selected grid points, not a basin-wide measurement. Both
  points must have full next-24-hour coverage and updates no older than 24 hours.
  Partial native intervals use uniform apportionment; missing values are not zero.
- Tide extrema are NOAA predictions in feet MLLW at Bellingham, not local access
  clearance. Times display in America/Los_Angeles, including PST/PDT.
- Numbered research summaries are a fixed October 11, 2026 snapshot checked against
  the C1/C2 analysis outputs. Unverified bacteria/reopening summaries from the prior
  public version were removed. No raw/sample-level records, laboratory rows,
  correspondence or private source files are included in this update. Publishing
  these aggregate summaries does not assert provider endorsement or permission to
  redistribute the underlying records.
- Research has not established a dependable operational artificial-intelligence (AI)
  warning. Established sampling procedures and DOH decisions remain authoritative.

`backtest.js` is an unchanged historical asset from the preceding public version.
The current page neither loads it nor uses it to calculate any displayed value.

## Browser checks

Use an isolated quality-assurance environment with `playwright==1.63.0` and its
Chromium browser. The website itself requires no installation or build.

```sh
python tests/check_site.py
```

The test starts and stops its own loopback-only static server. It also accepts an
explicit local URL as the first argument. For the required release accessibility
pass, set `AXE_PATH` to an axe-core 4.10.3 browser bundle and `REQUIRE_AXE=1` before
running it. The ordinary local smoke test can omit both variables.

Tests intercept external feeds with synthetic fixtures. They cover 95 numerical
contracts, including Pacific-time seasonal boundaries, strict earlier baselines,
gauge and forecast coverage, first-capture immutability, exact saved-path age and
nearest-reading change windows, corrupt interior path points, malformed storage,
unrounded warning decisions, forecast revisions,
rainfall coverage, and tide times. Browser checks cover the learning, tracking,
above-saved-path, outpacing, stale, partial-feed and all-feed-failure states; field
snapshot download; keyboard navigation; clipboard fallback; and panel overflow at
320/390/768/1440 pixels in light and dark modes. Screenshots go to a temporary
directory outside the repository. Tests never run scientific models.

The release also receives independent claim and user-experience reviews, live
provider checks, and axe-core 4.10.3 Web Content Accessibility Guidelines (WCAG)
2.0 A/AA, 2.1 AA and 2.2 AA checks across the learning, tracking,
above-saved-path, outpacing and all-feeds-unavailable states in light/dark mode.
The three panels are all checked in the outpacing state. Automated
checks supplement browser inspection; they do not establish universal accessibility
or scientific fitness.

Provider contracts: [USGS API migration](https://api.waterdata.usgs.gov/docs/ogcapi/migration/),
[NWS grid points](https://weather-gov.github.io/api/gridpoints),
[NOAA tide API](https://api.tidesandcurrents.noaa.gov/api/prod/).
