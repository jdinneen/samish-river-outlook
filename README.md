# Samish River Outlook

[Published field-planning page](https://jdinneen.github.io/samish-river-outlook/)

Buildless HTML, CSS and JavaScript. Each browser requests public river, forecast,
rain, radar, gauge-upstream drainage-area and tide sources directly. There is no runtime package,
tracking, account, backend, automated alert or background monitor.

This source is version 7. `version.json` is the machine-readable receipt that
binds a public release to its asset commit and file hashes. It is written when a
version is published, so it names the release that is live, which can be older
than this source.

## Version 7

Version 7 puts what the gauge measured first and stops the page from saying more
than it knows. A review of version 6 against the Samish rise of 29 September 2026
found that the page said “still rising” after the river had stopped, printed no
time beside the river reading, had forgotten by the next morning that the
seasonal number had been passed, and could not flag a forecast that was missing
the rise unless the same device had been open hours earlier.

What changed:

- **River block**, first on the page. The flow in the largest type on the page
  with the reading’s Pacific clock time and its age in minutes; the change over
  the last hour and over about three hours; the rise above the lowest reading of
  the past 24 hours as a share of the seasonal number; and, for 48 hours of
  readings after that rise passes the number, one sentence saying where the rise
  stands. “Still rising” is said only for a new high whose last-hour change is
  “rising”; any other new high is called “New high”. A reading more than 90
  minutes old, or a hole of more than 60 minutes in the last hour, gives “Cannot
  tell whether the river is rising” and no change figure.
- **NOAA block.** The current National Oceanic and Atmospheric Administration
  (NOAA) forecast issue is set against the gauge. A NOAA forecast path starts at
  its next six-hourly point, some hours after it is issued. When the path covers
  the time of the newest gauge reading, NOAA’s value for that time is set against
  the reading: the gauge is above the line when it is higher by at least 10% of
  the seasonal number, and with a measured rise in progress the page then says
  the forecast is not tracking the rise. Until the path reaches the reading, no
  value is invented for the reading’s time. The reading is set against the
  path’s first value, the next thing NOAA says: the gauge is above the line when
  it is higher than that value by the same 10% while the last-hour change is not
  “falling”. A river falling toward NOAA’s first value is not called above it,
  and a larger value days ahead in the path does not hide a mismatch with the
  first one. In that case the page prints measured figures only and never says
  “not tracking”. In both cases the gauge is also above the line whenever it is
  above the highest value in NOAA’s forecast by any amount while the last-hour
  change is “rising”. This uses no saved history, so it works on a first visit.
- NOAA’s peak-time words (a forecast-high time, or that its forecast falls from
  its first value, named with its time) appear only when that comparison was
  made and the gauge is not above the line. Otherwise the page says no peak time
  is read, either because the gauge is above the forecast or because the two
  cannot be compared right now.
- **Tide block.** The last Bellingham high or low stays on screen after it
  passes, with the direction and the next two.
- The earlier-forecast comparison says “rising” only when the last-hour change
  meets the same test as the River block.
- The NOAA-based rise card is titled “What NOAA’s forecast adds” and never says
  “below the numeric line” while the measured rise has passed the number in the
  last 48 hours of readings. It is withheld, with the reason, whenever the River
  block cannot tell, so no rise is computed from a reading the block has refused.
  When it is shown while the gauge is above NOAA’s forecast, it says the forward
  look is built on that forecast.
- A six-hour rain block with no value is drawn as a hatched “no data” column
  instead of an empty space that looks like zero. One observed-rain gauge at
  0.00 inch for 24 hours while both others report 0.25 inch or more is marked
  suspect.
- A Research section dated 13 October 2026 gives the look-back counts the page
  quotes. From May to October the rain card carries one paragraph of context
  about heavy forecast rain. It is context, not an alert.
- The chart axis carries Pacific clock times.
- An unused data file left over from an earlier version is no longer published,
  and the page no longer names the grower whose account prompted these changes.

Meaning and limits of the new blocks:

- Every duration in the River block is counted between gauge reading time
  stamps, never against the device clock. The device’s check time is used only
  for the age of the newest reading.
- A new high is any reading strictly higher than every earlier reading of the
  rise; an equal reading is not one. The last-hour change is called “rising”
  only at +2 cubic feet per second (cfs) and +2% or more. When a higher reading
  from the last 48 hours is held from before this rise began, the new-high line
  names it.
- A reading below an earlier top is called climbing again when its last-hour
  change is “rising”, or when it stands above the lowest reading since that top
  by at least 5% of the top, the about-three-hour change is positive and the
  last-hour change is not negative. Without the second test a slow second climb
  read as “falling”; without its last condition a second bump already on its
  way down read as climbing.
- “This rise” starts at a fresh upward crossing of the seasonal number inside
  the last 48 hours of readings. When the readings do not reach back to where a
  rise began, the page says so, names the highest reading it holds, and prints no
  pause, peak or falling line and no count.
- One hole of more than 60 minutes no longer blanks the measured rise for a day:
  the rise above the lowest reading held is printed as “at least”, a lower bound,
  and the passing of the number as “since at or before”. When the holes inside
  the 24 hours add up to more than 6 hours, the bound is printed without a share
  of the seasonal number, because most of the rise may be hidden.
- When the newest gauge reading is stamped more than 5 minutes after the
  device’s time, the device clock is behind the gauge. The page says so and
  prints no age, no change figure and no state.
- After a new high the page prints both sides of what past rises did: the top
  came within the next 2 hours about 1 time in 4, and was still 8 hours or more
  away about 1 time in 4 (4,027 new-high readings in 172 rises).
- The sentences describe readings already taken. No sentence says the top of a
  rise has passed, and the page prints no clock time and no countdown for it.
  “Paused” (60 minutes of readings with no new high), “may have peaked” (120
  minutes) and “falling” (5% below the high) each come with the count of past
  rises that went higher again. A count is taken from a stated point: the 2-hour
  mark for “may have peaked”, and the first reading 5% below the high for
  “falling”. It is not printed once the newest reading is more than 24 hours of
  readings past that point, the longest span the count covers. After 120 minutes
  with no new high, while the newest reading is higher than the one about three
  hours earlier, the page prints those two facts instead of “may have peaked”,
  with no count.
- Those counts are read from one object, `SamishData.EVIDENCE` in `data.js`: 172
  Samish rises of 2011 to 2023 at 15-minute readings, and three look-backs on
  forecasts (two of them cover July 2018 to early October 2026). Each entry names its period and source. Each is a look-back on past
  years, not a forecast, and none is a chance for the next rise. The display
  rules are in `SamishData.RIVER_RULES`; the Sources tab prints them.
- The dry-season rain paragraph is counted on a different rain forecast from the
  two points the page shows and has not been checked against them. The page
  computes no rain rule, colour or percentage. The two rain sentences appear
  beside “may have peaked” only.
- The 100, 200 and 400 cfs numbers and the 24-hour period are as published in the
  Washington Department of Health’s growing-area map record for Samish Bay (record
  dated 4 September 2026, read 13 October 2026). How the Department sets the
  starting flow, and its clock at a season boundary, are not published there.
- The measured rise is this page’s arithmetic, not the Department of Health’s
  decision, and every line that says the seasonal number was passed ends by
  saying so. No fitted model supplies any value on the page.

## Version 6

Version 6 keeps every Version 5 calculation and evidence boundary, while making
the operating view easier to scan:

- replaces developer-facing browser, profile and storage messages with concise
  operating language;
- collapses the earlier-forecast metrics when no valid comparison exists;
- places the river, forecast and seasonal-summary cards before the optional
  storm-check form; and
- tests each visible tab for the removed internal wording at desktop and phone
  widths, including the save-unavailable state.

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
  A reading older than 90 minutes is shown with its time and age and no
  direction (two hours in version 6).
- NOAA forecasts are shown without alignment to the latest gauge. An issue older
  than 48 hours, an unsupported gap or expired coverage withholds the forecast.
  The chart never extrapolates. A forecast high is not a confirmed crest or a
  validated sampling window.
- The seasonal screen is a transparent planning calculation, not the Department
  of Health formula. It uses one constant gauge alignment, a strictly earlier
  rolling 24-hour low, and the published seasonal numbers: 400 cubic feet per
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
  Bellingham, not Samish Bay water levels or access clearance. The request
  starts 24 to 48 hours back so the high or low that just passed is in hand.
- The page attempts automatic refresh only while it is open, visible and the device
  is awake. It sends no notification and guarantees no background monitoring.
- A failed source clears that source’s displayed values and cannot become a
  reassuring zero or “low risk.” Failures remain isolated from independent feeds.
- Local storm checks are created only when the user presses Save. They remain in
  that browser profile, can be exported or deleted, and are not sent anywhere. On
  the next save, records older than 90 days are removed and only the newest 500 are kept.
- Historical research summaries are a fixed October 11, 2026 snapshot checked
  against their C1/C2 result records, with the look-back on past rises added on
  13 October 2026. Public-feed refreshes do not update them.
  No experimental model supplies current values on this page.

## Browser checks

Use an isolated quality-assurance environment with `playwright==1.63.0` and its
Chromium browser. The website itself requires no installation or build.

```sh
python -m venv qa_env
qa_env/bin/python -m pip install playwright==1.63.0      # qa_env\Scripts\python on Windows
qa_env/bin/python -m playwright install chromium
AXE_PATH=/path/to/axe.min.js REQUIRE_AXE=1 SAMISH_SCREENSHOT_DIR=/path/to/screenshots \
  qa_env/bin/python tests/check_site.py
```

The test starts and stops its own loopback-only server and intercepts external
requests with deterministic fixtures. An explicit local URL is also accepted.
For the required accessibility pass, set `AXE_PATH` to an axe-core 4.13.0 browser
bundle and `REQUIRE_AXE=1`. `SAMISH_SCREENSHOT_DIR` is optional; without it the
screenshots go to a temporary folder.

Harness notes. The synthetic radar and legend images are served with
`Cache-Control: no-store`: without it this Chromium build reuses an image it
already holds, sends no request, and an injected legend or layer failure never
reaches the page (the version 6 suite failed that way in this environment). The
version 7 replay fixes the device clock with Playwright’s clock interface.

Version 7 adds 319 numerical contracts for the river, forecast, tide, rain and
look-back rules, and a replay of the rise of 29 September 2026 through the page
with the clock fixed: eleven moments from 12:20 PM to 8:20 AM the next day, at
desktop and phone sizes, with every River, NOAA and Tide sentence asserted
exactly. The 15-minute gauge readings, the tide predictions and the NOAA river
forecast issues in that replay are real (each moment is served the newest issue
stamped at or before it); the rain and the radar in it are invented and are
marked so in the test file. Further checks cover a stalled feed and a hole in
the readings, a device clock that is behind, a device outside the Pacific time
zone, a first visit, a rise older than the readings compared, a long outage, a
second climb below an earlier top, a second bump already on its way down, a new
high below a reading held from an earlier rise, a count past its 24 hours (the
last four on invented or synthetic readings, marked so), the
phone windows 390 by 664 and 375 by 548 with minimum type sizes, a missing rain
block against a zero one, every look-back count on the page against the
evidence object, words that must not appear on the Outlook tab, and what a
screen reader is told when the state changes.

The version 6 suite covered 143 numerical contracts, including Pacific-time seasonal
boundaries; strict river-history and forecast support; first-capture immutability;
six-hour rain mass and missing coverage; Seattle rain-report zero, missing,
monotonic-window, age, index/payload-clock and exact-row identity handling; radar
capability clocks; closed, nondegenerate, non-self-intersecting basin and grid geometry;
valid shell, hole and multi-polygon relationships; full grid-cell containment across concave
boundaries and holes, including boundary-touching holes and rejection of cells with unexpected
interior rings or non-quadrilateral shapes; seasonal-boundary
selection by relative rise rather than raw rise;
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
