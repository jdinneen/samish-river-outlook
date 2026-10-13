(function () {
  'use strict';
  const D = SamishData, H = D.H, $ = id => document.getElementById(id);
  const fmt = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
  const date = t => t === null || t === undefined ? 'Unavailable' : fmt.format(t);
  const num = n => n === null || n === undefined ? '—' : n.toLocaleString('en-US', { maximumFractionDigits: 1 });
  const inches = mm => mm > 0 && mm / 25.4 < 0.01 ? '<0.01' : (mm / 25.4).toFixed(2);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const put = (id, s) => { $(id).textContent = s; };
  const badge = (id, text, cls = 'neutral') => { put(id, text); $(id).className = 'pill ' + cls; };
  const signed = n => n === null || n === undefined ? '—' : (n > 0 ? '+' : '') + num(n);
  const pacificDay = t => {
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(t));
    const value = Object.fromEntries(parts.map(p => [p.type, p.value]));
    return value.year + value.month + value.day;
  };
  // Version 7 wording helpers. Every count in a sentence is read from D.EVIDENCE or D.RIVER_RULES; none is typed here.
  const E = D.EVIDENCE, RULES = D.RIVER_RULES;
  const clockFmt = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
  // A Pacific clock time with its zone. The date is added whenever the Pacific day differs from the check time's day.
  const clock = (t, ref) => t === null || t === undefined ? 'Unavailable' : pacificDay(t) === pacificDay(ref) ? clockFmt.format(t) : fmt.format(t);
  const plural = (n, word) => num(n) + ' ' + word + (n === 1 ? '' : 's');
  const hoursMinutes = minutes => Math.floor(minutes / 60) + ' h ' + (minutes % 60) + ' min';
  const elapsed = minutes => minutes < 60 ? plural(minutes, 'minute') : hoursMinutes(minutes);
  const issueAge = minutes => minutes < 60 ? plural(minutes, 'minute') : plural(Math.round(minutes / 60), 'hour');
  const halves = n => Number.isInteger(n) ? String(n) : Number.isInteger(n * 2) ? (Math.floor(n) || '') + '½' : num(n);
  const percent = fraction => num(Math.round(fraction * 1000) / 10);
  const smallWord = n => ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'][n] ?? String(n);
  const within = hours => hours === 24 ? 'a day' : hours === 36 ? 'a day and a half' : hours + ' hours';
  const show = (id, text) => { const el = $(id); el.hidden = !text; el.textContent = text || ''; };
  const SAY = Object.freeze({
    afterNewHigh: () => { const a = E.afterNewHigh; return 'When a reading was a new high in past rises, the top of the rise came within the next ' + a.withinHours + ' hours about 1 time in ' + a.aboutOneInWithin + ' and was still ' + a.atLeastHours + ' hours or more away about 1 time in ' + a.aboutOneInAtLeast + ' (' + num(a.readings) + ' such readings in ' + a.rises + ' rises). A new high can be the top; a long rise is not due to stop.'; },
    rainPause: () => 'If rain is still falling over the basin on radar, a pause is less likely to be the peak. Rain stopping does not mean the river has peaked: on ' + E.rainPause.storm + ' the rain ended ' + E.rainPause.rainEnded + ' and the river kept rising until ' + E.rainPause.riverRoseUntil + '.',
    pause: () => 'A pause is not a peak: after a ' + (E.pause.afterMinutes === 60 ? 'one-hour' : E.pause.afterMinutes + '-minute') + ' pause, ' + E.pause.higherAgain + ' of ' + E.pause.rises + ' past rises went higher again within ' + within(E.pause.withinHours) + ', ' + E.pause.higherByMoreThan5Percent + ' of them by more than 5%.',
    peak: () => 'Of ' + E.peak2h.rises + ' past rises that went ' + num(E.peak2h.afterMinutes / 60) + ' hours without a new high, counted from that ' + num(E.peak2h.afterMinutes / 60) + '-hour mark, the river later climbed more than 5% above that high within 12 hours in ' + E.peak2h.within12h + ' (about 1 in ' + E.peak2h.aboutOneIn12h + ') and within 24 hours in ' + E.peak2h.within24h + ' (about 1 in ' + E.peak2h.aboutOneIn24h + ').',
    falling: () => 'Of ' + E.falling.rises + ' past rises, counted from that point, the river later climbed more than 5% above that high within 12 hours in ' + E.falling.within12h + ' (about 1 in ' + E.falling.aboutOneIn12h + ') and within 24 hours in ' + E.falling.within24h + ' (about 1 in ' + E.falling.aboutOneIn24h + ').',
    noaaDry: () => 'NOAA’s river forecast, read hour by hour, showed a closure-size rise ' + E.noaaDry.leadHours + ' or more hours ahead for ' + E.noaaDry.shown12hAhead + ' of ' + E.noaaDry.rises + ' ' + E.noaaDry.period + ', and not for ' + E.noaaDry.notShown + ', among them ' + E.noaaDry.notShownIncludes + '.',
    rainContext: () => { const c = E.rainContext; return 'In a look-back over the ' + c.period + ', the river forecast centre’s rain forecast for this basin reached ' + c.thresholdIn + ' inch or more in ' + c.windowHours + ' hours about ' + c.perSeason + ' times a season. About half of those times (' + c.followed + ' of ' + c.occasions + ') the river then rose by ' + c.riseCfs + ' cubic feet per second or more within ' + within(c.followedWithinHours) + '. When NOAA’s river forecast showed no such rise and the rain forecast was that high, a rise followed about 1 time in ' + c.aboutOneInWithNoNoaaRise + ' (' + c.withNoNoaaRiseFollowed + ' of ' + c.withNoNoaaRise + '). Rain that high was in the forecast ' + c.leadHours + ' or more hours ahead of ' + c.ofThoseRainForecastAhead + ' of the ' + c.risesNoaaDidNotShow + ' dry-season rises that NOAA’s river forecast did not show, all ' + smallWord(c.ofThoseRainForecastAhead) + ' in ' + c.aheadYears + ', including ' + c.aheadIncludes + '. Less rain than this is not an all-clear: ' + c.risesWithLessRain + ' of ' + c.risesWithForecast + ' rises came with less. These counts are for a different rain forecast from the two points shown here and have not been checked against them.'; }
  });
  // NOAA's peak-time words are printed only when a comparison was made and the gauge is not above the line.
  const NO_PEAK_ABOVE = 'No peak time is read from NOAA’s forecast while the gauge is above it.';
  const NO_PEAK_UNCOMPARED = 'No peak time is read from NOAA’s forecast: it cannot be compared with the gauge right now.';
  const SNAPSHOT_KEY = 'samish-river-outlook.forecast-snapshots.v1';
  const STORM_LOG_KEY = 'samish-river-outlook.storm-checks.v1';
  const RADAR_PAUSE_KEY = 'samish-river-outlook.radar-paused.v1';
  const RADAR_BASE = 'https://opengeo.ncep.noaa.gov/geoserver/katx/ows';
  const RADAR_PAGE = 'https://radar.weather.gov/station/KATX/standard';
  const RADAR_BBOX = Object.freeze({ west: -122.55, south: 48.45, east: -122.05, north: 48.78 });
  const RADAR_PRODUCTS = Object.freeze({
    reflectivity: Object.freeze({ layer: 'katx_sr_bref', label: 'Base reflectivity', note: 'Reflectivity shows echo intensity aloft in decibels of reflectivity (dBZ). It is not rain measured at the ground.' }),
    hourly: Object.freeze({ layer: 'katx_boha', label: 'Estimated one-hour accumulation', note: 'This is a radar estimate of precipitation during the previous hour, in inches—not a rain-gauge total.' }),
    storm: Object.freeze({ layer: 'katx_bdsa', label: 'Estimated storm-total accumulation', note: 'This is a radar estimate in inches since the radar algorithm’s precipitation event began. The period can span more than one day.' })
  });
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let state = null, busy = false, basinPromise = null, radarTimer = null, rainChartWidth = 0;
  let radar = { product: 'reflectivity', capabilities: null, error: null, requestedAt: null, retrievedAt: null, frame: 0, validTime: null, imageError: null, legendError: null, legendLoaded: false, legendUrl: null, playing: !prefersReducedMotion && readPausePreference() !== true };
  const sources = [
    { name: 'NOAA river forecast & gauge copy', url: 'https://api.water.noaa.gov/nwps/v1/gauges/smrw1/stageflow' },
    { name: 'USGS Burlington gauge', url: 'https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items?monitoring_location_id=USGS-12201500&parameter_code=00060&time=P3D&f=json&limit=1000' },
    { name: 'NWS rain · grid 136,114', url: 'https://api.weather.gov/gridpoints/SEW/136,114' },
    { name: 'NWS rain · upper-east gauge-upstream grid 139,116', url: 'https://api.weather.gov/gridpoints/SEW/139,116' },
    { name: 'NOAA Bellingham tide predictions', url: '' }
  ];
  const RRM_INDEX = { name: 'NWS Seattle provisional rain report', url: 'https://api.weather.gov/products/types/RRM/locations/SEW' };
  const BASIN_SOURCE = { name: 'USGS simplified gauge-upstream drainage area', url: 'https://api.water.usgs.gov/nldi/linked-data/nwissite/USGS-12201500/basin?f=json' };
  async function fetchFeed(s) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(s.url, { signal: controller.signal, cache: 'no-store' });
      if (!response.ok) throw Error('HTTP ' + response.status);
      return { ...s, data: s.responseType === 'text' ? await response.text() : await response.json(), retrieved: Date.now() };
    } catch (e) { return { ...s, error: e.name === 'AbortError' ? 'Request timed out' : 'Feed could not be retrieved' }; }
    finally { clearTimeout(timer); }
  }
  async function fetchLatestRrm(now) {
    const index = await fetchFeed(RRM_INDEX);
    if (index.error) return index;
    let selected;
    try { selected = D.rrmProductId(index.data, now); }
    catch (e) { return { ...RRM_INDEX, retrieved: index.retrieved, error: e.message }; }
    const productUrl = 'https://api.weather.gov/products/' + encodeURIComponent(selected.id);
    const product = await fetchFeed({ ...RRM_INDEX, url: productUrl });
    return product.error ? product : { ...product, indexUrl: RRM_INDEX.url, selectedIssue: selected.issued };
  }
  function fetchBasinOnce() {
    if (!basinPromise) basinPromise = fetchFeed(BASIN_SOURCE);
    return basinPromise;
  }
  function parse(feed, fn) {
    if (feed.error) return null;
    try { return fn(feed.data); } catch (e) { feed.error = e.message; return null; }
  }
  function readHistory() {
    try {
      const raw = localStorage.getItem(SNAPSHOT_KEY);
      if (raw === null) return { status: 'available', snapshots: [] };
      const snapshots = JSON.parse(raw);
      return Array.isArray(snapshots) && snapshots.length <= 50 ? { status: 'available', snapshots } : { status: 'unavailable', snapshots: [] };
    } catch { return { status: 'unavailable', snapshots: [] }; }
  }
  function saveSnapshot(history, snapshot, now) {
    if (history.status !== 'available') return history;
    try {
      const cutoff = now - D.WATCH.retentionDays * 24 * H;
      const kept = history.snapshots.filter(r => Number.isFinite(Date.parse(r?.capturedAt)) && Date.parse(r.capturedAt) >= cutoff);
      if (snapshot && !kept.some(r => r?.issueTime === snapshot.issueTime)) kept.unshift(snapshot);
      const snapshots = kept.slice(0, 50);
      localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snapshots));
      return { status: 'available', snapshots };
    } catch { return { status: 'unavailable', snapshots: [] }; }
  }
  function readPausePreference() {
    try { return localStorage.getItem(RADAR_PAUSE_KEY) === 'true'; }
    catch { return null; }
  }
  function writePausePreference(paused) {
    try { localStorage.setItem(RADAR_PAUSE_KEY, String(paused)); } catch { /* Radar still works without persistence. */ }
  }
  function radarMapUrl(layer, validTime) {
    const query = new URLSearchParams({ service: 'WMS', version: '1.1.1', request: 'GetMap', layers: layer, styles: '', format: 'image/png', transparent: 'false', srs: 'EPSG:4326', bbox: [RADAR_BBOX.west, RADAR_BBOX.south, RADAR_BBOX.east, RADAR_BBOX.north].join(','), width: '900', height: '600', time: new Date(validTime).toISOString() });
    return RADAR_BASE + '?' + query.toString();
  }
  function radarLegendUrl(layer) {
    return RADAR_BASE + '?' + new URLSearchParams({ service: 'WMS', version: '1.1.1', request: 'GetLegendGraphic', format: 'image/png', layer }).toString();
  }
  function radarSourceCard() {
    const product = RADAR_PRODUCTS[radar.product], unavailable = !!radar.error || !!radar.imageError || !radar.capabilities, partial = !unavailable && !!radar.legendError;
    const status = unavailable ? 'Unavailable' : partial ? 'Partial' : 'Retrieved';
    const detail = unavailable ? radar.error || radar.imageError || 'Radar metadata unavailable' : product.label + ' valid ' + date(radar.validTime) + '. This is the radar product time—not the page-check time.';
    const legend = radar.legendError ? ' Official legend unavailable.' : radar.legendLoaded ? ' Official legend retrieved.' : ' Official legend pending.';
    return '<article id="radar-source-card" class="card source-card"><h2>National Weather Service KATX radar</h2><span class="pill ' + (unavailable || partial ? 'caution' : 'neutral') + '">' + status + '</span><p class="detail">' + esc(detail) + '</p><p class="meta">' + esc(radar.retrievedAt ? 'Capabilities retrieved ' + date(radar.retrievedAt) + '.' + legend : radar.requestedAt ? 'Capabilities requested ' + date(radar.requestedAt) + '.' : 'Radar metadata has not been requested yet.') + '</p><a href="' + RADAR_PAGE + '" target="_blank" rel="noopener">Inspect official radar ↗</a></article>';
  }
  function updateRadarSourceCard() {
    const card = $('radar-source-card');
    if (card) card.outerHTML = radarSourceCard();
  }
  function projectRadarPoint(lon, lat) {
    return { x: (lon - RADAR_BBOX.west) / (RADAR_BBOX.east - RADAR_BBOX.west) * 900, y: (RADAR_BBOX.north - lat) / (RADAR_BBOX.north - RADAR_BBOX.south) * 600 };
  }
  function renderRadarOverlay() {
    const svg = $('radar-overlay');
    if (!state) { svg.innerHTML = ''; return; }
    const paths = (state.basin?.rings || []).map(ring => ring.map((point, index) => { const p = projectRadarPoint(point[0], point[1]); return (index ? 'L' : 'M') + p.x.toFixed(1) + ',' + p.y.toFixed(1); }).join(' ') + ' Z').join(' ');
    const markers = [];
    if (state.gaugePoint) markers.push({ ...state.gaugePoint, label: 'Gauge', cls: 'gauge-marker', labelY: 7 });
    (state.gridPoints || []).forEach((point, index) => { if (point) markers.push({ ...point, label: index ? 'Upper-east grid' : 'Mid grid', cls: 'rain-marker', labelY: index ? 34 : -16 }); });
    const description = (paths ? 'The simplified drainage area upstream of United States Geological Survey gauge 12201500, based on whole NHDPlusV2 catchments, ' : 'The gauge-upstream drainage outline is unavailable; ') + 'the Burlington river gauge and available National Weather Service forecast grid points are marked.';
    svg.innerHTML = '<title>Gauge-upstream drainage reference overlay</title><desc>' + description + '</desc>' + (paths ? '<path class="basin-shape" fill-rule="evenodd" d="' + paths + '"><title>Simplified drainage area upstream of gauge 12201500 from the USGS Network Linked Data Index</title></path>' : '') + markers.map(marker => { const p = projectRadarPoint(marker.lon, marker.lat), rightSide = p.x > 470, textX = rightSide ? -14 : 14, anchor = rightSide ? 'end' : 'start'; return '<g class="' + marker.cls + '" transform="translate(' + p.x.toFixed(1) + ' ' + p.y.toFixed(1) + ')"><circle r="9"></circle><text x="' + textX + '" y="' + marker.labelY + '" text-anchor="' + anchor + '">' + esc(marker.label) + '</text></g>'; }).join('');
    svg.setAttribute('aria-label', paths ? 'Simplified gauge-upstream drainage reference with Burlington river gauge and available forecast rain points' : 'Gauge-upstream drainage outline unavailable; Burlington river gauge and available forecast rain points only');
    svg.dataset.basin = paths ? 'available' : 'unavailable';
    $('radar-basin-note').hidden = !!paths;
    put('radar-basin-note', paths ? '' : 'Drainage outline unavailable; forecast-rain points were withheld because their grid cells could not be checked. Radar remains independent.');
    const image = $('radar-loop');
    if (radar.imageError || radar.error) markRadarImageUnavailable(image);
    else if (radar.validTime) image.alt = RADAR_PRODUCTS[radar.product].label + ' from National Weather Service KATX, valid ' + date(radar.validTime) + (paths ? ', with the simplified drainage area upstream of gauge 12201500 outlined.' : '. The gauge-upstream drainage outline is unavailable.');
  }
  function renderRadarLegendStatus() {
    const wrap = $('radar-legend-wrap');
    if (radar.imageError) {
      wrap.hidden = true;
      put('radar-legend-status', 'Official legend hidden because the selected radar image is unavailable. Open the full radar for context.');
      $('radar-legend-status').className = 'measurement-limit radar-legend-status';
    } else if (radar.legendError) {
      wrap.hidden = true;
      put('radar-legend-status', 'Official radar legend unavailable. Open the full radar before interpreting colours.');
      $('radar-legend-status').className = 'measurement-limit radar-legend-status';
    } else if (radar.legendLoaded) {
      wrap.hidden = false;
      put('radar-legend-status', 'Official legend retrieved below; scroll sideways when the full scale is wider than this panel.');
      $('radar-legend-status').className = 'meta radar-legend-status';
    } else {
      wrap.hidden = true;
      put('radar-legend-status', 'Official radar legend loading…');
      $('radar-legend-status').className = 'meta radar-legend-status';
    }
  }
  function selectedRadarTimes() {
    const layer = RADAR_PRODUCTS[radar.product].layer;
    return (radar.capabilities?.[layer]?.times || []).slice(-10);
  }
  function markRadarImageUnavailable(image) {
    image.alt = 'Selected National Weather Service KATX radar image unavailable.';
  }
  function updateRadarFrame(quiet = false) {
    clearTimeout(radarTimer);
    const product = RADAR_PRODUCTS[radar.product], times = selectedRadarTimes(), image = $('radar-loop');
    document.querySelectorAll('[data-radar-product]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.radarProduct === radar.product)));
    put('radar-product-note', product.note);
    if (!times.length || radar.error) {
      radar.validTime = null; image.removeAttribute('src'); image.parentElement.classList.add('unavailable');
      markRadarImageUnavailable(image);
      badge('radar-status', 'Unavailable', 'caution'); put('radar-frame-time', 'Radar product time unavailable');
      put('radar-requested', radar.error || 'No recent product time was advertised. River and rain feeds remain independent.');
      radar.legendLoaded = false; radar.legendError = 'Legend not requested because this radar product is unavailable.'; radar.legendUrl = null; $('radar-legend').removeAttribute('src'); renderRadarLegendStatus();
      $('radar-toggle').disabled = true; updateRadarSourceCard(); return;
    }
    radar.imageError = null;
    const legend = $('radar-legend'), nextLegendUrl = radarLegendUrl(product.layer);
    if (radar.legendUrl !== nextLegendUrl) {
      radar.legendUrl = nextLegendUrl; radar.legendLoaded = false; radar.legendError = null;
      legend.dataset.layer = product.layer; legend.alt = 'Official legend for ' + product.label; legend.src = nextLegendUrl;
    }
    renderRadarLegendStatus();
    radar.frame = Math.max(0, Math.min(radar.frame, times.length - 1));
    radar.validTime = times[radar.frame];
    image.dataset.validTime = String(radar.validTime);
    image.alt = product.label + ' from National Weather Service KATX, valid ' + date(radar.validTime) + (state?.basin ? ', with the simplified drainage area upstream of gauge 12201500 outlined.' : '. The gauge-upstream drainage outline is unavailable.');
    image.parentElement.classList.remove('unavailable');
    image.src = radarMapUrl(product.layer, radar.validTime);
    put('radar-frame-time', product.label + ' · valid ' + date(radar.validTime));
    put('radar-requested', 'Official product time from capabilities retrieved ' + date(radar.retrievedAt) + '. Showing frame ' + (radar.frame + 1) + ' of ' + times.length + '.');
    put('radar-toggle', radar.playing ? 'Pause animation' : 'Play animation'); $('radar-toggle').disabled = times.length < 2;
    if (!quiet) badge('radar-status', 'Loading frame', 'neutral');
    updateRadarSourceCard();
  }
  async function refreshRadar() {
    clearTimeout(radarTimer); radar.requestedAt = Date.now(); radar.retrievedAt = null; radar.error = null; radar.capabilities = null; radar.legendUrl = null; radar.legendLoaded = false; radar.legendError = null;
    badge('radar-status', 'Loading', 'neutral'); put('radar-requested', 'Requesting official KATX product times…'); $('radar-toggle').disabled = true;
    const feed = await fetchFeed({ name: 'NWS KATX radar capabilities', url: RADAR_BASE + '?service=WMS&version=1.3.0&request=GetCapabilities', responseType: 'text' });
    if (feed.error) radar.error = feed.error;
    else {
      try { radar.capabilities = D.radarCapabilities(feed.data, Date.now()); radar.retrievedAt = Date.now(); }
      catch (e) { radar.error = e.message; }
    }
    const times = selectedRadarTimes(); radar.frame = Math.max(0, times.length - 1); updateRadarFrame();
  }
  async function load() {
    if (busy) return;
    busy = true; $('refresh').disabled = true; $('main').setAttribute('aria-busy', 'true');
    put('update-status', 'Checking the latest public data… Existing readings remain dated until the check finishes.');
    try {
    const requestTime = Date.now(), tideWindow = D.tideRequest(requestTime);
    // The request starts 24 to 48 hours back so the high or low that just passed is still in hand.
    sources[4].url = tideWindow ? 'https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions&station=9449211&begin_date=' + tideWindow.beginDate + '&range=' + tideWindow.rangeHours + '&datum=MLLW&units=english&time_zone=gmt&interval=hilo&format=json&application=samish_outlook' : '';
    const [coreFeeds, rrmFeed, basinFeed] = await Promise.all([Promise.all(sources.map(fetchFeed)), fetchLatestRrm(requestTime), fetchBasinOnce()]), now = Date.now();
    // Each series is parsed independently: a malformed forecast must not erase a valid gauge.
    const riverFeed = coreFeeds[0], gaugeCopy = { ...riverFeed }, observations = parse(gaugeCopy, d => D.nwpsSeries(d.observed, now, true)) || [];
    let rawForecast = [], issue = null;
    if (!riverFeed.error) {
      try { rawForecast = D.nwpsSeries(riverFeed.data.forecast, now, false); issue = riverFeed.data.forecast.issuedTime; }
      catch (e) { riverFeed.error = 'Forecast: ' + e.message; }
    }
    const direct = parse(coreFeeds[1], d => D.usgs(d, now)) || [];
    const gaugePoint = coreFeeds[1].error ? null : D.gaugePoint(coreFeeds[1].data);
    if (!coreFeeds[1].error && !direct.length) coreFeeds[1].error = 'No valid discharge readings';
    const merged = [...new Map([...observations, ...direct].map(r => [r.t, r])).values()].sort((a, b) => a.t - b.t);
    const fc = D.forecast(rawForecast, issue, now);
    const rains = [2, 3].map(i => { const r = parse(coreFeeds[i], d => D.rain(d, now)); return r ? { ...r, ...D.rainWindow(r, now, 24), bins: D.rainBins(r, now, 36, 6), fresh: now - r.updated <= 24 * H } : null; });
    const basin = parse(basinFeed, D.basinGeometry);
    if (basinFeed.error) basinPromise = null;
    const gridPoints = [2, 3].map(i => coreFeeds[i].error ? null : D.gridPoint(coreFeeds[i].data));
    gridPoints.forEach((point, index) => {
      if (!coreFeeds[index + 2].error && (!point || !basin || !D.gridCellWithinBasin(point, basin))) {
        coreFeeds[index + 2].error = !point ? 'Forecast grid geometry unavailable; precipitation values withheld' : !basin ? 'Gauge-upstream drainage geometry unavailable; precipitation values withheld' : 'Forecast grid is not fully inside the displayed gauge-upstream drainage reference; precipitation values withheld';
        rains[index] = null;
        gridPoints[index] = null;
      }
    });
    const observedRain = parse(rrmFeed, d => D.rrmRain(d, now, rrmFeed.selectedIssue));
    // Unfiltered highs and lows go to tideState, which keeps the last one after it passes.
    const tideRows = parse(coreFeeds[4], D.tides), tide = D.tideState(tideRows, now);
    if (!coreFeeds[4].error && !tide.available) coreFeeds[4].error = tide.reason;
    // The measured River block reads the gauge only; NOAA's current issue is then set against it.
    // riverState is handed every reading the feeds supplied, including any stamped after this device's time: a
    // newest reading stamped ahead of the device clock is how a slow clock is noticed. Everything else uses `merged`.
    const stampedCopy = gaugeCopy.error ? [] : parse({ ...gaugeCopy }, d => D.nwpsSeries(d.observed, Infinity, true)) || [], stampedDirect = coreFeeds[1].error ? [] : parse({ ...coreFeeds[1] }, d => D.usgs(d, Infinity)) || [];
    const stamped = [...new Map([...stampedCopy, ...stampedDirect].map(r => [r.t, r])).values()];
    const river = D.riverState(stamped, now), noaa = D.noaaAgainstGauge(river, rawForecast, issue, now), anchor = D.countAnchor(stamped, river);
    const latest = merged.at(-1), three = river.threeHour, refused = cannotTellWhy(river);
    // When the River block cannot tell, the NOAA-based rise card is withheld too: no rise is computed from that reading.
    const screen = refused ? { usable: false, reason: 'Withheld: ' + refused + '.', alignedRows: [] } : fc.usable ? D.planningScreen(merged, rawForecast, now) : { usable: false, reason: 'A current usable NOAA forecast is required', alignedRows: [] };
    const initialHistory = readHistory();
    // The earlier-forecast comparison keeps its own rule; its "rising" word is then taken from the last-hour label.
    let watch = D.watchWithLastHour(D.surpriseWatch({ t: latest?.t, q: latest?.q, change3: three?.change, span3: three ? three.spanMinutes / 60 : undefined, fresh: river.fresh }, initialHistory.snapshots, initialHistory.status), river);
    const revision = D.forecastRevision(fc, initialHistory.snapshots, now);
    const history = saveSnapshot(initialHistory, D.makeSnapshot(fc, screen, latest, now), now);
    if (history.status !== 'available') watch = D.watchWithLastHour(D.surpriseWatch(null, [], 'unavailable'), river);
    state = { now, feeds: [...coreFeeds, rrmFeed, basinFeed], observations: merged, rawForecast, direct, gaugeCopy, fc, rains, observedRain, basin, gaugePoint, gridPoints, tideRows: tideRows || [], tide, river, noaa, anchor, screen, watch, revision, history };
    render();
    } catch {
      const failedAt = Date.now(), noRiver = D.riverState([], failedAt);
      state = { now: failedAt, feeds: [...sources, RRM_INDEX, BASIN_SOURCE].map(s => ({ ...s, error: 'Unexpected feed processing error' })), observations: [], rawForecast: [], direct: [], gaugeCopy: { error: 'Unavailable' }, fc: { usable: false, reason: 'Forecast processing unavailable', issued: null, rows: [] }, rains: [null, null], observedRain: null, basin: null, gaugePoint: null, gridPoints: [], tideRows: [], tide: D.tideState(null, failedAt), river: noRiver, noaa: D.noaaAgainstGauge(noRiver, null, null, failedAt), anchor: null, screen: { usable: false, reason: 'River processing unavailable' }, watch: { code: 'unknown', reason: 'River processing unavailable', lastHourLabel: null }, revision: { usable: false, reason: 'River processing unavailable' }, history: readHistory() };
      render();
    } finally { busy = false; $('refresh').disabled = false; $('main').setAttribute('aria-busy', 'false'); }
  }
  function render() {
    const { now, feeds, observations, direct, gaugeCopy, fc, rains, observedRain, tideRows, tide, river, noaa, anchor, screen, watch, revision, history } = state, last = observations.at(-1);
    put('update-status', 'Data checked ' + date(now) + ' · Updates about every 10 minutes while this page is on screen. No alerts are sent.');
    const problems = [];
    const clockBehind = river.staleCode === 'clock-behind';
    if (!river.fresh && !clockBehind) problems.push(!river.available ? 'The gauge is unavailable' : river.staleCode === 'old-reading' ? 'The newest gauge reading is ' + plural(river.ageMinutes, 'minute') + ' old' : 'Gauge readings are missing in the last hour');
    if (!fc.usable) problems.push('the river forecast is unavailable');
    if (!rains.every(r => r?.fresh && r.complete)) problems.push('the rain summary is incomplete');
    if (!observedRain || !observedRain.fresh) problems.push('the nearby observed-rain report is ' + (observedRain ? 'stale' : 'unavailable'));
    if (!tide.available) problems.push('tide predictions are unavailable');
    $('feed-alert').hidden = !problems.length && !clockBehind;
    const problemText = problems.join('; ');
    // A device clock that is behind the gauge is said in the banner in the River block's own words, before anything else.
    put('feed-alert', [clockBehind ? cannotTellSentence(river) : '', problemText ? problemText.charAt(0).toUpperCase() + problemText.slice(1) + '. Check the dated source details before planning.' : ''].filter(Boolean).join(' '));
    const onlyFalls = fc.usable && noaa.pathOnlyFalls === true;
    const riverSaid = renderRiver(river, anchor, now), compared = renderNoaa(noaa, river, now);
    // NOAA's peak-time words (a forecast-high time, "falls from its first value") appear ONLY when a comparison was made and the
    // gauge is not above the line. Otherwise one of two sentences says why no peak time is read.
    const peakWithheld = compared.compare === 'within' ? null : compared.compare === 'above' ? NO_PEAK_ABOVE : NO_PEAK_UNCOMPARED;
    renderTide(tide, now);
    announce([[[river.staleCode || 'fresh', river.riseStatus, river.riseStart?.atOrBefore ? 'at-or-before' : upOnThreeHours(river) ? 'no-new-high-but-up-on-three-hours' : river.state].join('|'), riverSaid], [noaa.code + '|' + compared.compare, compared.said]]);
    put('observation-note', 'Flow in cubic feet per second (cfs) · U.S. Geological Survey (USGS) station 12201500 · provisional observations, subject to revision' + (last ? ' · ' + last.source : ''));
    const threshold = D.thresholdAt(now);
    put('ops-threshold', threshold ? threshold.cfs + ' cfs' : 'Unavailable');
    put('ops-threshold-note', threshold ? threshold.label + ' · not a forecast' : 'Season unavailable · not a forecast');
    const issuedText = fc.issued === null ? 'issue time unavailable' : 'issued ' + clock(fc.issued, now);
    put('ops-forecast', !fc.usable ? 'Unavailable' : onlyFalls ? 'Only falls' : num(fc.max) + ' cfs');
    put('ops-forecast-note', !fc.usable ? fc.reason : (onlyFalls ? 'NOAA’s path falls from its first value · ' : 'within the available path · ') + issuedText);
    renderWatch(watch, history);
    renderRise(screen, last ? D.thresholdAt(last.t) : threshold, river, compared.compare, now);
    badge('forecast-status', fc.usable ? (fc.complete ? 'Up to 72 h' : 'Shorter horizon') : 'Unavailable', fc.usable ? 'neutral' : 'caution');
    put('forecast-high', fc.usable && !onlyFalls ? num(fc.max) : '—');
    $('forecast-metric').hidden = fc.usable && onlyFalls;   // a path that only falls has no "high": words, not a number
    put('forecast-time', !fc.usable ? fc.reason : peakWithheld ? peakWithheld : onlyFalls ? 'NOAA’s forecast path only falls from its first value (' + num(fc.rows[0].q) + ' cfs at ' + clock(fc.rows[0].t, now) + '). That value is not a forecast high.' : fc.atStart && fc.atEnd ? 'Highest value occurs at both ends of the available window' : fc.atEnd ? 'Highest at the end · peak may be later' : fc.atStart ? 'Highest at the start of this forecast window' : 'Forecast high around ' + date(fc.firstMax));
    put('forecast-coverage', fc.usable ? (fc.startsAfterCheck ? 'Path begins ' + date(fc.start) + ' · ' + num((fc.start - now) / H) + ' h after this check; no check-time value was inserted. ' : '') + 'Available through ' + date(fc.end) + ' · ' + num(fc.hours) + ' h from this check.' + (fc.firstMax !== fc.lastMax ? ' The highest value occurs at more than one forecast time.' : '') : 'No forecast high or timing estimate is shown.');
    put('forecast-issue', fc.issued === null ? 'Issue time unavailable' : 'NOAA issued · ' + date(fc.issued));
    put('forecast-revision', revision.usable ? 'Across the same next 24 hours, the latest NOAA issue’s high is ' + signed(revision.difference) + ' cfs versus the earlier issue from ' + date(revision.previousIssue) + '.' : revision.reason);
    renderRainForecast(rains, now);
    renderObservedRain(observedRain);
    badge('tide-status', tide.available ? 'Predicted' : 'Unavailable', tide.available ? 'neutral' : 'caution');
    const listed = tideList();
    $('tide-list').innerHTML = listed.length ? listed.map(r => '<div class="tide-row"><span>' + (r.type === 'H' ? 'High' : 'Low') + '</span><strong>' + feet(r.v) + '<span class="small-label">ft MLLW</span></strong><time datetime="' + new Date(r.t).toISOString() + '">' + esc(date(r.t)) + (r.passed ? ' · passed' : '') + '</time></div>').join('') : 'Tide predictions unavailable. Use the official tide source.';
    renderCrest(fc, tideRows, peakWithheld, onlyFalls, now);
    const directLast = [...direct].sort((a, b) => a.t - b.t).at(-1);
    const sourceTimes = [(fc.issued === null ? 'Forecast issue time unavailable' : 'Forecast issued ' + date(fc.issued)) + (gaugeCopy.error ? ' · Gauge copy: ' + gaugeCopy.error : ''), directLast ? 'Latest direct USGS reading ' + date(directLast.t) : 'No direct USGS reading', ...rains.map(r => r ? 'Forecast updated ' + date(r.updated) : 'Update unavailable'), 'Astronomical high/low predictions; issue time not supplied', observedRain ? 'Product issued ' + date(observedRain.issued) + '; issue time is not a gauge measurement time' : 'Product issue time unavailable', state.basin ? 'Simplified gauge-upstream drainage area · ' + state.basin.pointCount + ' source vertices · based on whole NHDPlusV2 catchments' : 'Gauge-upstream drainage geometry unavailable'];
    $('source-status').innerHTML = feeds.map((f, i) => '<article class="card source-card"><h2>' + esc(f.name) + '</h2><span class="pill ' + (f.error ? 'caution' : 'neutral') + '">' + (f.error ? 'Feed problem' : 'Retrieved') + '</span><p class="detail">' + esc(sourceTimes[i]) + '</p><p class="meta">' + esc(f.error || 'Retrieved ' + date(f.retrieved)) + '</p><a href="' + esc(f.url) + '" target="_blank" rel="noopener">Inspect public feed ↗</a></article>').join('') + radarSourceCard();
    $('forecast-table').innerHTML = fc.usable ? '<table><caption>Available NOAA forecast; ' + (fc.startsAfterCheck ? 'the path starts at NOAA’s first future value and no check-time value was inserted.' : 'the check-time and final values may be interpolated within supported intervals.') + '</caption><thead><tr><th scope="col">Pacific time</th><th scope="col">Flow (cfs)</th></tr></thead><tbody>' + fc.rows.map(r => '<tr><td>' + esc(date(r.t)) + '</td><td>' + num(r.q) + '</td></tr>').join('') + '</tbody></table>' : '<p>No usable river forecast. No values have been extrapolated.</p>';
    const recent = observations.filter(r => r.t >= now - 48 * H).slice().reverse();
    $('observed-table').innerHTML = recent.length ? '<table><caption>Provisional USGS observations from the past 48 hours, newest first.</caption><thead><tr><th scope="col">Pacific time</th><th scope="col">Flow (cfs)</th><th scope="col">Retrieved via</th></tr></thead><tbody>' + recent.map(r => '<tr><td>' + esc(date(r.t)) + '</td><td>' + num(r.q) + '</td><td>' + esc(r.source) + '</td></tr>').join('') + '</tbody></table>' : '<p>No observations retrieved for the past 48 hours.</p>';
    $('copy-brief').disabled = false; $('download-brief').disabled = false; $('brief-fallback').hidden = true; put('copy-status', '');
    renderRadarOverlay();
    renderStormLog();
    chart();
  }
  // Why the River block cannot tell, in plain words; null when it can. The NOAA comparison and the NOAA-based rise
  // card are withheld for the same reason, so the page never computes from a reading the River block has refused.
  function cannotTellWhy(river) {
    if (river.fresh) return null;
    if (river.staleCode === 'clock-behind') return 'this device’s clock is behind the gauge (the newest reading is stamped ' + plural(river.clockBehindMinutes, 'minute') + ' after this device’s time)';
    return !river.reading ? 'no gauge reading was retrieved' : river.staleCode === 'old-reading' ? 'the gauge feed is ' + plural(river.ageMinutes, 'minute') + ' behind' : river.gapMinutes === null ? 'the gauge readings do not reach back one hour' : 'there is a ' + num(river.gapMinutes) + '-minute hole in the gauge readings of the last hour';
  }
  // What the River block prints when it cannot tell. The alert banner repeats the clock sentence word for word.
  function cannotTellSentence(river) {
    const why = cannotTellWhy(river);
    return why === null ? '' : river.staleCode === 'clock-behind' ? 'Cannot tell: ' + why + '. Correct the device clock.' : 'Cannot tell whether the river is rising: ' + why + '.';
  }
  // One rounding for every share of the seasonal number, in the River block and on the rise card: down, so that
  // 100% is printed only once the number is reached.
  const shareText = fraction => Math.floor(fraction * 100 + 1e-9).toLocaleString('en-US');
  const tenth = value => { const shown = Math.round(value * 10) / 10; return shown === 0 ? 0 : shown; };
  // Two hours or more without a new high while the river is up on about three hours earlier AND not down in the last
  // hour (that change present, not negative, not "falling"): the page then prints the two measured facts and neither
  // "may have peaked" nor its count. With the last hour down, the ordinary "may have peaked" sentence stands.
  const upOnThreeHours = river => river.state === 'may-have-peaked' && !!river.threeHour && tenth(river.threeHour.change) > 0
    && !!river.lastHour && tenth(river.lastHour.change) >= 0 && river.lastHour.label !== 'falling';
  // The measured River block. Everything printed here comes from D.riverState: every duration is counted between
  // gauge reading time stamps, and the device's check time is used only for the reading's age. No colour or class
  // changes with the state. `anchor` is D.countAnchor(...): where a look-back count is counted from and whether it
  // still applies. Returns the sentence a screen reader is told when the state changes.
  function renderRiver(river, anchor, now) {
    const t = value => clock(value, now), reading = river.reading, start = river.riseStart, high = river.high;
    const delta = value => (tenth(value) > 0 ? '+' : '') + num(tenth(value));
    const age = reading && river.ageMinutes !== null ? plural(river.ageMinutes, 'minute') : '';
    put('flow', reading ? num(reading.q) : '—');
    put('river-time', reading ? 'at ' + t(reading.t) : 'No gauge reading retrieved');
    put('river-age', age ? age + ' old' : '');
    if (!river.fresh) {
      const cannotTell = cannotTellSentence(river);
      for (const id of ['river-change', 'river-older', 'river-past', 'river-high', 'river-new-high-note', 'river-rain-note', 'river-rise']) show(id, '');
      show('river-state', cannotTell);
      return cannotTell;
    }
    const hour = river.lastHour, three = river.threeHour, number = river.threshold, rising = !!hour && hour.label === 'rising';
    // Two figures, each kept on one line of its own when the block is narrow. A missing figure stays visibly unavailable.
    $('river-change').hidden = false;
    $('river-change').innerHTML = '<span>' + esc((hour ? (hour.spanMinutes === 60 ? 'Last hour: ' : 'Last ' + num(hour.spanMinutes) + ' minutes: ') + delta(hour.change) + ' cfs (' + hour.label + ')' : 'Last hour: unavailable') + '.') + '</span> <span>' + esc((three ? 'About 3 hours: ' + delta(three.change) + ' cfs' : 'About 3 hours: unavailable') + '.') + '</span>';
    // The rise: exact when the 24 hours are whole; a lower bound when a hole may hide a lower reading; else unavailable.
    show('river-rise', river.rise && river.low24 && number ? 'Rise above the 24-hour low: ' + num(river.rise.cfs) + ' cfs (' + shareText(river.rise.share) + '% of the ' + number.cfs + ' cfs ' + number.label + ' number; low ' + num(river.low24.q) + ' cfs at ' + t(river.low24.t) + ').'
      : river.riseAtLeast && river.lowHeld24 && number ? 'Rise above the lowest reading held from the last 24 hours: at least ' + num(river.riseAtLeast.cfs) + ' cfs'
        // Holes adding up to more than hiddenRiseGapHours: the bound is printed without a share of the seasonal number.
        + (river.lowHeld24.gapTotalMinutes > RULES.hiddenRiseGapHours * 60 ? '. The gauge record has gaps adding up to ' + num(tenth(river.lowHeld24.gapTotalMinutes / 60)) + ' hours in that time, so most of the rise may be hidden.'
          : ' (' + shareText(river.riseAtLeast.share) + '% of the ' + number.cfs + ' cfs ' + number.label + ' number). The gauge record has a ' + num(river.lowHeld24.gapMinutes) + '-minute gap in that time, so the rise may be larger.')
        : 'Measured rise unavailable: the gauge record has a gap in the last 24 hours.');
    let olderText = '', stateText = '', pastText = '', highText = '', noteText = '', rainText = '';
    if (river.riseStatus === 'in-progress' && start && high) {
      const top = num(high.q) + ' cfs at ' + t(high.t);
      // "Still rising" is said only when the last-hour label is "rising". Any other new high is a "New high".
      const newHigh = ofWhat => (rising ? 'Still rising' : 'New high') + ' as of ' + t(reading.t) + ' (reading ' + age + ' old): ' + num(reading.q) + ' cfs is the highest ' + ofWhat + (rising ? ', up ' + num(tenth(hour.change)) + ' cfs in the hour before' : hour ? ', ' + delta(hour.change) + ' cfs on the hour before' : '') + '.';
      if (start.atOrBefore && !start.lowerBound) {
        // The readings do not reach back to where this rise began, so its top may be older than they are OR may be the
        // newest reading. Only what the readings held show is said: no pause, peak or falling line and no count.
        olderText = 'The measured rise passed the ' + start.threshold.cfs + ' cfs number at or before ' + t(start.t) + '; this page’s readings do not reach back to where that rise began. This page’s arithmetic, not the Department of Health’s decision.';
        stateText = river.state === 'new-high' ? newHigh('reading this page holds from the last ' + RULES.riseMemoryHours + ' hours') : 'Highest reading held from the last ' + RULES.riseMemoryHours + ' hours: ' + top + '.';
      } else {
        pastText = start.lowerBound ? 'Past the ' + start.threshold.cfs + ' cfs number since at or before the ' + t(start.t) + ' reading (a gap in the gauge record hides the exact time). This page’s arithmetic, not the Department of Health’s decision.'
          : 'Past the ' + start.threshold.cfs + ' cfs ' + start.threshold.label + ' number since the ' + t(start.t) + ' reading. This page’s arithmetic, not the Department of Health’s decision.';
        if (river.state === 'new-high') {
          // After a fresh crossing a higher reading can still be held from an earlier rise: name it, so "highest of
          // this rise" is not read as the highest of the last 48 hours.
          stateText = newHigh('of this rise so far') + ' The top of this rise is at this reading or later.' + (river.higherBefore ? ' A higher reading, ' + num(river.higherBefore.q) + ' cfs at ' + t(river.higherBefore.t) + ', is held from before this rise began.' : '');
          noteText = SAY.afterNewHigh();
        }
        else if (river.state === 'rising-again') {
          // Below an earlier top and climbing: by the last hour, or by the climb back from the lowest reading since that top.
          stateText = river.risingAgainBasis === 'last-hour' ? 'Up ' + num(tenth(hour.change)) + ' cfs in the last hour; the newest reading is ' + num(tenth(river.belowHigh.cfs)) + ' cfs below this rise’s high of ' + top + '.'
            : 'Climbing again: ' + num(reading.q) + ' cfs is ' + num(tenth(reading.q - river.lowSinceHigh.q)) + ' cfs above the lowest reading since this rise’s high (' + num(river.lowSinceHigh.q) + ' cfs at ' + t(river.lowSinceHigh.t) + ') and ' + num(tenth(river.belowHigh.cfs)) + ' cfs below that high of ' + top + '.';
        } else if (river.state === 'falling') {
          // The count is taken from the first reading that far below the high, and is dropped once the newest
          // reading is more than the count's 24 hours of readings past it.
          const lead = 'Now at least ' + percent(RULES.fallingFraction) + '% below the high of ' + top;
          stateText = !anchor ? lead + '.' : lead + '; the river first read that far below it at ' + t(anchor.t) + (anchor.withinHorizon ? '. ' + SAY.falling() : ', more than ' + D.LOOKBACK_RULES.countHorizonHours + ' hours of readings ago.');
        } else if (upOnThreeHours(river)) {
          // Two hours without a new high, yet higher than about three hours earlier and not down in the last hour: the two measured facts, with no
          // "may have peaked", no count and no rain sentence. The sentence does not name the high, so it gets its own line.
          stateText = 'No new high since ' + t(high.t) + ' (' + hoursMinutes(river.minutesSinceHigh) + ' of readings), but the river is up ' + num(tenth(three.change)) + ' cfs on about 3 hours earlier.';
          highText = 'Highest reading since then: ' + top + '.';
        } else if (river.state === 'may-have-peaked') {
          // The count is taken from the 2-hour mark and is dropped once that mark is more than 24 hours of readings back.
          stateText = 'No new high since ' + t(high.t) + ' (' + hoursMinutes(river.minutesSinceHigh) + ' of readings): the river may have peaked at ' + num(high.q) + ' cfs.' + (anchor && anchor.withinHorizon ? ' ' + SAY.peak() : '');
          rainText = SAY.rainPause();
        } else if (river.state === 'paused') {
          // A sentence that does not name the high, so the high gets its own line here.
          stateText = 'No new high since ' + t(high.t) + '. ' + SAY.pause();
          highText = 'Highest reading since then: ' + top + '.';
        } else if (river.state === 'just-off-high') stateText = 'Highest reading of this rise: ' + top + ', ' + plural(river.minutesSinceHigh, 'minute') + ' of readings before the newest one. Under an hour without a new high says nothing about the top of a rise.';
        // 'cannot-tell': a hole lies between the highest reading held and the newest one. Measured facts only.
        else stateText = 'Gauge readings are missing for ' + num(river.gapMinutes) + ' minutes between the highest reading held (' + top + ') and the newest reading. No state is given for this rise.';
      }
    }
    show('river-older', olderText); show('river-state', stateText); show('river-past', pastText); show('river-high', highText); show('river-new-high-note', noteText); show('river-rain-note', rainText);
    return [olderText, stateText].filter(Boolean).join(' ');
  }
  // NOAA's CURRENT issue against the gauge. It reads no saved history, so it works on a first visit. Returns
  // { said, compare }: the sentence a screen reader is told, and 'above' (a comparison was made and the gauge is
  // above the line), 'within' (made, not above) or 'none' (no comparison can be made right now).
  function renderNoaa(noaa, river, now) {
    const t = value => clock(value, now), issued = noaa.issued !== null && noaa.issueAgeMinutes !== null ? 'issued ' + t(noaa.issued) + ' (' + issueAge(noaa.issueAgeMinutes) + ' ago)' : null;
    const refused = cannotTellWhy(river), by = value => num(tenth(value));
    // Above the highest value in NOAA's forecast by less than the line, with the last hour "rising".
    const risingAbove = () => 'The gauge is ' + by(noaa.aboveTopBy) + ' cfs above the highest value in NOAA’s forecast and rose ' + by(river.lastHour.change) + ' cfs in the last hour.';
    let compare, above = '', state = 'none';
    if (!issued) compare = 'NOAA’s river forecast is unavailable' + (noaa.reason && noaa.reason !== 'NOAA river forecast unavailable' ? ' (' + noaa.reason + ')' : '') + '. No comparison is made.';
    else if (!river.reading) compare = 'NOAA’s river forecast was ' + issued + '. No gauge reading is available to compare with it.';
    else if (refused) compare = 'NOAA’s river forecast, ' + issued + ', is not compared with the gauge: ' + refused + '.';
    else if (!noaa.compared) compare = 'NOAA’s river forecast, ' + issued + ', has no value for ' + t(noaa.readingTime) + ', the time of the newest gauge reading. No comparison is made.';
    else if (noaa.covered) {
      const gap = tenth(noaa.difference);
      state = noaa.aboveLine ? 'above' : 'within';
      compare = 'NOAA’s river forecast, ' + issued + ', has ' + num(noaa.forecastCfs) + ' cfs for ' + t(noaa.readingTime) + '. The gauge read ' + num(noaa.gaugeCfs) + ' cfs then: ' + (gap > 0 ? num(gap) + ' cfs higher' : gap < 0 ? num(-gap) + ' cfs lower' : 'the same to the nearest tenth') + '.';
      if (noaa.aboveTop) above = 'The gauge is already ' + by(noaa.aboveTopBy) + ' cfs above the highest value in NOAA’s forecast.';
      else if (noaa.basis === 'above-highest-and-rising') above = risingAbove();
    } else {
      // A real NOAA path starts some hours after its issue stamp: no value is invented for the reading's time, and
      // only measured facts are printed. Nothing here says "not tracking".
      const hour = river.lastHour;
      state = noaa.aboveLine ? 'above' : 'within';
      compare = 'NOAA’s river forecast, ' + issued + ', starts at ' + t(noaa.first.t) + ' with ' + num(noaa.first.q) + ' cfs; its highest value is ' + num(noaa.top.q) + ' cfs at ' + t(noaa.top.t) + '. The gauge read ' + num(noaa.gaugeCfs) + ' cfs at ' + t(noaa.readingTime) + '.';
      if (noaa.basis === 'above-first') {
        above = 'The gauge is ' + by(noaa.aboveFirstBy) + ' cfs above NOAA’s first value' + (!hour ? '' : hour.label === 'rising' ? ' and rose ' + by(hour.change) + ' cfs in the last hour' : hour.label === 'about level' ? ' and was about level in the last hour' : '') + '.'
          + (noaa.aboveTopAndRising ? ' It is also above the highest value in NOAA’s forecast (' + num(noaa.top.q) + ' cfs).' : '');
      } else if (noaa.basis === 'above-highest-and-rising') above = risingAbove();
    }
    // "Not tracking" is said of the at-the-reading-time comparison only; the data layer never gives that code otherwise.
    const flag = state !== 'above' ? '' : noaa.code === 'not-tracking' ? 'NOAA’s forecast is not tracking this rise. Do not read a peak time from it.' : noaa.covered && noaa.code === 'unknown' ? 'Whether a measured rise is in progress cannot be told from the gauge record. ' + NO_PEAK_ABOVE : '';
    put('noaa-compare', compare); show('noaa-above', above); show('noaa-flag', flag);
    // A screen reader is told the flag; where being above the line carries no flag, the measured sentence instead.
    return { said: flag || (state === 'above' ? above : ''), compare: state };
  }
  const feet = value => { const text = value.toFixed(1); return text === '-0.0' ? '0.0' : text; };
  // The Tide block: the last high or low (kept after it passes), the direction, and the next two.
  function renderTide(tide, now) {
    if (!tide.available) { put('tide-now', 'Tide predictions unavailable. Use the official tide source.'); return; }
    const t = value => clock(value, now), name = r => (r.type === 'H' ? 'high' : 'low') + ' of ' + feet(r.v) + ' ft at ' + t(r.t);
    const ahead = 'a ' + name(tide.next[0]) + (tide.next[1] ? ', then a ' + name(tide.next[1]) : '');
    if (tide.last && tide.direction) put('tide-now', (tide.last.type === 'H' ? 'High' : 'Low') + ' of ' + feet(tide.last.v) + ' ft was at ' + t(tide.last.t) + ', ' + elapsed(tide.minutesSinceLast) + ' before this check. The tide is ' + tide.direction + ' to ' + ahead + '.');
    else put('tide-now', (tide.last ? 'Last: a ' + name(tide.last) + '. ' : '') + 'Next: ' + ahead + '. No tide direction is given: ' + tide.reason.charAt(0).toLowerCase() + tide.reason.slice(1) + '.');
  }
  // The last high or low stays listed after it passes, marked as passed, followed by the next four.
  function tideList() {
    const { tide, tideRows, now } = state;
    return tide.available ? [...(tide.last ? [{ ...tide.last, passed: true }] : []), ...tideRows.filter(r => r.t > now).slice(0, 4)] : [];
  }
  let announced = null;
  // Screen readers are told once when the river state or the NOAA comparison changes: only the part that changed,
  // not on every refresh, and not on first load. `parts` is [[state key, sentence], ...].
  function announce(parts) {
    const changed = announced === null ? [] : parts.filter((part, index) => part[0] !== announced[index]);
    if (changed.length) put('river-announce', changed.map(part => part[1]).filter(Boolean).join(' '));
    announced = parts.map(part => part[0]);
  }
  function renderRainForecast(rains, now) {
    const fullRain = rains.every(r => r?.fresh && r.complete);
    const meanMm = fullRain ? (rains[0].mm + rains[1].mm) / 2 : null;
    badge('rain-status', fullRain ? 'Full 24 h coverage' : 'Incomplete / unavailable', fullRain ? 'neutral' : 'caution');
    put('rain-total', fullRain ? inches(meanMm) : '—');
    put('ops-rain', fullRain ? inches(meanMm) + ' in.' : 'Unavailable');
    const verifiedGeometry = !!state?.basin && (state.gridPoints || []).length === 2 && state.gridPoints.every(Boolean);
    put('rain-note', verifiedGeometry ? 'Two separate National Weather Service (NWS) point forecasts whose current full grid-cell polygons were verified inside the displayed gauge-upstream drainage reference. The headline is their mean for the 24 hours from ' + date(now) + '; it is not an observed or area-wide total.' : 'A National Weather Service (NWS) forecast point is shown only after its current full grid-cell polygon is verified inside the displayed gauge-upstream drainage reference. Any point that cannot be checked is withheld; no partial set becomes the headline mean.');
    const labels = ['Mid area · grid 136,114', 'Upper-east area · grid 139,116'];
    $('rain-points').innerHTML = rains.map((r, i) => '<div class="rain-point"><strong><span>' + labels[i] + '</span><span>' + (r?.fresh && r.complete ? esc(inches(r.mm)) + ' in.' : 'Unavailable') + '</span></strong><small>' + (r ? (r.fresh ? '' : 'Stale · ') + 'Forecast updated ' + esc(date(r.updated)) + ' · ' + num(r.coveredHours) + '/24 h covered' : 'Forecast feed unavailable') + '</small></div>').join('');
    // The dry-season context is words only: no rule, no colour and no computed "at or above" line on this page's rain.
    $('rain-context').hidden = D.drySeasonContext(now) !== true;
    $('rain-context').innerHTML = $('rain-context').hidden ? '' : '<strong>Context, not an alert.</strong> <span id="rain-context-text">' + esc(SAY.rainContext()) + '</span> <span class="lookback-caveat">' + esc(E.caveat) + '</span>';
    // Each six-hour block is "missing" (no value), "zero" (a complete block forecast at exactly 0) or "amount".
    const rows = Array.from({ length: 6 }, (_, index) => ({ index, a: rains[0]?.bins?.[index] || null, b: rains[1]?.bins?.[index] || null })).map(row => ({ ...row, blocks: [D.rainBlockState(row.a), D.rainBlockState(row.b)] }));
    const cell = block => block.status === 'missing' ? 'Unavailable' : esc(inches(block.mm)) + ' in.';
    $('rain-forecast-table').innerHTML = '<table><caption>Six-hour forecast accumulation blocks beginning at this page’s feed-check time. Missing coverage remains unavailable.</caption><thead><tr><th scope="col">Pacific interval</th><th scope="col">Mid · 136,114</th><th scope="col">Upper-east · 139,116</th></tr></thead><tbody>' + rows.map(row => { const start = row.a?.t ?? row.b?.t, end = row.a?.end ?? row.b?.end; return '<tr><td>' + (Number.isFinite(start) && Number.isFinite(end) ? esc(date(start)) + '–' + esc(date(end)) : 'Unavailable') + '</td><td>' + cell(row.blocks[0]) + '</td><td>' + cell(row.blocks[1]) + '</td></tr>'; }).join('') + '</tbody></table>';
    const available = rows.flatMap(row => row.blocks).filter(block => block.status !== 'missing'), anyMissing = rows.some(row => row.blocks.some(block => block.status === 'missing'));
    if (!available.length) { $('rain-chart').className = 'rain-chart chart-empty'; put('rain-chart', 'Complete six-hour rain blocks are unavailable.'); return; }
    const w = Math.max(260, Math.round($('rain-chart').clientWidth || 760)), h = anyMissing ? 258 : 240, left = 45, right = 12, top = anyMissing ? 52 : 34, bottom = 48, inner = w - left - right, group = inner / rows.length, bar = Math.min(34, group * .3), maxIn = Math.max(.01, ...available.map(block => block.mm / 25.4)) * 1.15;
    rainChartWidth = w;
    const y = value => top + (1 - value / maxIn) * (h - top - bottom);
    const secondLegendX = Math.max(148, Math.min(205, w - 125));
    let svg = '<svg viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-labelledby="rain-svg-title rain-svg-desc"><title id="rain-svg-title">Forecast rain in six-hour blocks at two National Weather Service grid points</title><desc id="rain-svg-desc">Paired bars show forecast inches at mid-area grid 136,114 and upper-east grid 139,116. A block with no value is drawn as a hatched column labelled no data. A block forecast at exactly zero is labelled 0. Values are also available in the table.</desc><defs><pattern id="rain-missing-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" class="rain-missing-line"></line></pattern></defs><g class="rain-legend"><rect x="45" y="8" width="12" height="12" class="rain-a"></rect><text x="63" y="19">Mid point</text><rect x="' + secondLegendX + '" y="8" width="12" height="12" class="rain-b"></rect><text x="' + (secondLegendX + 18) + '" y="19">Upper-east point</text>' + (anyMissing ? '<rect x="45" y="27" width="12" height="12" class="rain-missing"></rect><text x="63" y="38">No data (not zero)</text>' : '') + '</g>';
    for (let i = 0; i <= 3; i++) { const value = maxIn * i / 3, yy = y(value); svg += '<line x1="' + left + '" x2="' + (w - right) + '" y1="' + yy + '" y2="' + yy + '" class="chart-grid"></line><text x="' + (left - 7) + '" y="' + (yy + 4) + '" text-anchor="end">' + value.toFixed(2) + '</text>'; }
    rows.forEach((row, index) => {
      const center = left + group * (index + .5);
      row.blocks.forEach((block, series) => {
        const x = center + (series ? 2 : -bar - 2), middle = x + bar / 2;
        if (block.status === 'missing') {
          // Pattern plus words, never colour alone: a hatched column over the whole plot height and "no data".
          const middleY = (top + h - bottom) / 2;
          svg += '<rect x="' + x + '" y="' + top + '" width="' + bar + '" height="' + (h - bottom - top) + '" class="rain-missing"><title>' + labels[series] + ': no data for this block</title></rect><text class="rain-missing-label" x="' + middle + '" y="' + (middleY + 4) + '" text-anchor="middle" transform="rotate(-90 ' + middle + ' ' + middleY + ')">no data</text>';
        } else if (block.status === 'zero') svg += '<text class="rain-zero-label" x="' + middle + '" y="' + (h - bottom - 5) + '" text-anchor="middle">0<title>' + labels[series] + ': forecast at exactly 0.00 inches</title></text>';
        else { const yy = y(block.mm / 25.4); svg += '<rect x="' + x + '" y="' + yy + '" width="' + bar + '" height="' + Math.max(0, h - bottom - yy) + '" class="' + (series ? 'rain-b' : 'rain-a') + '"><title>' + labels[series] + ': ' + inches(block.mm) + ' inches</title></rect>'; }
      });
      // A narrow chart has no room for "+18–24 h" six times: the hours go under the axis and the unit in a caption.
      svg += '<text x="' + center + '" y="' + (h - (group < 58 ? 28 : 20)) + '" text-anchor="middle">' + (group < 58 ? (index * 6) + '–' + ((index + 1) * 6) : '+' + (index * 6) + '–' + ((index + 1) * 6) + ' h') + '</text>';
    });
    if (group < 58) svg += '<text x="' + (left + inner / 2) + '" y="' + (h - 9) + '" text-anchor="middle">hours after this check</text>';
    svg += '<text x="7" y="20">in.</text></svg>';
    $('rain-chart').className = 'rain-chart'; $('rain-chart').innerHTML = svg;
  }
  function renderObservedRain(report) {
    if (!report) {
      badge('observed-rain-status', 'Unavailable', 'caution'); put('observed-rain-issued', 'No usable Seattle rain report retrieved');
      $('observed-rain-table').innerHTML = '<p>Nearby station totals are unavailable. No missing value is treated as zero.</p>'; return;
    }
    badge('observed-rain-status', report.fresh ? 'Recent report' : 'Stale report', report.fresh ? 'neutral' : 'caution');
    put('observed-rain-issued', 'Report issued ' + date(report.issued) + ' · issue time, not a gauge measurement time');
    // Consistency flag, computed only from the totals shown: one gauge at 0.00 inch for 24 hours while both others report rain.
    const windows = report.windows.slice(0, 5), suspect = D.suspectZeroRain(report);
    $('observed-rain-table').innerHTML = '<table><caption>Provisional rolling precipitation totals in inches from automated stations near the watershed. National Weather Service accuracy has not been verified.</caption><thead><tr><th scope="col">Station</th>' + windows.map(value => '<th scope="col">' + value + ' h</th>').join('') + '</tr></thead><tbody>' + report.stations.map((station, row) => '<tr><th scope="row">' + esc(station.label) + (suspect.flags[row] ? '<span class="suspect-note">Reads zero while both other gauges report rain; treat as suspect.</span>' : '') + '</th>' + windows.map((value, index) => '<td>' + (station.available && station.values[index] !== null ? station.values[index].toFixed(2) : 'Unavailable') + '</td>').join('') + '</tr>').join('') + '</tbody></table>';
  }
  function renderWatch(watch, history) {
    const labels = { outpacing: 'ABOVE EARLIER FORECAST', 'above-prior': 'ABOVE EARLIER FORECAST', tracking: 'NOT ABOVE CHECK LINE', learning: 'NO EARLIER FORECAST', unknown: 'CHECK UNAVAILABLE' };
    // The word "rising" comes only from the last-hour label (D.watchWithLastHour). With no label, neither "rising"
    // nor "not rising" is printed.
    const titles = { outpacing: 'River is above the earlier NOAA forecast and rising in the last hour of readings', 'above-prior': watch.lastHourLabel ? 'River is above the earlier NOAA forecast, but not rising in the last hour of readings' : 'River is above the earlier NOAA forecast', tracking: 'River is not above the earlier-forecast check line', learning: 'No earlier forecast to compare yet', unknown: 'Earlier-forecast check unavailable' };
    $('surprise-watch').className = 'watch-card ' + (watch.code || 'unknown');
    badge('watch-state', labels[watch.code] || labels.unknown, watch.code === 'outpacing' || watch.code === 'above-prior' ? 'caution' : 'neutral');
    put('watch-title', titles[watch.code] || titles.unknown);
    $('watch-metrics').hidden = !watch.snapshot;
    if (watch.snapshot) {
      put('watch-detail', 'An earlier NOAA forecast expected ' + num(watch.expected) + ' cfs at this time. The gauge reads ' + num(watch.observed) + ' cfs (' + signed(watch.difference) + ' cfs) and changed ' + signed(watch.change3) + ' cfs over ' + num(watch.span3) + ' hours. ' + (watch.lastHourLabel ? 'Over the last hour of readings it was ' + watch.lastHourLabel + '. ' : 'The last-hour change is unavailable, so no direction is given. ') + 'The check line is ' + num(watch.line) + ' cfs above the earlier forecast. This is not a closure, safety, or all-clear signal.');
      put('watch-source', 'Earlier NOAA issue: ' + date(watch.snapshot.issueTime) + ' · first recorded here ' + date(watch.snapshot.capturedAt) + ' · ' + num(watch.age) + ' hours before this gauge reading. The check line is unvalidated and is not an alert threshold.');
    } else {
      put('watch-detail', watch.code === 'learning' ? 'An eligible NOAA forecast from 3–36 hours earlier is not available yet. Use the dated panels above to see which current data are available.' : 'The earlier-forecast check is unavailable. Use the dated panels above to see which current data are available.');
      put('watch-source', history.status === 'available' ? 'Once this dashboard has an eligible forecast from an earlier check, the comparison appears automatically. Planning aid only—not an alert threshold.' : 'Earlier-forecast history cannot be read on this device. Other panels remain independent of this check; use their dated status labels.');
    }
    put('watch-expected', watch.expected === null || watch.expected === undefined ? '—' : num(watch.expected));
    put('watch-observed', watch.observed === null || watch.observed === undefined ? '—' : num(watch.observed));
    put('watch-change', watch.change3 === null || watch.change3 === undefined ? '—' : signed(watch.change3));
  }
  // "What NOAA's forecast adds": the forward look from the newest gauge reading. While the River block shows the
  // number was passed in the last 48 hours of readings, this card never prints "below the numeric line".
  function renderRise(screen, threshold, river, compare, now) {
    const start = river?.riseStatus === 'in-progress' ? river.riseStart : null;
    show('rise-passed', start ? 'The measured rise passed the ' + start.threshold.cfs + ' cfs number ' + (start.atOrBefore ? 'at or before ' + clock(start.t, now) : 'at the ' + clock(start.t, now) + ' reading') + ' (River block at the top). The figures on this card look forward from the newest reading and do not undo that.' : '');
    show('rise-noaa-dry', D.drySeasonContext(now) === true ? SAY.noaaDry() + ' ' + E.caveat : '');
    $('rise-progress').parentElement.hidden = false;
    // The forward look leans on NOAA's forecast: say so whenever the gauge is above that forecast or cannot be set against it.
    show('rise-noaa-basis', compare !== 'within' ? 'This forward look is built on NOAA’s forecast, ' + (compare === 'above' ? 'which the gauge is currently above.' : 'which cannot currently be compared with the gauge.') : '');
    if (!screen?.usable) {
      badge('rise-status', 'Unavailable', 'caution'); put('rise-percent', '—'); put('rise-title', screen?.reason || 'Planning comparison unavailable');
      put('screen-rise', '—'); put('season-threshold', threshold ? threshold.cfs + ' cfs' : '—'); put('rise-detail', 'No partial path is turned into a reassuring result.'); $('rise-progress').style.width = '0'; return;
    }
    const share = shareText(screen.percent / 100), relation = D.lineRelation(screen.difference), exceeded = relation.code === 'above';
    badge('rise-status', 'Experimental', exceeded ? 'caution' : 'neutral'); put('rise-percent', share);
    put('rise-title', 'Largest relative rise: ' + num(screen.riseAtHighestShare) + ' cfs, or ' + share + '% of the ' + screen.threshold.cfs + ' cfs ' + screen.threshold.label + ' reference.');
    put('screen-rise', num(screen.riseAtHighestShare) + ' cfs'); put('season-threshold', screen.threshold.cfs + ' cfs');
    const relationText = start && relation.code === 'below' ? 'Forward look from the newest reading; its largest relative rise is' : relation.code === 'at' ? 'At the numeric line' : num(relation.distance) + ' cfs ' + relation.code + ' the numeric line';
    put('rise-detail', relationText + ' at the ' + screen.pointSource + ' point ' + date(screen.pointTime) + '. This point has the largest rise relative to the seasonal reference in effect at that time; a larger raw rise may exist when the reference changes. Rolling low ' + num(screen.baselineCfs) + ' cfs at ' + date(screen.baselineTime) + '. Gauge alignment ' + signed(screen.adjustment) + ' cfs. Not official status.');
    // A bar filling toward a number the measured rise already passed would read as "not there yet": leave it out.
    $('rise-progress').parentElement.hidden = !!start && relation.code === 'below';
    $('rise-progress').style.width = Math.min(100, Math.max(0, screen.percent)) + '%';
    $('rise-progress').style.background = exceeded ? 'var(--coral)' : 'var(--teal)';
  }
  function renderCrest(fc, tides, peakWithheld, onlyFalls, now) {
    $('crest-nearby').innerHTML = '';
    // No falling-forecast sentence and no forecast-high time unless a comparison was made and the gauge is not above the line.
    if (fc?.usable && peakWithheld) { put('crest-time', peakWithheld); put('crest-detail', 'No forecast-high time or tide pairing is shown.'); return; }
    if (!fc?.usable || fc.atStart || fc.atEnd) {
      // The first value is named with its time: a NOAA path can start hours after this check, so "the start of the
      // window" is not now. A path that dips and partly recovers is not said to fall.
      const first = fc?.usable ? ' (' + num(fc.rows[0].q) + ' cfs at ' + clock(fc.rows[0].t, now) + ')' : '';
      put('crest-time', !fc?.usable ? 'Forecast timing unavailable' : fc.atEnd ? 'Highest value is at the forecast’s end' : 'Highest value is at the forecast’s start');
      put('crest-detail', !fc?.usable ? fc.reason : fc.atEnd ? 'The high may occur later than the available path. No tide pairing is inferred.' : (onlyFalls ? 'NOAA’s forecast falls from its first value' + first + '.' : 'No later value in NOAA’s forecast is higher than its first' + first + '.') + ' No future high time is inferred.'); return;
    }
    const highTime = fc.firstMax, before = [...tides].filter(r => r.t <= highTime).at(-1), after = tides.find(r => r.t >= highTime);
    put('crest-time', 'NOAA forecast high around ' + date(highTime));
    put('crest-detail', 'Nearby Bellingham predictions are shown only to reduce mental arithmetic. The forecast high is not a confirmed crest or sampling window.');
    $('crest-nearby').innerHTML = [before, after].filter((r, i, a) => r && (!i || r.t !== a[0]?.t)).map(r => '<div class="crest-tide"><span class="small-label">' + (r.t <= highTime ? 'Before forecast high' : 'After forecast high') + '</span><strong>' + (r.type === 'H' ? 'High' : 'Low') + ' · ' + r.v.toFixed(1) + ' ft</strong><span>' + esc(date(r.t)) + ' · ' + num(Math.abs(r.t - highTime) / H) + ' h away</span></div>').join('');
  }
  function chart() {
    if (!state) return;
    const { now, observations, fc, watch } = state, start = now - 48 * H, end = now + 72 * H;
    const obs = observations.filter(r => r.t >= start), future = fc.usable ? fc.rows : [];
    const saved = (watch?.snapshot?.alignedPath || []).map(r => ({ t: Number(r?.t), q: Number(r?.q) })).filter(r => Number.isFinite(r.t) && Number.isFinite(r.q) && r.q >= 0 && r.t >= start && r.t <= end);
    const all = [...obs, ...future, ...saved];
    $('saved-path-legend').hidden = !saved.length;
    if (!all.length) { $('flow-chart').className = 'chart-empty'; put('flow-chart', 'River data unavailable. Check the official sources.'); put('chart-description', 'No river path is available. The radar remains separate weather context.'); return; }
    const w = Math.max(230, $('flow-chart').clientWidth), h = 296, l = 49, right = 13, top = 22, bottom = 60;
    const max = Math.max(1, ...all.map(r => r.q)) * 1.15, x = t => l + (t - start) / (end - start) * (w - l - right), y = q => top + (1 - q / max) * (h - top - bottom);
    const paths = (rows, gap, color, dash) => {
      const groups = []; rows.forEach((r, i) => { if (!i || r.t - rows[i - 1].t > gap) groups.push([]); groups.at(-1).push(r); });
      return groups.map(g => g.length === 1 ? '<circle cx="' + x(g[0].t) + '" cy="' + y(g[0].q) + '" r="3" fill="' + color + '"/>' : '<path d="' + g.map((r, i) => (i ? 'L' : 'M') + x(r.t).toFixed(2) + ',' + y(r.q).toFixed(2)).join(' ') + '" fill="none" stroke="' + color + '" stroke-width="2.5"' + (dash ? ' stroke-dasharray="' + dash + '"' : '') + '/>').join('');
    };
    const desc = 'Flow in cubic feet per second. Observations cover the previous 48 hours where available. ' + (fc.usable ? 'NOAA forecast extends ' + num(fc.hours) + ' hours from this check; highest forecast value is ' + num(fc.max) + ' cfs.' + (fc.startsAfterCheck ? ' The forecast begins ' + num((fc.start - now) / H) + ' hours after check time, and that gap is left visible.' : '') : 'NOAA forecast unavailable.') + (saved.length ? ' An earlier eligible NOAA forecast is shown separately after one gauge alignment.' : ' No eligible earlier NOAA forecast is available.');
    let svg = '<svg viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-labelledby="flow-title flow-desc"><title id="flow-title">Samish river flow</title><desc id="flow-desc">' + esc(desc) + '</desc>';
    for (let i = 0; i <= 4; i++) { const q = max * i / 4; svg += '<line x1="' + l + '" x2="' + (w - right) + '" y1="' + y(q) + '" y2="' + y(q) + '" stroke="var(--line)"/><text x="' + (l - 7) + '" y="' + (y(q) + 4) + '" text-anchor="end">' + Math.round(q).toLocaleString('en-US') + '</text>'; }
    svg += '<text x="' + l + '" y="13">cfs</text><line x1="' + x(now) + '" x2="' + x(now) + '" y1="' + top + '" y2="' + (h - bottom) + '" stroke="var(--muted)" stroke-dasharray="3 4"/>';
    const ticks = w < 500 ? [[start, '−48 h'], [now, '0 h'], [end, '+72 h']] : [[start, '−48 h'], [now - 24 * H, '−24 h'], [now, 'Check time'], [now + 24 * H, '+24 h'], [now + 48 * H, '+48 h'], [end, '+72 h']];
    // Each tick carries its offset from the check time and, beneath it, the Pacific clock time it stands for.
    // On a narrow chart only the check time has room for its clock time; the two ends carry the day.
    const tickClock = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', weekday: 'short', hour: 'numeric', minute: '2-digit' }), tickDay = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', weekday: 'short' });
    for (let i = 0; i < ticks.length; i++) { const anchor = i === 0 ? 'start' : i === ticks.length - 1 ? 'end' : 'middle', under = w >= 500 || ticks[i][0] === now ? tickClock : tickDay; svg += '<text x="' + x(ticks[i][0]) + '" y="' + (h - 34) + '" text-anchor="' + anchor + '">' + ticks[i][1] + '</text><text class="tick-clock" x="' + x(ticks[i][0]) + '" y="' + (h - 16) + '" text-anchor="' + anchor + '">' + esc(under.format(ticks[i][0])) + '</text>'; }
    svg += paths(saved, 6 * H, 'var(--saved)', '2 5') + paths(obs, 2 * H, 'var(--teal)', '') + paths(future, 6 * H, 'var(--navy)', '7 5') + '</svg>';
    $('flow-chart').className = ''; $('flow-chart').innerHTML = svg;
    put('chart-description', (saved.length ? 'The dotted amber line is an earlier NOAA forecast after one gauge alignment. ' : 'No eligible earlier NOAA forecast is available yet. ') + 'NOAA’s current dashed forecast remains raw and unshifted. Gaps stay visible. Clock times under the axis are Pacific; 0 h is this page’s data-check time, ' + clockFmt.format(now) + '.');
  }
  function readStormLog() {
    try {
      const raw = localStorage.getItem(STORM_LOG_KEY);
      if (raw === null) return { available: true, records: [] };
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed) || parsed.length > 500) throw Error('Stored event log is malformed');
      return { available: true, records: parsed.map(D.stormRecord) };
    } catch { return { available: false, records: [], reason: 'Storm checks cannot be opened on this device right now. Existing records, if any, were left unchanged.' }; }
  }
  function writeStormLog(records) {
    try {
      const clean = records.map(D.stormRecord);
      localStorage.setItem(STORM_LOG_KEY, JSON.stringify(clean));
      if (localStorage.getItem(STORM_LOG_KEY) === null) throw Error('Storage write could not be verified');
      return { available: true, records: clean };
    } catch { return { available: false, records: [], reason: 'This storm check could not be saved on this device.' }; }
  }
  function currentStormRecord(tag, note) {
    const last = state.observations.at(-1), threshold = D.thresholdAt(state.now), fullRain = state.rains.every(r => r?.fresh && r.complete);
    const observed24 = label => state.observedRain?.stations.find(station => station.label === label)?.values?.[4] ?? null;
    const random = window.crypto?.getRandomValues ? window.crypto.getRandomValues(new Uint32Array(1))[0].toString(16) : Math.floor(Math.random() * 0xffffffff).toString(16);
    return D.stormRecord({
      id: new Date().toISOString().replace(/[^0-9A-Za-z]/g, '') + '-' + random,
      savedAt: new Date().toISOString(), tag, note, feedCheckAt: new Date(state.now).toISOString(), gaugeCfs: last?.q ?? null, gaugeTime: last ? new Date(last.t).toISOString() : null,
      change3Cfs: state.river.threeHour?.change ?? null, forecastHighCfs: state.fc.usable ? state.fc.max : null, forecastIssue: state.fc.issued === null ? null : new Date(state.fc.issued).toISOString(), forecastHighTime: state.fc.usable && state.fc.firstMax !== null ? new Date(state.fc.firstMax).toISOString() : null,
      riseThresholdCfs: threshold?.cfs ?? null, rain24MeanIn: fullRain ? (state.rains[0].mm + state.rains[1].mm) / 2 / 25.4 : null, rainForecastUpdated1: state.rains[0] ? new Date(state.rains[0].updated).toISOString() : null, rainForecastUpdated2: state.rains[1] ? new Date(state.rains[1].updated).toISOString() : null,
      observedRainIssue: state.observedRain ? new Date(state.observedRain.issued).toISOString() : null, padilla24In: observed24('Padilla Bay Farm'), burlington24In: observed24('Burlington'), sedroWoolley24In: observed24('Sedro-Woolley RAWS'),
      radarProduct: radar.validTime ? RADAR_PRODUCTS[radar.product].label : null, radarValidTime: radar.validTime ? new Date(radar.validTime).toISOString() : null
    });
  }
  function renderStormLog(message = '') {
    const log = readStormLog();
    badge('storm-log-count', log.available ? log.records.length + ' saved' : 'SAVE UNAVAILABLE', log.available ? 'neutral' : 'caution');
    $('storm-log-save').disabled = !log.available || !state;
    $('storm-log-export').disabled = !log.available || !log.records.length;
    $('storm-log-clear').disabled = !log.available || !log.records.length;
    put('storm-log-status', log.available ? message : log.reason);
    if (!log.available) { $('storm-log-list').innerHTML = '<p class="measurement-limit"><strong>Nothing was changed.</strong> Use Copy snapshot instead, or try again later.</p>'; return; }
    if (!log.records.length) { $('storm-log-list').innerHTML = '<p>No storm checks saved on this device.</p>'; return; }
    $('storm-log-list').innerHTML = '<div class="table-wrap" role="region" aria-label="Saved storm checks" tabindex="0"><table><caption>Manual storm checks saved on this device, newest first.</caption><thead><tr><th scope="col">Saved</th><th scope="col">Moment / note</th><th scope="col">River</th><th scope="col">Forecast</th><th scope="col"><span class="sr-only">Delete</span></th></tr></thead><tbody>' + log.records.map(record => '<tr><td>' + esc(date(Date.parse(record.savedAt))) + '</td><td><strong>' + esc(record.tag) + '</strong>' + (record.note ? '<br><span>' + esc(record.note) + '</span>' : '') + '</td><td>' + (record.gaugeCfs === null ? 'Unavailable' : num(record.gaugeCfs) + ' cfs') + '<br><span class="meta">3 h: ' + (record.change3Cfs === null ? 'Unavailable' : signed(record.change3Cfs) + ' cfs') + '</span></td><td>' + (record.forecastHighCfs === null ? 'Unavailable' : num(record.forecastHighCfs) + ' cfs') + '<br><span class="meta">Rain: ' + (record.rain24MeanIn === null ? 'Unavailable' : record.rain24MeanIn.toFixed(2) + ' in.') + '</span></td><td><button class="delete-log" type="button" data-delete-log="' + esc(record.id) + '" aria-label="Delete check saved ' + esc(date(Date.parse(record.savedAt))) + '">Delete</button></td></tr>').join('') + '</tbody></table></div>';
  }
  function downloadBlob(contents, type, filename) {
    const blob = new Blob([contents], { type }), url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  }
  function brief() {
    const observedLines = state.observedRain ? state.observedRain.stations.map(station => station.label + ' rolling 24 h: ' + (station.values[4] === null ? 'Unavailable' : station.values[4].toFixed(2) + ' in.')) : ['Nearby observed-rain report unavailable'];
    // Only lines the page is showing are copied, so the snapshot never says more than the screen did.
    const shown = ids => ids.map(id => $(id)).filter(el => !el.hidden && el.textContent).map(el => el.textContent);
    const upcomingTides = tideList();
    return ['Samish River Outlook — field-planning snapshot', 'Data checked: ' + date(state.now), '', 'RIVER, measured at the gauge: ' + $('flow').textContent + ' cfs ' + $('river-time').textContent + ($('river-age').textContent ? ', ' + $('river-age').textContent : ''), ...shown(['river-change', 'river-older', 'river-state', 'river-past', 'river-high', 'river-new-high-note', 'river-rain-note', 'river-rise']), '', 'NOAA RIVER FORECAST, current issue against the gauge', ...shown(['noaa-compare', 'noaa-above', 'noaa-flag']), '', 'TIDE, Bellingham prediction, not Samish Bay water level or boat clearance', $('tide-now').textContent, '', 'RADAR CONTEXT: ' + $('radar-status').textContent, $('radar-frame-time').textContent, $('radar-product-note').textContent, 'Official KATX radar context; not used in a river, closure or safety calculation.', '', 'FORECAST CHANGE CHECK: ' + $('watch-state').textContent, $('watch-title').textContent, $('watch-detail').textContent, $('watch-source').textContent, '', 'WHAT NOAA’S FORECAST ADDS (seasonal rise comparison): ' + $('rise-status').textContent, $('rise-title').textContent, ...shown(['rise-passed', 'rise-noaa-basis']), $('rise-detail').textContent, '', 'NOAA forecast high: ' + $('forecast-high').textContent + ' cfs', $('forecast-time').textContent, $('forecast-coverage').textContent, $('forecast-issue').textContent, $('forecast-revision').textContent, '', $('crest-time').textContent, $('crest-detail').textContent, 'Next 24 h rain, mean of two forecast points: ' + $('rain-total').textContent + ' in. · ' + $('rain-status').textContent, $('rain-note').textContent, ...[...document.querySelectorAll('.rain-point')].map(el => el.innerText), '', 'NEARBY PROVISIONAL OBSERVED RAIN', state.observedRain ? 'Report issued ' + date(state.observedRain.issued) + '; issue time is not a measurement time.' : 'Report unavailable.', ...observedLines, '', 'Tides: Bellingham predictions, ft MLLW; not Samish Bay access clearance.', ...upcomingTides.map(r => (r.type === 'H' ? 'High ' : 'Low ') + feet(r.v) + ' ft · ' + date(r.t) + (r.passed ? ' · passed' : '')), '', 'Official commercial status is not ingested. Check Washington Department of Health.', 'No confirmed crest, dispatch recommendation, closure call, artificial-intelligence warning, all-clear or reopening authorization. Use established procedures; the Department of Health makes closure and reopening decisions.', 'https://doh.wa.gov/commercialshellfishmap', 'https://jdinneen.github.io/samish-river-outlook/'].join('\n');
  }
  $('copy-brief').addEventListener('click', async () => {
    const text = brief();
    try { await navigator.clipboard.writeText(text); put('copy-status', 'Field brief copied, including source times and limits.'); }
    catch { $('brief-fallback').value = text; $('brief-fallback').hidden = false; $('brief-fallback').focus(); $('brief-fallback').select(); put('copy-status', 'Select and copy the brief below.'); }
  });
  $('download-brief').addEventListener('click', () => {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(state.now));
    const stamp = Object.fromEntries(parts.map(p => [p.type, p.value]));
    downloadBlob(brief(), 'text/plain;charset=utf-8', 'samish-field-snapshot-' + stamp.year + stamp.month + stamp.day + '-' + stamp.hour + stamp.minute + '-Pacific.txt');
    put('copy-status', 'Field snapshot download prepared from the values currently shown.');
  });
  $('storm-log-form').addEventListener('submit', event => {
    event.preventDefault();
    const log = readStormLog();
    if (!log.available || !state) { renderStormLog(); return; }
    try {
      const record = currentStormRecord($('storm-log-tag').value, $('storm-log-note').value);
      const cutoff = Date.now() - 90 * 24 * H;
      const result = writeStormLog([record, ...log.records.filter(row => Date.parse(row.savedAt) >= cutoff)].slice(0, 500));
      if (!result.available) { renderStormLog(); return; }
      $('storm-log-note').value = '';
      renderStormLog('Saved this check on this device at ' + date(Date.parse(record.savedAt)) + '.');
    } catch { put('storm-log-status', 'This check could not be saved. Nothing was changed.'); }
  });
  $('storm-log-export').addEventListener('click', () => {
    const log = readStormLog();
    if (!log.available || !log.records.length) { renderStormLog(); return; }
    try { downloadBlob('\ufeff' + D.stormCsv(log.records), 'text/csv;charset=utf-8', 'samish-storm-checks-' + pacificDay(Date.now()) + '.csv'); put('storm-log-status', 'Event-log export prepared from ' + log.records.length + ' saved check' + (log.records.length === 1 ? '' : 's') + '.'); }
    catch { put('storm-log-status', 'The event log could not be exported. Nothing was deleted.'); }
  });
  $('storm-log-clear').addEventListener('click', () => {
    const log = readStormLog();
    if (!log.available || !log.records.length || !window.confirm('Clear all saved Samish storm checks from this device? This cannot be undone unless you exported them.')) return;
    try { localStorage.removeItem(STORM_LOG_KEY); if (localStorage.getItem(STORM_LOG_KEY) !== null) throw Error('Clear could not be verified'); renderStormLog('All storm checks saved on this device were cleared.'); }
    catch { renderStormLog(); }
  });
  $('storm-log-list').addEventListener('click', event => {
    const button = event.target.closest('[data-delete-log]');
    if (!button) return;
    const log = readStormLog();
    if (!log.available) { renderStormLog(); return; }
    const kept = log.records.filter(record => record.id !== button.dataset.deleteLog);
    if (kept.length === log.records.length) { put('storm-log-status', 'That saved check was not found. Nothing was changed.'); return; }
    const result = writeStormLog(kept);
    renderStormLog(result.available ? 'One saved check was deleted.' : '');
  });
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  function select(tab) { for (const t of tabs) { const active = t === tab; t.setAttribute('aria-selected', String(active)); t.tabIndex = active ? 0 : -1; $(t.getAttribute('aria-controls')).hidden = !active; } if (tab.id === 'tab-outlook') chart(); }
  for (const tab of tabs) { tab.addEventListener('click', () => select(tab)); tab.addEventListener('keydown', e => { let i = tabs.indexOf(tab); if (e.key === 'ArrowRight') i = (i + 1) % tabs.length; else if (e.key === 'ArrowLeft') i = (i + tabs.length - 1) % tabs.length; else if (e.key === 'Home') i = 0; else if (e.key === 'End') i = tabs.length - 1; else return; e.preventDefault(); select(tabs[i]); tabs[i].focus(); }); }
  $('radar-loop').addEventListener('load', event => {
    if (Number(event.currentTarget.dataset.validTime) !== radar.validTime) return;
    const times = selectedRadarTimes();
    event.currentTarget.parentElement.classList.remove('unavailable');
    const status = radar.playing && times.length > 1 ? 'Animating retrieved frames' : radar.frame === times.length - 1 ? 'Latest retrieved frame' : 'Retrieved frame';
    if ($('radar-status').textContent !== status) badge('radar-status', status, 'good');
    $('radar-toggle').disabled = times.length < 2; put('radar-toggle', radar.playing ? 'Pause animation' : 'Play animation');
    updateRadarSourceCard();
    if (radar.playing && times.length > 1 && !document.hidden) radarTimer = setTimeout(() => { radar.frame = (radar.frame + 1) % times.length; updateRadarFrame(true); }, 1200);
  });
  $('radar-loop').addEventListener('error', event => {
    if (Number(event.currentTarget.dataset.validTime) !== radar.validTime) return;
    clearTimeout(radarTimer); radar.imageError = 'The selected radar image could not be decoded.';
    markRadarImageUnavailable(event.currentTarget);
    badge('radar-status', 'Unavailable', 'caution');
    put('radar-requested', 'The selected National Weather Service radar image could not be loaded. River and rain values remain independent.');
    $('radar-toggle').disabled = true; event.currentTarget.parentElement.classList.add('unavailable');
    renderRadarLegendStatus(); updateRadarSourceCard();
  });
  $('radar-legend').addEventListener('load', event => {
    if (event.currentTarget.dataset.layer !== RADAR_PRODUCTS[radar.product].layer) return;
    radar.legendLoaded = true; radar.legendError = null; renderRadarLegendStatus(); updateRadarSourceCard();
  });
  $('radar-legend').addEventListener('error', event => {
    if (event.currentTarget.dataset.layer !== RADAR_PRODUCTS[radar.product].layer) return;
    radar.legendLoaded = false; radar.legendError = 'The official radar legend could not be loaded.'; renderRadarLegendStatus(); updateRadarSourceCard();
  });
  document.querySelectorAll('[data-radar-product]').forEach(button => button.addEventListener('click', () => { radar.product = button.dataset.radarProduct; const times = selectedRadarTimes(); radar.frame = Math.max(0, times.length - 1); updateRadarFrame(); }));
  $('radar-toggle').addEventListener('click', () => { radar.playing = !radar.playing; writePausePreference(!radar.playing); const times = selectedRadarTimes(); if (radar.playing && radar.frame >= times.length - 1) radar.frame = 0; updateRadarFrame(); });
  $('refresh').addEventListener('click', () => { load(); refreshRadar(); });
  new ResizeObserver(() => { if (!$('outlook').hidden) chart(); }).observe($('flow-chart'));
  new ResizeObserver(entries => {
    const width = Math.round(entries[0]?.contentRect?.width || 0);
    if (state && !$('outlook').hidden && width && Math.abs(width - rainChartWidth) > 1) renderRainForecast(state.rains, state.now);
  }).observe($('rain-chart'));
  setInterval(() => { if (!document.hidden) load(); }, 10 * 60 * 1000);
  setInterval(() => { if (!document.hidden) refreshRadar(); }, 5 * 60 * 1000);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { clearTimeout(radarTimer); return; }
    if (state && Date.now() - state.now > 10 * 60 * 1000) load();
    if (!radar.requestedAt || Date.now() - radar.requestedAt > 5 * 60 * 1000) refreshRadar();
    else updateRadarFrame(true);
  });
  // Research tab: the look-back on past rises. Static text, written once at start-up; every count is read from D.EVIDENCE.
  function renderLookback() {
    const all = E.timing.all, dry = E.timing.dry, wait = E.wait, aligned = E.aligned, peak = E.peak2h, fall = E.falling, after = E.afterNewHigh, rainy = E.rainPause, p = text => '<p>' + esc(text) + '</p>';
    const card = (key, label, title, body) => '<article class="card" data-evidence="' + key + '"><p class="eyebrow">' + esc(label) + '</p><h3>' + esc(title) + '</h3>' + body + '<p class="note">Period: ' + esc(E[key].period) + '. ' + esc(E.caveat) + '</p><p class="meta">' + esc(E[key].source) + '</p></article>';
    const span = values => halves(Math.min(...values)) + ' to ' + halves(Math.max(...values));
    put('lookback-title', 'What ' + E.rises.count + ' past rises say about the peak');
    put('lookback-lede', 'Counts from ' + E.rises.count + ' rises at the ' + E.rises.place + ', ' + E.rises.period + ', read from ' + E.rises.readings + ', with three look-backs on forecasts. A rise is counted from the hour its 24-hour rise passed the seasonal number. Every count describes past years: none is a forecast, a chance for the next rise, or a sampling rule.');
    const waitTable = '<div class="table-wrap lookback-table" role="region" aria-label="Further hours to the highest reading at each stage" tabindex="0"><table><caption>Rises whose highest reading had not yet come, by hours since the seasonal number was passed, and the further hours to that reading.</caption><thead><tr><th scope="col">Hours since passed</th><th scope="col">Rises still short of their highest reading</th><th scope="col">Lower quarter: this many hours or fewer</th><th scope="col">Middle value</th><th scope="col">Upper quarter: this many hours or more</th></tr></thead><tbody>' + wait.stagesHours.map((stage, i) => '<tr><td>' + num(stage) + '</td><td>' + num(wait.risesStillWaiting[i]) + '</td><td>' + num(wait.lowerQuartileMoreHours[i]) + '</td><td>' + num(wait.medianMoreHours[i]) + '</td><td>' + num(wait.upperQuartileMoreHours[i]) + '</td></tr>').join('') + '</tbody></table></div>';
    $('lookback-grid').innerHTML = [
      card('timing', 'TIMING OF THE HIGHEST READING', 'From the seasonal number to the highest reading',
        p('Across ' + all.rises + ' rises, the highest reading came a median of ' + halves(all.medianHours) + ' hours after the 24-hour rise passed the seasonal number (the middle value: half took less, half took more). Half of the rises took between ' + halves(all.middleHalfHours[0]) + ' and ' + halves(all.middleHalfHours[1]) + ' hours; ' + all.under2h + ' took under 2 hours and ' + all.atLeast16h + ' of ' + all.rises + ' took 16 hours or more.') +
        p('In ' + dry.months + ' (' + dry.rises + ' rises) the median was ' + halves(dry.medianHours) + ' hours and half took between ' + halves(dry.middleHalfHours[0]) + ' and ' + halves(dry.middleHalfHours[1]) + ' hours; ' + dry.over8h + ' took more than 8 hours and ' + dry.atLeast16h + ' took 16 hours or more.') +
        p('The spread is too wide for one clock time, so this page prints no time for the top of a rise.')),
      card('afterNewHigh', 'AFTER A NEW HIGH', 'How far away the top was when a reading set a new high',
        p('Of ' + num(after.readings) + ' readings that were a new high for their rise (' + after.rises + ' rises), the highest reading of the rise came within the next ' + after.withinHours + ' hours for ' + after.withinPercent + '% (about 1 in ' + after.aboutOneInWithin + ') and was still ' + after.atLeastHours + ' hours or more away for ' + after.atLeastPercent + '% (about 1 in ' + after.aboutOneInAtLeast + ').') +
        p('The last new high of every rise is its top, so a new high can be the top; and a long rise is not due to stop.')),
      card('wait', 'TIME STILL TO GO', 'How much longer past rises took',
        p('For the rises whose highest reading had not yet come, the further time to it was wide at every stage checked: a quarter of them got there within ' + span(wait.lowerQuartileMoreHours) + ' hours, the middle value was ' + span(wait.medianMoreHours) + ' hours, and a quarter needed ' + span(wait.upperQuartileMoreHours) + ' hours or more.') + waitTable),
      card('pause', 'A ONE-HOUR PAUSE', 'A pause is not a peak',
        p('The first time each rise went ' + E.pause.afterMinutes + ' minutes of readings with no new high, ' + E.pause.higherAgain + ' of ' + E.pause.rises + ' went higher again within ' + within(E.pause.withinHours) + ', ' + E.pause.higherByMoreThan5Percent + ' of them by more than 5%.')),
      card('peak2h', 'NO NEW HIGH', num(peak.afterMinutes / 60) + ' hours with no new high',
        p('The first time each rise went ' + num(peak.afterMinutes / 60) + ' hours of readings with no new high, the river later climbed more than 5% above that high within 12 hours in ' + peak.within12h + ' of ' + peak.rises + ' rises (about 1 in ' + peak.aboutOneIn12h + ') and within 24 hours in ' + peak.within24h + ' (about 1 in ' + peak.aboutOneIn24h + ').')),
      card('rainPause', 'RAIN AND A PAUSE', 'Rain when the river stops setting new highs', p(SAY.rainPause())),
      card('falling', 'OFF THE HIGH', percent(fall.belowHighFraction) + '% below the high',
        p('The first time each rise read at least ' + percent(fall.belowHighFraction) + '% below its highest reading so far, the river later climbed more than 5% above that high within 12 hours in ' + fall.within12h + ' of ' + fall.rises + ' rises (about 1 in ' + fall.aboutOneIn12h + ') and within 24 hours in ' + fall.within24h + ' (about 1 in ' + fall.aboutOneIn24h + ').')),
      card('aligned', 'NOAA FORECAST AND THE GAUGE', 'Shifting NOAA’s forecast to the latest gauge reading',
        p('At the Samish over ' + aligned.period + ' (' + aligned.rises + ' rises), NOAA’s river forecast shifted to start at the latest gauge reading gave ' + aligned.falseAlertEpisodesAligned + ' false-alert episodes against ' + aligned.falseAlertEpisodesAsIssued + ' for the forecast read as issued, with ' + aligned.warned12hEitherWay + ' rises warned ' + aligned.leadHours + ' hours or more ahead either way.') +
        p('Limit: the shift does nothing for a rise NOAA’s river forecast does not show. This page does not draw the current forecast shifted to the gauge; it says when the gauge is above the forecast instead.')),
      card('noaaDry', 'NOAA IN THE DRY SEASON', 'NOAA’s river forecast before May to October rises',
        p(SAY.noaaDry()) + p('A closure-size rise is a 24-hour rise as large as the seasonal number.')),
      card('rainContext', 'RAIN FORECAST · CONTEXT, NOT AN ALERT', 'Heavy forecast rain in the dry season', p(SAY.rainContext()))
    ].join('');
  }
  // Sources tab: the River, NOAA, tide and rain display rules, written from the rule constants so they cannot drift.
  function renderRules() {
    const line = percent(D.WATCH.seasonalFraction), drop = percent(RULES.fallingFraction), rise = percent(RULES.risingFraction), climb = percent(RULES.climbBackFraction);
    $('river-rules').innerHTML = [
      'A gauge reading is treated as recent for ' + RULES.freshMinutes + ' minutes. Its clock time and its age are printed beside it. When the newest reading is older than that, or more than ' + RULES.maxGapMinutes + ' minutes of readings are missing inside the last hour, the page prints “Cannot tell whether the river is rising” and shows no change figure and no state.',
      'When the newest gauge reading is stamped more than ' + RULES.clockBehindMinutes + ' minutes after this device’s time, the device clock is behind the gauge: the page says so and prints no age, no change figure and no state until the clock is corrected.',
      'Every duration in the River block is counted between gauge reading time stamps, never against this device’s clock. The device’s check time is used only for the age of the newest reading.',
      'The last-hour change is the newest reading minus the reading nearest one hour earlier, within ' + RULES.lastHourToleranceMinutes + ' minutes either way. It is called “rising” only at +' + RULES.risingCfs + ' cubic feet per second (cfs) and +' + rise + '% or more, “falling” only at −' + RULES.risingCfs + ' cfs and −' + rise + '% or beyond, and “about level” otherwise.',
      'The measured rise is the newest reading minus the lowest reading of the 24 hours before it. With readings reaching back 24 hours and no hole over ' + RULES.maxGapMinutes + ' minutes it is exact. With such a hole it is printed as “at least”, a lower bound above the lowest reading held, because a lower reading may have been missed. When the holes inside those 24 hours add up to more than ' + RULES.hiddenRiseGapHours + ' hours, the bound is printed without its share of the seasonal number, because most of the rise may be hidden. When the readings do not reach back 24 hours it is shown as unavailable, never as zero or as “no rise”. Its share of the seasonal number is rounded down, here and on the rise card.',
      '“This rise” starts at the first reading of the last ' + RULES.riseMemoryHours + ' hours at which that measured rise crossed up to the seasonal number in force at that reading, and it is remembered for ' + RULES.riseMemoryHours + ' hours of readings. A reading whose lower bound reaches the number counts as past it, and the page then says “since at or before”, because a gap hides the exact time. When no reading in those ' + RULES.riseMemoryHours + ' hours crosses up to the number and the earliest one compared is already past it, the page says its readings do not reach back to where that rise began, prints the highest reading it holds, and gives no pause, peak or falling line and no count.',
      'A new high is any reading strictly higher than every earlier reading of this rise. An equal reading is not a new high. “Still rising” is said only for a new high whose last-hour change is “rising”; otherwise the page says “New high”. When a higher reading from the last ' + RULES.riseMemoryHours + ' hours is held from before this rise began, the new-high line names it.',
      'State lines: ' + RULES.pauseMinutes + ' minutes of readings with no new high is called a pause; ' + RULES.peakMinutes + ' minutes or more is “may have peaked”; a newest reading at least ' + drop + '% below the high is “falling”. None of these says the top of the rise has passed. After ' + RULES.peakMinutes + ' minutes with no new high, while the newest reading is higher than the one about three hours earlier and the last-hour change is not negative, the page prints those two facts instead of “may have peaked”, with no count. A reading below the high is instead called climbing again when its last-hour change is “rising”, or when it stands above the lowest reading since the high by at least ' + climb + '% of the high, the about-three-hour change is positive and the last-hour change is not negative. A hole over ' + RULES.maxGapMinutes + ' minutes between the high and the newest reading gives no state.',
      'The count beside “falling” is taken from the first reading at least ' + drop + '% below the high, and the count beside “may have peaked” from the ' + (RULES.peakMinutes / 60) + '-hour mark. Neither count is printed once the newest reading is more than ' + D.LOOKBACK_RULES.countHorizonHours + ' hours of readings past that point.',
      '“Not tracking” sets NOAA’s current forecast issue against the gauge. When NOAA’s path covers the time of the newest gauge reading, its value for that time (read along a straight line between forecast points no more than 6 hours apart) is set against the reading: the gauge is above the line at ' + line + '% of the seasonal number or more, and with a measured rise in progress the page then says the forecast is not tracking it. A NOAA path starts some hours after it is issued. Until its first point is reached no value is invented for the reading’s time: the gauge is above the line when it stands above the path’s first value by that ' + line + '% or more while the last-hour change is not “falling”, and the page prints the measured figures only and does not say “not tracking”. In both cases the gauge is also above the line whenever it is above the highest value in NOAA’s forecast by any amount while the last-hour change is “rising”. This uses no saved history, so it works on a first visit.',
      'NOAA’s peak-time words (a forecast high time, or that its forecast falls from its first value) are printed only when that comparison was made and the gauge is not above the line. When the River block cannot tell, the comparison is not made and the NOAA-based rise card (“What NOAA’s forecast adds”) is withheld for the same reason.',
      'The counts printed beside a state are look-backs on ' + E.rises.count + ' Samish rises of ' + E.rises.period + ' (' + E.rises.readings + '), listed under Research & limits. ' + E.caveat,
      'The tide block keeps the last high or low after it passes and shows the next two. They are Bellingham predictions, not Samish Bay water levels or boat clearance.',
      'A six-hour rain block with no value is drawn as a hatched “no data” column, and a block forecast at exactly zero is labelled 0. An observed-rain gauge reading 0.00 inch for 24 hours while both other listed gauges report ' + D.RAIN_RULES.suspectZeroOtherGaugesIn + ' inch or more is marked suspect. The dry-season rain context is shown from May to October only, and the two rain sentences appear beside “may have peaked” only.'
    ].map(text => '<li>' + esc(text) + '</li>').join('');
  }
  renderLookback();
  renderRules();
  refreshRadar();
  load();
})();
