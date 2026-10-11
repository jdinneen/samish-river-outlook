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
  let state = null, busy = false;
  const sources = [
    { name: 'NOAA river forecast & gauge copy', url: 'https://api.water.noaa.gov/nwps/v1/gauges/smrw1/stageflow' },
    { name: 'USGS Burlington gauge', url: 'https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items?monitoring_location_id=USGS-12201500&parameter_code=00060&time=P3D&f=json&limit=1000' },
    { name: 'NWS rain · grid 136,114', url: 'https://api.weather.gov/gridpoints/SEW/136,114' },
    { name: 'NWS rain · grid 138,111', url: 'https://api.weather.gov/gridpoints/SEW/138,111' },
    { name: 'NOAA Bellingham tide predictions', url: '' }
  ];
  async function fetchFeed(s) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(s.url, { signal: controller.signal, cache: 'no-store' });
      if (!response.ok) throw Error('HTTP ' + response.status);
      return { ...s, data: await response.json(), retrieved: Date.now() };
    } catch (e) { return { ...s, error: e.name === 'AbortError' ? 'Request timed out' : 'Feed could not be retrieved' }; }
    finally { clearTimeout(timer); }
  }
  function parse(feed, fn) {
    if (feed.error) return null;
    try { return fn(feed.data); } catch (e) { feed.error = e.message; return null; }
  }
  async function load() {
    if (busy) return;
    busy = true; $('refresh').disabled = true; $('outlook').setAttribute('aria-busy', 'true');
    put('update-status', 'Refreshing public feeds… Existing readings remain dated while requests finish.');
    try {
    sources[4].url = 'https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions&station=9449211&begin_date=' + new Date().toISOString().slice(0, 10).replaceAll('-', '') + '&range=168&datum=MLLW&units=english&time_zone=gmt&interval=hilo&format=json&application=samish_outlook';
    const feeds = await Promise.all(sources.map(fetchFeed)), now = Date.now();
    // Each series is parsed independently: a malformed forecast must not erase a valid gauge.
    const river = feeds[0], gaugeCopy = { ...river }, observations = parse(gaugeCopy, d => D.nwpsSeries(d.observed, now, true)) || [];
    let rawForecast = [], issue = null;
    if (!river.error) {
      try { rawForecast = D.nwpsSeries(river.data.forecast, now, false); issue = river.data.forecast.issuedTime; }
      catch (e) { river.error = 'Forecast: ' + e.message; }
    }
    const direct = parse(feeds[1], d => D.usgs(d, now)) || [];
    if (!feeds[1].error && !direct.length) feeds[1].error = 'No valid discharge readings';
    const merged = [...new Map([...observations, ...direct].map(r => [r.t, r])).values()].sort((a, b) => a.t - b.t);
    const fc = D.forecast(rawForecast, issue, now);
    const rains = [2, 3].map(i => { const r = parse(feeds[i], d => D.rain(d, now)); return r ? { ...r, ...D.rainWindow(r, now, 24), fresh: now - r.updated <= 24 * H } : null; });
    const tides = (parse(feeds[4], D.tides) || []).filter(r => r.t >= now).slice(0, 4);
    if (!feeds[4].error && !tides.length) feeds[4].error = 'No upcoming high or low tides';
    state = { now, feeds, observations: merged, direct, gaugeCopy, fc, rains, tides };
    render();
    } catch {
      state = { now: Date.now(), feeds: sources.map(s => ({ ...s, error: 'Unexpected feed processing error' })), observations: [], direct: [], gaugeCopy: { error: 'Unavailable' }, fc: { usable: false, reason: 'Forecast processing unavailable', issued: null, rows: [] }, rains: [null, null], tides: [] };
      render();
    } finally { busy = false; $('refresh').disabled = false; $('outlook').setAttribute('aria-busy', 'false'); }
  }
  function render() {
    const { now, feeds, observations, direct, gaugeCopy, fc, rains, tides } = state, last = observations.at(-1);
    put('update-status', 'Feed check completed ' + date(now) + ' · Refreshes every 10 minutes while this page is visible.');
    const problems = [];
    if (!last || now - last.t > 2 * H) problems.push('The gauge is ' + (last ? 'stale' : 'unavailable'));
    if (!fc.usable) problems.push('the river forecast is unavailable');
    if (!rains.every(r => r?.fresh && r.complete)) problems.push('the rain summary is incomplete');
    if (!tides.length) problems.push('tide predictions are unavailable');
    $('feed-alert').hidden = !problems.length;
    put('feed-alert', problems.join('; ') + (problems.length ? '. Check the dated source details before planning.' : ''));
    put('gauge-heading', last && now - last.t > 2 * H ? 'Last river reading' : 'River now');
    put('flow', num(last?.q));
    badge('gauge-status', last ? (now - last.t <= 2 * H ? 'Recent observation' : 'Stale observation') : 'Unavailable', last && now - last.t <= 2 * H ? 'good' : 'caution');
    put('gauge-time', last ? 'Last reading · ' + date(last.t) : 'No valid gauge reading retrieved');
    put('observation-note', 'USGS 12201500 · provisional observations' + (last ? ' · ' + last.source : ''));
    for (const hours of [24, 3]) {
      const prev = last && D.atBefore(observations, last.t - hours * H);
      put('change' + hours, prev ? (last.q - prev.q > 0 ? '+' : '') + num(last.q - prev.q) + ' cfs' : 'Unavailable');
    }
    badge('forecast-status', fc.usable ? (fc.complete ? 'Up to 72 h' : 'Shorter horizon') : 'Unavailable', fc.usable ? 'neutral' : 'caution');
    put('forecast-high', fc.usable ? num(fc.max) : '—');
    put('forecast-time', !fc.usable ? fc.reason : fc.atStart && fc.atEnd ? 'Highest value occurs at both ends of the available window' : fc.atEnd ? 'Highest at the end · peak may be later' : fc.atStart ? 'Highest at the start of this forecast window' : 'Forecast high around ' + date(fc.firstMax));
    put('forecast-coverage', fc.usable ? 'Available through ' + date(fc.end) + ' · ' + num(fc.hours) + ' h from this check.' + (fc.firstMax !== fc.lastMax ? ' The highest value occurs at more than one forecast time.' : '') : 'No forecast high or timing estimate is shown.');
    put('forecast-issue', fc.issued === null ? 'Issue time unavailable' : 'NOAA issued · ' + date(fc.issued));
    const fullRain = rains.every(r => r?.fresh && r.complete);
    badge('rain-status', fullRain ? 'Full 24 h coverage' : 'Incomplete / unavailable', fullRain ? 'neutral' : 'caution');
    put('rain-total', fullRain ? inches(rains[0].mm / 2 + rains[1].mm / 2) : '—');
    put('rain-note', 'Mean of two selected NWS grid points for the 24 hours from ' + date(now) + '.');
    $('rain-points').innerHTML = rains.map((r, i) => '<div class="rain-point"><strong><span>Grid ' + (i ? '138,111' : '136,114') + '</span><span>' + (r?.fresh && r.complete ? esc(inches(r.mm)) + ' in.' : 'Unavailable') + '</span></strong><small>' + (r ? (r.fresh ? '' : 'Stale · ') + 'Updated ' + esc(date(r.updated)) + ' · ' + num(r.coveredHours) + '/24 h covered' : 'Feed unavailable') + '</small></div>').join('');
    badge('tide-status', tides.length ? 'Predicted' : 'Unavailable', tides.length ? 'neutral' : 'caution');
    $('tide-list').innerHTML = tides.length ? tides.map(r => '<div class="tide-row"><span>' + (r.type === 'H' ? 'High' : 'Low') + '</span><strong>' + r.v.toFixed(1) + '<span class="small-label">ft MLLW</span></strong><time datetime="' + new Date(r.t).toISOString() + '">' + esc(date(r.t)) + '</time></div>').join('') : 'No upcoming predictions retrieved. Use the official tide source.';
    const directLast = [...direct].sort((a, b) => a.t - b.t).at(-1);
    const sourceTimes = [(fc.issued === null ? 'Forecast issue time unavailable' : 'Forecast issued ' + date(fc.issued)) + (gaugeCopy.error ? ' · Gauge copy: ' + gaugeCopy.error : ''), directLast ? 'Latest direct USGS reading ' + date(directLast.t) : 'No direct USGS reading', ...rains.map(r => r ? 'Forecast updated ' + date(r.updated) : 'Update unavailable'), 'Astronomical high/low predictions; issue time not supplied'];
    $('source-status').innerHTML = feeds.map((f, i) => '<article class="card source-card"><h2>' + esc(f.name) + '</h2><span class="pill ' + (f.error ? 'caution' : 'neutral') + '">' + (f.error ? 'Feed problem' : 'Retrieved') + '</span><p class="detail">' + esc(sourceTimes[i]) + '</p><p class="meta">' + esc(f.error || 'Retrieved ' + date(f.retrieved)) + '</p><a href="' + esc(f.url) + '" target="_blank" rel="noopener">Inspect public feed ↗</a></article>').join('');
    $('forecast-table').innerHTML = fc.usable ? '<table><caption>Available NOAA forecast; first and last values may be interpolated within supported intervals.</caption><thead><tr><th scope="col">Pacific time</th><th scope="col">Flow (cfs)</th></tr></thead><tbody>' + fc.rows.map(r => '<tr><td>' + esc(date(r.t)) + '</td><td>' + num(r.q) + '</td></tr>').join('') + '</tbody></table>' : '<p>No usable river forecast. No values have been extrapolated.</p>';
    const recent = observations.filter(r => r.t >= now - 48 * H).slice().reverse();
    $('observed-table').innerHTML = recent.length ? '<table><caption>Provisional USGS observations from the past 48 hours, newest first.</caption><thead><tr><th scope="col">Pacific time</th><th scope="col">Flow (cfs)</th><th scope="col">Retrieved via</th></tr></thead><tbody>' + recent.map(r => '<tr><td>' + esc(date(r.t)) + '</td><td>' + num(r.q) + '</td><td>' + esc(r.source) + '</td></tr>').join('') + '</tbody></table>' : '<p>No observations retrieved for the past 48 hours.</p>';
    $('copy-brief').disabled = false; $('brief-fallback').hidden = true; put('copy-status', '');
    chart();
  }
  function chart() {
    if (!state) return;
    const { now, observations, fc } = state, start = now - 48 * H, end = now + 72 * H;
    const obs = observations.filter(r => r.t >= start), future = fc.usable ? fc.rows : [], all = [...obs, ...future];
    if (!all.length) { $('flow-chart').className = 'chart-empty'; put('flow-chart', 'River data unavailable. Check the official sources.'); return; }
    const w = Math.max(230, $('flow-chart').clientWidth), h = 280, l = 49, right = 13, top = 22, bottom = 44;
    const max = Math.max(1, ...all.map(r => r.q)) * 1.15, x = t => l + (t - start) / (end - start) * (w - l - right), y = q => top + (1 - q / max) * (h - top - bottom);
    const paths = (rows, gap, color, dashed) => {
      const groups = []; rows.forEach((r, i) => { if (!i || r.t - rows[i - 1].t > gap) groups.push([]); groups.at(-1).push(r); });
      return groups.map(g => g.length === 1 ? '<circle cx="' + x(g[0].t) + '" cy="' + y(g[0].q) + '" r="3" fill="' + color + '"/>' : '<path d="' + g.map((r, i) => (i ? 'L' : 'M') + x(r.t).toFixed(2) + ',' + y(r.q).toFixed(2)).join(' ') + '" fill="none" stroke="' + color + '" stroke-width="2.5"' + (dashed ? ' stroke-dasharray="7 5"' : '') + '/>').join('');
    };
    const desc = 'Flow in cubic feet per second. Observations cover the previous 48 hours where available. ' + (fc.usable ? 'NOAA forecast extends ' + num(fc.hours) + ' hours from this check; highest forecast value is ' + num(fc.max) + ' cfs.' : 'NOAA forecast unavailable.');
    let svg = '<svg viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-labelledby="flow-title flow-desc"><title id="flow-title">Samish river flow</title><desc id="flow-desc">' + esc(desc) + '</desc>';
    for (let i = 0; i <= 4; i++) { const q = max * i / 4; svg += '<line x1="' + l + '" x2="' + (w - right) + '" y1="' + y(q) + '" y2="' + y(q) + '" stroke="var(--line)"/><text x="' + (l - 7) + '" y="' + (y(q) + 4) + '" text-anchor="end">' + Math.round(q).toLocaleString('en-US') + '</text>'; }
    svg += '<text x="' + l + '" y="13">cfs</text><line x1="' + x(now) + '" x2="' + x(now) + '" y1="' + top + '" y2="' + (h - bottom) + '" stroke="var(--muted)" stroke-dasharray="3 4"/>';
    const ticks = w < 500 ? [[start, '−48 h'], [now, '0 h'], [end, '+72 h']] : [[start, '−48 h'], [now - 24 * H, '−24 h'], [now, 'Check time'], [now + 24 * H, '+24 h'], [now + 48 * H, '+48 h'], [end, '+72 h']];
    for (let i = 0; i < ticks.length; i++) svg += '<text x="' + x(ticks[i][0]) + '" y="' + (h - 16) + '" text-anchor="' + (i === 0 ? 'start' : i === ticks.length - 1 ? 'end' : 'middle') + '">' + ticks[i][1] + '</text>';
    svg += paths(obs, 2 * H, 'var(--teal)', false) + paths(future, 6 * H, 'var(--navy)', true) + '</svg>';
    $('flow-chart').className = ''; $('flow-chart').innerHTML = svg;
  }
  function brief() {
    return ['Samish River Outlook — field planning only', 'Feed check: ' + date(state.now), 'Gauge: ' + $('flow').textContent + ' cfs · ' + $('gauge-status').textContent, $('gauge-time').textContent, 'NOAA forecast high: ' + $('forecast-high').textContent + ' cfs', $('forecast-time').textContent, $('forecast-coverage').textContent, $('forecast-issue').textContent, 'Next 24 h rain, two-point mean: ' + $('rain-total').textContent + ' in. · ' + $('rain-status').textContent, $('rain-note').textContent, ...[...document.querySelectorAll('.rain-point')].map(el => el.innerText), 'Tides: Bellingham predictions, ft MLLW; not Samish Bay access clearance.', ...state.tides.map(r => (r.type === 'H' ? 'High ' : 'Low ') + r.v.toFixed(1) + ' ft · ' + date(r.t)), 'No confirmed crest, dispatch recommendation, AI warning or reopening authorization. Use established sampling procedures; DOH makes closure/reopening decisions.', 'https://jdinneen.github.io/samish-river-outlook/'].join('\n');
  }
  $('copy-brief').addEventListener('click', async () => {
    const text = brief();
    try { await navigator.clipboard.writeText(text); put('copy-status', 'Field brief copied, including source times and limits.'); }
    catch { $('brief-fallback').value = text; $('brief-fallback').hidden = false; $('brief-fallback').focus(); $('brief-fallback').select(); put('copy-status', 'Select and copy the brief below.'); }
  });
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  function select(tab) { for (const t of tabs) { const active = t === tab; t.setAttribute('aria-selected', String(active)); t.tabIndex = active ? 0 : -1; $(t.getAttribute('aria-controls')).hidden = !active; } if (tab.id === 'tab-outlook') chart(); }
  for (const tab of tabs) { tab.addEventListener('click', () => select(tab)); tab.addEventListener('keydown', e => { let i = tabs.indexOf(tab); if (e.key === 'ArrowRight') i = (i + 1) % tabs.length; else if (e.key === 'ArrowLeft') i = (i + tabs.length - 1) % tabs.length; else if (e.key === 'Home') i = 0; else if (e.key === 'End') i = tabs.length - 1; else return; e.preventDefault(); select(tabs[i]); tabs[i].focus(); }); }
  $('refresh').addEventListener('click', load);
  new ResizeObserver(() => { if (!$('outlook').hidden) chart(); }).observe($('flow-chart'));
  setInterval(() => { if (!document.hidden) load(); }, 10 * 60 * 1000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && state && Date.now() - state.now > 10 * 60 * 1000) load(); });
  load();
})();
