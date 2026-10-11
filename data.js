(function (root) {
  'use strict';
  const H = 3600000;
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
  function nwpsSeries(s, now, observed) {
    if (!s || !Array.isArray(s.data)) throw Error('River series missing');
    const key = ['primary', 'secondary'].find(k => /discharge|streamflow/i.test(s[k + 'Name'] || '') && factor(s[k + 'Units']) !== null);
    if (!key) throw Error('Discharge units not recognized');
    const scale = factor(s[key + 'Units']);
    const rows = s.data.map(r => ({ t: time(r.validTime), q: number(r[key]), source: 'NOAA copy of USGS' }))
      .filter(r => r.t !== null && r.q !== null && r.q >= 0 && (!observed || r.t <= now))
      .map(r => ({ ...r, q: r.q * scale })).filter(r => Number.isFinite(r.q));
    return [...new Map(rows.map(r => [r.t, r])).values()].sort((a, b) => a.t - b.t);
  }
  function usgs(d, now) {
    if (!Array.isArray(d?.features)) throw Error('Gauge response not recognized');
    return d.features.map(f => f.properties || {}).filter(p => p.parameter_code === '00060' && p.monitoring_location_id === 'USGS-12201500')
      .map(p => ({ t: time(p.time), q: number(p.value), scale: factor(p.unit_of_measure), source: 'USGS direct' }))
      .filter(r => r.t !== null && r.t <= now && r.q !== null && r.q >= 0 && r.scale !== null)
      .map(r => ({ t: r.t, q: r.q * r.scale, source: r.source })).filter(r => Number.isFinite(r.q));
  }
  function duration(s) {
    const m = /^P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$/.exec(s || '');
    if (!m || !m.slice(1).some(Boolean) || s.endsWith('T')) return null;
    const v = ((Number(m[1] || 0) * 24 + Number(m[2] || 0)) * 3600 + Number(m[3] || 0) * 60 + Number(m[4] || 0)) * 1000;
    return Number.isFinite(v) && v > 0 ? v : null;
  }
  function rain(d, now) {
    const p = d?.properties, q = p?.quantitativePrecipitation;
    const scale = new Map([['wmoUnit:mm', 1], ['wmoUnit:in', 25.4]]).get(q?.uom);
    const updated = time(p?.updateTime);
    if (scale === undefined || !Array.isArray(q?.values) || updated === null || updated > now) throw Error('Rain units or update time not recognized');
    const rows = q.values.map(r => {
      const parts = String(r.validTime).split('/'), [start, span] = parts;
      const t = time(start), len = duration(span), v = number(r.value);
      return { t, end: parts.length !== 2 || t === null || len === null ? null : t + len, mm: v === null || v < 0 || !Number.isFinite(v * scale) ? null : v * scale };
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
  function forecast(rows, issued, now) {
    const issue = time(issued);
    if (issue === null || issue > now || now - issue > 48 * H) return { usable: false, reason: issue !== null && issue <= now ? 'Forecast is over 48 hours old' : 'Forecast issue time unavailable or invalid', issued: issue, rows: [] };
    const end = Math.min(now + 72 * H, rows.at(-1)?.t ?? now);
    if (end <= now || interpolate(rows, now) === null) return { usable: false, reason: 'Forecast does not cover the current time', issued: issue, rows: [] };
    if (rows.some((r, i) => i && r.t > now && rows[i - 1].t < end && r.t - rows[i - 1].t > 6 * H)) return { usable: false, reason: 'Forecast has an unsupported gap', issued: issue, rows: [] };
    const points = [{ t: now, q: interpolate(rows, now) }, ...rows.filter(r => r.t > now && r.t < end), { t: end, q: interpolate(rows, end) }];
    const max = Math.max(...points.map(r => r.q)), peaks = points.filter(r => Math.abs(r.q - max) < 1e-8);
    return { usable: true, issued: issue, rows: points, end, hours: (end - now) / H, complete: end >= now + 72 * H, max, firstMax: peaks[0].t, lastMax: peaks.at(-1).t, atStart: peaks[0].t === now, atEnd: peaks.at(-1).t === end };
  }
  function tides(d) {
    if (!Array.isArray(d?.predictions)) throw Error('Tide predictions unavailable');
    return d.predictions.filter(r => /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(r.t)).map(r => ({ t: time(String(r.t).replace(' ', 'T') + ':00Z'), v: number(r.v), type: r.type }))
      .filter(r => r.t !== null && r.v !== null && ['H', 'L'].includes(r.type)).sort((a, b) => a.t - b.t);
  }
  root.SamishData = { H, number, time, nwpsSeries, usgs, duration, rain, rainWindow, interpolate, atBefore, forecast, tides };
})(globalThis);
