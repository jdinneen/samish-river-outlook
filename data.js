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
  function segmentsTouch(a, b, c, d) {
    const orientation = (p, q, r) => {
      const cross = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
      return Math.abs(cross) <= 1e-12 ? 0 : Math.sign(cross);
    };
    const o1 = orientation(a, b, c), o2 = orientation(a, b, d), o3 = orientation(c, d, a), o4 = orientation(c, d, b);
    return (o1 * o2 < 0 && o3 * o4 < 0) || (o1 === 0 && pointOnSegment(c, a, b)) || (o2 === 0 && pointOnSegment(d, a, b)) || (o3 === 0 && pointOnSegment(a, c, d)) || (o4 === 0 && pointOnSegment(b, c, d));
  }
  function ringsTouch(first, second) {
    for (let a = 0; a < first.length - 1; a++) {
      for (let b = 0; b < second.length - 1; b++) {
        if (segmentsTouch(first[a], first[a + 1], second[b], second[b + 1])) return true;
      }
    }
    return false;
  }
  function validateBasinTopology(polygons) {
    for (const polygon of polygons) {
      const outer = polygon[0], holes = polygon.slice(1);
      for (let index = 0; index < holes.length; index++) {
        const hole = holes[index];
        if (hole.slice(0, -1).some(point => pointInRing(point, outer) !== 1) || ringsTouch(hole, outer)) throw Error('Basin hole is not strictly inside its outer ring');
        for (let prior = 0; prior < index; prior++) {
          const other = holes[prior];
          if (ringsTouch(hole, other) || pointInRing(hole[0], other) !== 0 || pointInRing(other[0], hole) !== 0) throw Error('Basin holes overlap, touch, or nest');
        }
      }
    }
    for (let index = 0; index < polygons.length; index++) {
      const outer = polygons[index][0];
      for (let prior = 0; prior < index; prior++) {
        const other = polygons[prior][0];
        if (ringsTouch(outer, other) || pointInRing(outer[0], other) !== 0 || pointInRing(other[0], outer) !== 0) throw Error('Basin polygons overlap, touch, or contain one another');
      }
    }
  }
  function basinGeometry(d) {
    if (!Array.isArray(d?.features) || d.features.length !== 1) throw Error('Basin response not recognized');
    const geometry = d.features[0]?.geometry;
    const polygons = geometry?.type === 'Polygon' ? [geometry.coordinates] : geometry?.type === 'MultiPolygon' ? geometry.coordinates : null;
    if (!Array.isArray(polygons) || !polygons.length) throw Error('Basin geometry unavailable');
    let pointCount = 0;
    const rings = [], validatedPolygons = [];
    for (const polygon of polygons) {
      if (!Array.isArray(polygon) || !polygon.length) throw Error('Basin polygon malformed');
      const validatedRings = [];
      for (const ring of polygon) {
        const clean = ringMetrics(ring, 'Basin').clean;
        pointCount += clean.length;
        if (pointCount > 5000) throw Error('Basin geometry is unexpectedly large');
        rings.push(clean);
        validatedRings.push(clean);
      }
      validatedPolygons.push(validatedRings);
    }
    validateBasinTopology(validatedPolygons);
    return { rings, polygons: validatedPolygons, pointCount };
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
    const polygons = d?.geometry?.coordinates;
    const coordinates = d?.geometry?.type === 'Polygon' && Array.isArray(polygons) && polygons.length === 1 ? polygons[0] : null;
    try {
      const metrics = ringMetrics(coordinates, 'Forecast grid');
      if (!convexQuadrilateral(metrics.clean)) throw Error('Forecast grid is not a convex four-corner cell');
      return { lon: metrics.lon, lat: metrics.lat, ring: metrics.clean };
    } catch { return null; }
  }
  function convexQuadrilateral(ring) {
    if (!Array.isArray(ring) || ring.length !== 5) return false;
    const vertices = ring.slice(0, -1);
    let direction = 0;
    for (let i = 0; i < vertices.length; i++) {
      const a = vertices[i], b = vertices[(i + 1) % vertices.length], c = vertices[(i + 2) % vertices.length];
      const cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]);
      if (Math.abs(cross) <= 1e-12) return false;
      const current = Math.sign(cross);
      if (direction && current !== direction) return false;
      direction = current;
    }
    return true;
  }
  function pointOnSegment(point, a, b) {
    const cross = (point[0] - a[0]) * (b[1] - a[1]) - (point[1] - a[1]) * (b[0] - a[0]);
    return Math.abs(cross) <= 1e-10 && point[0] >= Math.min(a[0], b[0]) - 1e-10 && point[0] <= Math.max(a[0], b[0]) + 1e-10 && point[1] >= Math.min(a[1], b[1]) - 1e-10 && point[1] <= Math.max(a[1], b[1]) + 1e-10;
  }
  function pointInRing(point, ring) {
    let inside = false;
    for (let i = 0; i < ring.length - 1; i++) {
      const a = ring[i], b = ring[i + 1];
      if (pointOnSegment(point, a, b)) return 2;
      if ((a[1] > point[1]) !== (b[1] > point[1]) && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
    }
    return inside ? 1 : 0;
  }
  function pointCoveredByPolygon(point, polygon) {
    if (!Array.isArray(polygon) || !polygon.length || pointInRing(point, polygon[0]) === 0) return false;
    return polygon.slice(1).every(hole => pointInRing(point, hole) !== 1);
  }
  function intersectionParameters(a, b, c, d) {
    const rx = b[0] - a[0], ry = b[1] - a[1], sx = d[0] - c[0], sy = d[1] - c[1];
    const cross = (x1, y1, x2, y2) => x1 * y2 - y1 * x2;
    const denominator = cross(rx, ry, sx, sy), qx = c[0] - a[0], qy = c[1] - a[1];
    if (Math.abs(denominator) > 1e-12) {
      const t = cross(qx, qy, sx, sy) / denominator, u = cross(qx, qy, rx, ry) / denominator;
      return t >= -1e-10 && t <= 1 + 1e-10 && u >= -1e-10 && u <= 1 + 1e-10 ? [Math.min(1, Math.max(0, t))] : [];
    }
    if (Math.abs(cross(qx, qy, rx, ry)) > 1e-12) return [];
    const lengthSquared = rx * rx + ry * ry;
    if (lengthSquared <= 1e-20) return [];
    return [((c[0] - a[0]) * rx + (c[1] - a[1]) * ry) / lengthSquared, ((d[0] - a[0]) * rx + (d[1] - a[1]) * ry) / lengthSquared]
      .filter(t => t >= -1e-10 && t <= 1 + 1e-10).map(t => Math.min(1, Math.max(0, t)));
  }
  function gridWithinPolygon(grid, polygon) {
    const ring = grid.ring;
    if (ring.slice(0, -1).some(point => !pointCoveredByPolygon(point, polygon))) return false;
    const centroid = [grid.lon, grid.lat];
    if (pointInRing(centroid, ring) !== 0 && !pointCoveredByPolygon(centroid, polygon)) return false;
    for (let edge = 0; edge < ring.length - 1; edge++) {
      const a = ring[edge], b = ring[edge + 1], parameters = [0, 1];
      for (const boundary of polygon) {
        for (let i = 0; i < boundary.length - 1; i++) parameters.push(...intersectionParameters(a, b, boundary[i], boundary[i + 1]));
      }
      const unique = [...new Set(parameters.map(value => value.toFixed(12)))].map(Number).sort((x, y) => x - y);
      for (let i = 1; i < unique.length; i++) {
        if (unique[i] - unique[i - 1] <= 1e-10) continue;
        const t = (unique[i] + unique[i - 1]) / 2;
        if (!pointCoveredByPolygon([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], polygon)) return false;
      }
    }
    for (const hole of polygon.slice(1)) {
      if (hole.slice(0, -1).some(point => pointInRing(point, ring) === 1)) return false;
      for (let i = 0; i < hole.length - 1; i++) {
        const midpoint = [(hole[i][0] + hole[i + 1][0]) / 2, (hole[i][1] + hole[i + 1][1]) / 2];
        if (pointInRing(midpoint, ring) === 1) return false;
      }
    }
    return true;
  }
  function gridCellWithinBasin(grid, basin) {
    if (!convexQuadrilateral(grid?.ring) || !Number.isFinite(grid.lon) || !Number.isFinite(grid.lat) || !Array.isArray(basin?.polygons)) return false;
    return basin.polygons.some(polygon => gridWithinPolygon(grid, polygon));
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
      riseAtHighestShare: selected.rise,
      selectionBasis: 'highest-seasonal-reference-share',
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
    if (storageStatus !== 'available') return watchUnknown('Earlier-forecast comparison is unavailable on this device');
    if (!observation?.fresh) return watchUnknown('A recent gauge reading and a near-three-hour comparison are required');
    const observationTime = Number(observation.t), observed = number(observation.q), change3 = number(observation.change3), span3 = number(observation.span3);
    const threshold = thresholdAt(observationTime);
    if (!Number.isFinite(observationTime) || observed === null || observed < 0 || change3 === null || span3 === null || span3 < 2.5 || span3 > 3.5 || !threshold) return watchUnknown('The current gauge comparison did not pass timing and value checks');
    if (!Array.isArray(snapshots)) return watchUnknown('Earlier-forecast comparison is unavailable because its history could not be read');
    const normalized = [];
    for (const row of snapshots) {
      const snapshot = normalizeSnapshot(row);
      if (!snapshot) return watchUnknown('Earlier-forecast comparison is unavailable because its history could not be read');
      if (snapshot.issueTime > snapshot.capturedAt || snapshot.gaugeTime > snapshot.capturedAt) return watchUnknown('Earlier-forecast comparison is unavailable because its times do not agree');
      normalized.push(snapshot);
    }
    if (new Set(normalized.map(r => r.issueTime)).size !== normalized.length) return watchUnknown('Earlier-forecast comparison is unavailable because its history has duplicate entries');
    let pathFailure = false;
    const eligible = normalized.flatMap(snapshot => {
      const age = (observationTime - snapshot.capturedAt) / H;
      if (age < WATCH.minimumAgeHours || age > WATCH.maximumAgeHours) return [];
      const expected = interpolateGap(snapshot.alignedPath, observationTime, WATCH.maximumGapHours);
      if (!expected) { pathFailure = true; return []; }
      return [{ snapshot, age, expected }];
    }).sort((a, b) => b.snapshot.capturedAt - a.snapshot.capturedAt);
    if (pathFailure) return watchUnknown('The earlier forecast does not cover the current gauge time');
    if (!eligible.length) {
      const result = watchUnknown('No earlier forecast from 3–36 hours ago is available yet', 'learning');
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
    if (!Array.isArray(snapshots)) return unavailable('unknown', 'Earlier-forecast history could not be read');
    const normalized = [];
    for (const row of snapshots) {
      const snapshot = normalizeSnapshot(row);
      if (!snapshot) return unavailable('unknown', 'Earlier-forecast history could not be read');
      if (snapshot.issueTime > snapshot.capturedAt || snapshot.gaugeTime > snapshot.capturedAt) return unavailable('unknown', 'Earlier-forecast times do not agree');
      normalized.push(snapshot);
    }
    if (new Set(normalized.map(r => r.issueTime)).size !== normalized.length) return unavailable('unknown', 'Earlier-forecast history contains duplicate entries');
    const prior = normalized.filter(r => r.issueTime < fc.issued && r.capturedAt < now && now - r.capturedAt <= WATCH.maximumAgeHours * H)
      .sort((a, b) => b.issueTime - a.issueTime)[0];
    if (!prior) return unavailable('learning', 'No earlier NOAA issue is available for comparison yet');
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

  // ---------------------------------------------------------------------------------------------
  // Version 7: measured river state, NOAA's current issue against the gauge, tide, rain flags and
  // the look-back counts. Everything below is pure: no page access, no network, no clock of its own.
  // Every duration is counted between reading time stamps; the device's check time ("now") is used
  // only for a reading's age and to drop future-dated rows. A value that cannot be computed is
  // returned as null and never as zero. Times are epoch milliseconds; flows are cubic feet per
  // second ("cfs"); rain is inches unless a field name says millimetres.
  // ---------------------------------------------------------------------------------------------
  const MIN = 60000, EPS = 1e-9;
  // RIVER_RULES (frozen). The display rules of the River block, all in reading time.
  //   freshMinutes 90              newest reading older than this (whole minutes): no direction, no state
  //   pauseMinutes 60              no new high for this long: "paused"
  //   peakMinutes 120              no new high for this long: "may have peaked"
  //   fallingFraction 0.05         newest reading this far below the high: "falling"
  //   risingCfs 2, risingFraction 0.02   last-hour change must reach BOTH for the word "rising"
  //                                (and the mirror, -2 cfs and -2%, for "falling" as a last-hour label)
  //   riseMemoryHours 48           how long a passed seasonal number is remembered
  //   lastHourToleranceMinutes 20  the "hour before" reading must lie within 60 +/- 20 minutes of the newest
  //   maxGapMinutes 60             a longer hole in the readings (last hour, 24-hour low, since the high): cannot tell
  //   climbBackFraction 0.05       a reading below the high that is this share of the high above the lowest reading
  //                                since the high, with a positive about-three-hour change, is "rising again"
  //   clockBehindMinutes 5         a newest reading stamped more than this after the device's check time: the
  //                                device clock is behind the gauge, and nothing is said about the river
  const RIVER_RULES = Object.freeze({ freshMinutes: 90, pauseMinutes: 60, peakMinutes: 120, fallingFraction: 0.05, risingCfs: 2, risingFraction: 0.02, riseMemoryHours: 48, lastHourToleranceMinutes: 20, maxGapMinutes: 60, climbBackFraction: 0.05, clockBehindMinutes: 5 });
  // RAIN_RULES (frozen). suspectZeroOtherGaugesIn: the 24-hour total both other gauges must reach before
  // a gauge reading exactly zero is marked suspect. dryMonths: Pacific months in which the dry-season
  // rain context applies.
  const RAIN_RULES = Object.freeze({ suspectZeroOtherGaugesIn: 0.25, dryMonths: Object.freeze([5, 6, 7, 8, 9, 10]) });
  function deepFreeze(value) {
    for (const item of Object.values(value)) if (item && typeof item === 'object') deepFreeze(item);
    return Object.freeze(value);
  }
  function pacificMonth(t) {
    if (typeof t !== 'number' || !Number.isFinite(t)) return null;
    const month = Number(new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', month: 'numeric' }).formatToParts(new Date(t)).find(p => p.type === 'month')?.value);
    return Number.isInteger(month) && month >= 1 && month <= 12 ? month : null;
  }
  // Valid readings at or before the check time, oldest first; null when the input cannot be trusted
  // (not an array, no check time, or two readings carrying one time stamp).
  function gaugeReadings(rows, now) {
    if (!Array.isArray(rows) || typeof now !== 'number' || !Number.isFinite(now)) return null;
    const clean = rows.map(r => ({ t: r?.t, q: number(r?.q) }))
      .filter(r => typeof r.t === 'number' && Number.isFinite(r.t) && r.q !== null && r.q >= 0 && r.t <= now).sort((a, b) => a.t - b.t);
    return clean.some((r, i) => i && r.t === clean[i - 1].t) ? null : clean;
  }
  // The 24 hours ending at rows[i] (both ends included). Returns { t, q, exact, gapMinutes } for the lowest reading
  // held in them (the EARLIEST on a tie), or null when the readings do not reach back 24 hours at all.
  //   exact true   the readings reach back the full 24 hours with no hole over maxGapMinutes: this is the 24-hour low
  //   exact false  there is such a hole (gapMinutes: the largest one), so a lower reading may have been missed and
  //                a rise measured from this reading is only a LOWER BOUND
  function lowIn24At(rows, i) {
    const start = rows[i].t - 24 * H, gap = RIVER_RULES.maxGapMinutes * MIN;
    let low = rows[i], j = i, hole = 0;
    while (j > 0 && rows[j].t > start) {
      hole = Math.max(hole, rows[j].t - rows[j - 1].t);
      j--;
      if (rows[j].t >= start && rows[j].q <= low.q) low = rows[j];
    }
    if (rows[j].t > start) return null;
    return { t: low.t, q: low.q, exact: hole <= gap, gapMinutes: hole > gap ? Math.round(hole / MIN) : null };
  }
  // The newest valid reading whatever its time stamp; used to notice a device clock that is behind the gauge.
  function newestStamped(rows) {
    let newest = null;
    for (const r of Array.isArray(rows) ? rows : []) {
      const q = number(r?.q);
      if (typeof r?.t === 'number' && Number.isFinite(r.t) && q !== null && q >= 0 && (!newest || r.t > newest.t)) newest = { t: r.t, q };
    }
    return newest;
  }
  // Reading nearest to `minutesBack` before rows[i], within the tolerance; the more recent on a tie.
  function readingNear(rows, i, minutesBack, toleranceMinutes) {
    const target = rows[i].t - minutesBack * MIN, tolerance = toleranceMinutes * MIN;
    let best = null, bestOffset = Infinity;
    for (let j = i - 1; j >= 0 && rows[j].t >= target - tolerance; j--) {
      const offset = Math.abs(rows[j].t - target);
      if (offset <= tolerance && offset < bestOffset) { best = rows[j]; bestOffset = offset; }
    }
    return best;
  }
  // lastHourLabel(change, earlier) -- the word for a change over the last hour.
  //   change   newest reading minus the reading an hour before, in cfs
  //   earlier  that earlier reading, in cfs
  // Returns 'rising' (change >= +2 cfs AND >= +2% of earlier), 'falling' (<= -2 cfs AND <= -2%),
  // 'about level' otherwise, or null when either input is not a valid number.
  function lastHourLabel(change, earlier) {
    const R = RIVER_RULES;
    if (typeof change !== 'number' || !Number.isFinite(change) || typeof earlier !== 'number' || !Number.isFinite(earlier) || earlier < 0) return null;
    if (change >= R.risingCfs - EPS && change >= R.risingFraction * earlier - EPS) return 'rising';
    if (change <= -R.risingCfs + EPS && change <= -R.risingFraction * earlier + EPS) return 'falling';
    return 'about level';
  }
  // riverState(rows, now) -- the measured River block. Reads the gauge only; nothing here reads NOAA's forecast.
  //   rows  observed readings [{ t, q }, ...] in any order (the page's merged gauge series; extra fields are
  //         ignored; rows with an invalid time or flow are dropped). Hand it EVERY reading the feed supplied,
  //         including any stamped after `now`: that is how a device clock that is behind is noticed.
  //   now   the device's check time
  // Returns one object, always with every key below:
  //   available        false when there is no usable reading (then reading and ageMinutes are null)
  //   reason           plain words when not available, not fresh, or the state is 'cannot-tell'; else null
  //   checkTime        `now`
  //   reading          { t, q } the newest reading at or before `now` (for 'clock-behind': the newest reading as stamped)
  //   ageMinutes       whole minutes (rounded down) from the reading to the check time; print it beside the reading
  //                    (null for 'clock-behind': no age can be trusted)
  //   fresh            ageMinutes <= 90 AND no hole over 60 minutes in the last 60 minutes of readings.
  //                    When false EVERY field below is null (riseStatus is 'unknown'): no change figure, no state.
  //   staleCode        null when fresh; else 'no-reading' | 'old-reading' | 'gap-in-last-hour' | 'clock-behind'
  //   gapMinutes       size of the hole that caused 'gap-in-last-hour' or 'cannot-tell' (null when the readings
  //                    simply do not reach back one hour, and null otherwise)
  //   clockBehindMinutes  for 'clock-behind' only: whole minutes by which the newest reading is stamped AFTER `now`
  //                    (more than clockBehindMinutes; a reading up to 5 minutes ahead is simply not used yet)
  //   lastHour         { change, percent, label, before: { t, q }, spanMinutes } or null when no reading lies
  //                    within 60 +/- 20 minutes before the newest. label is 'rising' (change >= +2 cfs AND >= +2%
  //                    of the earlier reading), 'falling' (<= -2 cfs AND <= -2%) or 'about level'.
  //                    percent is null when the earlier reading is 0.
  //   threeHour        { change, before: { t, q }, spanMinutes } or null (nearest reading 2.5 to 3.5 hours back)
  //   threshold        { label, cfs } seasonal number for the Pacific month of the reading, or null
  //   low24            { t, q } lowest reading of the 24 hours ending at the reading (earliest on a tie); null
  //                    unless readings reach back 24 hours with no hole over 60 minutes
  //   rise             { cfs, share } reading minus low24, and that as a fraction of threshold.cfs; null with low24
  //   lowHeld24        null unless low24 is unavailable ONLY because of holes; then { t, q, gapMinutes }: the lowest
  //                    reading held in those 24 hours and the largest hole. A lower reading may have been missed.
  //   riseAtLeast      { cfs, share } reading minus lowHeld24: a LOWER BOUND on the rise; null with lowHeld24
  //   riseStatus       'in-progress' a seasonal number was passed within the last 48 hours of readings
  //                    'none'        the newest reading's own rise is computable and no such passing was found
  //                    'unknown'     not fresh, or the exact 24-hour low is unavailable and no passing was found:
  //                                  the page must NOT print this as "no rise"
  //   riseStart        null unless 'in-progress'; else { t, q, riseCfs, low: { t, q }, threshold: { label, cfs },
  //                    atOrBefore, lowerBound }. A reading counts as at or above the number when its rise over its
  //                    own 24-hour low (or, with a hole, its LOWER BOUND over the lowest reading held) reaches the
  //                    seasonal number in force AT THAT READING. The start is the earliest such reading of the last
  //                    48 hours that is a fresh upward crossing (the previous computable reading, no more than 60
  //                    minutes earlier, was below the number). When no fresh crossing exists in the span, it is the
  //                    earliest reading at or above the number, with atOrBefore true: the number was passed at or
  //                    before it. lowerBound true: that reading's rise is a lower bound, so a gap in the record
  //                    hides the exact time. A second surge after a fresh crossing belongs to the same rise.
  //   high             null unless 'in-progress'; else { t, q }, the EARLIEST on equal values (a tie is not a new
  //                    high): the highest reading from riseStart to the newest; or, when riseStart is atOrBefore
  //                    and not lowerBound (the rise is older than the readings compared), the highest reading held
  //                    in the whole last 48 hours
  //   minutesSinceHigh whole minutes of READING time from high to the newest reading (0 when it is the newest)
  //   belowHigh        { cfs, fraction } how far the newest reading is below high (0 and 0 at the high)
  //   lowSinceHigh     { t, q } the lowest reading after high (earliest on a tie); null when high is the newest
  //   risingAgainBasis null unless state is 'rising-again'; then 'last-hour' (lastHour.label is 'rising') or
  //                    'climb-back' (the newest reading is above lowSinceHigh by at least climbBackFraction of the
  //                    high AND the about-three-hour change is positive)
  //   state            null unless fresh and 'in-progress'; else exactly one of, tested in this order:
  //                    'cannot-tell'     a hole over 60 minutes lies between the high and the newest reading
  //                    'new-high'        the newest reading is the high
  //                    'rising-again'    the newest reading is below the high and either basis above holds
  //                    'falling'         the newest reading is at least 5% below the high
  //                    'may-have-peaked' 120 minutes or more of readings since the high
  //                    'paused'          60 to 119 minutes
  //                    'just-off-high'   under 60 minutes
  function riverState(rows, now) {
    const R = RIVER_RULES, gap = R.maxGapMinutes * MIN;
    const absent = { fresh: false, staleCode: null, gapMinutes: null, clockBehindMinutes: null, lastHour: null, threeHour: null, threshold: null, low24: null, rise: null, lowHeld24: null, riseAtLeast: null, riseStatus: 'unknown', riseStart: null, high: null, minutesSinceHigh: null, belowHigh: null, lowSinceHigh: null, risingAgainBasis: null, state: null };
    const clean = gaugeReadings(rows, now), checkTime = typeof now === 'number' && Number.isFinite(now) ? now : null;
    // A newest reading stamped well after the device's time means the device clock is behind: say so, and nothing else.
    const stamped = clean ? newestStamped(rows) : null;
    if (stamped && stamped.t - now > R.clockBehindMinutes * MIN) return { available: true, reason: 'The newest gauge reading is stamped after this device’s time', checkTime, reading: stamped, ageMinutes: null, ...absent, staleCode: 'clock-behind', clockBehindMinutes: Math.floor((stamped.t - now) / MIN) };
    if (!clean || !clean.length) return { available: false, reason: clean ? 'No gauge reading at or before the check time' : 'Gauge readings could not be read', checkTime, reading: null, ageMinutes: null, ...absent, staleCode: 'no-reading' };
    const i = clean.length - 1, last = clean[i], ageMinutes = Math.floor((now - last.t) / MIN);
    const base = { available: true, reason: null, checkTime, reading: { t: last.t, q: last.q }, ageMinutes, ...absent };
    if (ageMinutes > R.freshMinutes) return { ...base, reason: 'The newest gauge reading is ' + ageMinutes + ' minutes old', staleCode: 'old-reading' };
    for (let j = i; clean[j].t > last.t - 60 * MIN; j--) {
      if (j === 0) return { ...base, reason: 'Gauge readings do not reach back one hour', staleCode: 'gap-in-last-hour' };
      const hole = clean[j].t - clean[j - 1].t;
      if (hole > gap) return { ...base, reason: 'Gauge readings are missing in the last hour', staleCode: 'gap-in-last-hour', gapMinutes: Math.round(hole / MIN) };
    }
    const earlier = readingNear(clean, i, 60, R.lastHourToleranceMinutes);
    const lastHour = earlier ? { change: last.q - earlier.q, percent: earlier.q > 0 ? (last.q - earlier.q) / earlier.q * 100 : null, label: lastHourLabel(last.q - earlier.q, earlier.q), before: { t: earlier.t, q: earlier.q }, spanMinutes: (last.t - earlier.t) / MIN } : null;
    const three = recentChange(clean, last, 3, now);
    const threeHour = three ? { change: three.change, before: { t: three.before.t, q: three.before.q }, spanMinutes: (last.t - three.before.t) / MIN } : null;
    const threshold = thresholdAt(last.t), window24 = lowIn24At(clean, i);
    const low24 = window24 && window24.exact ? { t: window24.t, q: window24.q } : null;
    const rise = low24 && threshold ? { cfs: last.q - low24.q, share: (last.q - low24.q) / threshold.cfs } : null;
    const lowHeld24 = window24 && !window24.exact ? { t: window24.t, q: window24.q, gapMinutes: window24.gapMinutes } : null;
    const riseAtLeast = lowHeld24 && threshold ? { cfs: last.q - lowHeld24.q, share: (last.q - lowHeld24.q) / threshold.cfs } : null;
    // "This rise": the earliest fresh upward crossing of the remembered span; failing that, the earliest reading
    // at or above the number in force at that reading (the number was then passed at or before it).
    const spanStart = last.t - R.riseMemoryHours * H;
    let firstAbove = null, crossing = null, prior = null;
    for (let k = 0; k <= i && !crossing; k++) {
      if (clean[k].t < spanStart) continue;
      const window = lowIn24At(clean, k), number24 = thresholdAt(clean[k].t);
      if (!window || !number24) continue;
      const riseCfs = clean[k].q - window.q, above = riseCfs >= number24.cfs - EPS;
      if (!above && !window.exact) continue;   // only a lower bound, and it is under the number: cannot be told
      if (above) {
        const fresh = !!prior && prior.below && clean[k].t - prior.t <= gap;
        const found = { index: k, t: clean[k].t, q: clean[k].q, riseCfs, low: { t: window.t, q: window.q }, threshold: number24, atOrBefore: !fresh, lowerBound: !window.exact };
        if (fresh) crossing = found; else if (!firstAbove) firstAbove = found;
      }
      prior = { t: clean[k].t, below: !above };
    }
    const chosen = crossing || firstAbove, riseStart = chosen ? { t: chosen.t, q: chosen.q, riseCfs: chosen.riseCfs, low: chosen.low, threshold: chosen.threshold, atOrBefore: chosen.atOrBefore, lowerBound: chosen.lowerBound } : null;
    const riseStatus = riseStart ? 'in-progress' : rise ? 'none' : 'unknown';
    const result = { ...base, fresh: true, lastHour, threeHour, threshold, low24, rise, lowHeld24, riseAtLeast, riseStatus, riseStart };
    if (!riseStart) return result;
    // A rise older than the readings compared has no known start: its high is the highest reading held in the span.
    const from = riseStart.atOrBefore && !riseStart.lowerBound ? clean.findIndex(r => r.t >= spanStart) : chosen.index;
    let top = from;
    for (let k = from + 1; k <= i; k++) if (clean[k].q > clean[top].q) top = k;
    let hole = 0, lowAfter = null;
    for (let k = top + 1; k <= i; k++) { hole = Math.max(hole, clean[k].t - clean[k - 1].t); if (!lowAfter || clean[k].q < lowAfter.q) lowAfter = clean[k]; }
    const high = { t: clean[top].t, q: clean[top].q }, sinceHigh = last.t - high.t, drop = high.q - last.q;
    const byLastHour = lastHour?.label === 'rising' && last.q < high.q;
    const byClimbBack = !!lowAfter && last.q < high.q && last.q - lowAfter.q >= R.climbBackFraction * high.q - EPS && !!threeHour && threeHour.change > 0;
    const state = hole > gap ? 'cannot-tell'
      : top === i ? 'new-high'
        : byLastHour || byClimbBack ? 'rising-again'
          : drop >= R.fallingFraction * high.q - EPS ? 'falling'
            : sinceHigh >= R.peakMinutes * MIN ? 'may-have-peaked'
              : sinceHigh >= R.pauseMinutes * MIN ? 'paused' : 'just-off-high';
    return { ...result, reason: state === 'cannot-tell' ? 'Gauge readings are missing between the highest reading and the newest one' : null, gapMinutes: state === 'cannot-tell' ? Math.round(hole / MIN) : null, high, minutesSinceHigh: Math.floor(sinceHigh / MIN), belowHigh: { cfs: drop, fraction: high.q > 0 ? drop / high.q : 0 }, lowSinceHigh: lowAfter ? { t: lowAfter.t, q: lowAfter.q } : null, risingAgainBasis: state === 'rising-again' ? (byLastHour ? 'last-hour' : 'climb-back') : null, state };
  }
  // forecastOnlyFalls(fc) -- "NOAA's path only falls from its first point".
  //   fc  the object D.forecast(...) returns (its rows start at the check time, or at NOAA's first future value)
  // Returns true when no value is higher than the one before it AND the last is lower than the first;
  // false for any other usable path (a flat path is false); null when fc is not usable.
  // When true, the first value is an interpolated check-time value, not a forecast "high": say so in words.
  function forecastOnlyFalls(fc) {
    const rows = fc?.usable ? path(fc.rows) : null;
    if (!rows) return null;
    return rows.every((r, i) => !i || r.q <= rows[i - 1].q + EPS) && rows.at(-1).q < rows[0].q - EPS;
  }
  // noaaAgainstGauge(river, forecastRows, issued, now) -- NOAA's CURRENT issue against the gauge. Needs no saved
  // history, so it works on a first visit.
  //   river         the object riverState(...) returned
  //   forecastRows  NOAA's raw forecast path [{ t, q }, ...] (the rows D.nwpsSeries(forecast, now, false) returns,
  //                 the same rows handed to D.forecast; NOT fc.rows, which start at the check time)
  //   issued        NOAA's issue time: the ISO string D.forecast takes, or epoch milliseconds
  //   now           the device's check time
  // A real NOAA path starts at the next six-hourly point AFTER its issue stamp, so for a few hours after every
  // issue the newest gauge reading is earlier than the path's first point. Two cases are therefore compared:
  //   covered  the reading lies inside the path: NOAA's value for the reading's time (straight line between
  //            forecast points no more than 6 hours apart) is set against the gauge. Above the line when the
  //            gauge is higher by at least the line.
  //   ahead    the reading is earlier than the path's first point: no value is invented for the reading's time.
  //            Above the line when the gauge is above the HIGHEST value anywhere in the path by the line, OR
  //            above the path's FIRST value by the line while the river's last-hour label is 'rising'.
  // Returns one object, always with every key below:
  //   code            'not-tracking' above the line AND a rise is in progress
  //                   'above-line'   above the line, and riverState found no rise in progress
  //                   'within-line'  a comparison was made and the gauge is not above the line
  //                   'unknown'      cannot be told; `reason` says why in plain words
  //   notTracking     true only for 'not-tracking'. Note 'unknown' with aboveLine true (the gauge's 24-hour
  //                   history incomplete) is NOT evidence that NOAA is tracking.
  //   reason          plain words when code is 'unknown'; else null
  //   issued          NOAA's issue time (null when invalid); issueAgeMinutes: whole minutes from issue to `now`
  //   readingTime     time of the gauge reading compared; gaugeCfs: that reading
  //   compared        true when either case above could be evaluated; false otherwise (then aboveLine is null)
  //   covered         true / false for the two cases; null when not compared
  //   forecastCfs     covered only: NOAA's value for readingTime; null in the ahead case and outside the path
  //   difference      gaugeCfs minus forecastCfs (null with forecastCfs)
  //   first           { t, q } the path's first point (null without a usable forecast)
  //   top             { t, q } the highest value in the path from the reading's time on, the earliest on a tie
  //                   (covered: NOAA's value at the reading's time counts; ahead: the whole path)
  //   aboveTopBy      gaugeCfs minus top.q; aboveTop: that is at least the line
  //   aboveFirstBy    ahead only: gaugeCfs minus first.q; else null
  //   basis           what put the gauge above the line: 'at-reading-time' (covered), 'above-highest' or
  //                   'above-first-and-rising' (ahead); null when not above
  //   threshold       { label, cfs } seasonal number at readingTime; line: 10% of it (WATCH.seasonalFraction)
  //   aboveLine       see the two cases; null when not compared
  //   riseInProgress  true / false from riverState; null when it is not fresh or its riseStatus is 'unknown'
  //   pathOnlyFalls   forecastOnlyFalls of the usable window from the check time; null without a usable forecast
  function noaaAgainstGauge(river, forecastRows, issued, now) {
    const blank = { code: 'unknown', notTracking: false, reason: null, issued: null, issueAgeMinutes: null, readingTime: null, gaugeCfs: null, compared: false, covered: null, forecastCfs: null, difference: null, first: null, top: null, aboveTopBy: null, aboveTop: null, aboveFirstBy: null, basis: null, threshold: null, line: null, aboveLine: null, riseInProgress: null, pathOnlyFalls: null };
    const clean = path(forecastRows), issue = typeof issued === 'number' && Number.isFinite(issued) && Math.abs(issued) <= 8640000000000000 ? new Date(issued).toISOString() : issued;
    const fc = clean && typeof now === 'number' && Number.isFinite(now) ? forecast(clean, issue, now) : null;
    if (!fc?.usable) return { ...blank, reason: fc?.reason || 'NOAA river forecast unavailable', issued: fc?.issued ?? null };
    const known = { ...blank, issued: fc.issued, issueAgeMinutes: Math.floor((now - fc.issued) / MIN), pathOnlyFalls: forecastOnlyFalls(fc), first: { t: clean[0].t, q: clean[0].q } };
    const reading = river?.available ? river.reading : null;
    if (!reading || typeof reading.t !== 'number' || !Number.isFinite(reading.t) || typeof reading.q !== 'number' || !Number.isFinite(reading.q)) return { ...known, reason: 'No gauge reading is available to compare' };
    const riseInProgress = river.fresh && river.riseStatus !== 'unknown' ? river.riseStatus === 'in-progress' : null;
    const withReading = { ...known, readingTime: reading.t, gaugeCfs: reading.q, riseInProgress };
    const threshold = thresholdAt(reading.t), ahead = reading.t < clean[0].t, expected = ahead ? null : interpolateGap(clean, reading.t, 6);
    if (!threshold || (!ahead && !expected)) return { ...withReading, threshold, reason: 'The NOAA forecast path does not cover the time of the newest gauge reading' };
    const line = threshold.cfs * WATCH.seasonalFraction;
    // The highest value from the reading's time on; a strict comparison keeps the earliest on a tie.
    const candidates = ahead ? clean : [{ t: reading.t, q: expected.q }, ...clean.filter(r => r.t > reading.t)];
    const top = candidates.reduce((best, r) => r.q > best.q ? r : best), aboveTopBy = reading.q - top.q, aboveTop = aboveTopBy >= line - EPS;
    const aboveFirstBy = ahead ? reading.q - clean[0].q : null, difference = ahead ? null : reading.q - expected.q;
    const rising = river.fresh === true && !!river.lastHour && river.lastHour.label === 'rising';
    const basis = ahead ? (aboveTop ? 'above-highest' : aboveFirstBy >= line - EPS && rising ? 'above-first-and-rising' : null) : difference >= line - EPS ? 'at-reading-time' : null;
    const aboveLine = basis !== null;
    const code = !aboveLine ? 'within-line' : riseInProgress === true ? 'not-tracking' : riseInProgress === false ? 'above-line' : 'unknown';
    return { ...withReading, code, notTracking: code === 'not-tracking', reason: code === 'unknown' ? 'The gauge is above the NOAA forecast, but whether a rise is in progress cannot be told' : null, compared: true, covered: !ahead, forecastCfs: ahead ? null : expected.q, difference, top: { t: top.t, q: top.q }, aboveTopBy, aboveTop, aboveFirstBy, basis, threshold, line, aboveLine };
  }
  // watchWithLastHour(watch, river) -- makes the earlier-forecast comparison's "rising" word follow the River block.
  //   watch  the object surpriseWatch(...) returned (surpriseWatch itself is unchanged: on its own, its
  //          'outpacing' still means the near-three-hour change is above zero)
  //   river  the object riverState(...) returned
  // Returns a copy of `watch` with one added key, lastHourLabel ('rising' | 'falling' | 'about level' | null).
  // For the two "above the earlier forecast" codes, code becomes 'outpacing' ONLY when lastHourLabel is
  // 'rising', otherwise 'above-prior'. Every other code is returned as it was. When lastHourLabel is null the
  // direction cannot be told: the page must print neither "rising" nor "not rising".
  function watchWithLastHour(watch, river) {
    if (!watch || typeof watch !== 'object') return { ...watchUnknown('Earlier-forecast comparison is unavailable'), lastHourLabel: null };
    const label = river?.fresh && river.lastHour ? river.lastHour.label : null;
    const above = watch.code === 'outpacing' || watch.code === 'above-prior';
    return { ...watch, code: above ? (label === 'rising' ? 'outpacing' : 'above-prior') : watch.code, lastHourLabel: label };
  }
  // tideRequest(now) -- how far back the tide request must start so the extreme that just passed is in hand.
  // Returns { beginDate, rangeHours }: beginDate is the GMT calendar date 'YYYYMMDD' of the moment 24 hours
  // before `now` (so the request starts 24 to 48 hours back) and rangeHours is 192 (at least 6 days ahead).
  // Use them as begin_date and range with time_zone=gmt. Null when `now` is not a valid time.
  function tideRequest(now) {
    if (typeof now !== 'number' || !Number.isFinite(now) || Math.abs(now) > 8640000000000000 - 24 * H) return null;
    return { beginDate: new Date(now - 24 * H).toISOString().slice(0, 10).replace(/-/g, ''), rangeHours: 192 };
  }
  // tideState(rows, now) -- the Tide block.
  //   rows  the array D.tides(...) returns ([{ t, v, type: 'H' | 'L' }, ...]), INCLUDING past extremes; pass
  //         null when the feed failed or could not be parsed
  //   now   the device's check time
  // Returns { available, reason, last, minutesSinceLast, direction, next }:
  //   available         false when no extreme after `now` is in hand (failed, empty or ended feed): show
  //                     "unavailable", never an empty list
  //   reason            plain words when not available or when direction is null; else null
  //   last              { t, v, type } the last high or low at or before `now` (kept after it passes); null when
  //                     the predictions do not reach back that far
  //   minutesSinceLast  whole minutes from `last` to `now`; null without `last`
  //   direction         'rising' after a low, 'falling' after a high; null without `last`, or when the highs
  //                     and lows around `now` do not alternate (a broken list is not guessed at)
  //   next              the next one or two extremes after `now`, soonest first
  function tideState(rows, now) {
    const none = reason => ({ available: false, reason, last: null, minutesSinceLast: null, direction: null, next: [] });
    if (!Array.isArray(rows) || typeof now !== 'number' || !Number.isFinite(now)) return none('Tide predictions unavailable');
    const clean = rows.filter(r => r && typeof r.t === 'number' && Number.isFinite(r.t) && typeof r.v === 'number' && Number.isFinite(r.v) && (r.type === 'H' || r.type === 'L'))
      .map(r => ({ t: r.t, v: r.v, type: r.type })).sort((a, b) => a.t - b.t);
    if (clean.some((r, i) => i && r.t === clean[i - 1].t)) return none('Tide predictions contain duplicate times');
    const next = clean.filter(r => r.t > now).slice(0, 2), last = clean.filter(r => r.t <= now).at(-1) || null;
    if (!next.length) return none(clean.length ? 'Tide predictions do not reach past the check time' : 'Tide predictions unavailable');
    const around = [last, ...next].filter(Boolean), alternates = around.every((r, i) => !i || r.type !== around[i - 1].type);
    const direction = last && alternates ? (last.type === 'L' ? 'rising' : 'falling') : null;
    return { available: true, reason: direction ? null : last ? 'Tide highs and lows do not alternate; direction withheld' : 'Tide predictions do not reach back to the last high or low', last, minutesSinceLast: last ? Math.floor((now - last.t) / MIN) : null, direction, next };
  }
  // rainBlockState(bin) -- missing against zero for one six-hour forecast-rain block.
  //   bin  one element of D.rainBins(...), or null / undefined when the point's feed failed
  // Returns { status, mm }: 'missing' (mm null: no value, incomplete coverage or no feed -- draw "no data"),
  // 'zero' (a complete block forecast to be exactly 0) or 'amount' (a complete block above 0).
  function rainBlockState(bin) {
    const mm = bin && bin.complete === true && typeof bin.mm === 'number' && Number.isFinite(bin.mm) && bin.mm >= 0 ? bin.mm : null;
    return mm === null ? { status: 'missing', mm: null } : { status: mm === 0 ? 'zero' : 'amount', mm };
  }
  // suspectZeroRain(report) -- the observed-rain consistency flag, computed only from what the table shows.
  //   report  the object D.rrmRain(...) returned, or null
  // Returns { evaluated, totals24In, flags }, the arrays in the order of report.stations:
  //   evaluated   true only when all three listed gauges have a 24-hour total; otherwise no row is flagged
  //   totals24In  each gauge's 24-hour total in inches, null when unavailable
  //   flags       true for a gauge whose 24-hour total is exactly 0 while BOTH others are at least 0.25 inch
  function suspectZeroRain(report) {
    const stations = Array.isArray(report?.stations) ? report.stations : [], column = Array.isArray(report?.windows) ? report.windows.indexOf(24) : -1;
    const totals24In = stations.map(s => { const v = s && s.available === true && Array.isArray(s.values) && column >= 0 ? s.values[column] : null; return typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null; });
    const evaluated = totals24In.length === 3 && totals24In.every(v => v !== null);
    return { evaluated, totals24In, flags: totals24In.map((v, i) => evaluated && v === 0 && totals24In.every((other, j) => j === i || other >= RAIN_RULES.suspectZeroOtherGaugesIn - EPS)) };
  }
  // drySeasonContext(t) -- true when the Pacific month of `t` is May to October (the dry-season rain context
  // applies), false from November to April, null when `t` is not a valid time.
  function drySeasonContext(t) {
    const month = pacificMonth(t);
    return month === null ? null : RAIN_RULES.dryMonths.includes(month);
  }
  // LOOKBACK_RULES (frozen). countHorizonHours: the longest span the "falling" and "may have peaked" look-back
  // counts cover (their "within 24 hours" figure). A count is not printed once the newest reading is more than
  // this many hours of readings past the point the count is taken from.
  const LOOKBACK_RULES = Object.freeze({ countHorizonHours: 24 });
  // countAnchor(rows, river) -- the point a look-back count is counted from, in reading time. It changes no rule
  // of riverState; it only says where the count printed beside a state starts and whether it still applies.
  //   rows   the observed readings handed to riverState
  //   river  the object riverState(rows, now) returned
  // Returns null unless river.state is 'falling' or 'may-have-peaked' (so also null when not fresh); otherwise
  // { state, t, q, minutesSince, withinHorizon }:
  //   state 'falling'          t, q: the EARLIEST reading after river.high that was at least fallingFraction (5%)
  //                            below it (the newest reading itself when it is the first that far below)
  //   state 'may-have-peaked'  t: the 2-hour mark, river.high.t plus peakMinutes (a moment, not necessarily a
  //                            reading); q is null
  //   minutesSince             whole minutes of READING time from t to the newest reading
  //   withinHorizon            t is at most countHorizonHours before the newest reading (exactly 24 hours is inside)
  function countAnchor(rows, river) {
    if (!river || river.fresh !== true || !river.high || !river.reading || (river.state !== 'falling' && river.state !== 'may-have-peaked')) return null;
    const newest = river.reading.t, horizon = LOOKBACK_RULES.countHorizonHours * H;
    const anchor = (t, q) => ({ state: river.state, t, q, minutesSince: Math.floor((newest - t) / MIN), withinHorizon: newest - t <= horizon });
    if (river.state === 'may-have-peaked') return anchor(river.high.t + RIVER_RULES.peakMinutes * MIN, null);
    const clean = gaugeReadings(rows, newest);
    const first = clean ? clean.find(r => r.t > river.high.t && river.high.q - r.q >= RIVER_RULES.fallingFraction * river.high.q - EPS) : null;
    return first ? anchor(first.t, first.q) : null;
  }
  // EVIDENCE (deeply frozen). Every count the page prints about past rises is read from here; nothing is
  // typed into a sentence by hand. Each entry carries its numbers, its period and a `source` in plain words.
  // Every entry is a look-back on past years, not a forecast: print EVIDENCE.caveat beside any of them.
  // Fields ending "AsComputed" hold the look-back's own figures where the sentence uses them rounded to the
  // nearest half hour.
  const EVIDENCE = deepFreeze({
    caveat: 'A look-back on past years, not a forecast.',
    rises: { count: 172, period: '2011 to 2023', place: 'Samish River gauge near Burlington (USGS 12201500)', readings: '15-minute readings' },
    // After the first hour of readings with no new high: higher again within a day, and by more than 5%.
    pause: { rises: 172, afterMinutes: 60, withinHours: 24, higherAgain: 67, higherByMoreThan5Percent: 42, period: '2011 to 2023',
      source: 'Look-back on 172 Samish rises, 2011 to 2023, 15-minute gauge readings: the first time each rise went one hour of readings with no new high, and what the river did in the following 24 hours.' },
    // After the first two hours of readings with no new high: later more than 5% above that high.
    peak2h: { rises: 172, afterMinutes: 120, within12h: 19, aboutOneIn12h: 9, within24h: 30, aboutOneIn24h: 6, period: '2011 to 2023',
      source: 'Look-back on 172 Samish rises, 2011 to 2023, 15-minute gauge readings: the first time each rise went two hours of readings with no new high, and whether the river later climbed more than 5% above that high within 12 and within 24 hours.' },
    // After the first reading at least 5% below the high so far: later more than 5% above that high.
    falling: { rises: 172, belowHighFraction: 0.05, within12h: 10, aboutOneIn12h: 17, within24h: 21, aboutOneIn24h: 8, period: '2011 to 2023',
      source: 'Look-back on 172 Samish rises, 2011 to 2023, 15-minute gauge readings: the first time each rise read at least 5% below its highest reading so far, and whether the river later climbed more than 5% above that high within 12 and within 24 hours.' },
    // Hours from the seasonal number being passed to the highest reading of the rise.
    timing: { period: '2011 to 2023',
      all: { rises: 172, medianHours: 5.5, middleHalfHours: [3, 9], middleHalfHoursAsComputed: [3.2, 9.1], under2h: 18, atLeast16h: 22 },
      dry: { rises: 52, months: 'May to October', medianHours: 6, medianHoursAsComputed: 5.9, middleHalfHours: [3.5, 8], middleHalfHoursAsComputed: [3.4, 8.1], over8h: 13, atLeast16h: 5 },
      source: 'Look-back on 172 Samish rises, 2011 to 2023: hours from the hour the 24-hour rise passed the seasonal number to the highest 15-minute reading of that rise.' },
    // For rises whose highest reading had not yet come at each stage: the further hours to it.
    wait: { period: '2011 to 2023', stagesHours: [0, 2, 4, 6, 8, 12], risesStillWaiting: [167, 150, 109, 74, 49, 29], medianMoreHours: [5.5, 4, 3.5, 4, 5.8, 7], lowerQuartileMoreHours: [3.2, 2, 1.5, 1.5, 2, 4], upperQuartileMoreHours: [9.4, 8, 8.8, 11.9, 12.8, 13.8], typicalWaitHours: [3.5, 7], oneInFourAtLeastHours: 8,
      source: 'Look-back on 172 Samish rises, 2011 to 2023: for the rises whose highest 15-minute reading had not yet come 0, 2, 4, 6, 8 and 12 hours after the seasonal number was passed, the further hours to that reading (the lower quarter, the middle value and the upper quarter at each stage).' },
    // Every 15-minute reading that was a new high for its rise: how far away the highest reading of the rise then was.
    afterNewHigh: { readings: 4027, rises: 172, withinHours: 2, withinPercent: 24.9, aboutOneInWithin: 4, atLeastHours: 8, atLeastPercent: 26.6, aboutOneInAtLeast: 4, period: '2011 to 2023',
      source: 'Look-back on 172 Samish rises, 2011 to 2023: every 15-minute reading, from the seasonal number being passed to the highest reading, that was a new high for its rise (4,027 readings), and the further hours from each to the highest reading of that rise.' },
    // Rain and a two-hour pause, and the one storm the sentence beside "may have peaked" names.
    rainPause: { afterMinutes: 120, radarWindowHours: 3, radarAtLeastMm: 0.5, pausesWithRadar: 62, rainingPauses: 23, rainingRoseAgain: 4, dryPauses: 39, dryRoseAgain: 2, storm: '29 September 2026', rainEnded: 'about 2 pm', riverRoseUntil: '9 to 10 pm', highestHourlyCfs: 191, period: '2011 to 2023, and the rise of 29 September 2026',
      source: 'Look-back on the two-hour pauses of 172 Samish rises, 2011 to 2023, that have a radar reading (62 pauses): rain over the basin in the three hours before the pause against whether the river rose again. And the rise of 29 September 2026: the last hour with rain on the basin radar ended at 2 pm, and the highest hourly flow came at 9 and 10 pm.' },
    // NOAA's river forecast shifted to start at the latest gauge reading, against the forecast as issued.
    aligned: { rises: 66, falseAlertEpisodesAligned: 29, falseAlertEpisodesAsIssued: 38, warned12hEitherWay: 36, leadHours: 12, period: 'October 2020 to September 2026',
      source: 'Look-back at the Samish over every decision time from October 2020 to September 2026 (six water years, 66 rises): the NOAA river forecast read as issued, against the same forecast shifted to start at the latest gauge reading.' },
    // NOAA's river forecast before the dry-season rises.
    noaaDry: { rises: 32, shown12hAhead: 25, notShown: 7, notShownIncludes: '29 September 2026', leadHours: 12, period: 'May to October rises of July 2018 to early October 2026',
      source: 'Look-back on the 32 May to October Samish rises of July 2018 to early October 2026: the NOAA river forecast read hour by hour against the seasonal number.' },
    // The river forecast centre's basin rain forecast in the dry season. NOT the two points shown on the page.
    rainContext: { thresholdIn: 0.75, windowHours: 24, seasons: 8.46, perSeason: 5, occasions: 45, followed: 23, riseCfs: 100, followedWithinHours: 36, withNoNoaaRise: 26, withNoNoaaRiseFollowed: 7, aboutOneInWithNoNoaaRise: 4, risesNoaaDidNotShow: 7, ofThoseRainForecastAhead: 4, leadHours: 12, aheadYears: '2024 to 2026', aheadIncludes: '29 September 2026', risesWithForecast: 32, risesWithLessRain: 10, period: 'dry seasons of July 2018 to early October 2026',
      source: 'Look-back over the dry seasons (May to October) of July 2018 to early October 2026: the river forecast centre’s basin-average rain forecast for the next 24 hours, read hour by hour. This is a different rain forecast from the two National Weather Service points shown on this page and has not been checked against them.' }
  });
  root.SamishData = { H, WATCH, number, time, nwpsSeries, usgs, duration, rain, rainWindow, rainBins, rrmProductId, rrmRain, basinGeometry, gaugePoint, gridPoint, gridCellWithinBasin, radarCapabilities, csvCell, stormRecord, stormCsv, interpolate, atBefore, thresholdAt, recentChange, planningScreen, lineRelation, makeSnapshot, surpriseWatch, forecastRevision, forecast, tides,
    RIVER_RULES, RAIN_RULES, LOOKBACK_RULES, EVIDENCE, riverState, countAnchor, lastHourLabel, forecastOnlyFalls, noaaAgainstGauge, watchWithLastHour, tideRequest, tideState, rainBlockState, suspectZeroRain, drySeasonContext };
})(globalThis);
