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
    const detail = unavailable ? radar.error || radar.imageError || 'Radar metadata unavailable' : product.label + ' valid ' + date(radar.validTime) + '. Product-valid time—not browser request time.';
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
    put('update-status', 'Refreshing public feeds… Existing readings remain dated while requests finish.');
    try {
    const requestTime = Date.now();
    sources[4].url = 'https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions&station=9449211&begin_date=' + pacificDay(requestTime) + '&range=168&datum=MLLW&units=english&time_zone=gmt&interval=hilo&format=json&application=samish_outlook';
    const [coreFeeds, rrmFeed, basinFeed] = await Promise.all([Promise.all(sources.map(fetchFeed)), fetchLatestRrm(requestTime), fetchBasinOnce()]), now = Date.now();
    // Each series is parsed independently: a malformed forecast must not erase a valid gauge.
    const river = coreFeeds[0], gaugeCopy = { ...river }, observations = parse(gaugeCopy, d => D.nwpsSeries(d.observed, now, true)) || [];
    let rawForecast = [], issue = null;
    if (!river.error) {
      try { rawForecast = D.nwpsSeries(river.data.forecast, now, false); issue = river.data.forecast.issuedTime; }
      catch (e) { river.error = 'Forecast: ' + e.message; }
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
    const allTides = (parse(coreFeeds[4], D.tides) || []).filter(r => r.t >= now);
    if (!coreFeeds[4].error && !allTides.length) coreFeeds[4].error = 'No upcoming high or low tides';
    const latest = merged.at(-1), change3 = D.recentChange(merged, latest, 3, now);
    const screen = fc.usable ? D.planningScreen(merged, rawForecast, now) : { usable: false, reason: 'A current usable NOAA forecast is required', alignedRows: [] };
    const initialHistory = readHistory();
    let watch = D.surpriseWatch({ t: latest?.t, q: latest?.q, change3: change3?.change, span3: change3?.spanHours, fresh: !!latest && now - latest.t <= 2 * H }, initialHistory.snapshots, initialHistory.status);
    const revision = D.forecastRevision(fc, initialHistory.snapshots, now);
    const history = saveSnapshot(initialHistory, D.makeSnapshot(fc, screen, latest, now), now);
    if (history.status !== 'available') watch = D.surpriseWatch(null, [], 'unavailable');
    state = { now, feeds: [...coreFeeds, rrmFeed, basinFeed], observations: merged, rawForecast, direct, gaugeCopy, fc, rains, observedRain, basin, gaugePoint, gridPoints, tides: allTides.slice(0, 4), allTides, change3, screen, watch, revision, history };
    render();
    } catch {
      state = { now: Date.now(), feeds: [...sources, RRM_INDEX, BASIN_SOURCE].map(s => ({ ...s, error: 'Unexpected feed processing error' })), observations: [], rawForecast: [], direct: [], gaugeCopy: { error: 'Unavailable' }, fc: { usable: false, reason: 'Forecast processing unavailable', issued: null, rows: [] }, rains: [null, null], observedRain: null, basin: null, gaugePoint: null, gridPoints: [], tides: [], allTides: [], change3: null, screen: { usable: false, reason: 'River processing unavailable' }, watch: { code: 'unknown', reason: 'River processing unavailable' }, revision: { usable: false, reason: 'River processing unavailable' }, history: readHistory() };
      render();
    } finally { busy = false; $('refresh').disabled = false; $('main').setAttribute('aria-busy', 'false'); }
  }
  function render() {
    const { now, feeds, observations, direct, gaugeCopy, fc, rains, observedRain, tides, allTides, screen, watch, revision, history } = state, last = observations.at(-1);
    put('update-status', 'Feed check completed ' + date(now) + ' · Automatic refresh is attempted every 10 minutes only while this page is open, visible and the device is awake. No notifications are sent.');
    const problems = [];
    if (!last || now - last.t > 2 * H) problems.push('The gauge is ' + (last ? 'stale' : 'unavailable'));
    if (!fc.usable) problems.push('the river forecast is unavailable');
    if (!rains.every(r => r?.fresh && r.complete)) problems.push('the rain summary is incomplete');
    if (!observedRain || !observedRain.fresh) problems.push('the nearby observed-rain report is ' + (observedRain ? 'stale' : 'unavailable'));
    if (!tides.length) problems.push('tide predictions are unavailable');
    $('feed-alert').hidden = !problems.length;
    const problemText = problems.join('; ');
    put('feed-alert', problemText ? problemText.charAt(0).toUpperCase() + problemText.slice(1) + '. Check the dated source details before planning.' : '');
    put('gauge-heading', last && now - last.t > 2 * H ? 'Last river reading' : 'River now');
    put('flow', num(last?.q));
    badge('gauge-status', last ? (now - last.t <= 2 * H ? 'Recent observation' : 'Stale observation') : 'Unavailable', last && now - last.t <= 2 * H ? 'good' : 'caution');
    put('gauge-time', last ? 'Last reading · ' + date(last.t) : 'No valid gauge reading retrieved');
    put('observation-note', 'U.S. Geological Survey (USGS) station 12201500 · provisional observations, subject to revision' + (last ? ' · ' + last.source : ''));
    for (const hours of [24, 3]) { const change = D.recentChange(observations, last, hours, now); put('change' + hours, change ? signed(change.change) + ' cfs' : 'Unavailable'); }
    const threshold = D.thresholdAt(now);
    put('ops-flow', last ? num(last.q) + (now - last.t > 2 * H ? ' · stale' : '') : 'Unavailable');
    put('ops-change', state.change3 ? signed(state.change3.change) : 'Unavailable');
    put('ops-threshold', threshold ? threshold.cfs + ' cfs' : 'Unavailable');
    put('ops-threshold-note', threshold ? threshold.label + ' · not a forecast' : 'Season unavailable · not a forecast');
    put('ops-forecast', fc.usable ? num(fc.max) + ' cfs' : 'Unavailable');
    renderWatch(watch, history);
    renderRise(screen, last ? D.thresholdAt(last.t) : threshold);
    badge('forecast-status', fc.usable ? (fc.complete ? 'Up to 72 h' : 'Shorter horizon') : 'Unavailable', fc.usable ? 'neutral' : 'caution');
    put('forecast-high', fc.usable ? num(fc.max) : '—');
    put('forecast-time', !fc.usable ? fc.reason : fc.atStart && fc.atEnd ? 'Highest value occurs at both ends of the available window' : fc.atEnd ? 'Highest at the end · peak may be later' : fc.atStart ? 'Highest at the start of this forecast window' : 'Forecast high around ' + date(fc.firstMax));
    put('forecast-coverage', fc.usable ? (fc.startsAfterCheck ? 'Path begins ' + date(fc.start) + ' · ' + num((fc.start - now) / H) + ' h after this check; no check-time value was inserted. ' : '') + 'Available through ' + date(fc.end) + ' · ' + num(fc.hours) + ' h from this check.' + (fc.firstMax !== fc.lastMax ? ' The highest value occurs at more than one forecast time.' : '') : 'No forecast high or timing estimate is shown.');
    put('forecast-issue', fc.issued === null ? 'Issue time unavailable' : 'NOAA issued · ' + date(fc.issued));
    put('forecast-revision', revision.usable ? 'Compared on the same next 24 hours, the latest NOAA issue’s high is ' + signed(revision.difference) + ' cfs versus the issue saved ' + date(revision.previousIssue) + '.' : revision.reason);
    renderRainForecast(rains, now);
    renderObservedRain(observedRain);
    badge('tide-status', tides.length ? 'Predicted' : 'Unavailable', tides.length ? 'neutral' : 'caution');
    $('tide-list').innerHTML = tides.length ? tides.map(r => '<div class="tide-row"><span>' + (r.type === 'H' ? 'High' : 'Low') + '</span><strong>' + r.v.toFixed(1) + '<span class="small-label">ft MLLW</span></strong><time datetime="' + new Date(r.t).toISOString() + '">' + esc(date(r.t)) + '</time></div>').join('') : 'No upcoming predictions retrieved. Use the official tide source.';
    renderCrest(fc, allTides);
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
    const rows = Array.from({ length: 6 }, (_, index) => ({ index, a: rains[0]?.bins?.[index] || null, b: rains[1]?.bins?.[index] || null }));
    $('rain-forecast-table').innerHTML = '<table><caption>Six-hour forecast accumulation blocks beginning at this page’s feed-check time. Missing coverage remains unavailable.</caption><thead><tr><th scope="col">Pacific interval</th><th scope="col">Mid · 136,114</th><th scope="col">Upper-east · 139,116</th></tr></thead><tbody>' + rows.map(row => { const start = row.a?.t ?? row.b?.t, end = row.a?.end ?? row.b?.end; return '<tr><td>' + (Number.isFinite(start) && Number.isFinite(end) ? esc(date(start)) + '–' + esc(date(end)) : 'Unavailable') + '</td><td>' + (row.a?.complete && row.a.mm !== null ? esc(inches(row.a.mm)) + ' in.' : 'Unavailable') + '</td><td>' + (row.b?.complete && row.b.mm !== null ? esc(inches(row.b.mm)) + ' in.' : 'Unavailable') + '</td></tr>'; }).join('') + '</tbody></table>';
    const available = rows.flatMap(row => [row.a, row.b]).filter(bin => bin?.complete && bin.mm !== null);
    if (!available.length) { $('rain-chart').className = 'rain-chart chart-empty'; put('rain-chart', 'Complete six-hour rain blocks are unavailable.'); return; }
    const w = Math.max(260, Math.round($('rain-chart').clientWidth || 760)), h = 240, left = 45, right = 12, top = 34, bottom = 48, inner = w - left - right, group = inner / rows.length, bar = Math.min(34, group * .3), maxIn = Math.max(.01, ...available.map(bin => bin.mm / 25.4)) * 1.15;
    rainChartWidth = w;
    const y = value => top + (1 - value / maxIn) * (h - top - bottom);
    const secondLegendX = Math.max(148, Math.min(205, w - 125));
    let svg = '<svg viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-labelledby="rain-svg-title rain-svg-desc"><title id="rain-svg-title">Forecast rain in six-hour blocks at two National Weather Service grid points</title><desc id="rain-svg-desc">Paired bars show forecast inches at mid-area grid 136,114 and upper-east grid 139,116. Missing blocks have no bar. Values are also available in the table.</desc><g class="rain-legend"><rect x="45" y="8" width="12" height="12" class="rain-a"></rect><text x="63" y="19">Mid point</text><rect x="' + secondLegendX + '" y="8" width="12" height="12" class="rain-b"></rect><text x="' + (secondLegendX + 18) + '" y="19">Upper-east point</text></g>';
    for (let i = 0; i <= 3; i++) { const value = maxIn * i / 3, yy = y(value); svg += '<line x1="' + left + '" x2="' + (w - right) + '" y1="' + yy + '" y2="' + yy + '" class="chart-grid"></line><text x="' + (left - 7) + '" y="' + (yy + 4) + '" text-anchor="end">' + value.toFixed(2) + '</text>'; }
    rows.forEach((row, index) => {
      const center = left + group * (index + .5), values = [row.a, row.b];
      values.forEach((bin, series) => { if (!bin?.complete || bin.mm === null) return; const value = bin.mm / 25.4, yy = y(value); svg += '<rect x="' + (center + (series ? 2 : -bar - 2)) + '" y="' + yy + '" width="' + bar + '" height="' + Math.max(0, h - bottom - yy) + '" class="' + (series ? 'rain-b' : 'rain-a') + '"><title>' + labels[series] + ': ' + inches(bin.mm) + ' inches</title></rect>'; });
      svg += '<text x="' + center + '" y="' + (h - 20) + '" text-anchor="middle">+' + (index * 6) + '–' + ((index + 1) * 6) + ' h</text>';
    });
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
    const windows = report.windows.slice(0, 5);
    $('observed-rain-table').innerHTML = '<table><caption>Provisional rolling precipitation totals in inches from automated stations near the watershed. National Weather Service accuracy has not been verified.</caption><thead><tr><th scope="col">Station</th>' + windows.map(value => '<th scope="col">' + value + ' h</th>').join('') + '</tr></thead><tbody>' + report.stations.map(station => '<tr><th scope="row">' + esc(station.label) + '</th>' + windows.map((value, index) => '<td>' + (station.available && station.values[index] !== null ? station.values[index].toFixed(2) : 'Unavailable') + '</td>').join('') + '</tr>').join('') + '</tbody></table>';
  }
  function renderWatch(watch, history) {
    const labels = { outpacing: 'ABOVE EARLIER PATH', 'above-prior': 'ABOVE EARLIER PATH', tracking: 'NOT ABOVE COMPARISON LINE', learning: 'BUILDING HISTORY', unknown: 'COMPARISON UNAVAILABLE' };
    const titles = { outpacing: 'River is above an earlier saved NOAA path and still rising', 'above-prior': 'River is above an earlier saved NOAA path; near-3-hour change is not positive', tracking: 'Gauge is below the unvalidated positive comparison line', learning: 'This browser needs an older saved forecast', unknown: 'Saved-forecast comparison unavailable' };
    $('surprise-watch').className = 'watch-card ' + (watch.code || 'unknown');
    badge('watch-state', labels[watch.code] || labels.unknown, watch.code === 'outpacing' || watch.code === 'above-prior' ? 'caution' : 'neutral');
    put('watch-title', titles[watch.code] || titles.unknown);
    if (watch.snapshot) {
      put('watch-detail', 'A gauge-aligned NOAA path saved ' + num(watch.age) + ' hours before this observation expected ' + num(watch.expected) + ' cfs. The gauge reads ' + num(watch.observed) + ' cfs (' + signed(watch.difference) + ' cfs), and changed ' + signed(watch.change3) + ' cfs over ' + num(watch.span3) + ' hours. The frozen comparison line is ' + num(watch.line) + ' cfs. This is not a risk or safety status, closure call, or all-clear.');
      put('watch-source', 'Saved ' + date(watch.snapshot.capturedAt) + ' from NOAA issue ' + date(watch.snapshot.issueTime) + '. The 10% comparison line is an unvalidated experimental heuristic—not an alert threshold.');
    } else {
      const recovery = history.status === 'available' ? ' Keep this tab visible or revisit it during weather so this browser profile can save NOAA issues. No refreshes occur while the tab is hidden or closed.' : ' Browser storage is unavailable or malformed; keeping the tab open cannot build history until storage works or the malformed local history is cleared.';
      put('watch-detail', (watch.reason || 'No comparison is available.') + '.' + recovery);
      put('watch-source', (history.status === 'available' ? history.snapshots.length : 0) + ' NOAA issue' + ((history.snapshots?.length || 0) === 1 ? '' : 's') + ' stored in this browser profile · retained up to 14 days · clearing browser data clears the history.');
    }
    put('watch-expected', watch.expected === null || watch.expected === undefined ? '—' : num(watch.expected));
    put('watch-observed', watch.observed === null || watch.observed === undefined ? '—' : num(watch.observed));
    put('watch-change', watch.change3 === null || watch.change3 === undefined ? '—' : signed(watch.change3));
  }
  function renderRise(screen, threshold) {
    if (!screen?.usable) {
      badge('rise-status', 'Unavailable', 'caution'); put('rise-percent', '—'); put('rise-title', screen?.reason || 'Planning comparison unavailable');
      put('screen-rise', '—'); put('season-threshold', threshold ? threshold.cfs + ' cfs' : '—'); put('rise-detail', 'No partial path is turned into a reassuring result.'); $('rise-progress').style.width = '0'; return;
    }
    const percent = Math.round(screen.percent), relation = D.lineRelation(screen.difference), exceeded = relation.code === 'above';
    badge('rise-status', 'Experimental', exceeded ? 'caution' : 'neutral'); put('rise-percent', percent.toLocaleString('en-US'));
    put('rise-title', num(screen.riseAtHighestShare) + ' cfs rise at the highest seasonal share versus the ' + screen.threshold.cfs + ' cfs ' + screen.threshold.label + ' number');
    put('screen-rise', num(screen.riseAtHighestShare) + ' cfs'); put('season-threshold', screen.threshold.cfs + ' cfs');
    const relationText = relation.code === 'at' ? 'At the numeric line' : num(relation.distance) + ' cfs ' + relation.code + ' the numeric line';
    put('rise-detail', relationText + ' at the ' + screen.pointSource + ' point ' + date(screen.pointTime) + '. This point has the highest rise divided by its applicable seasonal number; it may not be the largest raw rise when that number changes. Rolling low ' + num(screen.baselineCfs) + ' cfs at ' + date(screen.baselineTime) + '. Gauge alignment ' + signed(screen.adjustment) + ' cfs. Not official status.');
    $('rise-progress').style.width = Math.min(100, Math.max(0, screen.percent)) + '%';
    $('rise-progress').style.background = exceeded ? 'var(--coral)' : 'var(--teal)';
  }
  function renderCrest(fc, tides) {
    $('crest-nearby').innerHTML = '';
    if (!fc?.usable || fc.atStart || fc.atEnd) {
      put('crest-time', !fc?.usable ? 'Forecast timing unavailable' : fc.atEnd ? 'Highest value is at the forecast’s end' : 'Highest value is at the forecast’s start');
      put('crest-detail', !fc?.usable ? fc.reason : fc.atEnd ? 'The high may occur later than the available path. No tide pairing is inferred.' : 'The river is forecast to fall from the start of the window. No future high time is inferred.'); return;
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
    const w = Math.max(230, $('flow-chart').clientWidth), h = 280, l = 49, right = 13, top = 22, bottom = 44;
    const max = Math.max(1, ...all.map(r => r.q)) * 1.15, x = t => l + (t - start) / (end - start) * (w - l - right), y = q => top + (1 - q / max) * (h - top - bottom);
    const paths = (rows, gap, color, dash) => {
      const groups = []; rows.forEach((r, i) => { if (!i || r.t - rows[i - 1].t > gap) groups.push([]); groups.at(-1).push(r); });
      return groups.map(g => g.length === 1 ? '<circle cx="' + x(g[0].t) + '" cy="' + y(g[0].q) + '" r="3" fill="' + color + '"/>' : '<path d="' + g.map((r, i) => (i ? 'L' : 'M') + x(r.t).toFixed(2) + ',' + y(r.q).toFixed(2)).join(' ') + '" fill="none" stroke="' + color + '" stroke-width="2.5"' + (dash ? ' stroke-dasharray="' + dash + '"' : '') + '/>').join('');
    };
    const desc = 'Flow in cubic feet per second. Observations cover the previous 48 hours where available. ' + (fc.usable ? 'NOAA forecast extends ' + num(fc.hours) + ' hours from this check; highest forecast value is ' + num(fc.max) + ' cfs.' + (fc.startsAfterCheck ? ' The forecast begins ' + num((fc.start - now) / H) + ' hours after check time, and that gap is left visible.' : '') : 'NOAA forecast unavailable.') + (saved.length ? ' An earlier eligible gauge-aligned path is shown separately.' : ' No eligible earlier saved path is available.');
    let svg = '<svg viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-labelledby="flow-title flow-desc"><title id="flow-title">Samish river flow</title><desc id="flow-desc">' + esc(desc) + '</desc>';
    for (let i = 0; i <= 4; i++) { const q = max * i / 4; svg += '<line x1="' + l + '" x2="' + (w - right) + '" y1="' + y(q) + '" y2="' + y(q) + '" stroke="var(--line)"/><text x="' + (l - 7) + '" y="' + (y(q) + 4) + '" text-anchor="end">' + Math.round(q).toLocaleString('en-US') + '</text>'; }
    svg += '<text x="' + l + '" y="13">cfs</text><line x1="' + x(now) + '" x2="' + x(now) + '" y1="' + top + '" y2="' + (h - bottom) + '" stroke="var(--muted)" stroke-dasharray="3 4"/>';
    const ticks = w < 500 ? [[start, '−48 h'], [now, '0 h'], [end, '+72 h']] : [[start, '−48 h'], [now - 24 * H, '−24 h'], [now, 'Check time'], [now + 24 * H, '+24 h'], [now + 48 * H, '+48 h'], [end, '+72 h']];
    for (let i = 0; i < ticks.length; i++) svg += '<text x="' + x(ticks[i][0]) + '" y="' + (h - 16) + '" text-anchor="' + (i === 0 ? 'start' : i === ticks.length - 1 ? 'end' : 'middle') + '">' + ticks[i][1] + '</text>';
    svg += paths(saved, 6 * H, 'var(--saved)', '2 5') + paths(obs, 2 * H, 'var(--teal)', '') + paths(future, 6 * H, 'var(--navy)', '7 5') + '</svg>';
    $('flow-chart').className = ''; $('flow-chart').innerHTML = svg;
    put('chart-description', (saved.length ? 'The dotted amber line is the earlier saved path after one gauge alignment. ' : 'No eligible earlier saved path is available yet. ') + 'NOAA’s current dashed forecast remains raw and unshifted. Gaps stay visible; 0 h is this page’s feed-check time.');
  }
  function readStormLog() {
    try {
      const raw = localStorage.getItem(STORM_LOG_KEY);
      if (raw === null) return { available: true, records: [] };
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed) || parsed.length > 500) throw Error('Stored event log is malformed');
      return { available: true, records: parsed.map(D.stormRecord) };
    } catch { return { available: false, records: [], reason: 'Browser storage is blocked or the saved event log is malformed. It was not overwritten.' }; }
  }
  function writeStormLog(records) {
    try {
      const clean = records.map(D.stormRecord);
      localStorage.setItem(STORM_LOG_KEY, JSON.stringify(clean));
      if (localStorage.getItem(STORM_LOG_KEY) === null) throw Error('Storage write could not be verified');
      return { available: true, records: clean };
    } catch { return { available: false, records: [], reason: 'The event log could not be saved in this browser profile.' }; }
  }
  function currentStormRecord(tag, note) {
    const last = state.observations.at(-1), threshold = D.thresholdAt(state.now), fullRain = state.rains.every(r => r?.fresh && r.complete);
    const observed24 = label => state.observedRain?.stations.find(station => station.label === label)?.values?.[4] ?? null;
    const random = window.crypto?.getRandomValues ? window.crypto.getRandomValues(new Uint32Array(1))[0].toString(16) : Math.floor(Math.random() * 0xffffffff).toString(16);
    return D.stormRecord({
      id: new Date().toISOString().replace(/[^0-9A-Za-z]/g, '') + '-' + random,
      savedAt: new Date().toISOString(), tag, note, feedCheckAt: new Date(state.now).toISOString(), gaugeCfs: last?.q ?? null, gaugeTime: last ? new Date(last.t).toISOString() : null,
      change3Cfs: state.change3?.change ?? null, forecastHighCfs: state.fc.usable ? state.fc.max : null, forecastIssue: state.fc.issued === null ? null : new Date(state.fc.issued).toISOString(), forecastHighTime: state.fc.usable && state.fc.firstMax !== null ? new Date(state.fc.firstMax).toISOString() : null,
      riseThresholdCfs: threshold?.cfs ?? null, rain24MeanIn: fullRain ? (state.rains[0].mm + state.rains[1].mm) / 2 / 25.4 : null, rainForecastUpdated1: state.rains[0] ? new Date(state.rains[0].updated).toISOString() : null, rainForecastUpdated2: state.rains[1] ? new Date(state.rains[1].updated).toISOString() : null,
      observedRainIssue: state.observedRain ? new Date(state.observedRain.issued).toISOString() : null, padilla24In: observed24('Padilla Bay Farm'), burlington24In: observed24('Burlington'), sedroWoolley24In: observed24('Sedro-Woolley RAWS'),
      radarProduct: radar.validTime ? RADAR_PRODUCTS[radar.product].label : null, radarValidTime: radar.validTime ? new Date(radar.validTime).toISOString() : null
    });
  }
  function renderStormLog(message = '') {
    const log = readStormLog();
    badge('storm-log-count', log.available ? log.records.length + ' saved' : 'Storage unavailable', log.available ? 'neutral' : 'caution');
    $('storm-log-save').disabled = !log.available || !state;
    $('storm-log-export').disabled = !log.available || !log.records.length;
    $('storm-log-clear').disabled = !log.available || !log.records.length;
    put('storm-log-status', log.available ? message : log.reason);
    if (!log.available) { $('storm-log-list').innerHTML = '<p class="measurement-limit"><strong>Nothing was changed.</strong> Enable browser storage or use Copy snapshot instead.</p>'; return; }
    if (!log.records.length) { $('storm-log-list').innerHTML = '<p>No checks saved in this browser profile.</p>'; return; }
    $('storm-log-list').innerHTML = '<div class="table-wrap" role="region" aria-label="Saved local storm checks" tabindex="0"><table><caption>Manual storm checks saved only in this browser profile, newest first.</caption><thead><tr><th scope="col">Saved</th><th scope="col">Moment / note</th><th scope="col">River</th><th scope="col">Forecast</th><th scope="col"><span class="sr-only">Delete</span></th></tr></thead><tbody>' + log.records.map(record => '<tr><td>' + esc(date(Date.parse(record.savedAt))) + '</td><td><strong>' + esc(record.tag) + '</strong>' + (record.note ? '<br><span>' + esc(record.note) + '</span>' : '') + '</td><td>' + (record.gaugeCfs === null ? 'Unavailable' : num(record.gaugeCfs) + ' cfs') + '<br><span class="meta">3 h: ' + (record.change3Cfs === null ? 'Unavailable' : signed(record.change3Cfs) + ' cfs') + '</span></td><td>' + (record.forecastHighCfs === null ? 'Unavailable' : num(record.forecastHighCfs) + ' cfs') + '<br><span class="meta">Rain: ' + (record.rain24MeanIn === null ? 'Unavailable' : record.rain24MeanIn.toFixed(2) + ' in.') + '</span></td><td><button class="delete-log" type="button" data-delete-log="' + esc(record.id) + '" aria-label="Delete check saved ' + esc(date(Date.parse(record.savedAt))) + '">Delete</button></td></tr>').join('') + '</tbody></table></div>';
  }
  function downloadBlob(contents, type, filename) {
    const blob = new Blob([contents], { type }), url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  }
  function brief() {
    const observedLines = state.observedRain ? state.observedRain.stations.map(station => station.label + ' rolling 24 h: ' + (station.values[4] === null ? 'Unavailable' : station.values[4].toFixed(2) + ' in.')) : ['Nearby observed-rain report unavailable'];
    return ['Samish River Outlook — field-planning snapshot', 'Feed check: ' + date(state.now), '', 'RADAR CONTEXT: ' + $('radar-status').textContent, $('radar-frame-time').textContent, $('radar-product-note').textContent, 'Official KATX radar context; not used in a river, closure or safety calculation.', '', 'SAVED-FORECAST COMPARISON: ' + $('watch-state').textContent, $('watch-title').textContent, $('watch-detail').textContent, $('watch-source').textContent, '', 'Gauge: ' + $('flow').textContent + ' cfs · ' + $('gauge-status').textContent, $('gauge-time').textContent, 'About-24-hour change: ' + $('change24').textContent, 'Near-3-hour change: ' + $('change3').textContent, '', 'SEASONAL RISE COMPARISON: ' + $('rise-status').textContent, $('rise-title').textContent, $('rise-detail').textContent, '', 'NOAA forecast high: ' + $('forecast-high').textContent + ' cfs', $('forecast-time').textContent, $('forecast-coverage').textContent, $('forecast-issue').textContent, $('forecast-revision').textContent, '', $('crest-time').textContent, $('crest-detail').textContent, 'Next 24 h rain, mean of two forecast points: ' + $('rain-total').textContent + ' in. · ' + $('rain-status').textContent, $('rain-note').textContent, ...[...document.querySelectorAll('.rain-point')].map(el => el.innerText), '', 'NEARBY PROVISIONAL OBSERVED RAIN', state.observedRain ? 'Report issued ' + date(state.observedRain.issued) + '; issue time is not a measurement time.' : 'Report unavailable.', ...observedLines, '', 'Tides: Bellingham predictions, ft MLLW; not Samish Bay access clearance.', ...state.tides.map(r => (r.type === 'H' ? 'High ' : 'Low ') + r.v.toFixed(1) + ' ft · ' + date(r.t)), '', 'Official commercial status is not ingested. Check Washington Department of Health.', 'No confirmed crest, dispatch recommendation, closure call, artificial-intelligence warning, all-clear or reopening authorization. Use established procedures; the Department of Health makes closure and reopening decisions.', 'https://doh.wa.gov/commercialshellfishmap', 'https://jdinneen.github.io/samish-river-outlook/'].join('\n');
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
      renderStormLog('Saved this check locally at ' + date(Date.parse(record.savedAt)) + '.');
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
    if (!log.available || !log.records.length || !window.confirm('Clear all saved Samish storm checks from this browser profile? This cannot be undone unless you exported them.')) return;
    try { localStorage.removeItem(STORM_LOG_KEY); if (localStorage.getItem(STORM_LOG_KEY) !== null) throw Error('Clear could not be verified'); renderStormLog('All locally saved storm checks were cleared.'); }
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
    renderStormLog(result.available ? 'One locally saved check was deleted.' : '');
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
  refreshRadar();
  load();
})();
