# Samish River Outlook

[Published field-planning page](https://jdinneen.github.io/samish-river-outlook/)

Buildless HTML, CSS and JavaScript. Each browser requests public river, forecast,
rain, radar, gauge-upstream drainage-area and tide sources directly. There is no runtime package,
tracking, account, backend, automated alert or background monitor.

The source contains published version 5. `version.json` is the machine-readable
receipt that binds the public release to its asset commit and file hashes.

## Version 5

Version 5 keeps the earlier evidence boundaries and makes the page more useful
during a storm:

- a first-screen operating strip for river flow, near-three-hour change, the
  applicable seasonal rise number, the current National Oceanic and Atmospheric
  Administration (NOAA) path high, and next-24-hour forecast rain;
- the river graph and official National Weather Service KATX radar side by side,
  followed immediately by a six-hour forecast-rain chart;
- three source-timestamped radar views: base reflectivity, estimated previous-hour
  accumulation, and estimated storm-total accumulation, with the official legend
  when it loads and a simplified gauge-upstream drainage-area overlay;
- provisional rolling rain totals from Padilla Bay Farm, Burlington and
  Sedro-Woolley RAWS, displayed separately from forecast locations;
- neutral saved-path comparison wording instead of alert-like wording; and
- an explicit browser-local storm-check log with notes, source timestamps,
  individual deletion, confirmed clear-all and spreadsheet-safe CSV export.

## Meaning and limits

- U.S. Geological Survey (USGS) river measurements are provisional. Direct USGS
  values take precedence at matching timestamps; NOAA’s gauge copy is a fallback.
  A reading older than two hours is labeled stale.
- NOAA forecasts are shown without alignment to the latest gauge. An issue older
  than 48 hours, an unsupported gap or expired coverage withholds the forecast.
  The chart never extrapolates. A forecast high is not a confirmed crest or a
  validated sampling window.
- The seasonal screen is a transparent planning calculation, not the Department
  of Health formula. It uses one constant gauge alignment, a strictly earlier
  rolling 24-hour low, and the confirmed seasonal numbers: 400 cubic feet per
  second (cfs) in November–February, 200 cfs in March–April, and 100 cfs in
  May–October. It reports the rise with the highest share of the seasonal number
  that applies at that point; across a seasonal boundary, this may differ from
  the largest raw rise. Incomplete gauge or forecast support withholds the result.
- The saved-path comparison stores the first capture of each NOAA issue in that
  browser profile for up to 14 days. Its unvalidated 10% comparison line is a
  measuring rule—not a closure probability, alert, dispatch recommendation or
  all-clear. Clearing browser data clears this history.
- Forecast rain comes from two National Weather Service (NWS) grid points. The
  headline is their mean only when both fully cover the next 24 hours. The chart
  uses six-hour blocks. Amounts crossing a block boundary are apportioned
  uniformly; actual timing inside the interval can differ. On every refresh, the
  complete convex four-corner polygons for grids SEW 136,114 and SEW 139,116 must be verified inside
  the current displayed gauge-upstream drainage reference. They are still point
  forecasts, not an area average. Invalid, missing or out-of-reference grid
  geometry—or unavailable reference geometry—withholds that point; missing is never zero.
- The Seattle NWS rain report contains provisional automated-station rolling totals
  for 1, 3, 6, 12, 24, 48 and 72 hours. It is not an hourly history, a basin average
  or ground truth at either forecast point. The page never subtracts the unlike
  locations.
- Radar reflectivity shows echoes aloft. One-hour and storm-total accumulation are
  radar estimates in inches; storm total begins at the radar algorithm’s event
  start and can span more than one day. Radar does not correct NOAA’s river path.
- The USGS Network Linked Data Index supplies a simplified drainage area upstream
  of gauge 12201500, based on whole NHDPlusV2 catchments. It is not the full Samish
  watershed. The outline is a display reference, not a property, harvest-area or
  regulatory boundary. It gates whether each rain point can be displayed but does
  not change any precipitation amount.
- Tide extrema are NOAA predictions in feet relative to mean lower low water at
  Bellingham, not Samish Bay water levels or access clearance.
- The page attempts automatic refresh only while it is open, visible and the device
  is awake. It sends no notification and guarantees no background monitoring.
- A failed source clears that source’s displayed values and cannot become a
  reassuring zero or “low risk.” Failures remain isolated from independent feeds.
- Local storm checks are created only when the user presses Save. They remain in
  that browser profile, can be exported or deleted, and are not sent anywhere. On
  the next save, records older than 90 days are removed and only the newest 500 are kept.
- Historical research summaries are a fixed October 11, 2026 snapshot checked
  against their C1/C2 result records. Public-feed refreshes do not update them.
  No experimental model supplies current values on this page.

`backtest.js` is an unchanged historical asset from the preceding public version.
The current page neither loads it nor uses it to calculate a displayed value.

## Browser checks

Use an isolated quality-assurance environment with `playwright==1.63.0` and its
Chromium browser. The website itself requires no installation or build.

```sh
python tests/check_site.py
```

The test starts and stops its own loopback-only server and intercepts external
requests with deterministic fixtures. An explicit local URL is also accepted.
For the required accessibility pass, set `AXE_PATH` to an axe-core 4.13.0 browser
bundle and `REQUIRE_AXE=1`.

The suite covers 135 numerical contracts, including Pacific-time seasonal
boundaries; strict river-history and forecast support; first-capture immutability;
six-hour rain mass and missing coverage; Seattle rain-report zero, missing,
monotonic-window, age, index/payload-clock and exact-row identity handling; radar
capability clocks; closed, nondegenerate, non-self-intersecting basin and grid geometry;
full grid-cell containment across concave boundaries and holes, including boundary-touching holes and rejection of unexpected non-quadrilateral cells; seasonal-boundary
selection by share rather than raw rise;
stale river-change rejection; storm-record validation; and CSV formula neutralization.

Browser checks cover all radar products, exact product time, official-legend failure,
gauge-upstream overlay and retry, missing and out-of-reference rain-grid geometry,
rain chart and table,
event-log save/reload/export/delete/clear,
storage denial and corruption, reduced motion, source-specific failures, total-feed
failure, keyboard tabs, clipboard fallback, and horizontal overflow at 320, 390,
768, 1024 and 1440 pixels in light and dark modes. The required pass also runs
Web Content Accessibility Guidelines (WCAG) 2.0 A/AA, 2.1 AA and 2.2 AA axe-core
checks across operational and failure states. Automated checks supplement—not
replace—browser inspection and source/claim review.

Provider references: [USGS water API](https://api.waterdata.usgs.gov/),
[USGS Network Linked Data Index](https://labs.waterdata.usgs.gov/docs/nldi/),
[NWS grid data](https://weather-gov.github.io/api/gridpoints),
[NWS Seattle text products](https://api.weather.gov/products/types/RRM/locations/SEW),
[NWS KATX Web Map Service](https://opengeo.ncep.noaa.gov/geoserver/katx/ows?service=WMS&request=GetCapabilities),
and [NOAA tide API](https://api.tidesandcurrents.noaa.gov/api/prod/).
