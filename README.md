# Samish River Outlook

[Live field-planning page](https://jdinneen.github.io/samish-river-outlook/)

Buildless HTML, CSS and JavaScript. Each browser requests the public USGS Burlington
gauge, NOAA SMRW1 forecast, two NWS precipitation grid points, and Bellingham tide
predictions. No runtime dependencies, tracking, accounts, backend or automated alerts.
GitHub Pages serves this repository's main branch at the existing address.

The October 2026 redesign separates observations, forecasts and retrospective
research. It removes the previous probability/action labels and inferred crest
status. It adds timestamps, missing/stale-feed handling, accessible data tables,
keyboard tabs, mobile/dark layouts and a copyable field brief.

## Meaning and limits

- USGS measurements are provisional. Direct USGS values take precedence at matching
  timestamps; the NOAA gauge copy is a fallback. Older-than-two-hour readings are
  labeled stale.
- NOAA forecasts are shown without alignment to the latest gauge. More-than-48-hour
  issue age, missing issue clocks, unsupported gaps and expired coverage withhold
  the forecast. The chart never extrapolates beyond supplied support. An available
  forecast high is not a confirmed crest or a validated sampling window.
- Rain is a mean of two selected grid points, not a basin-wide measurement. Both
  points must have full next-24-hour coverage and updates no older than 24 hours.
  Partial native intervals use uniform apportionment; missing values are not zero.
- Tide extrema are NOAA predictions in feet MLLW at Bellingham, not local access
  clearance. Times display in America/Los_Angeles, including PST/PDT.
- Research summaries are a fixed October 11, 2026 snapshot checked against C1/C2
  analysis outputs and frozen P11/P12 receipts. No raw/sample-level records, laboratory
  rows, correspondence or private source files are included in this update. Publishing
  these user-requested aggregate summaries does not assert provider endorsement or
  permission to redistribute the underlying records.
- Research has not established a dependable operational AI warning. The historical
  bacteria model is evaluated at sample time; reopening clocks include imputation.
  Established sampling procedures and DOH decisions remain authoritative.

`backtest.js` is an unchanged historical asset from the preceding public version.
The current page neither loads it nor uses it to calculate any displayed value.

## Browser checks

Use an isolated QA environment with `playwright==1.63.0` and its Chromium browser.
The website itself requires no installation or build.

```sh
python -m http.server 8769 --bind 127.0.0.1
# In a separate terminal, using the QA Python environment:
python tests/check_site.py http://127.0.0.1:8769
```

Tests intercept external feeds with synthetic fixtures. They cover numerical parsing,
units, nulls, overflow, clocks, forecast horizons/gaps, rainfall coverage, tide times,
fallbacks, stale/failed refreshes, keyboard navigation, clipboard fallback, and panel
overflow at 320/390/768/1440 pixels in light and dark modes. Screenshots go to a
temporary directory outside the repository. Tests never run scientific models.

The release also received independent data, research-language and UX reviews; live
provider checks; and axe-core 4.10.3 WCAG 2 A/AA and 2.1 AA checks across all three
panels in light/dark mode. Automated checks supplement browser inspection; they do
not establish universal accessibility or scientific fitness.

Provider contracts: [USGS API migration](https://api.waterdata.usgs.gov/docs/ogcapi/migration/),
[NWS grid points](https://weather-gov.github.io/api/gridpoints),
[NOAA tide API](https://api.tidesandcurrents.noaa.gov/api/prod/).
