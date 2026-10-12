(function (root) {
  'use strict';
  const H = 3600000;
  const THRESHOLDS = Object.freeze([
    Object.freeze({ label: 'November–February', months: Object.freeze([11, 12, 1, 2]), cfs: 400 }),
    Object.freeze({ label: 'March–April', months: Object.freeze([3, 4]), cfs: 200 }),
    Object.freeze({ label: 'May–October', months: Object.freeze([5, 6, 7, 8, 9, 10]), cfs: 100 })
  ]);
  const WATCH = Object.freeze({ minimumAgeHours: 3, maximumAgeHours: 36, maximumGapHours: 12, seasonalFraction: 0.1, retentionDays: 14 });
  function number(v) {
    if ((typeof v !== 'number' && typeof v !== 'string') || (typeof v === 'string' && !/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(v.trim()))) return null;
    const n = Number(v); return Number.isFinite(n) ? n : null;
  }
  function time(v) {
    if (typeof v !== 'string') return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,9})?)?(Z|[+-]\d{2}:\d{2})$/.exec(v);
    if (!m || +m[2] < 1 || +m[2] > 12 || +m[3] < 1 || +m[3] > new Date(Date.UTC(+m[1], +m[2], 0)).getUTCDate() || +m[4] > 23 || +m[5] > 59 || +(m[6] || 0) > 59) return null;
    const t = Date.parse(v); return Number.isFinite(t) ? t : null;
  }
  function factor(u) { return new Map([['cfs', 1], ['kcfs', 1000], ['ft3/s', 1], ['ft^3/s', 1]]).get(String(u).toLowerCase()) ?? null; }
  function rejectDuplicateTimes(rows, label) {
    const sorted = [...rows].sort((a, b) => a.t - b.t);
    if (sorted.some((r, i) => i && r.t === sorted[i - 1].t)) throw Error(label + ' contains duplicate timestamps');
    return sorted;
  }
  function nwpsSeries(s, now, observed) {
    if (!s || !Array.isArray(s.data)) throw Error('River series missing');
    const key = ['primary', 'secondary'].find(k => String(s[k + 'Name'] || '').trim().toLowerCase() === 'river discharge' && factor(s[k + 'Units']) !== null);
    if (!key) throw Error('Discharge units not recognized');
    const scale = factor(s[key + 'Units']);
    const rows = s.data.map(r => ({ t: time(r.validTime), q: number(r[key]), source: 'NOAA copy of USGS' }))
      .filter(r => r.t !== null && r.q !== null && r.q >= 0 && (!observed || r.t <= now))
      .map(r => ({ ...r, q: r.q * scale })).filter(r => Number.isFinite(r.q));
    return rejectDuplicateTimes(rows, 'River series');
  }
  function usgs(d, now) {
    if (!Array.isArray(d?.features)) throw Error('Gauge response not recognized');
    const rows = d.features.map(f => f.properties || {}).filter(p => p.parameter_code === '00060' && p.monitoring_location_id === 'USGS-12201500')
      .map(p => ({ t: time(p.time), q: number(p.value), scale: factor(p.unit_of_measure), source: 'USGS direct' }))
      .filter(r => r.t !== null && r.t <= now && r.q !== null && r.q >= 0 && r.scale !== null)
      .map(r => ({ t: r.t, q: r.q * r.scale, source: r.source })).filter(r => Number.isFinite(r.q));
    return rejectDuplicateTimes(rows, 'Gauge series');
  }
  function duration(s) {
    const m = /^P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$/.exec(s || '');
    if (!m || !m.slice(1).some(Boolean) || s.endsWith('T')) return null;
    const v = ((Number(m[1] || 0) * 24 + Number(m[2] || 0)) * 3600 + Number(m[3] || 0) * 60 + Number(m[4] || 0)) * 1000;
    return Number.isFinite(v) && v > 0 ? v : null;
  }
  function rain(d, now) {
    const p = d?.properties, q = p?.quantitativePrecipitation;
    const scale = q?.uom === 'wmoUnit:mm' ? 1 : null;
    const updated = time(p?.updateTime);
    if (scale === null || !Array.isArray(q?.values) || updated === null || updated > now) throw Error('Rain units or update time not recognized');
    const rows = q.values.map(r => {
      const parts = String(r.validTime).split('/'), [start, span] = parts;
      const t = time(start), len = duration(span), v = number(r.value);
      const mm = v === null ? null : v * scale;
      // 1,000 mm/hour is a corruption ceiling, not a weather threshold. It is
      // deliberately far above credible local rainfall and prevents malformed
      // finite numbers from becoming operational displays.
      const maximum = len === null ? null : len / H * 1000;
      return { t, end: parts.length !== 2 || t === null || len === null ? null : t + len, mm: mm === null || mm < 0 || !Number.isFinite(mm) || maximum === null || mm > maximum ? null : mm };
    }).filter(r => r.t !== null && r.end !== null && Number.isFinite(r.end) && r.end <= 8640000000000000).sort((a, b) => a.t - b.t);
    if (rows.some((r, i) => i && r.t < rows[i - 1].end)) throw Error('Overlapping rain intervals');
    return { rows, updated };
  }
  function rainWindow(s, start, hours) {
    let mm = 0, covered = 0;
    for (const r of s?.rows || []) {
      const overlap = Math.max(0, Math.min(start + hours * H, r.end) - Math.max(start, r.t));
      if (r.mm !== null && overlap) { mm += r.mm * (overlap / (r.end - r.t)); covered += overlap; }
    }
    return { mm: Number.isFinite(mm) ? mm : null, coveredHours: covered / H, complete: Number.isFinite(mm) && Math.abs(covered - hours * H) < 1000 };
  }
  function rainBins(s, start, hours = 36, binHours = 6) {
    if (!s || !Array.isArray(s.rows) || !Number.isFinite(start) || !Number.isFinite(hours) || !Number.isFinite(binHours) || hours <= 0 || binHours <= 0 || hours % binHours !== 0) return [];
    const bins = [];
    for (let offset = 0; offset < hours; offset += binHours) {
      const t = start + offset * H, end = t + binHours * H;
      let mm = 0, covered = 0;
      for (const row of s.rows) {
        const overlap = Math.max(0, Math.min(end, row.end) - Math.max(t, row.t));
        if (row.mm !== null && overlap) {
          mm += row.mm * overlap / (row.end - row.t);
          covered += overlap;
        }
      }
      const complete = Math.abs(covered - binHours * H) < 1000;
      bins.push({ t, end, mm: complete && Number.isFinite(mm) ? mm : null, coveredHours: covered / H, complete });
    }
    return bins;
  }
  function rrmProductId(d, now) {
    if (!Array.isArray(d?.['@graph']) || !Number.isFinite(now)) throw Error('Rain-report index not recognized');
    const rows = d['@graph'].map(row => ({ id: typeof row?.id === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(row.id) ? row.id : null, issued: time(row?.issuanceTime) }))
      .filter(row => row.id && row.issued !== null && row.issued <= now && now - row.issued <= 24 * H)
      .sort((a, b) => b.issued - a.issued);
    if (!rows.length) throw Error('No recent Seattle rain report was indexed');
    return rows[0];
  }
  const RRM_STATIONS = Object.freeze([
    Object.freeze({ source: 'Padilla Bay Farm', label: 'Padilla Bay Farm' }),
    Object.freeze({ source: 'Burlington', label: 'Burlington' }),
    Object.freeze({ source: 'Sedro Wooley RAWS', label: 'Sedro-Woolley RAWS' })
  ]);
  function rrmRain(d, now, expectedIssue) {
    if (!d || typeof d.productText !== 'string' || d.productText.length > 200000 || !Number.isFinite(now)) throw Error('Rain report not recognized');
    const issued = time(d.issuanceTime);
    if (issued === null || issued > now || now - issued > 24 * H) throw Error('Rain-report issue time unavailable, stale, or future-dated');
    if (expectedIssue !== undefined && (!Number.isFinite(expectedIssue) || issued !== expectedIssue)) throw Error('Rain-report issue does not match the selected index entry');
    if (d.productCode !== undefined && d.productCode !== 'RRM') throw Error('Unexpected rain-report product');
    if (d.issuingOffice !== undefined && d.issuingOffice !== 'KSEW') throw Error('Unexpected rain-report office');
    if (!/(?:^|\n)RRMSEW\s*(?:\r?\n)/.test(d.productText) || !/National Weather Service Seattle WA/.test(d.productText)) throw Error('Seattle rain-report identity not found');
    const lines = d.productText.replace(/\r/g, '').split('\n');
    const maxima = [8, 15, 25, 35, 50, 80, 100];
    const stations = RRM_STATIONS.map(station => {
      const line = lines.find(value => value.startsWith(station.source) && (value.length === station.source.length || /\s/.test(value[station.source.length])));
      if (!line) return { label: station.label, sourceLabel: station.source, available: false, reason: 'Station row missing', values: Array(7).fill(null) };
      const tokens = line.slice(station.source.length).trim().split(/\s+/);
      if (tokens.length !== 7) return { label: station.label, sourceLabel: station.source, available: false, reason: 'Station row malformed', values: Array(7).fill(null) };
      const values = tokens.map((token, index) => {
        if (token === 'M' || token === 'MSG') return null;
        const value = number(token);
        return value !== null && value >= 0 && value <= maxima[index] ? value : NaN;
      });
      if (values.some(Number.isNaN)) return { label: station.label, sourceLabel: station.source, available: false, reason: 'Station row failed range checks', values: Array(7).fill(null) };
      const present = values.filter(value => value !== null);
      if (present.some((value, index) => index && value + 1e-9 < present[index - 1])) return { label: station.label, sourceLabel: station.source, available: false, reason: 'Accumulation windows were not internally consistent', values: Array(7).fill(null) };
      return { label: station.label, sourceLabel: station.source, available: values.some(value => value !== null), reason: values.some(value => value !== null) ? null : 'All values missing', values };
    });
    return { issued, fresh: now - issued <= 2 * H, stations, windows: [1, 3, 6, 12, 24, 48, 72] };
  }
  function ringMetrics(ring, label) {
    if (!Array.isArray(ring) || ring.length < 4) throw Error(label + ' ring malformed');
    const clean = ring.map(point => {
      if (!Array.isArray(point) || point.length < 2) throw Error(label + ' coordinate malformed');
      const lon = number(point[0]), lat = number(point[1]);
      if (lon === null || lat === null || lon < -125 || lon > -120 || lat < 46 || lat > 50) throw Error(label + ' coordinate outside the expected region');
      return [lon, lat];
    });
    if (clean[0][0] !== clean.at(-1)[0] || clean[0][1] !== clean.at(-1)[1]) throw Error(label + ' ring is not closed');
    const distinct = new Set(clean.slice(0, -1).map(point => point[0] + ',' + point[1]));
    if (distinct.size < 3) throw Error(label + ' ring is degenerate');
    const orientation = (a, b, c) => {
      const cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
      return Math.abs(cross) < 1e-12 ? 0 : Math.sign(cross);
    };
    const onSegment = (a, b, p) => p[0] >= Math.min(a[0], b[0]) - 1e-12 && p[0] <= Math.max(a[0], b[0]) + 1e-12 && p[1] >= Math.min(a[1], b[1]) - 1e-12 && p[1] <= Math.max(a[1], b[1]) + 1e-12;
    const intersects = (a, b, c, d) => {
      const o1 = orientation(a, b, c), o2 = orientation(a, b, d), o3 = orientation(c, d, a), o4 = orientation(c, d, b);
      return (o1 * o2 < 0 && o3 * o4 < 0) || (o1 === 0 && onSegment(a, b, c)) || (o2 === 0 && onSegment(a, b, d)) || (o3 === 0 && onSegment(c, d, a)) || (o4 === 0 && onSegment(c, d, b));
    };
    const edgeCount = clean.length - 1;
    for (let i = 0; i < edgeCount; i++) {
      for (let j = i + 1; j < edgeCount; j++) {
        if (j === i + 1 || (i === 0 && j === edgeCount - 1)) continue;
        if (intersects(clean[i], clean[i + 1], clean[j], clean[j + 1])) throw Error(label + ' ring self-intersects');
      }
    }
    let twiceArea = 0, cxNumerator = 0, cyNumerator = 0;
    for (let i = 0; i < clean.length - 1; i++) {
      const a = clean[i], b = clean[i + 1], cross = a[0] * b[1] - b[0] * a[1];
      twiceArea += cross;
      cxNumerator += (a[0] + b[0]) * cross;
      cyNumerator += (a[1] + b[1]) * cross;
    }
    if (!Number.isFinite(twiceArea) || Math.abs(twiceArea) < 1e-12) throw Error(label + ' ring has zero area');
    const lon = cxNumerator / (3 * twiceArea), lat = cyNumerator / (3 * twiceArea);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) throw Error(label + ' centroid unavailable');
    return { clean, lon, lat };
  }
  function basinGeometry(d) {
    if (!Array.isArray(d?.features) || d.features.length !== 1) throw Error('Basin response not recognized');
    const geometry = d.features[0]?.geometry;
    const polygons = geometry?.type === 'Polygon' ? [geometry.coordinates] : geometry?.type === 'MultiPolygon' ? geometry.coordinates : null;
    if (!Array.isArray(polygons) || !polygons.length) throw Error('Basin geometry unavailable');
    let pointCount = 0;
    const rings = [];
    for (const polygon of polygons) {
      if (!Array.isArray(polygon) || !polygon.length) throw Error('Basin polygon malformed');
      for (const ring of polygon) {
        const clean = ringMetrics(ring, 'Basin').clean;
        pointCount += clean.length;
        if (pointCount > 5000) throw Error('Basin geometry is unexpectedly large');
        rings.push(clean);
      }
    }
    return { rings, pointCount };
  }
  function gaugePoint(d) {
    if (!Array.isArray(d?.features)) return null;
    const feature = d.features.find(item => item?.properties?.monitoring_location_id === 'USGS-12201500' && item?.geometry?.type === 'Point');
    const coordinates = feature?.geometry?.coordinates;
    if (!Array.isArray(coordinates) || coordinates.length < 2) return null;
    const lon = number(coordinates[0]), lat = number(coordinates[1]);
    return lon !== null && lat !== null && lon >= -125 && lon <= -120 && lat >= 46 && lat <= 50 ? { lon, lat } : null;
  }
  function gridPoint(d) {
    const coordinates = d?.geometry?.type === 'Polygon' ? d.geometry.coordinates?.[0] : null;
    try {
      const metrics = ringMetrics(coordinates, 'Forecast grid');
      return { lon: metrics.lon, lat: metrics.lat };
    } catch { return null; }
  }
  function radarCapabilities(xmlText, now) {
    if (typeof xmlText !== 'string' || xmlText.length > 2000000 || !Number.isFinite(now) || typeof DOMParser === 'undefined') throw Error('Radar capabilities unavailable');
    const document = new DOMParser().parseFromString(xmlText, 'application/xml');
    if (document.getElementsByTagName('parsererror').length) throw Error('Radar capabilities malformed');
    const wanted = ['katx_sr_bref', 'katx_boha', 'katx_bdsa'], result = {};
    const children = (node, localName) => [...node.children].filter(child => child.localName === localName);
    for (const layer of [...document.getElementsByTagNameNS('*', 'Layer')]) {
      const name = children(layer, 'Name')[0]?.textContent?.trim();
      if (!wanted.includes(name)) continue;
      const dimension = children(layer, 'Dimension').find(node => node.getAttribute('name') === 'time');
      const times = [...new Set(String(dimension?.textContent || '').split(',').map(value => time(value.trim())).filter(value => value !== null && value <= now && now - value <= 6 * H))].sort((a, b) => a - b);
      if (times.length) result[name] = { times, latest: times.at(-1) };
    }
    if (wanted.some(name => !result[name])) throw Error('A required KATX radar product is missing or stale');
    return result;
  }
  function csvCell(value) {
    let text = value === null || value === undefined ? '' : String(value);
    if (/^[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }
  const STORM_TAGS = Object.freeze(['Storm check', 'Before bed', 'Morning check', 'Other']);
  function stormRecord(input) {
    if (!input || !Number.isFinite(time(input.savedAt)) || !Number.isFinite(time(input.feedCheckAt)) || typeof input.id !== 'string' || !/^[A-Za-z0-9_.:-]{1,100}$/.test(input.id) || !STORM_TAGS.includes(input.tag)) throw Error('Storm record identity is invalid');
    const note = typeof input.note === 'string' ? input.note.trim() : '';
    if (note.length > 240) throw Error('Storm record note is too long');
    const numeric = ['gaugeCfs', 'change3Cfs', 'forecastHighCfs', 'riseThresholdCfs', 'rain24MeanIn', 'padilla24In', 'burlington24In', 'sedroWoolley24In'];
    const record = { schema: 1, id: input.id, savedAt: input.savedAt, tag: input.tag, note, feedCheckAt: input.feedCheckAt };
    for (const key of numeric) {
      const missing = input[key] === null || input[key] === undefined, value = missing ? null : number(input[key]);
      if (!missing && value === null) throw Error('Storm record number is invalid');
      if (value !== null && (key !== 'change3Cfs' && value < 0)) throw Error('Storm record number is invalid');
      record[key] = value;
    }
    for (const key of ['gaugeTime', 'forecastIssue', 'forecastHighTime', 'rainForecastUpdated1', 'rainForecastUpdated2', 'observedRainIssue', 'radarValidTime']) {
      const value = input[key] === null || input[key] === undefined ? null : input[key];
      if (value !== null && time(value) === null) throw Error('Storm record time is invalid');
      record[key] = value;
    }
    record.radarProduct = typeof input.radarProduct === 'string' && input.radarProduct.length <= 80 ? input.radarProduct : null;
    return record;
  }
  function stormCsv(records) {
    if (!Array.isArray(records)) throw Error('Storm records are invalid');
    const columns = [
      ['saved_at', 'savedAt'], ['moment', 'tag'], ['note', 'note'], ['feed_check_at', 'feedCheckAt'], ['gauge_cfs', 'gaugeCfs'], ['gauge_time', 'gaugeTime'], ['change_3h_cfs', 'change3Cfs'], ['noaa_forecast_high_cfs', 'forecastHighCfs'], ['noaa_forecast_issue', 'forecastIssue'], ['forecast_high_time', 'forecastHighTime'], ['seasonal_rise_cfs', 'riseThresholdCfs'], ['forecast_rain_24h_mean_in', 'rain24MeanIn'], ['rain_grid_136_114_updated', 'rainForecastUpdated1'], ['rain_grid_139_116_updated', 'rainForecastUpdated2'], ['observed_rain_report_issue', 'observedRainIssue'], ['padilla_24h_in', 'padilla24In'], ['burlington_24h_in', 'burlington24In'], ['sedro_woolley_24h_in', 'sedroWoolley24In'], ['radar_product', 'radarProduct'], ['radar_valid_time', 'radarValidTime']
    ];
    const clean = records.map(stormRecord);
    return [columns.map(column => csvCell(column[0])).join(','), ...clean.map(record => columns.map(column => csvCell(record[column[1]])).join(','))].join('\r\n') + '\r\n';
  }
  function interpolate(rows, t) {
    if (!rows.length || t < rows[0].t || t > rows.at(-1).t) return null;
    for (let i = 0; i < rows.length; i++) {
      if (rows[i].t === t) return rows[i].q;
      if (rows[i].t > t) { const a = rows[i - 1], b = rows[i]; return b.t - a.t <= 6 * H ? a.q + (b.q - a.q) * (t - a.t) / (b.t - a.t) : null; }
    }
    return null;
  }
  function atBefore(rows, t, tolerance = H / 2) {
    for (let i = rows.length - 1; i >= 0; i--) if (rows[i].t <= t) return t - rows[i].t <= tolerance ? rows[i] : null;
    return null;
  }
  function thresholdAt(t) {
    if (!Number.isFinite(t)) return null;
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', month: 'numeric' }).formatToParts(new Date(t));
    const month = Number(parts.find(p => p.type === 'month')?.value);
    const value = THRESHOLDS.find(r => r.months.includes(month));
    return value ? { label: value.label, cfs: value.cfs } : null;
  }
  function path(rows) {
    if (!Array.isArray(rows)) return null;
    const clean = rows.map(r => ({ t: Number(r?.t), q: number(r?.q) }))
      .filter(r => Number.isFinite(r.t) && r.q !== null && r.q >= 0).sort((a, b) => a.t - b.t);
    if (clean.length < 2 || clean.some((r, i) => i && r.t <= clean[i - 1].t)) return null;
    return clean;
  }
  function interpolateGap(rows, t, maximumGapHours = 6) {
    const clean = path(rows);
    if (!clean || !Number.isFinite(t) || t < clean[0].t || t > clean.at(-1).t) return null;
    const exact = clean.find(r => r.t === t);
    if (exact) return { q: exact.q, before: exact.t, after: exact.t, gapHours: 0 };
    for (let i = 1; i < clean.length; i++) {
      const a = clean[i - 1], b = clean[i];
      if (t <= a.t || t >= b.t) continue;
      const gapHours = (b.t - a.t) / H;
      if (gapHours > maximumGapHours) return null;
      return { q: a.q + (b.q - a.q) * (t - a.t) / (b.t - a.t), before: a.t, after: b.t, gapHours };
    }
    return null;
  }
  function recentChange(rows, latest, hours, now) {
    if (!latest || !Number.isFinite(latest.t) || !Number.isFinite(latest.q) || !Number.isFinite(now) || latest.t > now || now - latest.t > 2 * H) return null;
    const clean = path(rows);
    if (!clean || !Number.isFinite(hours) || hours <= 0) return null;
    const before = clean.filter(r => r.t < latest.t)
      .map(r => ({ row: r, spanHours: (latest.t - r.t) / H }))
      .filter(r => r.spanHours >= hours - 0.5 && r.spanHours <= hours + 0.5)
      .sort((a, b) => Math.abs(a.spanHours - hours) - Math.abs(b.spanHours - hours) || b.row.t - a.row.t)[0];
    if (!before) return null;
    return { change: latest.q - before.row.q, spanHours: before.spanHours, before: before.row };
  }
  function planningScreen(observationRows, forecastRows, now) {
    const observations = path(observationRows);
    const forecastPath = path(forecastRows);
    const unavailable = reason => ({ usable: false, reason, alignedRows: [] });
    if (!observations || !forecastPath || !Number.isFinite(now)) return unavailable('Complete gauge and forecast paths are required');
    const latest = observations.at(-1);
    if (now - latest.t > 2 * H || latest.t > now) return unavailable('The latest gauge reading is stale or future-dated');
    const historyStart = latest.t - 24 * H;
    const historyBoundary = interpolateGap(observations, historyStart, 1);
    if (!historyBoundary) return unavailable('A complete 24-hour gauge history is required');
    const recent = [{ t: historyStart, q: historyBoundary.q }, ...observations.filter(r => r.t > historyStart && r.t <= latest.t)];
    if (recent.some((r, i) => i && r.t - recent[i - 1].t > H)) return unavailable('The gauge history contains a gap over one hour');
    let handoffTime = latest.t, rawHandoff = interpolateGap(forecastPath, handoffTime, 6);
    if (!rawHandoff && now - latest.t <= H / 2) { handoffTime = now; rawHandoff = interpolateGap(forecastPath, handoffTime, 6); }
    if (!rawHandoff) return unavailable('The forecast cannot be aligned near the latest gauge reading');
    const adjustment = latest.q - rawHandoff.q;
    const alignedRows = [{ t: latest.t, q: latest.q }, ...forecastPath.filter(r => r.t > latest.t && r.t <= now + 72 * H)
      .map(r => ({ t: r.t, q: r.q + adjustment }))];
    if (alignedRows.some(r => !Number.isFinite(r.q) || r.q < 0)) return unavailable('Gauge alignment produced an invalid flow');
    if (alignedRows.at(-1).t < now + 60 * H) return unavailable('At least 60 hours of forecast reach are required');
    if (alignedRows.some((r, i) => i && r.t - alignedRows[i - 1].t > 6 * H)) return unavailable('The aligned forecast contains a gap over six hours');
    const combined = [...recent.map(r => ({ ...r, source: 'observed' })), ...alignedRows.filter(r => r.t > latest.t).map(r => ({ ...r, source: 'gauge-aligned forecast' }))]
      .sort((a, b) => a.t - b.t);
    const candidates = [];
    for (const candidate of combined.filter(r => r.t >= latest.t)) {
      const windowStart = candidate.t - 24 * H;
      const boundary = interpolateGap(combined, windowStart, 6);
      if (!boundary) continue;
      const prior = [{ t: windowStart, q: boundary.q, source: '24-hour boundary' }, ...combined.filter(r => r.t < candidate.t && r.t > windowStart)];
      const baseline = prior.reduce((best, r) => r.q < best.q ? r : best);
      const threshold = thresholdAt(candidate.t);
      if (!threshold) continue;
      const rise = Math.max(0, candidate.q - baseline.q);
      candidates.push({ candidate, baseline, threshold, rise, ratio: rise / threshold.cfs });
    }
    if (!candidates.length) return unavailable('No complete rolling 24-hour comparison is available');
    const selected = candidates.reduce((best, r) => r.ratio > best.ratio ? r : best);
    return {
      usable: true,
      projectedRise: selected.rise,
      percent: selected.ratio * 100,
      difference: selected.threshold.cfs - selected.rise,
      threshold: selected.threshold,
      pointTime: selected.candidate.t,
      pointSource: selected.candidate.source,
      baselineTime: selected.baseline.t,
      baselineCfs: selected.baseline.q,
      adjustment,
      handoffTime,
      alignedRows
    };
  }
  function lineRelation(difference) {
    const value = number(difference);
    if (value === null) throw Error('Seasonal-line difference is invalid');
    if (value < 0) return { code: 'above', distance: Math.abs(value) };
    if (value > 0) return { code: 'below', distance: value };
    return { code: 'at', distance: 0 };
  }
  function normalizeSnapshot(row) {
    const issueTime = time(row?.issueTime), capturedAt = time(row?.capturedAt), gaugeTime = time(row?.gaugeTime);
    const gaugeCfs = number(row?.gaugeCfs), adjustment = number(row?.adjustment);
    const alignedPath = path(row?.alignedPath), rawPath = path(row?.rawPath);
    const completeAlignedPath = alignedPath && alignedPath.length === row?.alignedPath?.length;
    const completeRawPath = rawPath && rawPath.length === row?.rawPath?.length;
    if ([issueTime, capturedAt, gaugeTime].some(v => v === null) || gaugeCfs === null || gaugeCfs < 0 || adjustment === null || !completeAlignedPath || !completeRawPath) return null;
    const issueAge = capturedAt - issueTime, gaugeAge = capturedAt - gaugeTime;
    if (issueAge < 0 || issueAge > 48 * H || gaugeAge < 0 || gaugeAge > 2 * H) return null;
    if (rawPath[0].t !== capturedAt || rawPath.at(-1).t < capturedAt + 60 * H || rawPath.some((r, i) => i && r.t - rawPath[i - 1].t > 6 * H)) return null;
    const close = (a, b) => Math.abs(a - b) <= 1e-8 * Math.max(1, Math.abs(a), Math.abs(b));
    if (alignedPath[0].t !== gaugeTime || !close(alignedPath[0].q, gaugeCfs)) return null;
    const rawByTime = new Map(rawPath.map(r => [r.t, r.q]));
    if (alignedPath.slice(1).some(r => !rawByTime.has(r.t) || !close(r.q, rawByTime.get(r.t) + adjustment))) return null;
    return { issueTime, capturedAt, gaugeTime, gaugeCfs, adjustment, alignedPath, rawPath };
  }
  function makeSnapshot(fc, screen, latest, now) {
    if (!fc?.usable || !screen?.usable || !latest || !Number.isFinite(now) || fc.issued === null || fc.issued > now || latest.t > now) return null;
    const rawPath = path(fc.rows), alignedPath = path(screen.alignedRows);
    if (!rawPath || !alignedPath) return null;
    return {
      issueTime: new Date(fc.issued).toISOString(), capturedAt: new Date(now).toISOString(), gaugeTime: new Date(latest.t).toISOString(),
      gaugeCfs: latest.q, adjustment: screen.adjustment,
      rawPath: rawPath.map(r => ({ t: r.t, q: r.q })), alignedPath: alignedPath.map(r => ({ t: r.t, q: r.q }))
    };
  }
  function watchUnknown(reason, code = 'unknown') {
    return { code, reason, expected: null, observed: null, difference: null, line: null, change3: null, span3: null, snapshot: null };
  }
  function surpriseWatch(observation, snapshots, storageStatus = 'available') {
    if (storageStatus !== 'available') return watchUnknown('Saved forecast history is unavailable on this device');
    if (!observation?.fresh) return watchUnknown('A recent gauge reading and a near-three-hour comparison are required');
    const observationTime = Number(observation.t), observed = number(observation.q), change3 = number(observation.change3), span3 = number(observation.span3);
    const threshold = thresholdAt(observationTime);
    if (!Number.isFinite(observationTime) || observed === null || observed < 0 || change3 === null || span3 === null || span3 < 2.5 || span3 > 3.5 || !threshold) return watchUnknown('The current gauge comparison did not pass timing and value checks');
    if (!Array.isArray(snapshots)) return watchUnknown('Saved forecast history is malformed, so the comparison failed closed');
    const normalized = [];
    for (const row of snapshots) {
      const snapshot = normalizeSnapshot(row);
      if (!snapshot) return watchUnknown('Saved forecast history is malformed, so the comparison failed closed');
      if (snapshot.issueTime > snapshot.capturedAt || snapshot.gaugeTime > snapshot.capturedAt) return watchUnknown('Saved forecast history has an inconsistent clock');
      normalized.push(snapshot);
    }
    if (new Set(normalized.map(r => r.issueTime)).size !== normalized.length) return watchUnknown('Saved forecast history contains duplicate NOAA issues, so the comparison failed closed');
    let pathFailure = false;
    const eligible = normalized.flatMap(snapshot => {
      const age = (observationTime - snapshot.capturedAt) / H;
      if (age < WATCH.minimumAgeHours || age > WATCH.maximumAgeHours) return [];
      const expected = interpolateGap(snapshot.alignedPath, observationTime, WATCH.maximumGapHours);
      if (!expected) { pathFailure = true; return []; }
      return [{ snapshot, age, expected }];
    }).sort((a, b) => b.snapshot.capturedAt - a.snapshot.capturedAt);
    if (pathFailure) return watchUnknown('An eligible saved path did not validly bracket the gauge reading');
    if (!eligible.length) {
      const result = watchUnknown('No saved path is between 3 and 36 hours old at this gauge time', 'learning');
      return { ...result, observed, change3, span3, line: threshold.cfs * WATCH.seasonalFraction, threshold };
    }
    const selected = eligible[0], expected = selected.expected.q, difference = observed - expected, line = threshold.cfs * WATCH.seasonalFraction;
    const base = { expected, observed, difference, line, change3, span3, threshold, age: selected.age, snapshot: selected.snapshot, interpolation: selected.expected };
    if (difference >= line && change3 > 0) return { ...base, code: 'outpacing' };
    if (difference >= line) return { ...base, code: 'above-prior' };
    return { ...base, code: 'tracking' };
  }
  function forecastRevision(fc, snapshots, now) {
    const unavailable = (code, reason) => ({ usable: false, code, reason });
    if (!fc?.usable || fc.issued === null) return unavailable('unknown', 'The current NOAA forecast is unavailable');
    if (!Array.isArray(snapshots)) return unavailable('unknown', 'Saved forecast history is malformed');
    const normalized = [];
    for (const row of snapshots) {
      const snapshot = normalizeSnapshot(row);
      if (!snapshot) return unavailable('unknown', 'Saved forecast history is malformed');
      if (snapshot.issueTime > snapshot.capturedAt || snapshot.gaugeTime > snapshot.capturedAt) return unavailable('unknown', 'Saved forecast history has an inconsistent clock');
      normalized.push(snapshot);
    }
    if (new Set(normalized.map(r => r.issueTime)).size !== normalized.length) return unavailable('unknown', 'Saved forecast history contains duplicate NOAA issues');
    const prior = normalized.filter(r => r.issueTime < fc.issued && r.capturedAt < now && now - r.capturedAt <= WATCH.maximumAgeHours * H)
      .sort((a, b) => b.issueTime - a.issueTime)[0];
    if (!prior) return unavailable('learning', 'A previous NOAA issue has not been saved on this device yet');
    const current = path(fc.rows), old = prior.rawPath, start = now, end = now + 24 * H;
    if (!current || !interpolateGap(current, start, 6) || !interpolateGap(current, end, 6) || !interpolateGap(old, start, 6) || !interpolateGap(old, end, 6)) return unavailable('unknown', 'The current and previous issues do not share a complete next-24-hour window');
    const times = [...new Set([start, end, ...current.filter(r => r.t > start && r.t < end).map(r => r.t), ...old.filter(r => r.t > start && r.t < end).map(r => r.t)])].sort((a, b) => a - b);
    const currentValues = times.map(t => interpolateGap(current, t, 6)?.q), oldValues = times.map(t => interpolateGap(old, t, 6)?.q);
    if (currentValues.some(v => v === undefined) || oldValues.some(v => v === undefined)) return unavailable('unknown', 'The issue comparison contains an unsupported gap');
    const currentMax = Math.max(...currentValues), priorMax = Math.max(...oldValues);
    return { usable: true, currentMax, priorMax, difference: currentMax - priorMax, previousIssue: prior.issueTime, windowStart: start, windowEnd: end };
  }
  function forecast(rows, issued, now) {
    const issue = time(issued);
    if (issue === null || issue > now || now - issue > 48 * H) return { usable: false, reason: issue !== null && issue <= now ? 'Forecast is over 48 hours old' : 'Forecast issue time unavailable or invalid', issued: issue, rows: [] };
    const end = Math.min(now + 72 * H, rows.at(-1)?.t ?? now);
    if (end <= now) return { usable: false, reason: 'Forecast has no future values', issued: issue, rows: [] };
    const atCheck = interpolate(rows, now), firstFuture = rows.find(r => r.t > now);
    if (atCheck === null && (!firstFuture || firstFuture.t - now > 6 * H)) return { usable: false, reason: 'Forecast begins more than six hours after this check', issued: issue, rows: [] };
    const points = atCheck === null ? rows.filter(r => r.t > now && r.t <= end) : [{ t: now, q: atCheck }, ...rows.filter(r => r.t > now && r.t <= end)];
    if (points.at(-1)?.t !== end) points.push({ t: end, q: interpolate(rows, end) });
    if (!points.length || points.some(r => r.q === null) || points.some((r, i) => i && r.t - points[i - 1].t > 6 * H)) return { usable: false, reason: 'Forecast has an unsupported gap', issued: issue, rows: [] };
    const max = Math.max(...points.map(r => r.q)), peaks = points.filter(r => Math.abs(r.q - max) < 1e-8);
    const start = points[0].t;
    return { usable: true, issued: issue, rows: points, start, startsAfterCheck: start > now, end, hours: (end - now) / H, complete: end >= now + 72 * H, max, firstMax: peaks[0].t, lastMax: peaks.at(-1).t, atStart: peaks[0].t === start, atEnd: peaks.at(-1).t === end };
  }
  function tides(d) {
    if (!Array.isArray(d?.predictions)) throw Error('Tide predictions unavailable');
    return d.predictions.filter(r => /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(r.t)).map(r => ({ t: time(String(r.t).replace(' ', 'T') + ':00Z'), v: number(r.v), type: r.type }))
      .filter(r => r.t !== null && r.v !== null && ['H', 'L'].includes(r.type)).sort((a, b) => a.t - b.t);
  }
  root.SamishData = { H, WATCH, number, time, nwpsSeries, usgs, duration, rain, rainWindow, rainBins, rrmProductId, rrmRain, basinGeometry, gaugePoint, gridPoint, radarCapabilities, csvCell, stormRecord, stormCsv, interpolate, atBefore, thresholdAt, recentChange, planningScreen, lineRelation, makeSnapshot, surpriseWatch, forecastRevision, forecast, tides };
})(globalThis);
