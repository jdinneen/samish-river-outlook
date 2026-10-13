"""Browser and numerical contract checks with synthetic feeds.

Run with its built-in local server: python tests/check_site.py
An explicit local URL remains supported as the first argument.
Nothing here calls scientific models or modifies provider data.
"""
import json
import os
import re
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SERVER = None
if len(sys.argv) > 1:
    URL = sys.argv[1]
else:
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass
    SERVER = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()
    URL = f'http://127.0.0.1:{SERVER.server_port}'
NOW = datetime.now(timezone.utc).replace(microsecond=0)
ISO = lambda h=0: (NOW + timedelta(hours=h)).isoformat()
RADAR_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="600" viewBox="0 0 900 600">
<rect width="900" height="600" fill="#11191b"/><g fill="none" stroke-linecap="round"><path d="M180 80 C360 110 560 220 780 270" stroke="#70c46e" stroke-width="72"/><path d="M280 120 C420 165 570 215 700 250" stroke="#f4d44d" stroke-width="45"/><path d="M390 165 C500 190 570 215 640 235" stroke="#dc6b3d" stroke-width="24"/></g><text x="20" y="35" font-family="sans-serif" font-size="22" fill="white">Synthetic KATX WMS fixture</text></svg>"""
LEGEND_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="30" viewBox="0 0 500 30"><rect width="500" height="30" fill="white"/><text x="5" y="20" font-family="sans-serif" font-size="12">low</text><rect x="35" y="7" width="130" height="15" fill="#70c46e"/><rect x="165" y="7" width="130" height="15" fill="#f4d44d"/><rect x="295" y="7" width="130" height="15" fill="#dc6b3d"/><text x="435" y="20" font-family="sans-serif" font-size="12">high</text></svg>"""

# ---- Version 7 fixture: the Samish rise of 29 September 2026, 15-minute readings ----
# REAL (U.S. Geological Survey gauge 12201500, provisional, cubic feet per second):
#   SEPT29_CFS            every quarter-hour from 8:00 AM Pacific on 29 September to 2:00 AM on 30 September
#   SEPT29_BEFORE_0800    7:00 to 7:45 AM, worked back from the one-hour changes of the 8:00 to 8:45 AM readings
#   SEPT30_HOURLY         the hourly readings from 3:00 to 8:00 AM on 30 September
# INVENTED (shape only, so the 24-hour low and the 48-hour memory can be computed): everything before
#   7:00 AM on 29 September. It is a slow recession to a single low of 15.9 cfs at 1:00 AM, the value of
#   the real 24-hour low, followed by a smooth climb to the 7:00 AM reading. Its timing is not real.
# Nothing here is fetched; every time is before 6 October 2026.
PACIFIC_DAYLIGHT = timezone(timedelta(hours=-7))
SEPT29_0800 = datetime(2026, 9, 29, 8, 0, tzinfo=PACIFIC_DAYLIGHT)
SEPT29_CFS = [
    46.0, 49.6, 53.4, 57.4, 62.5, 66.8, 71.3, 74.8, 78.3, 83.2, 88.3, 92.2,            # 8:00 to 10:45 AM
    97.5, 103.0, 107.0, 113.0, 119.0, 124.0, 128.0, 133.0, 137.0, 142.0, 147.0, 152.0,  # 11:00 AM to 1:45 PM
    157.0, 159.0, 161.0, 163.0, 163.0, 164.0, 164.0, 164.0, 164.0, 164.0, 166.0, 166.0,  # 2:00 to 4:45 PM
    168.0, 170.0, 170.0, 172.0, 174.0, 176.0, 177.0, 179.0, 181.0, 183.0, 183.0, 185.0,  # 5:00 to 7:45 PM
    187.0, 187.0, 189.0, 189.0, 191.0, 191.0, 191.0, 191.0, 191.0, 191.0, 191.0, 191.0,  # 8:00 to 10:45 PM
    189.0, 189.0, 187.0, 185.0, 185.0, 183.0, 181.0, 179.0, 177.0, 176.0, 174.0, 172.0,  # 11:00 PM to 1:45 AM
    170.0]                                                                               # 2:00 AM
SEPT29_BEFORE_0800 = [36.0, 38.4, 40.0, 43.4]
SEPT30_HOURLY = [163.0, 154.0, 147.0, 138.0, 132.0, 125.0]
# NOAA tide predictions for Bellingham (station 9449211), times in GMT, feet above mean lower low water.
# These are astronomical predictions, not observations. 2026-09-30 01:46 GMT is 6:46 PM Pacific on 29 September.
SEPT29_TIDES = {'predictions': [
    {'t': '2026-09-28 00:58', 'v': '8.176', 'type': 'H'}, {'t': '2026-09-28 07:33', 'v': '0.291', 'type': 'L'},
    {'t': '2026-09-28 14:09', 'v': '7.668', 'type': 'H'}, {'t': '2026-09-28 19:39', 'v': '3.674', 'type': 'L'},
    {'t': '2026-09-29 01:21', 'v': '8.2', 'type': 'H'}, {'t': '2026-09-29 08:12', 'v': '-0.603', 'type': 'L'},
    {'t': '2026-09-29 15:08', 'v': '7.802', 'type': 'H'}, {'t': '2026-09-29 20:21', 'v': '4.593', 'type': 'L'},
    {'t': '2026-09-30 01:46', 'v': '8.168', 'type': 'H'}, {'t': '2026-09-30 08:56', 'v': '-1.224', 'type': 'L'},
    {'t': '2026-09-30 16:13', 'v': '7.846', 'type': 'H'}, {'t': '2026-09-30 21:07', 'v': '5.443', 'type': 'L'},
    {'t': '2026-10-01 02:13', 'v': '8.071', 'type': 'H'}, {'t': '2026-10-01 09:44', 'v': '-1.507', 'type': 'L'},
    {'t': '2026-10-01 17:29', 'v': '7.84', 'type': 'H'}, {'t': '2026-10-01 22:02', 'v': '6.135', 'type': 'L'}]}

def sept29_readings():
    """Gauge readings as the page holds them: [{'t': epoch milliseconds, 'q': cfs}], oldest first."""
    ms = lambda moment: int(moment.timestamp() * 1000)
    quarter = timedelta(minutes=15)
    rows = []
    lead_start = SEPT29_0800 - timedelta(hours=56)   # midnight Pacific at the start of 27 September
    low_time = SEPT29_0800 - timedelta(hours=7)      # 1:00 AM Pacific on 29 September
    moment = lead_start
    while moment < low_time:                         # invented recession, 17.6 down to 16.0 cfs
        share = (moment - lead_start) / (low_time - quarter - lead_start)
        rows.append({'t': ms(moment), 'q': round(17.6 - 1.6 * share, 1)})
        moment += quarter
    rows.append({'t': ms(low_time), 'q': 15.9})      # the real 24-hour low, at an invented time
    for step in range(1, 24):                        # invented climb, 1:15 to 6:45 AM
        rows.append({'t': ms(low_time + step * quarter), 'q': round(16 + 20 * (step / 24) ** 2, 1)})
    for step, flow in enumerate(SEPT29_BEFORE_0800):
        rows.append({'t': ms(SEPT29_0800 - (4 - step) * quarter), 'q': flow})
    for step, flow in enumerate(SEPT29_CFS):
        rows.append({'t': ms(SEPT29_0800 + step * quarter), 'q': flow})
    for step, flow in enumerate(SEPT30_HOURLY):
        rows.append({'t': ms(SEPT29_0800 + timedelta(hours=19 + step)), 'q': flow})
    assert all(later['t'] > earlier['t'] for earlier, later in zip(rows, rows[1:]))
    assert max(row['t'] for row in rows) < ms(datetime(2026, 10, 6, tzinfo=timezone.utc))
    return rows

# ---- Version 7 page replay: the feeds as the page would have been handed them on 29 September 2026 ----
# REAL: the gauge readings (sept29_readings), the Bellingham tide predictions (SEPT29_TIDES), and the NOAA river
#   forecasts below: the five issues NOAA stamped for the Samish River near Burlington from 27 to 30 September
#   2026, as issued (issue stamp, time of the first forecast point, then one value every six hours, in cfs).
#   A real NOAA path begins at the next six-hourly point AFTER its issue stamp, so for two to three hours after
#   each issue the newest gauge reading is earlier than the path's first point. Each frame is served the newest
#   issue stamped at or before its check time (assumption: an issue can be read the minute it is stamped).
#   Every value is dated before 6 October 2026.
# INVENTED: the forecast rain, the observed-rain report and the radar frames in a replay frame.
REAL_NOAA_ISSUES = [
    ('2026-09-27T14:53:00+00:00', '2026-09-27T18:00:00+00:00', [21.68, 20.64, 19.69, 18.9, 17.9, 16.91, 15.97, 21.27, 41.13, 50.63, 35.82, 26.05, 23.32, 22.76, 22.62, 22.36, 22.1, 21.92, 21.93, 21.73, 21.56, 21.42, 21.3, 21.02, 20.83, 20.69, 20.55, 20.43, 20.25, 20.08, 19.94, 19.96, 20]),
    ('2026-09-28T15:37:00+00:00', '2026-09-28T18:00:00+00:00', [17.75, 17.46, 17.09, 24.59, 42.21, 39.5, 27.56, 21.12, 19.18, 18.67, 18.56, 18.53, 18.53, 18.45, 18.42, 18.41, 18.41, 18.41, 18.33, 17.93, 17.74, 17.69, 17.6, 17.56, 17.41, 17.33, 17.23, 17.56, 17.74]),
    ('2026-09-29T15:19:00+00:00', '2026-09-29T18:00:00+00:00', [58.48, 49.72, 33.14, 27.88, 26.71, 26.29, 26.02, 25.77, 25.53, 25.13, 24.82, 24.55, 24.45, 24.21, 23.94, 23.54, 23.22, 22.89, 22.6, 22.42, 22.2, 22.04, 21.77, 21.71, 21.64]),
    ('2026-09-29T21:36:00+00:00', '2026-09-30T00:00:00+00:00', [91.82, 44.23, 37.72, 35.83, 35.04, 34.41, 33.88, 33.15, 32.56, 32.11, 31.65, 31.16, 30.61, 30.08, 29.65, 29.27, 28.68, 28.28, 27.92, 27.55, 27.18, 26.75, 26.56, 26.29]),
    ('2026-09-30T15:10:00+00:00', '2026-09-30T18:00:00+00:00', [100.31, 71.06, 50.36, 47.36, 45.72, 44.51, 43.46, 42.61, 41.84, 41.03, 40.26, 39.58, 38.81, 38.12, 37.48, 36.8, 36.15, 35.6, 34.95, 34.53, 34.02])]

def noaa_issue_at(check):
    """(issue time, [(time, cfs), ...]) of the newest real NOAA issue stamped at or before `check`."""
    held = [row for row in REAL_NOAA_ISSUES if datetime.fromisoformat(row[0]) <= check]
    assert held, 'no real NOAA issue is held for that check time'
    stamp, first_point, values = held[-1]
    points = [((datetime.fromisoformat(first_point) + timedelta(hours=6 * step)).isoformat(), value) for step, value in enumerate(values)]
    assert points[-1][0] < '2026-10-06', 'nothing dated on or after 6 October 2026 is used'
    return datetime.fromisoformat(stamp), points

REPLAY_RAIN_MM = [2.54, 1.27, 0.51, 0, 0, 0, 0]   # invented six-hour forecast amounts from the check time

def pacific(day, hour, minute=0):
    """A Pacific daylight time on September `day`, 2026 (day 30 is 30 September)."""
    return datetime(2026, 9, day, hour, minute, tzinfo=PACIFIC_DAYLIGHT)

def replay_payload(check, newest=None, first=None, hole=None, noaa_path=None, noaa_issue=None, rain_mm=None, rrm_rows=None, tides=None, extra=None):
    """Every feed as the page would be handed it at `check`, the fixed device clock of a replay frame.

    newest   the newest gauge reading served. Default: the top of the hour at or before `check`, so a page
             opened at 7:20 PM holds the 7:00 PM reading, 20 minutes old. It may be LATER than `check`, to
             act out a device whose clock is behind the gauge.
    noaa_path, noaa_issue   a SYNTHETIC NOAA path and issue time in place of the real issue for that moment.
    first    drop every reading before this time (shortens the history the page can compare).
    hole     (start, end): drop the readings from start to end inclusive.
    extra    [(time, cfs), ...]: INVENTED readings added after the real ones, to carry a frame past the end of
             the real record. They are not gauge data.
    """
    newest = newest or check.replace(minute=0, second=0, microsecond=0)
    stamp = lambda moment: moment.astimezone(timezone.utc).isoformat()
    ms = lambda moment: int(moment.timestamp() * 1000)
    readings = [row for row in sept29_readings() + [{'t': ms(moment), 'q': flow_cfs} for moment, flow_cfs in (extra or [])] if row['t'] <= ms(newest)
                and (first is None or row['t'] >= ms(first))
                and (hole is None or not ms(hole[0]) <= row['t'] <= ms(hole[1]))]
    when = lambda row: datetime.fromtimestamp(row['t'] / 1000, timezone.utc).isoformat()
    flow = lambda rows, issued: {'primaryName': 'River Discharge', 'primaryUnits': 'cfs', 'secondaryName': 'Stage',
                                 'secondaryUnits': 'ft', 'issuedTime': issued, 'data': rows}
    real_issue, real_path = noaa_issue_at(check) if noaa_path is None or noaa_issue is None else (None, None)
    issue = stamp(noaa_issue or real_issue)
    amounts = REPLAY_RAIN_MM if rain_mm is None else rain_mm
    gauges = rrm_rows or ['Padilla Bay Farm 0.01 0.02 0.05 0.10 0.20 0.30 0.40', 'Burlington 0.00 0.01 0.03 0.08 0.18 0.28 0.38',
                          'Sedro Wooley RAWS M 0.02 0.04 0.09 0.19 0.29 0.39']
    radar_times = ','.join(stamp(check - timedelta(minutes=minutes)) for minutes in [45, 30, 15])
    base = fixtures(check)
    return {
        'nwps': {'observed': flow([{'validTime': when(row), 'primary': row['q'], 'secondary': 4} for row in readings], issue),
                 'forecast': flow([{'validTime': t, 'primary': q, 'secondary': 4} for t, q in (noaa_path or real_path)], issue)},
        'usgs': {'features': [{'properties': {'monitoring_location_id': 'USGS-12201500', 'parameter_code': '00060',
                 'time': when(row), 'value': str(row['q']), 'unit_of_measure': 'ft^3/s'},
                 'geometry': {'type': 'Point', 'coordinates': [-122.3382169, 48.54594127]}} for row in readings]},
        # Rain blocks start exactly at the check time, so each six-hour block on the page is one value here.
        'rain': {'properties': {'updateTime': stamp(check - timedelta(hours=1)), 'quantitativePrecipitation': {
                 'uom': 'wmoUnit:mm', 'values': [{'validTime': stamp(check + timedelta(hours=6 * i)) + '/PT6H', 'value': mm}
                                                 for i, mm in enumerate(amounts)]}}, 'geometry': base['rain']['geometry']},
        'rrm_index': {'@graph': [{'id': '123e4567-e89b-42d3-a456-426614174000', 'issuanceTime': stamp(check - timedelta(minutes=30))}]},
        'rrm': {'id': '123e4567-e89b-42d3-a456-426614174000', 'issuanceTime': stamp(check - timedelta(minutes=30)), 'productCode': 'RRM',
                'issuingOffice': 'KSEW', 'productText': '000\nRRMSEW\nNational Weather Service Seattle WA\n\n' + '\n'.join(gauges) + '\n'},
        'basin': base['basin'],
        'capabilities': '<?xml version="1.0"?><WMS_Capabilities xmlns="http://www.opengis.net/wms"><Capability><Layer>' + ''.join(
            f'<Layer><Name>{layer}</Name><Dimension name="time">{radar_times}</Dimension></Layer>'
            for layer in ['katx_sr_bref', 'katx_boha', 'katx_bdsa']) + '</Layer></Capability></WMS_Capabilities>',
        'tides': SEPT29_TIDES if tides is None else tides}

def synthetic_gauge_payload(check, readings):
    """The synthetic feeds of fixtures(check) with the gauge replaced by `readings`, [(time, cfs), ...]. Nothing here is real."""
    feeds = fixtures(check)
    stamp = lambda moment: moment.astimezone(timezone.utc).isoformat()
    feeds['nwps']['observed'] = {'primaryName': 'River Discharge', 'primaryUnits': 'cfs', 'secondaryName': 'Stage', 'secondaryUnits': 'ft',
                                 'issuedTime': stamp(check), 'data': [{'validTime': stamp(moment), 'primary': flow_cfs, 'secondary': 4} for moment, flow_cfs in readings]}
    feeds['usgs'] = {'features': [{'properties': {'monitoring_location_id': 'USGS-12201500', 'parameter_code': '00060', 'time': stamp(moment),
                     'value': str(flow_cfs), 'unit_of_measure': 'ft^3/s'}, 'geometry': {'type': 'Point', 'coordinates': [-122.3382169, 48.54594127]}}
                     for moment, flow_cfs in readings]}
    return feeds

def fixtures(now=None):
    """Synthetic feeds around `now` (default: the moment the suite started)."""
    ISO = lambda h=0: ((now or NOW) + timedelta(hours=h)).isoformat()
    def series(rows):
        return {'primaryName': 'River Discharge', 'primaryUnits': 'kcfs',
                'secondaryName': 'Stage', 'secondaryUnits': 'ft',
                'issuedTime': ISO(-1), 'data': [
                    {'validTime': ISO(h), 'primary': q / 1000, 'secondary': 4}
                    for h, q in rows]}
    radar_times = ','.join(ISO(minutes / 60) for minutes in [-45, -30, -15])
    capabilities = '<?xml version="1.0"?><WMS_Capabilities xmlns="http://www.opengis.net/wms"><Capability><Layer>' + ''.join(
        f'<Layer><Name>{layer}</Name><Dimension name="time">{radar_times}</Dimension></Layer>'
        for layer in ['katx_sr_bref', 'katx_boha', 'katx_bdsa']) + '</Layer></Capability></WMS_Capabilities>'
    rain_values = [{'validTime': ISO(h) + '/PT6H', 'value': 5.08} for h in range(0, 42, 6)]
    rain_geometry = {'type': 'Polygon', 'coordinates': [[[-122.29, 48.58], [-122.25, 48.58], [-122.25, 48.61], [-122.29, 48.61], [-122.29, 48.58]]]}
    rrm_text = f"""000
RRMSEW
National Weather Service Seattle WA
{(now or NOW).strftime('%H%M %p %a %b %d %Y')}

Padilla Bay Farm 0.01 0.02 0.05 0.10 0.20 0.30 0.40
Burlington 0.00 0.01 0.03 0.08 0.18 0.28 0.38
Sedro Wooley RAWS M 0.02 0.04 0.09 0.19 0.29 0.39
"""
    return {
        'nwps': {'observed': series([(h, 100 + h) for h in range(-48, 1)]),
                 'forecast': series([(h, 150 - abs(h - 24)) for h in range(-6, 79, 6)])},
        'usgs': {'features': [{'properties': {'monitoring_location_id': 'USGS-12201500',
                 'parameter_code': '00060', 'time': ISO(), 'value': '101', 'unit_of_measure': 'ft^3/s'},
                 'geometry': {'type': 'Point', 'coordinates': [-122.3382169, 48.54594127]}}]},
        'rain': {'properties': {'updateTime': ISO(-1), 'quantitativePrecipitation': {
                 'uom': 'wmoUnit:mm', 'values': rain_values}}, 'geometry': rain_geometry},
        'rrm_index': {'@graph': [{'id': '123e4567-e89b-42d3-a456-426614174000', 'issuanceTime': ISO(-.5)}]},
        'rrm': {'id': '123e4567-e89b-42d3-a456-426614174000', 'issuanceTime': ISO(-.5), 'productCode': 'RRM', 'issuingOffice': 'KSEW', 'productText': rrm_text},
        'basin': {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[[-122.46, 48.53], [-122.18, 48.53], [-122.16, 48.70], [-122.40, 48.71], [-122.46, 48.53]]]}, 'properties': {}}]},
        'capabilities': capabilities,
        # The low four hours back is the extreme that just passed; the page must keep it.
        'tides': {'predictions': [{'t': ((now or NOW) + timedelta(hours=h)).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M'),
                  'v': str(v), 'type': typ} for h, v, typ in [(-4, 2, 'L'), (2, 8, 'H'), (8, -1, 'L'), (14, 9, 'H'), (20, 1, 'L')]]}}

def saved_snapshot(expected=80):
    points = [NOW + timedelta(hours=h) for h in range(-6, 67, 6)]
    return {
        'issueTime': ISO(-7), 'capturedAt': ISO(-6), 'gaugeTime': ISO(-6),
        'gaugeCfs': 70, 'adjustment': -20,
        'alignedPath': [{'t': int(t.timestamp() * 1000), 'q': 70 if i == 0 else expected} for i, t in enumerate(points)],
        'rawPath': [{'t': int(t.timestamp() * 1000), 'q': 90 if i == 0 else expected + 20} for i, t in enumerate(points)],
    }

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    payload = fixtures()
    original_forecast = json.loads(json.dumps(payload['nwps']['forecast']))
    mode = {'fail': False, 'direct_fail': False, 'radar_fail': False, 'radar_layer_fail': None, 'radar_legend_fail': False, 'rrm_fail': False, 'basin_fail': False, 'basin_malformed_once': False, 'grid_geometry_fail': False, 'grid_outside_basin': False}

    def serve(req, source=None):
        # `source` lets a replay page be served its own feeds and record the addresses it asked for.
        data = source['payload'] if source else payload
        u = req.request.url
        if source is not None and '127.0.0.1' not in u and 'localhost' not in u:
            source.setdefault('requests', []).append(u)
        if '127.0.0.1' in u or 'localhost' in u:
            return req.continue_()
        parsed = urlparse(u)
        query = {key.lower(): value for key, value in parse_qs(parsed.query).items()}
        if 'opengeo.ncep.noaa.gov/geoserver/katx/ows' in u:
            request = query.get('request', [''])[0].lower()
            if mode['fail'] or mode['radar_fail']:
                return req.fulfill(status=503, body='Radar unavailable')
            if request == 'getcapabilities':
                return req.fulfill(status=200, content_type='application/xml', body=data['capabilities'], headers={'Access-Control-Allow-Origin': '*'})
            if request == 'getmap' and mode['radar_layer_fail'] in query.get('layers', []):
                return req.fulfill(status=200, content_type='application/xml', body='<ServiceException>synthetic layer failure</ServiceException>', headers={'Access-Control-Allow-Origin': '*'})
            if request == 'getlegendgraphic' and mode['radar_legend_fail']:
                return req.fulfill(status=503, body='Legend unavailable')
            body = LEGEND_SVG if request == 'getlegendgraphic' else RADAR_SVG
            # no-store: without it the browser may reuse a synthetic image it already holds for the
            # same address and send no request, so an injected legend or layer failure never arrives.
            return req.fulfill(status=200, content_type='image/svg+xml', body=body, headers={'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store'})
        if 'api.water.usgs.gov/nldi/' in u:
            if mode['fail'] or mode['basin_fail']:
                return req.fulfill(status=503, body='Basin unavailable')
            if mode['basin_malformed_once']:
                mode['basin_malformed_once'] = False
                return req.fulfill(status=200, content_type='application/json', body='{}', headers={'Access-Control-Allow-Origin': '*'})
            return req.fulfill(status=200, content_type='application/json', body=json.dumps(data['basin']), headers={'Access-Control-Allow-Origin': '*'})
        if 'api.weather.gov/products/types/RRM/locations/SEW' in u:
            if mode['fail'] or mode['rrm_fail']:
                return req.fulfill(status=503, body='Rain report unavailable')
            return req.fulfill(status=200, content_type='application/json', body=json.dumps(data['rrm_index']), headers={'Access-Control-Allow-Origin': '*'})
        if 'api.weather.gov/products/123e4567-e89b-42d3-a456-426614174000' in u:
            if mode['fail'] or mode['rrm_fail']:
                return req.fulfill(status=503, body='Rain report unavailable')
            return req.fulfill(status=200, content_type='application/json', body=json.dumps(data['rrm']), headers={'Access-Control-Allow-Origin': '*'})
        if mode['fail'] or mode['direct_fail'] and 'waterdata.usgs.gov' in u:
            return req.fulfill(status=503, body='Unavailable')
        if 'api.weather.gov/gridpoints/' in u and mode['grid_geometry_fail']:
            bad_grid = json.loads(json.dumps(data['rain']))
            bad_grid.pop('geometry', None)
            return req.fulfill(status=200, content_type='application/json', body=json.dumps(bad_grid), headers={'Access-Control-Allow-Origin': '*'})
        if 'api.weather.gov/gridpoints/SEW/139,116' in u and mode['grid_outside_basin']:
            bad_grid = json.loads(json.dumps(data['rain']))
            bad_grid['geometry'] = {'type': 'Polygon', 'coordinates': [[[-122.13, 48.58], [-122.09, 48.58], [-122.09, 48.61], [-122.13, 48.61], [-122.13, 48.58]]]}
            return req.fulfill(status=200, content_type='application/json', body=json.dumps(bad_grid), headers={'Access-Control-Allow-Origin': '*'})
        key = 'nwps' if '/nwps/' in u else 'usgs' if 'waterdata.usgs.gov' in u else 'rain' if 'api.weather.gov/gridpoints/' in u else 'tides'
        req.fulfill(status=200, content_type='application/json', body=json.dumps(data[key]), headers={'Access-Control-Allow-Origin': '*'})

    def route(req):
        # One argument only: the browser driver hands a two-argument handler the request as well.
        return serve(req)

    page.route('**/*', route)
    page.goto(URL)
    page.wait_for_function("!document.getElementById('refresh').disabled")
    page.wait_for_function("['Latest retrieved frame','Animating retrieved frames','Unavailable'].includes(document.getElementById('radar-status').textContent)")
    out = Path(os.environ.get('SAMISH_SCREENSHOT_DIR') or tempfile.mkdtemp(prefix='samish-browser-review-'))
    out.mkdir(parents=True, exist_ok=True)
    axe_path = os.environ.get('AXE_PATH')
    if os.environ.get('REQUIRE_AXE') == '1' and not axe_path:
        raise RuntimeError('REQUIRE_AXE=1 but AXE_PATH was not supplied')
    axe_runs = 0
    if axe_path:
        page.add_script_tag(path=axe_path)

    def audit_page(target, label, tabs=('outlook',)):
        """Accessibility audit of `target` in light and dark; returns the number of audits run."""
        if not axe_path:
            return 0
        if not target.evaluate("typeof axe !== 'undefined'"):
            target.add_script_tag(path=axe_path)
        runs = 0
        for scheme in ['light', 'dark']:
            target.emulate_media(color_scheme=scheme)
            target.wait_for_timeout(250)
            for tab in tabs:
                target.locator('#tab-' + tab).click()
                audit = target.evaluate("""async () => await axe.run(document, {
                    runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']}
                })""")
                assert not audit['violations'], {
                    'state': label, 'scheme': scheme, 'tab': tab,
                    'violations': [(v['id'], v['impact'], [(n['target'], n['failureSummary']) for n in v['nodes']]) for v in audit['violations']]
                }
                runs += 1
        target.locator('#tab-outlook').click()
        return runs

    def audit_state(label, tabs=('outlook',)):
        return audit_page(page, label, tabs)

    def screenshot_state(label):
        for scheme in ['light', 'dark']:
            page.emulate_media(color_scheme=scheme)
            for width in [390, 1440]:
                page.set_viewport_size({'width': width, 'height': 960})
                page.locator('#tab-outlook').click()
                page.screenshot(path=str(out / f'state-{label}-{scheme}-{width}.png'), full_page=True)

    result = page.evaluate("""() => {
      const D=SamishData, H=D.H, now=Date.now(), iso=t=>new Date(t).toISOString(); let count=0;
      const check=(v,name)=>{if(!v)throw Error(name);count++};
      for(const n of [null,undefined,'',' ',true,false,NaN,Infinity,'oops','0x10'])check(D.number(n)===null,'missing number '+n);
      check(D.number(0)===0&&D.number('0')===0,'real zero');
      check(D.time('2026-01-01T00:00:00')===null,'unqualified clock');
      check(D.time('bad:00Z')===null&&D.time('2026-02-30T00:00:00Z')===null,'malformed calendar');
      const series={primaryName:'Stage',primaryUnits:'ft',secondaryName:'River Discharge',secondaryUnits:'kcfs',data:[{validTime:iso(now),primary:100,secondary:0},{validTime:iso(now-H),secondary:null},{validTime:iso(now-2*H),secondary:.5}]};
      let rows=D.nwpsSeries(series,now,true);check(rows.length===2&&rows[0].q===500&&rows[1].q===0,'NWPS metadata and null');
      let threw=false;try{D.nwpsSeries({...series,secondaryUnits:'ft'},now,true)}catch{threw=true}check(threw,'reject stage units');
      threw=false;try{D.nwpsSeries({...series,secondaryName:'Imaginary Streamflow'},now,true)}catch{threw=true}check(threw,'reject nonofficial discharge series identity');
      for(const unit of ['constructor','__proto__']){threw=false;try{D.nwpsSeries({...series,secondaryUnits:unit},now,true)}catch{threw=true}check(threw,'inherited flow units');}
      check(D.nwpsSeries({...series,data:[{validTime:iso(now),secondary:1e308}]},now,true).length===0,'scaled flow overflow');
      threw=false;try{D.nwpsSeries({...series,data:[{validTime:iso(now),secondary:.1},{validTime:iso(now),secondary:.2}]},now,true)}catch{threw=true}check(threw,'duplicate NWPS timestamp rejected');
      const prop={monitoring_location_id:'USGS-12201500',parameter_code:'00060',unit_of_measure:'ft^3/s',time:iso(now),value:'0'};
      check(D.usgs({features:[{properties:prop},{properties:{...prop,value:null}},{properties:{...prop,monitoring_location_id:'other',value:5}}]},now).length===1,'USGS zero null station');
      for(const unit of ['constructor','__proto__'])check(D.usgs({features:[{properties:{...prop,unit_of_measure:unit}}]},now).length===0,'inherited USGS units');
      threw=false;try{D.usgs({features:[{properties:prop},{properties:{...prop,value:'1'}}]},now)}catch{threw=true}check(threw,'duplicate USGS timestamp rejected');
      check(D.duration('PT90M')===1.5*H&&D.duration('P1DT6H')===30*H&&D.duration('PT30S')===30000,'duration units');
      check(D.duration('P')===null&&D.duration('PT')===null&&D.duration('P1DT')===null&&D.duration('oops')===null&&D.duration('P'+'9'.repeat(310)+'D')===null,'malformed duration');
      const makeRain=(values,updated=iso(now-H))=>D.rain({properties:{updateTime:updated,quantitativePrecipitation:{uom:'wmoUnit:mm',values}}},now);
      const native=v=>[{validTime:iso(now-H)+'/PT30H',value:v}];
      for(const uom of ['constructor','__proto__']){threw=false;try{D.rain({properties:{updateTime:iso(now-H),quantitativePrecipitation:{uom,values:native(2)}}},now)}catch{threw=true}check(threw,'inherited rain units');}
      threw=false;try{D.rain({properties:{updateTime:iso(now-H),quantitativePrecipitation:{uom:'wmoUnit:in',values:native(2)}}},now)}catch{threw=true}check(threw,'non-mm rain unit rejected');
      check(Math.abs(D.rainWindow(makeRain(native(30)),now,24).mm-24)<1e-8,'partial interval mass');
      check(makeRain(native(1e100)).rows[0].mm===null,'corrupt finite rain amount withheld');
      check(D.rainWindow(makeRain(native(0)),now,24).complete,'real zero coverage');
      check(!D.rainWindow(makeRain(native(null)),now,24).complete,'null no coverage');
      check(!D.rainWindow(makeRain([{validTime:iso(now)+'/PT12H',value:0}]),now,24).complete,'partial day');
      threw=false;try{makeRain([...native(2),...native(3)])}catch{threw=true}check(threw,'rain overlap rejected');
      threw=false;try{makeRain(native(2),iso(now+H))}catch{threw=true}check(threw,'future rain clock');
      const sixHour=makeRain(Array.from({length:6},(_,i)=>({validTime:iso(now+i*6*H)+'/PT6H',value:i})));
      const bins=D.rainBins(sixHour,now,36,6);check(bins.length===6&&bins.every(r=>r.complete)&&bins[5].mm===5,'six-hour rain bins');
      check(Math.abs(bins.reduce((sum,r)=>sum+r.mm,0)-D.rainWindow(sixHour,now,36).mm)<1e-8,'rain bins preserve mass');
      check(D.rainBins(makeRain([{validTime:iso(now)+'/PT6H',value:0}]),now,12,6)[1].mm===null,'incomplete rain bin withheld');
      const rrmText='000\\nRRMSEW\\nNational Weather Service Seattle WA\\nPadilla Bay Farm 0.00 0.01 0.02 0.03 0.04 0.05 0.06\\nBurlington M 0.01 0.02 0.03 0.04 0.05 0.06\\nSedro Wooley RAWS 0.00 0.00 0.01 0.02 0.03 0.04 0.05\\n';
      let rrm=D.rrmRain({issuanceTime:iso(now-H/2),productCode:'RRM',issuingOffice:'KSEW',productText:rrmText},now);
      check(rrm.fresh&&rrm.stations[0].values[0]===0&&rrm.stations[1].values[0]===null,'RRM zero and missing values');
      const staleRrm=D.rrmRain({issuanceTime:iso(now-4*H),productText:rrmText.replace('Burlington M','Burlington MSG')},now);check(!staleRrm.fresh&&staleRrm.stations[1].values[0]===null,'stale RRM and MSG missing value');
      check(D.rrmProductId({'@graph':[{id:'123e4567-e89b-42d3-a456-426614174000',issuanceTime:iso(now-H)}]},now).issued===now-H,'RRM index selection');
      threw=false;try{D.rrmProductId({'@graph':[{id:'123e4567-e89b-42d3-a456-426614174000',issuanceTime:iso(now-25*H)}]},now)}catch{threw=true}check(threw,'old RRM index rejected');
      threw=false;try{D.rrmRain({issuanceTime:iso(now+H),productText:rrmText},now)}catch{threw=true}check(threw,'future RRM issue rejected');
      threw=false;try{D.rrmRain({issuanceTime:iso(now-25*H),productText:rrmText},now)}catch{threw=true}check(threw,'old RRM payload rejected');
      threw=false;try{D.rrmRain({issuanceTime:iso(now-H),productText:rrmText},now,now-2*H)}catch{threw=true}check(threw,'RRM payload issue must match selected index issue');
      const joinedLabel=rrmText.replace('Burlington M','Burlington0.10');
      rrm=D.rrmRain({issuanceTime:iso(now-H),productText:joinedLabel},now);check(!rrm.stations[1].available,'RRM station label requires a delimiter');
      const badRrm=rrmText.replace('0.00 0.01 0.02 0.03 0.04 0.05 0.06','0.02 0.01 0.02 0.03 0.04 0.05 0.06');
      rrm=D.rrmRain({issuanceTime:iso(now-H),productText:badRrm},now);check(!rrm.stations[0].available,'decreasing RRM windows rejected');
      const basin=D.basinGeometry({features:[{geometry:{type:'Polygon',coordinates:[[[-122.4,48.5],[-122.2,48.5],[-122.2,48.7],[-122.4,48.5]]]}}]});check(basin.pointCount===4,'basin polygon');
      threw=false;try{D.basinGeometry({features:[{geometry:{type:'Polygon',coordinates:[[[-122.4,48.5],[-122.2,48.5],[-122.2,48.7],[-122.3,48.6]]]}}]})}catch{threw=true}check(threw,'open basin ring rejected');
      threw=false;try{D.basinGeometry({features:[{geometry:{type:'Polygon',coordinates:[[[-122.4,48.5],[-122.4,48.5],[-122.4,48.5],[-122.4,48.5]]]}}]})}catch{threw=true}check(threw,'zero-area basin ring rejected');
      threw=false;try{D.basinGeometry({features:[{geometry:{type:'Polygon',coordinates:[[[-122.5,48.5],[-122.3,48.7],[-122.5,48.7],[-122.4,48.5],[-122.5,48.5]]]}}]})}catch{threw=true}check(threw,'self-intersecting basin ring rejected');
      threw=false;try{D.basinGeometry({features:[{geometry:{type:'Polygon',coordinates:[[[-122.5,48.3],[-122.1,48.3],[-122.1,48.7],[-122.5,48.7],[-122.5,48.3]],[[-122.55,48.45],[-122.3,48.45],[-122.3,48.55],[-122.55,48.55],[-122.55,48.45]]]}}]})}catch{threw=true}check(threw,'basin hole crossing outer ring rejected');
      threw=false;try{D.basinGeometry({features:[{geometry:{type:'Polygon',coordinates:[[[-122.5,48.3],[-122.1,48.3],[-122.1,48.7],[-122.5,48.7],[-122.5,48.3]],[[-122.0,48.45],[-121.9,48.45],[-121.9,48.55],[-122.0,48.55],[-122.0,48.45]]]}}]})}catch{threw=true}check(threw,'basin hole outside outer ring rejected');
      threw=false;try{D.basinGeometry({features:[{geometry:{type:'Polygon',coordinates:[[[-122.5,48.3],[-122.1,48.3],[-122.1,48.7],[-122.5,48.7],[-122.5,48.3]],[[-122.4,48.4],[-122.25,48.4],[-122.25,48.55],[-122.4,48.55],[-122.4,48.4]],[[-122.35,48.45],[-122.2,48.45],[-122.2,48.6],[-122.35,48.6],[-122.35,48.45]]]}}]})}catch{threw=true}check(threw,'overlapping basin holes rejected');
      threw=false;try{D.basinGeometry({features:[{geometry:{type:'Polygon',coordinates:[[[-122.5,48.3],[-122.1,48.3],[-122.1,48.7],[-122.5,48.7],[-122.5,48.3]],[[-122.4,48.4],[-122.2,48.4],[-122.2,48.6],[-122.4,48.6],[-122.4,48.4]],[[-122.35,48.45],[-122.25,48.45],[-122.25,48.55],[-122.35,48.55],[-122.35,48.45]]]}}]})}catch{threw=true}check(threw,'nested basin holes rejected');
      threw=false;try{D.basinGeometry({features:[{geometry:{type:'MultiPolygon',coordinates:[[[[-122.5,48.3],[-122.2,48.3],[-122.2,48.6],[-122.5,48.6],[-122.5,48.3]]],[[[-122.3,48.4],[-122.1,48.4],[-122.1,48.7],[-122.3,48.7],[-122.3,48.4]]]]}}]})}catch{threw=true}check(threw,'overlapping basin polygons rejected');
      threw=false;try{D.basinGeometry({features:[{geometry:{type:'MultiPolygon',coordinates:[[[[-122.5,48.3],[-122.1,48.3],[-122.1,48.7],[-122.5,48.7],[-122.5,48.3]]],[[[-122.4,48.4],[-122.2,48.4],[-122.2,48.6],[-122.4,48.6],[-122.4,48.4]]]]}}]})}catch{threw=true}check(threw,'contained basin polygon rejected');
      const splitBasin=D.basinGeometry({features:[{geometry:{type:'MultiPolygon',coordinates:[[[[-122.5,48.3],[-122.35,48.3],[-122.35,48.45],[-122.5,48.45],[-122.5,48.3]]],[[[-122.25,48.55],[-122.1,48.55],[-122.1,48.7],[-122.25,48.7],[-122.25,48.55]]]]}}]});check(splitBasin.polygons.length===2,'separate basin polygons accepted');
      const gp=D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.4,48.5],[-122.2,48.5],[-122.2,48.7],[-122.4,48.7],[-122.4,48.5]]]}});check(Math.abs(gp.lon+122.3)<1e-8&&Math.abs(gp.lat-48.6)<1e-8,'forecast grid centroid');
      check(D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.4,48.5],[-122.2,48.5],[-122.2,48.7],[-122.4,48.7]]]}})===null,'open forecast grid rejected');
      check(D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.4,48.5],[-122.4,48.5],[-122.4,48.5],[-122.4,48.5]]]}})===null,'zero-area forecast grid rejected');
      check(D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.5,48.5],[-122.3,48.7],[-122.5,48.7],[-122.4,48.5],[-122.5,48.5]]]}})===null,'self-intersecting forecast grid rejected');
      check(D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.4,48.5],[-122.2,48.5],[-122.2,48.7],[-122.4,48.7],[-122.4,48.5]],[[-122.35,48.55],[-122.25,48.55],[-122.25,48.65],[-122.35,48.65],[-122.35,48.55]]]}})===null,'forecast grid with interior ring rejected');
      const boxBasin=D.basinGeometry({features:[{geometry:{type:'Polygon',coordinates:[[[-122.5,48.3],[-122.1,48.3],[-122.1,48.7],[-122.5,48.7],[-122.5,48.3]]]}}]});
      check(D.gridCellWithinBasin(gp,boxBasin),'full forecast grid inside basin');
      const outsideGrid=D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.09,48.5],[-122.05,48.5],[-122.05,48.6],[-122.09,48.6],[-122.09,48.5]]]}});check(!D.gridCellWithinBasin(outsideGrid,boxBasin),'out-of-basin forecast grid rejected');
      const concaveBasin=D.basinGeometry({features:[{geometry:{type:'Polygon',coordinates:[[[-122.5,48.3],[-122.1,48.3],[-122.1,48.7],[-122.2,48.7],[-122.2,48.4],[-122.4,48.4],[-122.4,48.7],[-122.5,48.7],[-122.5,48.3]]]}}]});
      const bridgeGrid=D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.45,48.6],[-122.15,48.6],[-122.15,48.65],[-122.45,48.65],[-122.45,48.6]]]}});check(!D.gridCellWithinBasin(bridgeGrid,concaveBasin),'grid edge crossing concave basin gap rejected');
      const holeBasin=D.basinGeometry({features:[{geometry:{type:'Polygon',coordinates:[[[-122.5,48.3],[-122.1,48.3],[-122.1,48.7],[-122.5,48.7],[-122.5,48.3]],[[-122.35,48.45],[-122.25,48.45],[-122.25,48.55],[-122.35,48.55],[-122.35,48.45]]]}}]});
      const holeCoveringGrid=D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.4,48.4],[-122.2,48.4],[-122.2,48.6],[-122.4,48.6],[-122.4,48.4]]]}});check(!D.gridCellWithinBasin(holeCoveringGrid,holeBasin),'grid covering basin hole rejected');
      const boundaryHoleBasin=D.basinGeometry({features:[{geometry:{type:'Polygon',coordinates:[[[-122.5,48.3],[-122.1,48.3],[-122.1,48.7],[-122.5,48.7],[-122.5,48.3]],[[-122.4,48.45],[-122.3,48.4],[-122.2,48.45],[-122.4,48.45]]]}}]});check(!D.gridCellWithinBasin(holeCoveringGrid,boundaryHoleBasin),'basin hole with vertices on grid boundary rejected');
      const concaveGrid=D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.27,48.47],[-122.06,48.5],[-122.27,48.53],[-122.3,48.54],[-122.33,48.53],[-122.34,48.5],[-122.33,48.47],[-122.3,48.46],[-122.27,48.47]]]}});check(concaveGrid===null,'non-quadrilateral concave forecast cell rejected');
      const radarXml='<?xml version="1.0"?><WMS_Capabilities xmlns="http://www.opengis.net/wms"><Capability><Layer>'+['katx_sr_bref','katx_boha','katx_bdsa'].map(layer=>'<Layer><Name>'+layer+'</Name><Dimension name="time">'+iso(now-H)+','+iso(now)+'</Dimension></Layer>').join('')+'</Layer></Capability></WMS_Capabilities>';
      const caps=D.radarCapabilities(radarXml,now);check(caps.katx_sr_bref.latest===now&&caps.katx_boha.times.length===2,'radar capability times');
      threw=false;try{D.radarCapabilities(radarXml.replace('katx_bdsa','wrong_layer'),now)}catch{threw=true}check(threw,'missing radar product rejected');
      const record=D.stormRecord({id:'test-1',savedAt:iso(now),feedCheckAt:iso(now),tag:'Storm check',note:'=formula',gaugeCfs:0,change3Cfs:-2,forecastHighCfs:null,riseThresholdCfs:100,rain24MeanIn:0,padilla24In:null,burlington24In:0,sedroWoolley24In:null,gaugeTime:null,forecastIssue:null,forecastHighTime:null,rainForecastUpdated1:null,rainForecastUpdated2:null,observedRainIssue:null,radarProduct:null,radarValidTime:null});
      const csv=D.stormCsv([record]);check(csv.includes("'=formula")&&csv.includes('"0"'),'storm CSV formula guard and numeric zero');
      const rr=[{t:now-H,q:100},{t:now+5*H,q:200},{t:now+11*H,q:100}];
      let f=D.forecast(rr,iso(now-H),now);check(f.usable&&!f.complete&&f.hours===11&&f.max===200,'short actual forecast');
      f=D.forecast([{t:now+3*H,q:120},{t:now+6*H,q:100}],iso(now-H),now);check(f.usable&&f.startsAfterCheck&&f.start===now+3*H&&f.rows[0].t===now+3*H,'near-future forecast starts without invented check-time value');
      check(!D.forecast([{t:now+7*H,q:120},{t:now+12*H,q:100}],iso(now-H),now).usable,'distant future-only forecast rejected');
      check(D.interpolate(rr,now+12*H)===null,'no extrapolation');
      check(!D.forecast(rr,iso(now-49*H),now).usable,'wall-clock forecast stale');
      check(!D.forecast(rr,iso(now+H),now).usable,'future forecast issue');
      check(!D.forecast([{t:now-H,q:1},{t:now+8*H,q:2}],iso(now-H),now).usable,'large gap');
      f=D.forecast([{t:now,q:100},{t:now+3*H,q:50},{t:now+6*H,q:100}],iso(now-H),now);check(f.atStart&&f.atEnd&&f.rows[1].q===50,'separated maxima');
      check(D.atBefore([{t:now-H,q:1}],now)===null,'distant baseline');
      const tide=D.tides({predictions:[{t:'2026-11-01 09:30',v:'-1',type:'L'},{t:'bad',v:'4',type:'H'}]});check(tide.length===1&&tide[0].t===Date.parse('2026-11-01T09:30:00Z')&&tide[0].v===-1,'UTC tide and negative height');

      // Seasonal rules change at local Pacific midnight, not UTC midnight.
      check(D.thresholdAt(Date.parse('2026-11-01T06:30:00Z')).cfs===100,'October before Pacific boundary');
      check(D.thresholdAt(Date.parse('2026-11-01T07:30:00Z')).cfs===400,'November after Pacific boundary');
      check(D.thresholdAt(Date.parse('2026-03-01T07:30:00Z')).cfs===400,'February before Pacific boundary');
      check(D.thresholdAt(Date.parse('2026-03-01T08:30:00Z')).cfs===200,'March after Pacific boundary');
      check(D.thresholdAt(Date.parse('2026-05-01T06:30:00Z')).cfs===200,'April before Pacific boundary');
      check(D.thresholdAt(Date.parse('2026-05-01T07:30:00Z')).cfs===100,'May after Pacific boundary');

      const obs=Array.from({length:25},(_,i)=>({t:now+(-24+i)*H,q:100}));
      const future=Array.from({length:13},(_,i)=>({t:now+i*6*H,q:i<=4?100+i*30:220}));
      let screen=D.planningScreen(obs,future,now);
      check(screen.usable&&screen.riseAtHighestShare===120&&screen.selectionBasis==='highest-seasonal-reference-share'&&screen.baselineTime<screen.pointTime,'complete rise screen and strict earlier baseline');
      check(screen.threshold.cfs===D.thresholdAt(screen.pointTime).cfs,'candidate-time seasonal rule');
      const boundaryNow=Date.parse('2026-10-31T07:00:00Z');
      const boundaryObs=Array.from({length:25},(_,i)=>({t:boundaryNow+(-24+i)*H,q:100}));
      const boundaryFuture=Array.from({length:13},(_,i)=>({t:boundaryNow+i*6*H,q:i===1?190:i>=4?400:100}));
      const boundaryScreen=D.planningScreen(boundaryObs,boundaryFuture,boundaryNow);
      check(boundaryScreen.usable&&boundaryScreen.riseAtHighestShare===90&&boundaryScreen.threshold.cfs===100&&Math.max(...boundaryFuture.map(r=>r.q))-100===300,'seasonal screen selects highest reference share, not largest raw rise');
      check(D.lineRelation(-1).code==='above'&&D.lineRelation(-1).distance===1,'seasonal line above relation');
      check(D.lineRelation(0).code==='at'&&D.lineRelation(0).distance===0,'seasonal line exact equality');
      check(D.lineRelation(1).code==='below'&&D.lineRelation(1).distance===1,'seasonal line below relation');
      check(!D.planningScreen(obs.slice(1),future,now).usable,'rise screen requires full 24-hour history');
      check(!D.planningScreen(obs.filter(r=>r.t!==now-12*H),future,now).usable,'rise screen rejects gauge gap');
      check(!D.planningScreen(obs.slice(0,-3),future,now).usable,'rise screen rejects stale gauge');
      check(!D.planningScreen(obs,future.filter(r=>r.t<=now+54*H),now).usable,'rise screen rejects short reach');
      check(!D.planningScreen(obs,future.filter(r=>r.t!==now+30*H),now).usable,'rise screen rejects forecast gap');
      const lowObs=obs.map(r=>({...r,q:10})), falling=Array.from({length:13},(_,i)=>({t:now+i*6*H,q:200-i*20}));
      check(!D.planningScreen(lowObs,falling,now).usable,'rise screen rejects negative aligned flow');
      const changed=D.recentChange([{t:now-3.25*H,q:90},{t:now,q:101}],{t:now,q:101},3,now);
      check(changed.change===11&&changed.spanHours===3.25,'recent change reports actual span');
      const nearest=D.recentChange([{t:now-3.4*H,q:90},{t:now-2.9*H,q:110},{t:now,q:101}],{t:now,q:101},3,now);
      check(nearest.change===-9&&Math.abs(nearest.spanHours-2.9)<1e-8,'recent change uses nearest eligible reading');
      const tied=D.recentChange([{t:now-3.5*H,q:90},{t:now-2.5*H,q:110},{t:now,q:101}],{t:now,q:101},3,now);
      check(tied.change===-9&&tied.spanHours===2.5,'recent change tie uses more recent reading');
      check(D.recentChange([{t:now-10*H,q:90},{t:now-7*H,q:101}],{t:now-7*H,q:101},3,now)===null,'recent change rejects stale latest endpoint');

      const snapshot=(age=6,value=80,gap=6)=>{
        const start=now-age*H,times=[];
        for(let t=start;t<=now+72*H;t+=gap*H)times.push(t);
        return {issueTime:iso(now+(-age-1)*H),capturedAt:iso(start),gaugeTime:iso(start),gaugeCfs:70,adjustment:-20,
          alignedPath:times.map((t,i)=>({t,q:i?value:70})),rawPath:times.map((t,i)=>({t,q:i?value+20:90}))};
      };
      const observation={t:now,q:101,change3:4,span3:3,fresh:true};
      let watch=D.surpriseWatch(observation,[snapshot()]);
      check(watch.code==='outpacing'&&watch.expected===80&&watch.difference===21&&watch.line===10,'saved path outpacing');
      check(D.surpriseWatch({...observation,q:0},[snapshot(6,100)]).code==='tracking','far-below saved path is only below comparison line');
      check(D.surpriseWatch(observation,[snapshot(3)]).code==='outpacing','minimum snapshot age included');
      check(D.surpriseWatch(observation,[snapshot(36)]).code==='outpacing','maximum snapshot age included');
      check(D.surpriseWatch(observation,[snapshot(2.999)]).code==='learning','younger snapshot excluded');
      check(D.surpriseWatch(observation,[snapshot(36.001)]).code==='learning','older snapshot excluded');
      check(D.surpriseWatch({...observation,span3:2.5},[snapshot()]).code==='outpacing','minimum change span included');
      check(D.surpriseWatch({...observation,span3:3.5},[snapshot()]).code==='outpacing','maximum change span included');
      check(D.surpriseWatch({...observation,span3:2.49},[snapshot()]).code==='unknown','short change span rejected');
      check(D.surpriseWatch({...observation,change3:0},[snapshot()]).code==='above-prior','non-rising path is not outpacing');
      check(D.surpriseWatch(observation,[snapshot(6,91.01)]).code==='tracking','unrounded watch comparison below line');
      check(D.surpriseWatch(observation,[snapshot(6,91)]).code==='outpacing','exact watch line included');
      check(D.surpriseWatch(observation,[snapshot(6,95),snapshot(7,80)]).expected===95,'newest eligible snapshot wins');
      check(D.surpriseWatch(observation,[snapshot(-1)]).code==='learning','newer capture is ineligible, not corrupt');
      check(D.surpriseWatch(observation,[{...snapshot(),issueTime:iso(now-H),capturedAt:iso(now-2*H)}]).code==='unknown','issue after capture rejected');
      check(D.surpriseWatch(observation,[{...snapshot(),issueTime:iso(now-55*H)}]).code==='unknown','snapshot rejects issue over 48 hours before capture');
      const oldGauge=snapshot(); oldGauge.gaugeTime=iso(now-9*H); oldGauge.alignedPath[0].t=now-9*H;
      check(D.surpriseWatch(observation,[oldGauge]).code==='unknown','snapshot rejects gauge over two hours before capture');
      check(D.surpriseWatch(observation,[{...snapshot(),gaugeCfs:null}]).code==='unknown','malformed snapshot fails closed');
      const corruptInterior=snapshot(); corruptInterior.alignedPath[2].q='CORRUPT';
      check(D.surpriseWatch(observation,[corruptInterior]).code==='unknown','corrupt interior saved point fails closed');
      const negativeInterior=snapshot(); negativeInterior.rawPath[2].q=-1;
      check(D.surpriseWatch(observation,[negativeInterior]).code==='unknown','negative saved point fails closed');
      const nonfiniteInterior=snapshot(); nonfiniteInterior.alignedPath[2].q=Infinity;
      check(D.surpriseWatch(observation,[nonfiniteInterior]).code==='unknown','nonfinite saved point fails closed');
      const duplicateInterior=snapshot(); duplicateInterior.alignedPath[2].t=duplicateInterior.alignedPath[1].t;
      check(D.surpriseWatch(observation,[duplicateInterior]).code==='unknown','duplicate saved time fails closed');
      const shiftedWrong=snapshot(); shiftedWrong.rawPath=shiftedWrong.rawPath.map(r=>({...r,q:150}));
      check(D.surpriseWatch(observation,[shiftedWrong]).code==='unknown','saved aligned path must equal raw path plus one constant');
      const shiftedStart=snapshot(); shiftedStart.rawPath[0].t+=1;
      check(D.surpriseWatch(observation,[shiftedStart]).code==='unknown','saved raw path must start at capture time');
      const shortSaved=snapshot(); shortSaved.rawPath=shortSaved.rawPath.filter(r=>r.t<=shortSaved.rawPath[0].t+54*H); shortSaved.alignedPath=shortSaved.alignedPath.filter(r=>r.t<=shortSaved.alignedPath[0].t+54*H);
      check(D.surpriseWatch(observation,[shortSaved]).code==='unknown','saved raw path requires 60-hour reach');
      const wideGap=snapshot(); wideGap.rawPath.splice(2,1); wideGap.alignedPath.splice(2,1);
      check(D.surpriseWatch(observation,[wideGap]).code==='unknown','saved raw path rejects gaps over six hours');
      const gapped=snapshot(); gapped.alignedPath=[{t:now-6*H,q:70},{t:now+6.01*H,q:80}]; gapped.rawPath=[{t:now-6*H,q:90},{t:now+6.01*H,q:100}];
      check(D.surpriseWatch(observation,[gapped]).code==='unknown','unsupported saved path gap fails closed');
      check(D.surpriseWatch(observation,[snapshot(),snapshot()]).code==='unknown','duplicate saved NOAA issue fails closed');
      check(D.surpriseWatch(observation,{}).code==='unknown','non-array saved history fails closed');
      check(D.surpriseWatch({...observation,fresh:false},[snapshot()]).code==='unknown','stale observation rejected');
      check(D.surpriseWatch(observation,[snapshot()],'unavailable').code==='unknown','storage failure rejected');

      const issue=iso(now-H), currentRows=Array.from({length:5},(_,i)=>({t:now+i*6*H,q:100+i*5}));
      const prior=snapshot(6,80); prior.rawPath=Array.from({length:12},(_,i)=>({t:now-6*H+i*6*H,q:90+i*2}));
      prior.alignedPath=[{t:now-6*H,q:70},...prior.rawPath.slice(1).map(r=>({t:r.t,q:r.q-20}))];
      let revision=D.forecastRevision({usable:true,issued:Date.parse(issue),rows:currentRows},[prior],now);
      check(revision.usable&&revision.currentMax===120&&revision.priorMax===100&&revision.difference===20,'same-window issue revision');
      check(D.forecastRevision({usable:true,issued:Date.parse(issue),rows:currentRows},[],now).code==='learning','revision learns without prior issue');
      const shortPrior={...prior,rawPath:prior.rawPath.slice(0,5),alignedPath:prior.alignedPath.slice(0,5)};
      check(D.forecastRevision({usable:true,issued:Date.parse(issue),rows:currentRows},[shortPrior],now).code==='unknown','revision rejects incomplete common window');
      check(D.forecastRevision({usable:true,issued:Date.parse(issue),rows:currentRows},[{...prior,issueTime:iso(now-2*H),capturedAt:iso(now-3*H)}],now).code==='unknown','revision rejects inconsistent saved clock');
      check(D.forecastRevision({usable:true,issued:Date.parse(issue),rows:currentRows},[prior,{...prior}],now).code==='unknown','revision rejects duplicate saved issue');

      const snap=D.makeSnapshot({usable:true,issued:now-H,rows:future},screen,obs.at(-1),now);
      check(snap&&snap.issueTime===iso(now-H)&&snap.capturedAt===iso(now)&&snap.rawPath.length===future.length,'snapshot contract');
      check(D.makeSnapshot({usable:false,issued:now-H,rows:future},screen,obs.at(-1),now)===null,'unusable forecast not saved');
      return count;
    }""")
    # Version 7 contracts: measured river state, NOAA's current issue against the gauge, tide, rain flags and
    # the look-back counts. Every time here is fixed, so nothing depends on the day the suite runs.
    v7_result = page.evaluate("""(fx) => {
      const D=SamishData, H=D.H, M=60000, R=D.RIVER_RULES, at=text=>Date.parse(text), iso=t=>new Date(t).toISOString(); let count=0;
      const check=(v,name)=>{if(!v)throw Error(name);count++};
      const near=(a,b)=>Math.abs(a-b)<1e-6;
      // Synthetic gauges. scene: a quiet `base` every 15 minutes for 80 hours, then `tail` as [minutes before the
      // newest reading, cfs]. grid: one reading every 15 minutes for `hoursBack`, flow given by minutes back.
      const scene=(end,tail,base=50)=>{const first=Math.max(...tail.map(p=>p[0])),rows=[];for(let m=first+80*60;m>first;m-=15)rows.push({t:end-m*M,q:base});for(const [m,q] of tail)rows.push({t:end-m*M,q});return rows.sort((a,b)=>a.t-b.t)};
      const grid=(end,hoursBack,flow)=>{const rows=[];for(let m=hoursBack*60;m>=0;m-=15)rows.push({t:end-m*M,q:flow(m)});return rows};
      const upTo=(rows,t)=>rows.filter(r=>r.t<=t);
      const T=at('2026-07-15T19:00:00Z');   // noon Pacific in July: the May-October number, 100 cfs
      // A rise from a quiet 50 cfs: 90, then 150 (exactly 100 above the low), 180, and a 200 cfs high `x`
      // minutes before the newest reading; `after` follows the high. hold: one reading each quarter-hour after it.
      const climb=(x,after=[])=>scene(T,[[x+45,90],[x+30,150],[x+15,180],[x,200],...after]);
      const hold=(x,q=199)=>{const out=[];for(let m=Math.ceil(x/15)*15-15;m>=0;m-=15)out.push([m,q]);return out};

      // Rule constants.
      check(R.freshMinutes===90&&R.pauseMinutes===60&&R.peakMinutes===120&&R.fallingFraction===0.05&&R.risingCfs===2&&R.risingFraction===0.02&&R.riseMemoryHours===48&&R.lastHourToleranceMinutes===20&&R.maxGapMinutes===60&&R.climbBackFraction===0.05&&R.clockBehindMinutes===5,'river rule constants');
      check(Object.isFrozen(R)&&Object.keys(R).length===11,'river rule constants are one frozen object');
      check(Object.isFrozen(D.RAIN_RULES)&&D.RAIN_RULES.suspectZeroOtherGaugesIn===0.25&&D.RAIN_RULES.dryMonths.join()==='5,6,7,8,9,10','rain rule constants');

      // River state. Freshness: exactly 90 and 91 minutes; a feed 110 minutes behind; holes.
      const quiet=scene(T,[[0,50]]);
      let s=D.riverState(quiet,T+90*M);
      check(s.available&&s.fresh&&s.ageMinutes===90&&s.staleCode===null&&s.reason===null&&s.checkTime===T+90*M,'reading exactly 90 minutes old is fresh');
      s=D.riverState(quiet,T+90*M+59000);check(s.fresh&&s.ageMinutes===90,'age is counted in whole minutes');
      s=D.riverState(quiet,T+91*M);
      check(s.available&&!s.fresh&&s.ageMinutes===91&&s.staleCode==='old-reading'&&s.reading.t===T&&s.reading.q===50&&typeof s.reason==='string','reading 91 minutes old is not fresh but is still returned with its age');
      check(s.lastHour===null&&s.threeHour===null&&s.threshold===null&&s.low24===null&&s.rise===null&&s.riseStatus==='unknown'&&s.riseStart===null&&s.high===null&&s.minutesSinceHigh===null&&s.belowHigh===null&&s.state===null,'stale reading carries no change figure and no state');
      s=D.riverState(climb(0),T+20*M);check(s.fresh&&s.state==='new-high'&&s.riseStatus==='in-progress','rising river with a recent reading has a state');
      s=D.riverState(climb(0),T+110*M);
      check(!s.fresh&&s.ageMinutes===110&&s.staleCode==='old-reading'&&s.state===null&&s.lastHour===null&&s.rise===null&&s.riseStart===null&&s.high===null&&s.riseStatus==='unknown','a feed 110 minutes behind is not a plateau: no state and no change figures');
      s=D.riverState(quiet.filter(r=>r.t<=T-90*M||r.t===T),T+5*M);
      check(s.available&&!s.fresh&&s.staleCode==='gap-in-last-hour'&&s.gapMinutes===90&&s.ageMinutes===5&&s.state===null&&s.lastHour===null&&s.rise===null,'a 90-minute hole before the newest reading: cannot tell');
      s=D.riverState(quiet.filter(r=>(T-r.t)%(60*M)===0),T);check(s.fresh&&s.lastHour&&s.lastHour.change===0&&s.lastHour.spanMinutes===60,'readings exactly 60 minutes apart are not a hole');
      s=D.riverState([...quiet.filter(r=>r.t<=T-75*M),{t:T-61*M,q:50},{t:T,q:50}],T);check(!s.fresh&&s.staleCode==='gap-in-last-hour'&&s.gapMinutes===61,'a 61-minute hole is a hole');
      s=D.riverState(quiet.filter(r=>r.t<=T-135*M||r.t>=T-45*M),T);check(!s.fresh&&s.staleCode==='gap-in-last-hour'&&s.gapMinutes===90,'a hole that reaches into the last hour: cannot tell');
      s=D.riverState(quiet.filter(r=>r.t<=T-180*M||r.t>=T-75*M),T);
      check(s.fresh&&s.lastHour.label==='about level'&&s.low24===null&&s.rise===null&&s.riseStatus==='unknown'&&s.riseStart===null&&s.state===null,'an older hole leaves the last hour readable but the 24-hour low unknown, not zero');
      s=D.riverState(quiet.filter(r=>r.t>=T-45*M),T);check(!s.fresh&&s.staleCode==='gap-in-last-hour'&&s.gapMinutes===null,'readings that do not reach back one hour: cannot tell');
      s=D.riverState([],T);check(!s.available&&s.reading===null&&s.ageMinutes===null&&s.staleCode==='no-reading'&&!s.fresh&&s.state===null,'no reading at all');
      check(!D.riverState(null,T).available&&!D.riverState(quiet,NaN).available&&!D.riverState([{t:T,q:1},{t:T,q:2}],T).available,'unreadable gauge input fails closed');
      s=D.riverState([...quiet,{t:T+5*M,q:999},{t:T-7*M,q:'oops'},{t:'x',q:5}],T);check(s.fresh&&s.staleCode===null&&s.clockBehindMinutes===null&&s.reading.t===T&&s.reading.q===50,'a reading stamped exactly 5 minutes ahead is not used yet, and malformed rows are ignored');
      s=D.riverState([...quiet,{t:T+6*M,q:60}],T);
      check(s.available&&!s.fresh&&s.staleCode==='clock-behind'&&s.clockBehindMinutes===6&&s.reading.t===T+6*M&&s.reading.q===60&&s.ageMinutes===null&&typeof s.reason==='string','a newest reading stamped 6 minutes after the device time: the device clock is behind the gauge');
      check(s.lastHour===null&&s.threeHour===null&&s.rise===null&&s.riseAtLeast===null&&s.riseStatus==='unknown'&&s.riseStart===null&&s.high===null&&s.state===null,'a device clock that is behind gives no age, no change figure and no state');
      s=D.riverState([...climb(0),{t:T+55*M,q:210}],T);check(s.staleCode==='clock-behind'&&s.clockBehindMinutes===55&&s.state===null&&s.riseStart===null&&s.reading.q===210,'a rising river seen from a device 55 minutes slow: nothing is said about the river');
      check(D.noaaAgainstGauge(s,[{t:T-6*H,q:100},{t:T,q:100},{t:T+6*H,q:100},{t:T+12*H,q:100}],iso(T-H),T).riseInProgress===null,'no rise is read from a reading stamped after the device time');

      // River state. Change over the last hour: nearest reading within 60 +/- 20 minutes; both +2 cfs and +2% for "rising".
      const hourTail=(before,latest)=>scene(T,[[60,before],[45,before],[30,before],[15,before],[0,latest]]);
      s=D.riverState(hourTail(100,102),T);check(s.lastHour.change===2&&near(s.lastHour.percent,2)&&s.lastHour.label==='rising'&&s.lastHour.before.q===100&&s.lastHour.before.t===T-60*M,'+2 cfs and +2% is rising');
      s=D.riverState(hourTail(105,107),T);check(s.lastHour.change===2&&s.lastHour.percent<2&&s.lastHour.percent>1.9&&s.lastHour.label==='about level','+2 cfs with +1.9% is about level');
      s=D.riverState(hourTail(50,51.5),T);check(s.lastHour.label==='about level','+3% with only +1.5 cfs is about level');
      s=D.riverState(hourTail(100,98),T);check(s.lastHour.change===-2&&s.lastHour.label==='falling','-2 cfs and -2% is falling');
      s=D.riverState(hourTail(105,103),T);check(s.lastHour.label==='about level','-2 cfs with -1.9% is about level');
      check(65.1-63.1!==2,'fixture relies on binary rounding of a published 2.0 cfs step');
      s=D.riverState(hourTail(63.1,65.1),T);check(s.lastHour.label==='rising','a published +2.0 cfs step is rising despite binary rounding');
      check(D.lastHourLabel(2,100)==='rising'&&D.lastHourLabel(1.99,50)==='about level'&&D.lastHourLabel(-2,100)==='falling'&&D.lastHourLabel(0,100)==='about level'&&D.lastHourLabel(NaN,100)===null&&D.lastHourLabel(2,null)===null,'last-hour label function');
      s=D.riverState(scene(T,[[85,60],[35,64],[0,66]]),T);check(s.fresh&&s.lastHour===null,'no reading within 60 +/- 20 minutes: last-hour change absent, not zero');
      s=D.riverState(scene(T,[[80,60],[40,64],[0,66]]),T);check(s.lastHour.before.t===T-40*M&&s.lastHour.change===2&&s.lastHour.spanMinutes===40,'last-hour tie uses the more recent reading');
      s=D.riverState(scene(T,[[80,60],[45,61],[0,66]]),T);check(s.lastHour.before.t===T-45*M&&s.lastHour.change===5,'last-hour change uses the nearest reading inside the tolerance');
      s=D.riverState(grid(T,30,m=>m===0?66:m===180?60:50),T);check(s.threeHour.change===6&&s.threeHour.spanMinutes===180&&s.threeHour.before.t===T-180*M,'about-three-hour change');

      // River state. The 24-hour low, the measured rise and its share of the seasonal number.
      s=D.riverState(grid(T,30,m=>m===0?60:(m===600||m===300)?40:50),T);
      check(s.low24.q===40&&s.low24.t===T-600*M&&s.rise.cfs===20&&near(s.rise.share,0.2)&&s.threshold.cfs===100&&s.riseStatus==='none','24-hour low takes the earliest reading on a tie');
      s=D.riverState(grid(T,24,m=>m===1440?30:m===0?60:50),T);check(s.low24&&s.low24.q===30&&s.rise.cfs===30,'24-hour low includes the reading exactly 24 hours back');
      s=D.riverState(grid(T,23.75,m=>50),T);check(s.fresh&&s.low24===null&&s.rise===null&&s.riseStatus==='unknown','readings that stop short of 24 hours give no 24-hour low');
      s=D.riverState(grid(T,30,m=>50).filter(r=>r.t<=T-600*M||r.t>=T-525*M),T);check(s.fresh&&s.low24===null&&s.rise===null,'a 75-minute hole inside the 24 hours gives no 24-hour low');
      check(s.lowHeld24.q===50&&s.lowHeld24.gapMinutes===75&&s.riseAtLeast.cfs===0&&s.riseStatus==='unknown'&&s.riseStart===null,'with a hole the lowest reading held gives only a lower bound, and a bound under the number is never "no rise"');
      s=D.riverState(grid(T,23.75,m=>50),T);check(s.low24===null&&s.lowHeld24===null&&s.riseAtLeast===null&&s.riseStatus==='unknown','readings that stop short of 24 hours give no lower bound either');
      s=D.riverState(grid(T,30,m=>m===0?60:50),T);check(s.low24.q===50&&s.rise.cfs===10&&s.lowHeld24===null&&s.riseAtLeast===null,'a whole 24 hours gives the exact rise and no lower bound');
      // A 75-minute hole four hours back, then a climb: the first reading whose LOWER BOUND reaches the number starts the rise.
      const afterHole=top=>grid(T,60,m=>m>120?50:m>90?Math.min(top,120):m>60?Math.min(top,160):m>30?Math.min(top,175):top).filter(r=>r.t<=T-300*M||r.t>=T-225*M);
      s=D.riverState(afterHole(180),T);
      check(s.riseStatus==='in-progress'&&s.riseStart.t===T-90*M&&s.riseStart.q===160&&s.riseStart.riseCfs===110&&s.riseStart.lowerBound===true&&s.riseStart.atOrBefore===true,'a reading whose lower bound reaches the number counts as past it, at or before that reading');
      check(s.high.q===180&&s.high.t===T-30*M&&s.state==='just-off-high'&&s.low24===null&&s.rise===null&&s.riseAtLeast.cfs===130&&near(s.riseAtLeast.share,1.3)&&s.lowHeld24.gapMinutes===75,'after a lower-bound start the normal states apply, from that reading');
      s=D.riverState(afterHole(120),T);check(s.fresh&&s.riseStart===null&&s.riseStatus==='unknown'&&s.riseAtLeast.cfs===70&&s.state===null,'a lower bound under the number starts no rise and is not "no rise"');
      s=D.riverState(grid(T,30,m=>m===0?50.1:50),T);
      check(s.fresh&&s.riseStatus==='none'&&s.riseStart===null&&s.high===null&&s.minutesSinceHigh===null&&s.state===null&&s.lastHour.label==='about level'&&near(s.rise.cfs,0.1),'a one-step wobble on a quiet day is not a rise and has no high');

      // River state. "This rise": start, 48-hour memory, and the high since the start.
      s=D.riverState(climb(0),T);
      check(s.riseStart.t===T-30*M&&s.riseStart.q===150&&s.riseStart.riseCfs===100&&s.riseStart.low.q===50&&s.riseStart.threshold.cfs===100&&s.riseStart.atOrBefore===false,'rise starts at the first reading exactly at the seasonal number');
      check(s.high.q===200&&s.high.t===T&&s.minutesSinceHigh===0&&s.belowHigh.cfs===0&&s.belowHigh.fraction===0&&s.rise.cfs===150&&near(s.rise.share,1.5),'new high: the newest reading is the high');
      s=D.riverState(scene(T,[[45,90],[30,149.9],[15,180],[0,200]]),T);check(s.riseStart.t===T-15*M&&s.riseStart.riseCfs===130,'0.1 cfs short of the number is not the start');
      const blip=start=>grid(T,100,m=>({0:160,15:150,30:140,45:120,60:100,75:80,90:60})[start-m]??50);
      s=D.riverState(blip(47*60),T);
      check(s.riseStatus==='in-progress'&&s.riseStart.t===T-47*H&&s.riseStart.atOrBefore===false&&s.high.q===160&&s.high.t===T-47*H&&s.minutesSinceHigh===47*60&&s.state==='falling'&&s.rise.cfs===0,'a number passed 47 hours ago is still remembered');
      s=D.riverState(blip(49*60),T);check(s.fresh&&s.riseStatus==='none'&&s.riseStart===null&&s.high===null&&s.state===null,'a number passed 49 hours ago is no longer remembered');
      s=D.riverState(blip(48*60),T);check(s.riseStatus==='in-progress'&&s.riseStart.t===T-48*H&&s.riseStart.atOrBefore===true,'the earliest reading of the 48 hours already at the number is flagged at-or-before');
      s=D.riverState(grid(T,30,m=>m>=27*60?50:200),T);
      check(s.riseStatus==='in-progress'&&s.riseStart.atOrBefore===true&&s.riseStart.lowerBound===false&&s.riseStart.t===T-6*H&&s.high.q===200&&s.high.t===T-1605*M&&s.state==='may-have-peaked','a rise older than the readable history is flagged at-or-before, and its high is the highest reading held in the 48 hours');
      s=D.riverState(grid(T,30,m=>60+(1800-m)/15*2),T);
      check(s.riseStart.atOrBefore===true&&s.riseStart.t===T-6*H&&s.state==='new-high'&&s.high.t===T&&s.high.q===300&&s.lastHour.label==='rising','a rise older than the readings whose newest reading is the highest held is a new high, not an old top');
      // An old rise at the start of the 48 hours, a long level stretch, then a fresh crossing: "this rise" is the fresh one.
      const oldThenNew=grid(T,100,m=>m>3000?50:m>600?250:360);
      s=D.riverState(oldThenNew,T);
      check(s.riseStart.t===T-600*M&&s.riseStart.atOrBefore===false&&s.riseStart.riseCfs===110&&s.riseStart.low.q===250&&s.high.q===360&&s.high.t===T-600*M&&s.state==='may-have-peaked','a fresh upward crossing after an older rise starts this rise');
      s=D.riverState(grid(T,100,m=>m>3000?50:250),T);
      check(s.riseStart.atOrBefore===true&&s.riseStart.t===T-2880*M&&s.high.q===250&&s.high.t===T-2880*M&&s.state==='may-have-peaked','with no fresh crossing the start stays at-or-before the earliest reading of the 48 hours');

      // River state. States and their boundaries (reading time): 59, 60, 119 and 120 minutes; exactly 5% below.
      s=D.riverState(climb(59,hold(59)),T);check(s.state==='just-off-high'&&s.minutesSinceHigh===59&&s.high.q===200&&s.belowHigh.cfs===1,'59 minutes since the high: just off the high');
      s=D.riverState(climb(60,hold(60)),T);check(s.state==='paused'&&s.minutesSinceHigh===60,'60 minutes since the high: paused');
      s=D.riverState(climb(119,hold(119)),T);check(s.state==='paused'&&s.minutesSinceHigh===119,'119 minutes since the high: still paused');
      s=D.riverState(climb(120,hold(120)),T);check(s.state==='may-have-peaked'&&s.minutesSinceHigh===120,'120 minutes since the high: may have peaked');
      for(const late of [0,30,90]){s=D.riverState(climb(105,hold(105)),T+late*M);check(s.state==='paused'&&s.minutesSinceHigh===105&&s.ageMinutes===late,'durations count reading time, not the device clock (reading '+late+' minutes old)');}
      s=D.riverState(climb(90,[...hold(90).slice(0,-1),[0,190]]),T);check(s.state==='falling'&&near(s.belowHigh.fraction,0.05)&&s.belowHigh.cfs===10,'exactly 5% below the high: falling');
      s=D.riverState(climb(90,[...hold(90).slice(0,-1),[0,190.5]]),T);check(s.state==='paused'&&s.belowHigh.fraction<0.05,'just under 5% below the high is not falling');
      s=D.riverState(climb(180,[...hold(180).slice(0,-1),[0,150]]),T);check(s.state==='falling'&&s.minutesSinceHigh===180,'falling is named before may-have-peaked');
      const surge=[];for(let m=285;m>=0;m-=15)surge.push([m,m>=240?200-(300-m)/15*10:m>60?150:150+(60-m)/15*5]);
      s=D.riverState(climb(300,surge),T);
      check(s.state==='rising-again'&&s.lastHour.label==='rising'&&s.lastHour.change===20&&s.high.q===200&&s.high.t===T-300*M&&s.belowHigh.cfs===30&&s.minutesSinceHigh===300,'a second, lower surge is rising again, not may-have-peaked and not falling');
      s=D.riverState(climb(300,surge.map(p=>[p[0],Math.min(p[1],150)])),T);check(s.state==='falling','without the second surge the same river is falling');
      const tie=scene(T,[[60,100],[45,150],[30,180],[15,191],[0,191]]);
      s=D.riverState(tie,T);check(s.state==='just-off-high'&&s.high.q===191&&s.high.t===T-15*M&&s.minutesSinceHigh===15&&s.belowHigh.cfs===0,'191 then 191: a tie is not a new high');
      s=D.riverState(upTo(tie,T-15*M),T-15*M);check(s.state==='new-high'&&s.high.t===T-15*M,'the first 191 was the new high');
      const wobble=before=>scene(T,[[105,100],[90,150],[75,157],[60,before],[45,163],[30,163],[15,164],[0,163]]);
      const states=rows=>[45,30,15,0].map(m=>D.riverState(upTo(rows,T-m*M),T-m*M));
      let run=states(wobble(160));
      check(run.map(r=>r.state).join()==='new-high,just-off-high,new-high,just-off-high'&&run[3].high.q===164&&run[3].high.t===T-15*M&&run[3].lastHour.label==='about level','163, 163, 164, 163: no peak, pause or falling state, and the high stays 164');
      run=states(wobble(157));
      check(run.map(r=>r.state).join()==='new-high,just-off-high,new-high,rising-again'&&run[3].belowHigh.cfs===1&&run[3].lastHour.change===6,'163, 163, 164, 163 while the last hour is still up 6 cfs: rising again, 1 cfs below the high');
      check(run.every(r=>!['falling','paused','may-have-peaked','cannot-tell'].includes(r.state)),'a one-step dip never reads as a peak');
      const holed=scene(T,[[285,90],[270,150],[255,180],[240,200],[225,199],[210,199],[195,199],...[105,90,75,60,45,30,15,0].map(m=>[m,199])]);
      s=D.riverState(holed,T);
      check(s.fresh&&s.state==='cannot-tell'&&s.gapMinutes===90&&typeof s.reason==='string'&&s.riseStatus==='in-progress'&&s.high.q===200&&s.lastHour.label==='about level'&&s.low24===null&&s.rise===null,'a 90-minute hole between the high and the newest reading: cannot tell');

      // River state. Yesterday's higher peak belongs to no rise (it never passed the winter number), so it is not this rise's high.
      const TW=at('2026-01-16T20:00:00Z');   // noon Pacific in January: the November-February number, 400 cfs
      const winter=grid(TW,90,m=>m>=1560?600:m>=1200?600+(1560-m)/360*300:m>=480?900-(1200-m)/720*450:m>=300?450:450+(300-m)/300*410);
      s=D.riverState(winter,TW);
      check(s.threshold.cfs===400&&s.state==='new-high'&&s.high.q===860&&s.high.t===TW&&s.riseStart.t===TW&&near(s.rise.cfs,410)&&Math.max(...winter.map(r=>r.q))===900,'yesterday’s higher peak is not the high of a new rise');
      const winterHeld=[...winter,...[15,30,45,60,75].map(m=>({t:TW+m*M,q:860}))];
      s=D.riverState(winterHeld,TW+75*M);
      check(s.state==='paused'&&s.minutesSinceHigh===75&&s.high.q===860&&s.high.t===TW,'a new rise that pauses reads 75 minutes since its own high, not 20 hours since yesterday’s');

      // River state. Seasonal boundary: the number in force at each reading (31 October to 1 November, Pacific).
      const TB=at('2026-11-01T07:15:00Z');   // 12:15 AM Pacific on 1 November
      s=D.riverState(scene(TB,[[60,120],[45,160],[30,190],[15,200],[0,210]]),TB);
      check(s.riseStatus==='in-progress'&&s.riseStart.t===TB-45*M&&s.riseStart.threshold.cfs===100&&s.riseStart.threshold.label===D.thresholdAt(TB-45*M).label&&s.riseStart.riseCfs===110,'a rise that passed the October number before midnight keeps that number and start');
      check(s.threshold.cfs===400&&near(s.rise.share,0.4)&&s.rise.cfs===160&&s.state==='new-high','after midnight the share is measured against the November number');
      s=D.riverState(scene(TB,[[60,120],[45,140],[30,149],[15,200],[0,210]]),TB);
      check(s.fresh&&s.riseStatus==='none'&&s.riseStart===null&&s.state===null&&s.rise.cfs===160,'150 cfs of rise first reached after midnight is below the November number');

      // River state. The rise of 29 September 2026 (15-minute readings; times Pacific daylight, 7 hours behind GMT).
      const sept=fx.readings, P=clock=>at((clock<'03:00'?'2026-09-30T':'2026-09-29T')+clock+':00-07:00');
      const frame=(clock,delay=0)=>D.riverState(upTo(sept,P(clock)),P(clock)+delay*M);
      check(sept.length===303&&sept.at(-1).q===125&&sept.at(-1).t===at('2026-09-30T08:00:00-07:00'),'29 September fixture shape');
      s=frame('11:45');check(s.fresh&&s.riseStatus==='none'&&s.state===null&&near(s.rise.cfs,97.1)&&s.lastHour.label==='rising','11:45 AM: rising fast but the measured rise is still under 100 cfs');
      s=frame('12:00',20);
      check(s.riseStatus==='in-progress'&&s.riseStart.t===P('12:00')&&s.riseStart.q===119&&near(s.riseStart.riseCfs,103.1)&&s.riseStart.atOrBefore===false&&s.riseStart.threshold.cfs===100&&s.state==='new-high'&&s.ageMinutes===20,'12:00 PM: past the 100 cfs number at this reading');
      // 3:00 PM is NOT a new high: 163 cfs was first read at 2:45 PM and the 3:00 PM reading only equals it
      // (a tie is not a new high), so the state is just-off-high.
      s=frame('15:00');check(s.state==='just-off-high'&&s.high.q===163&&s.high.t===P('14:45')&&s.minutesSinceHigh===15&&s.reading.q===163,'3:00 PM: 163 cfs ties the 2:45 PM high');
      check(frame('14:45').state==='new-high'&&frame('15:15').state==='new-high'&&frame('15:15').high.q===164,'2:45 PM and 3:15 PM are the new highs either side');
      s=frame('16:00');check(s.state==='just-off-high'&&s.minutesSinceHigh===45&&s.high.q===164&&s.high.t===P('15:15')&&s.lastHour.change===1&&s.lastHour.label==='about level','4:00 PM: 45 minutes since the 3:15 PM high, last hour +1');
      // 4:15 PM is a pause, not just-off-high: 164 cfs was first read at 3:15 PM, exactly 60 minutes of readings
      // earlier (pauseMinutes is 60). The river then went on from 164 to 191 cfs.
      s=frame('16:15');check(s.state==='paused'&&s.minutesSinceHigh===60&&s.high.t===P('15:15')&&s.lastHour.change===0,'4:15 PM: 60 minutes since the 3:15 PM high is a pause');
      for(const clock of ['17:00','19:00','21:00']){s=frame(clock);check(s.state==='new-high'&&s.high.t===P(clock)&&s.minutesSinceHigh===0,clock+': new high');}
      s=frame('19:00',20);
      check(s.reading.q===181&&s.ageMinutes===20&&s.lastHour.change===7&&s.lastHour.label==='rising'&&s.threeHour.change===17&&near(s.rise.cfs,165.1)&&near(s.rise.share,1.651)&&s.low24.q===15.9&&s.low24.t===P('01:00')-24*H&&s.riseStart.t===P('12:00'),'7:00 PM read at 7:20 PM: 181 cfs, +7 in the hour before, 165 cfs above the 24-hour low');
      s=frame('22:00');check(s.state==='paused'&&s.minutesSinceHigh===60&&s.high.q===191&&s.high.t===P('21:00')&&s.lastHour.label==='about level'&&s.threeHour.change===10,'10:00 PM: paused, last hour level although the three-hour change is still +10');
      s=frame('22:45');check(s.state==='paused'&&s.minutesSinceHigh===105,'10:45 PM: paused');
      s=frame('22:45',20);check(s.state==='paused'&&s.minutesSinceHigh===105&&s.ageMinutes===20,'10:45 PM read at 11:05 PM: still 105 minutes of readings, still paused');
      s=frame('22:00',60);check(s.state==='paused'&&s.minutesSinceHigh===60&&s.ageMinutes===60,'11:00 PM with the newest reading an hour old: a one-hour pause, not two hours');
      s=frame('23:00');check(s.state==='may-have-peaked'&&s.minutesSinceHigh===120&&s.high.q===191&&s.high.t===P('21:00')&&s.lastHour.change===-2&&s.lastHour.label==='about level','11:00 PM: may have peaked');
      for(let t=P('12:00');t<P('23:00');t+=15*M){s=D.riverState(upTo(sept,t),t);check(!['may-have-peaked','falling','cannot-tell','rising-again',null].includes(s.state)&&s.riseStart.t===P('12:00'),'no may-have-peaked or falling state before 11:00 PM ('+iso(t)+')');}
      check(frame('16:15').state==='paused'&&frame('16:30').state==='new-high','the 4:15 PM pause was followed by a new high at 4:30 PM');
      check(frame('22:15').lastHour.label!=='rising'&&frame('23:15').lastHour.label!=='rising','no rising word at 10:15 PM or 11:15 PM');
      check(frame('00:15').state==='may-have-peaked'&&frame('00:30').state==='falling'&&near(frame('00:30').belowHigh.cfs,10),'falling first at 12:30 AM, 181 cfs against the 191 cfs high');
      s=D.riverState(sept,at('2026-09-30T08:20:00-07:00'));
      check(s.fresh&&s.riseStatus==='in-progress'&&s.riseStart.t===P('12:00')&&s.rise.cfs===79&&s.rise.share<1&&s.state==='falling'&&s.high.q===191&&s.high.t===P('21:00')&&s.minutesSinceHigh===660&&s.lastHour.change===-7,'next morning: the measured rise is back under 100 cfs but the number is still remembered since 12:00 PM');

      // Where a look-back count is counted from, and the 24 hours it covers.
      check(Object.isFrozen(D.LOOKBACK_RULES)&&D.LOOKBACK_RULES.countHorizonHours===24&&Object.keys(D.LOOKBACK_RULES).length===1,'the look-back counts cover 24 hours');
      const anchorOf=(rows,now)=>D.countAnchor(rows,D.riverState(rows,now));
      const fallRows=climb(90,[[75,199],[60,195],[45,190],[30,185],[15,188],[0,180]]);
      let mark=anchorOf(fallRows,T);
      check(mark.state==='falling'&&mark.t===T-45*M&&mark.q===190&&mark.minutesSince===45&&mark.withinHorizon===true,'falling is counted from the first reading exactly 5% below the high');
      mark=anchorOf(climb(90,[[75,199],[60,190.5],[45,199],[30,199],[15,199],[0,189]]),T);
      check(mark.state==='falling'&&mark.t===T&&mark.q===189&&mark.minutesSince===0&&mark.withinHorizon===true,'just under 5% does not start the count; the newest reading can be the first that far below');
      mark=anchorOf(climb(120,[[105,199],[90,188],[75,199],[60,199],[45,199],[30,199],[15,195],[0,185]]),T);
      check(mark.state==='falling'&&mark.t===T-90*M&&mark.q===188&&mark.minutesSince===90,'after a dip and a recovery the count is still from the earliest reading 5% below the high');
      const longFall=since=>grid(T,100,m=>m>since+60?50:m===since+60?150:m===since+45?180:m===since+30?200:m===since+15?195:185);
      mark=anchorOf(longFall(1440),T);check(mark.state==='falling'&&mark.t===T-1440*M&&mark.minutesSince===1440&&mark.withinHorizon===true,'a first reading exactly 24 hours of readings back is still inside the count');
      mark=anchorOf(longFall(1455),T);check(mark.state==='falling'&&mark.t===T-1455*M&&mark.minutesSince===1455&&mark.withinHorizon===false,'a first reading 24 hours and 15 minutes back is past the count');
      mark=anchorOf(climb(120,hold(120)),T);check(mark.state==='may-have-peaked'&&mark.t===T&&mark.q===null&&mark.minutesSince===0&&mark.withinHorizon===true,'may-have-peaked is counted from the 2-hour mark');
      mark=anchorOf(climb(135,hold(135)),T);check(mark.t===T-15*M&&mark.minutesSince===15&&mark.withinHorizon===true,'the 2-hour mark is the time of the high plus 120 minutes');
      const plateau=since=>grid(T,100,m=>m>since+30?50:m===since+30?150:m===since+15?180:m===since?200:199);
      mark=anchorOf(plateau(26*60),T);check(mark.state==='may-have-peaked'&&mark.t===T-1440*M&&mark.minutesSince===1440&&mark.withinHorizon===true,'a 2-hour mark exactly 24 hours of readings back is still inside the count');
      mark=anchorOf(plateau(26*60+15),T);check(mark.state==='may-have-peaked'&&mark.minutesSince===1455&&mark.withinHorizon===false,'a plateau 26 hours and 15 minutes long is past the count');
      for(const rows of [climb(0),climb(59,hold(59)),climb(60,hold(60)),quiet,surge&&climb(300,surge)])check(anchorOf(rows,T)===null,'no count anchor outside falling and may-have-peaked');
      check(D.countAnchor(fallRows,D.riverState(fallRows,T+110*M))===null&&D.countAnchor(fallRows,null)===null&&D.countAnchor(null,D.riverState(fallRows,T))===null,'no count anchor from a stalled feed or unreadable input');
      mark=D.countAnchor(sept,D.riverState(sept,at('2026-09-30T08:20:00-07:00')));
      check(mark.state==='falling'&&mark.t===P('00:30')&&mark.q===181&&mark.minutesSince===450&&mark.withinHorizon===true,'next morning: counted from the 12:30 AM reading, the first 5% below the 191 cfs high');
      mark=D.countAnchor(upTo(sept,P('23:00')),frame('23:00',20));check(mark.state==='may-have-peaked'&&mark.t===P('23:00')&&mark.minutesSince===0&&mark.withinHorizon===true,'11:00 PM: the 2-hour mark is that reading');
      check(D.countAnchor(upTo(sept,P('19:00')),frame('19:00'))===null,'7:00 PM: a new high has no count anchor');
      // A new high whose last hour is only "about level": the page must not call it "still rising".
      s=frame('16:30',20);check(s.state==='new-high'&&s.reading.q===166&&s.lastHour.change===2&&s.lastHour.percent<2&&s.lastHour.label==='about level'&&s.threeHour.change===19,'4:30 PM: a new high of 166 cfs, +2 cfs and +1.2% on the hour before, about level');

      // Climbing again below an earlier top. Synthetic winter storm (400 cfs number): a first surge to 1,400 cfs, a fall
      // to 820 cfs, then a second climb. Readings follow the gauge's reporting steps.
      const W=(d,h)=>at('2026-01-'+String(d).padStart(2,'0')+'T'+String(h).padStart(2,'0')+':00:00-08:00');
      const stepQ=q=>q<100?Math.round(q*10)/10:q<1000?Math.round(q):Math.round(q/10)*10;
      const piecewise=points=>{const out=[];let t=points[0][0];for(let i=1;i<points.length;i++){const [t0,q0]=points[i-1],[t1,q1]=points[i];while(t<t1){out.push({t,q:stepQ(q0+(q1-q0)*((t-t0)/(t1-t0)))});t+=15*M}}out.push({t:points.at(-1)[0],q:stepQ(points.at(-1)[1])});return out};
      const surge1=[[W(9,0),310],[W(12,6),300],[W(12,9),520],[W(12,12),980],[W(12,15),1400],[W(12,21),1250],[W(13,6),900],[W(13,9),820]];
      const secondSlow=piecewise([...surge1,[W(13,21),1000],[W(14,1),1060],[W(14,12),800]]);     // +15 cfs an hour: under the 2% "rising" test
      const secondNear=piecewise([...surge1,[W(13,12),1150],[W(13,15),1340],[W(13,19),1390],[W(14,12),900]]);   // creeps to within 5% of the first top
      const secondLower=piecewise([...surge1,[W(13,13),880],[W(13,17),1100],[W(13,23),980],[W(14,12),700]]);
      const winterAt=(rows,d,h)=>D.riverState(upTo(rows,W(d,h)),W(d,h)+20*M);
      s=winterAt(secondSlow,13,6);check(s.threshold.cfs===400&&s.state==='falling'&&s.high.q===1400&&s.high.t===W(12,15)&&s.lowSinceHigh.q===900&&s.risingAgainBasis===null,'falling from the first top');
      s=winterAt(secondSlow,13,12);check(s.state==='falling'&&s.reading.q===865&&s.lowSinceHigh.q===820&&s.lowSinceHigh.t===W(13,9),'45 cfs above the low is under 5% of the 1,400 cfs high: still falling');
      s=winterAt(secondSlow,13,15);
      check(s.state==='rising-again'&&s.risingAgainBasis==='climb-back'&&s.reading.q===910&&s.lastHour.label==='about level'&&s.lastHour.change===15&&s.threeHour.change===45&&s.lowSinceHigh.q===820&&s.lowSinceHigh.t===W(13,9)&&s.belowHigh.cfs===490,'a slow second climb (+15 cfs an hour) is climbing again, not falling');
      s=winterAt(secondSlow,14,0);check(s.state==='rising-again'&&s.risingAgainBasis==='climb-back'&&s.reading.q===1050,'still climbing again at midnight');
      s=winterAt(secondNear,13,17);
      check(s.state==='rising-again'&&s.risingAgainBasis==='climb-back'&&s.reading.q===1370&&s.lastHour.label==='about level'&&s.belowHigh.fraction<0.05&&s.minutesSinceHigh===26*60,'creeping to within 5% of the first top a day later is climbing again, not may-have-peaked');
      s=winterAt(secondLower,13,15);check(s.state==='rising-again'&&s.risingAgainBasis==='last-hour'&&s.lastHour.label==='rising'&&s.lastHour.change===55,'a fast second climb is rising again by the last hour');
      check(D.countAnchor(upTo(secondSlow,W(13,15)),winterAt(secondSlow,13,15))===null,'climbing again carries no look-back count');
      // The three-hour change must be positive: a level stretch above the low is not a climb.
      const dip=(plateau,newest)=>scene(T,[[645,90],[630,150],[615,180],[600,200],...Array.from({length:40},(_,i)=>{const m=585-i*15;return [m,m===585?180:m===570?165:m>=300?150:m>=270?(150+plateau)/2:m===0?newest:plateau]})]);
      s=D.riverState(dip(165,165),T);check(s.state==='falling'&&s.threeHour.change===0&&s.lowSinceHigh.q===150&&s.lowSinceHigh.t===T-555*M,'15 cfs above the low with a level three hours is not climbing');
      s=D.riverState(dip(165,166),T);check(s.state==='rising-again'&&s.risingAgainBasis==='climb-back'&&s.threeHour.change===1&&s.lastHour.label==='about level','with a positive three-hour change it is climbing again');
      s=D.riverState(dip(159,159.9),T);check(s.state==='falling'&&s.threeHour.change>0&&s.reading.q-s.lowSinceHigh.q<10,'less than 5% of the high above the low is not climbing');
      s=D.riverState(dip(159,160),T);check(s.state==='rising-again'&&s.reading.q-s.lowSinceHigh.q===10,'exactly 5% of the high above the low is climbing again');
      check(D.riverState(climb(0),T).lowSinceHigh===null&&D.riverState(climb(0),T).risingAgainBasis===null,'a new high has no low since the high');

      // NOAA's current issue against the gauge. This NOAA path is INVENTED: six-hourly values that never show
      // the rise (91 cfs at 11 AM Pacific, then falling), issued 8:14 AM Pacific. Only its arithmetic is tested.
      const noaaPath=[['2026-09-29T06:00:00Z',17],['2026-09-29T12:00:00Z',26],['2026-09-29T18:00:00Z',91],['2026-09-30T00:00:00Z',78],['2026-09-30T06:00:00Z',61],['2026-09-30T12:00:00Z',49],['2026-09-30T18:00:00Z',42],['2026-10-01T00:00:00Z',37],['2026-10-01T06:00:00Z',33],['2026-10-01T12:00:00Z',30],['2026-10-01T18:00:00Z',28],['2026-10-02T00:00:00Z',26],['2026-10-02T06:00:00Z',25],['2026-10-02T12:00:00Z',24],['2026-10-02T18:00:00Z',23]].map(([t,q])=>({t:at(t),q}));
      const noaaIssue='2026-09-29T15:14:00Z';
      const against=(clock,delay=20)=>D.noaaAgainstGauge(frame(clock,delay),noaaPath,noaaIssue,P(clock)+delay*M);
      let n=against('19:00');
      check(n.code==='not-tracking'&&n.notTracking&&n.reason===null&&n.gaugeCfs===181&&n.readingTime===P('19:00')&&near(n.forecastCfs,78-17/3)&&near(n.difference,181-(78-17/3))&&n.line===10&&n.threshold.cfs===100&&n.aboveLine===true&&n.riseInProgress===true,'7:00 PM: gauge 181 against NOAA 72.3 for that time, not tracking');
      check(n.compared===true&&n.covered===true&&n.basis==='at-reading-time'&&near(n.top.q,78-17/3)&&n.top.t===P('19:00')&&n.aboveTop===true&&near(n.aboveTopBy,n.difference)&&n.aboveFirstBy===null,'covered: on a falling path the highest value from the reading on is the value at the reading time');
      check(n.issued===at(noaaIssue)&&n.issueAgeMinutes===666&&n.pathOnlyFalls===true,'NOAA issue age and a path that only falls from the check time');
      check(D.noaaAgainstGauge(frame('19:00',20),noaaPath,at(noaaIssue),P('19:00')+20*M).code==='not-tracking','issue time accepted as epoch milliseconds');
      n=against('12:00');check(n.code==='not-tracking'&&near(n.forecastCfs,91-13/6)&&n.pathOnlyFalls===true,'12:00 PM: not tracking from the reading that passed the number');
      n=against('11:15');check(n.code==='above-line'&&!n.notTracking&&n.aboveLine===true&&n.riseInProgress===false&&n.difference>10,'11:15 AM: above NOAA by the line, but the measured rise has not passed the number');
      n=against('11:00');check(n.code==='within-line'&&n.aboveLine===false&&near(n.difference,6.5)&&!n.notTracking,'11:00 AM: 6.5 cfs above NOAA is inside the 10 cfs line');
      n=against('10:00');check(n.code==='within-line'&&n.difference<0&&n.pathOnlyFalls===false,'10:00 AM: gauge under NOAA, and the path still rises');
      check(n.top.q===91&&n.top.t===at('2026-09-29T18:00:00Z')&&n.aboveTop===false&&n.basis===null,'covered: the highest value from the reading on can be a later point');
      const flat=(value,from=-12)=>Array.from({length:16},(_,i)=>({t:T+(from+i*6)*H,q:value}));
      n=D.noaaAgainstGauge(D.riverState(climb(0),T+20*M),flat(100),iso(T-7*H+20*M),T+20*M);
      check(n.code==='not-tracking'&&n.issueAgeMinutes===420&&n.forecastCfs===100&&n.difference===100&&n.pathOnlyFalls===false,'first visit: a 7-hour-old issue and the gauge at twice its value');
      check(D.noaaAgainstGauge(D.riverState(climb(0),T),flat(190),iso(T-H),T).code==='not-tracking','exactly at the 10% line counts as above it');
      check(D.noaaAgainstGauge(D.riverState(climb(0),T),flat(190.5),iso(T-H),T).code==='within-line','just under the 10% line is within it');
      n=D.noaaAgainstGauge(D.riverState(quiet,T),flat(30),iso(T-H),T);check(n.code==='above-line'&&!n.notTracking&&n.difference===20&&n.riseInProgress===false,'above NOAA with no rise in progress is not "not tracking"');
      n=D.noaaAgainstGauge(D.riverState(climb(0),T+110*M),flat(100),iso(T-H),T+110*M);
      check(n.code==='unknown'&&!n.notTracking&&n.aboveLine===true&&n.riseInProgress===null&&typeof n.reason==='string'&&n.difference===100&&n.compared===true,'gauge feed late: the arithmetic is returned but the code is unknown (the page makes no comparison with a refused reading)');
      // The path below starts one hour AFTER the reading: no value is invented for the reading's time, and the gauge is
      // set against the highest value in the path, or against its first value while the last hour is "rising".
      n=D.noaaAgainstGauge(D.riverState(climb(0),T),flat(100,1),iso(T-H),T);
      check(n.compared===true&&n.covered===false&&n.forecastCfs===null&&n.difference===null&&n.gaugeCfs===200&&n.pathOnlyFalls===false&&n.reason===null,'no value is invented before the first point of the NOAA path');
      check(n.code==='not-tracking'&&n.aboveLine===true&&n.basis==='above-highest'&&n.first.q===100&&n.first.t===T+H&&n.top.q===100&&n.top.t===T+H&&n.aboveTopBy===100&&n.aboveTop===true&&n.aboveFirstBy===100,'reading before the path: the gauge is above the highest value in the path');
      check(D.noaaAgainstGauge(D.riverState(climb(0),T),flat(190,1),iso(T-H),T).basis==='above-highest'&&D.noaaAgainstGauge(D.riverState(climb(0),T),flat(190.5,1),iso(T-H),T).code==='within-line','reading before the path: exactly the 10% line above the highest value counts, just under does not');
      const laterHigher=flat(100,1).map((r,i)=>({...r,q:i===1||i===3?400:100}));
      n=D.noaaAgainstGauge(D.riverState(climb(0),T),laterHigher,iso(T-H),T);
      check(n.code==='not-tracking'&&n.basis==='above-first-and-rising'&&n.top.q===400&&n.top.t===T+7*H&&n.aboveTop===false&&n.aboveTopBy===-200&&n.aboveFirstBy===100,'reading before the path: above the first value while the last hour is rising; the highest value is the earliest on a tie');
      n=D.noaaAgainstGauge(D.riverState(climb(120,hold(120)),T),laterHigher,iso(T-H),T);
      check(n.compared===true&&n.code==='within-line'&&n.aboveLine===false&&n.basis===null&&n.aboveFirstBy===99&&n.riseInProgress===true,'reading before the path: above the first value but not rising in the last hour is not above the line');
      n=D.noaaAgainstGauge(D.riverState(quiet,T),flat(30,1),iso(T-H),T);check(n.code==='above-line'&&n.basis==='above-highest'&&n.riseInProgress===false,'reading before the path, above the highest value, no rise in progress');
      n=D.noaaAgainstGauge(D.riverState(quiet,T),flat(45,1),iso(T-H),T);check(n.code==='within-line'&&n.compared===true&&n.aboveTopBy===5,'reading before the path and within the line of it');
      n=D.noaaAgainstGauge(D.riverState(climb(0),T),[{t:T-8*H,q:100},...flat(100,1)],iso(T-H),T);check(n.forecastCfs===null&&n.code==='unknown'&&n.compared===false&&n.aboveLine===null,'no value across forecast points more than 6 hours apart');
      n=D.noaaAgainstGauge(D.riverState(climb(0),T),flat(100),iso(T-49*H),T);check(n.code==='unknown'&&n.pathOnlyFalls===null&&n.forecastCfs===null&&n.issued===T-49*H&&typeof n.reason==='string','an issue over 48 hours old is not compared');
      n=D.noaaAgainstGauge(null,flat(100),iso(T-H),T);check(n.code==='unknown'&&n.gaugeCfs===null&&n.pathOnlyFalls===false,'no gauge reading: nothing to compare');
      check(D.noaaAgainstGauge(D.riverState(climb(0),T),null,iso(T-H),T).code==='unknown'&&D.noaaAgainstGauge(D.riverState(climb(0),T),flat(100),undefined,T).code==='unknown','missing forecast path or issue time fails closed');
      const window72=rows=>D.forecast(rows,iso(T-H),T);
      check(D.forecastOnlyFalls(window72(flat(100).map((r,i)=>({...r,q:200-i}))))===true,'a path that only falls');
      check(D.forecastOnlyFalls(window72(flat(100)))===false,'a flat path does not fall');
      check(D.forecastOnlyFalls(window72(flat(100).map((r,i)=>({...r,q:i===5?150:200-i}))))===false,'a path that falls and then steps up does not only fall');
      check(D.forecastOnlyFalls(window72(flat(100).map((r,i)=>({...r,q:100+i}))))===false,'a rising path does not fall');
      check(D.forecastOnlyFalls({usable:false,rows:[]})===null&&D.forecastOnlyFalls(null)===null,'no usable forecast: no falls-only flag');

      // The earlier-forecast comparison takes its "rising" word from the last-hour label.
      const watch={code:'outpacing',expected:80,observed:101,difference:21,line:10,change3:4,span3:3,snapshot:{}};
      let w=D.watchWithLastHour(watch,{fresh:true,lastHour:{label:'rising'}});check(w.code==='outpacing'&&w.lastHourLabel==='rising'&&w.expected===80&&w.difference===21,'above the earlier forecast and rising in the last hour');
      w=D.watchWithLastHour(watch,{fresh:true,lastHour:{label:'about level'}});check(w.code==='above-prior'&&w.lastHourLabel==='about level','a positive three-hour change is not "rising" when the last hour is level');
      check(D.watchWithLastHour(watch,{fresh:true,lastHour:{label:'falling'}}).code==='above-prior','falling in the last hour is not rising');
      check(D.watchWithLastHour({...watch,code:'above-prior',change3:-1},{fresh:true,lastHour:{label:'rising'}}).code==='outpacing','rising in the last hour is rising even when the three-hour change is not');
      w=D.watchWithLastHour(watch,{fresh:false,lastHour:null});check(w.code==='above-prior'&&w.lastHourLabel===null,'no last-hour label: never "rising"');
      check(D.watchWithLastHour(watch,{fresh:true,lastHour:null}).lastHourLabel===null&&D.watchWithLastHour(watch,null).code==='above-prior','missing river state: never "rising"');
      for(const code of ['tracking','learning','unknown'])check(D.watchWithLastHour({...watch,code},{fresh:true,lastHour:{label:'rising'}}).code===code,'other comparison codes are unchanged: '+code);
      check(D.watchWithLastHour(null,{fresh:true,lastHour:{label:'rising'}}).code==='unknown','missing comparison stays unknown');
      const tenPm=frame('22:00'),savedTimes=Array.from({length:14},(_,i)=>P('16:00')+i*6*H);
      const saved={issueTime:iso(P('15:00')),capturedAt:iso(P('16:00')),gaugeTime:iso(P('16:00')),gaugeCfs:164,adjustment:80,alignedPath:savedTimes.map((t,i)=>({t,q:i?150:164})),rawPath:savedTimes.map((t,i)=>({t,q:i?70:84}))};
      w=D.surpriseWatch({t:tenPm.reading.t,q:tenPm.reading.q,change3:tenPm.threeHour.change,span3:tenPm.threeHour.spanMinutes/60,fresh:true},[saved]);
      check(w.code==='outpacing'&&w.change3===10,'10:00 PM on 29 September: the three-hour rule alone still says rising');
      check(D.watchWithLastHour(w,tenPm).code==='above-prior'&&D.watchWithLastHour(w,tenPm).lastHourLabel==='about level','10:00 PM on 29 September: with the last-hour label it does not');

      // Tide: the extreme that just passed, the direction, and the next two.
      const tideRows=D.tides(fx.tides);check(tideRows.length===16,'tide fixture parsed');
      let tide=D.tideState(tideRows,at('2026-09-29T19:20:00-07:00'));
      check(tide.available&&tide.reason===null&&tide.last.type==='H'&&tide.last.t===at('2026-09-29T18:46:00-07:00')&&near(tide.last.v,8.168)&&tide.minutesSinceLast===34&&tide.direction==='falling','the 6:46 PM high tide is still shown at 7:20 PM');
      check(tide.next.length===2&&tide.next[0].type==='L'&&tide.next[0].t===at('2026-09-30T01:56:00-07:00')&&near(tide.next[0].v,-1.224)&&tide.next[1].type==='H'&&tide.next[1].t===at('2026-09-30T09:13:00-07:00'),'the next two tide extremes');
      tide=D.tideState(tideRows,at('2026-09-29T18:46:00-07:00'));check(tide.last.type==='H'&&tide.minutesSinceLast===0&&tide.direction==='falling'&&tide.next[0].type==='L','an extreme exactly at the check time has passed');
      tide=D.tideState(tideRows,at('2026-09-29T18:45:00-07:00'));check(tide.last.type==='L'&&near(tide.last.v,4.593)&&tide.direction==='rising'&&tide.next[0].type==='H'&&tide.next[0].t===at('2026-09-29T18:46:00-07:00'),'one minute before the high the tide is still rising');
      tide=D.tideState([...tideRows].reverse(),at('2026-09-29T19:20:00-07:00'));check(tide.last.t===at('2026-09-29T18:46:00-07:00')&&tide.next.length===2,'tide rows in any order');
      for(const bad of [null,undefined,[],{},[{t:'x',v:1,type:'H'},{t:T+H,v:NaN,type:'H'},{t:T+2*H,v:1,type:'X'}]]){tide=D.tideState(bad,T);check(!tide.available&&tide.last===null&&tide.direction===null&&tide.next.length===0&&typeof tide.reason==='string','missing or failed tide feed is unavailable, not an empty list');}
      tide=D.tideState(tideRows,at('2026-10-02T00:00:00Z'));check(!tide.available&&tide.next.length===0&&typeof tide.reason==='string','predictions that end before the check time are unavailable');
      tide=D.tideState(tideRows,at('2026-09-27T12:00:00Z'));check(tide.available&&tide.last===null&&tide.minutesSinceLast===null&&tide.direction===null&&tide.next.length===2&&typeof tide.reason==='string','predictions that start after the check time give no direction');
      tide=D.tideState(tideRows.filter(r=>r.t!==at('2026-09-30T08:56:00Z')),at('2026-09-29T19:20:00-07:00'));check(tide.available&&tide.direction===null&&tide.last.type==='H'&&tide.next[0].type==='H'&&typeof tide.reason==='string','a list whose highs and lows do not alternate gives no direction');
      check(!D.tideState(tideRows,NaN).available&&!D.tideState([tideRows[0],{...tideRows[0]}],tideRows[0].t-H).available,'invalid check time or duplicate tide times fail closed');
      let request=D.tideRequest(at('2026-09-30T02:20:00Z'));check(request.beginDate==='20260929'&&request.rangeHours===192,'tide request starts on the GMT date 24 hours back');
      check(D.tideRequest(at('2026-09-30T00:00:00Z')).beginDate==='20260929'&&D.tideRequest(at('2026-09-29T23:59:00Z')).beginDate==='20260928'&&D.tideRequest(NaN)===null&&D.tideRequest(null)===null,'tide request date boundary');
      for(const hour of [0,7,13,23.9]){const now=at('2026-01-01T00:00:00Z')+hour*H;request=D.tideRequest(now);const begin=Date.UTC(+request.beginDate.slice(0,4),+request.beginDate.slice(4,6)-1,+request.beginDate.slice(6,8));check(begin<=now-24*H&&begin>now-48*H&&begin+request.rangeHours*H>=now+6*24*H,'tide request reaches 24 to 48 hours back and 6 days ahead');}

      // Rain: missing against zero, the suspect-zero flag, and the dry season.
      check(D.rainBlockState({complete:true,mm:0}).status==='zero'&&D.rainBlockState({complete:true,mm:0}).mm===0,'a complete block of exactly zero rain is zero');
      check(D.rainBlockState({complete:true,mm:2.54}).status==='amount'&&D.rainBlockState({complete:true,mm:2.54}).mm===2.54,'a complete block with rain is an amount');
      for(const bin of [null,undefined,{},{complete:false,mm:null},{complete:false,mm:0},{complete:true,mm:null},{complete:true,mm:-1},{complete:true,mm:'0'},{complete:true,mm:NaN},{complete:'yes',mm:0}]){const block=D.rainBlockState(bin);check(block.status==='missing'&&block.mm===null,'a block with no value is missing, never zero');}
      const feed=D.rain({properties:{updateTime:iso(T-H),quantitativePrecipitation:{uom:'wmoUnit:mm',values:[{validTime:iso(T)+'/PT6H',value:0},{validTime:iso(T+6*H)+'/PT6H',value:null},{validTime:iso(T+12*H)+'/PT6H',value:5.08}]}}},T);
      check(D.rainBins(feed,T,24,6).map(bin=>D.rainBlockState(bin).status).join()==='zero,missing,amount,missing','forecast blocks: zero, no value, an amount, and no coverage');
      const NL=String.fromCharCode(10), windows=total=>'0.00 0.00 0.00 0.00 '+(total===null?'M':total.toFixed(2))+' 9.00 9.00';   // 1, 3, 6, 12, 24, 48 and 72 hours
      const report=(padilla,burlington,sedro)=>D.rrmRain({issuanceTime:iso(T-H/2),productCode:'RRM',issuingOffice:'KSEW',productText:['000','RRMSEW','National Weather Service Seattle WA','','Padilla Bay Farm '+windows(padilla),'Burlington '+windows(burlington),'Sedro Wooley RAWS '+windows(sedro),''].join(NL)},T);
      let zero=D.suspectZeroRain(report(0.30,0.25,0));check(zero.evaluated&&zero.flags.join()==='false,false,true'&&zero.totals24In.join()==='0.3,0.25,0','a gauge at zero while both others report 0.25 inch or more is suspect');
      check(D.suspectZeroRain(report(0,0.25,0.25)).flags.join()==='true,false,false'&&D.suspectZeroRain(report(0.5,0,1)).flags.join()==='false,true,false','the flag follows whichever gauge reads zero');
      zero=D.suspectZeroRain(report(0.30,0.24,0));check(zero.evaluated&&!zero.flags.includes(true),'no flag when one of the others is under 0.25 inch');
      check(!D.suspectZeroRain(report(0.30,0.01,0.01)).flags.includes(true)&&!D.suspectZeroRain(report(0,0,0.50)).flags.includes(true)&&!D.suspectZeroRain(report(0,0,0)).flags.includes(true),'no flag for a small amount, for two zeros, or for a dry day');
      zero=D.suspectZeroRain(report(0,0.30,null));check(!zero.evaluated&&!zero.flags.includes(true)&&zero.totals24In[2]===null,'no flag when a gauge has no 24-hour total');
      zero=D.suspectZeroRain(report(0.30,0.25,null));check(!zero.evaluated&&!zero.flags.includes(true),'a missing total is not a zero');
      const partial=report(0,0.30,0.30);partial.stations[1]={...partial.stations[1],available:false};
      check(!D.suspectZeroRain(partial).evaluated&&!D.suspectZeroRain(partial).flags.includes(true),'no flag when a gauge row is unavailable');
      check(!D.suspectZeroRain({...report(0,0.30,0.30),stations:report(0,0.30,0.30).stations.slice(0,2)}).flags.includes(true),'no flag unless all three gauges are listed');
      zero=D.suspectZeroRain(null);check(!zero.evaluated&&zero.flags.length===0&&zero.totals24In.length===0,'no observed-rain report: nothing is flagged');
      check(D.drySeasonContext(at('2026-05-01T06:30:00Z'))===false&&D.drySeasonContext(at('2026-05-01T07:30:00Z'))===true,'dry-season context starts at Pacific midnight on 1 May');
      check(D.drySeasonContext(at('2026-11-01T06:30:00Z'))===true&&D.drySeasonContext(at('2026-11-01T07:30:00Z'))===false,'dry-season context ends at Pacific midnight on 1 November');
      check(D.drySeasonContext(at('2026-01-15T20:00:00Z'))===false&&D.drySeasonContext(T)===true&&D.drySeasonContext(NaN)===null&&D.drySeasonContext('2026-07-01')===null,'dry-season context by month, and null for an invalid time');

      // The look-back counts. Each number below was checked against the look-back's own printed output.
      const E=D.EVIDENCE;
      check(Object.isFrozen(E)&&Object.isFrozen(E.pause)&&Object.isFrozen(E.timing)&&Object.isFrozen(E.timing.all)&&Object.isFrozen(E.timing.all.middleHalfHours)&&Object.isFrozen(E.wait.medianMoreHours)&&Object.isFrozen(E.rainContext),'evidence is frozen at every level');
      check(E.caveat==='A look-back on past years, not a forecast.','evidence says it is a look-back, not a forecast');
      check(E.rises.count===172&&E.rises.period==='2011 to 2023'&&E.rises.readings==='15-minute readings','172 rises, 2011 to 2023, 15-minute readings');
      check(E.pause.rises===172&&E.pause.higherAgain===67&&E.pause.higherByMoreThan5Percent===42&&E.pause.withinHours===24&&E.pause.afterMinutes===R.pauseMinutes,'pause: 67 and 42 of 172');
      check(E.peak2h.rises===172&&E.peak2h.within12h===19&&E.peak2h.within24h===30&&E.peak2h.afterMinutes===R.peakMinutes,'two hours without a new high: 19 and 30 of 172');
      check(E.peak2h.aboutOneIn12h===9&&E.peak2h.aboutOneIn24h===6&&E.peak2h.aboutOneIn12h===Math.round(172/19)&&E.peak2h.aboutOneIn24h===Math.round(172/30),'two-hour odds follow from the counts');
      check(E.falling.rises===172&&E.falling.within12h===10&&E.falling.within24h===21&&E.falling.belowHighFraction===R.fallingFraction,'5% below the high: 10 and 21 of 172');
      check(E.falling.aboutOneIn12h===17&&E.falling.aboutOneIn24h===8&&E.falling.aboutOneIn12h===Math.round(172/10)&&E.falling.aboutOneIn24h===Math.round(172/21),'falling odds follow from the counts');
      check(E.timing.all.rises===172&&E.timing.all.medianHours===5.5&&E.timing.all.middleHalfHours.join()==='3,9'&&E.timing.all.middleHalfHoursAsComputed.join()==='3.2,9.1'&&E.timing.all.under2h===18&&E.timing.all.atLeast16h===22,'timing, all seasons');
      check(E.timing.dry.rises===52&&E.timing.dry.medianHours===6&&E.timing.dry.medianHoursAsComputed===5.9&&E.timing.dry.middleHalfHours.join()==='3.5,8'&&E.timing.dry.middleHalfHoursAsComputed.join()==='3.4,8.1'&&E.timing.dry.over8h===13&&E.timing.dry.atLeast16h===5,'timing, May to October');
      const half=value=>Math.round(value*2)/2;
      check(E.timing.all.middleHalfHoursAsComputed.map(half).join()===E.timing.all.middleHalfHours.join()&&E.timing.dry.middleHalfHoursAsComputed.map(half).join()===E.timing.dry.middleHalfHours.join()&&half(E.timing.dry.medianHoursAsComputed)===E.timing.dry.medianHours,'rounded timing figures are the computed ones to the nearest half hour');
      check(E.wait.stagesHours.join()==='0,2,4,6,8,12'&&E.wait.risesStillWaiting.join()==='167,150,109,74,49,29'&&E.wait.medianMoreHours.join()==='5.5,4,3.5,4,5.8,7'&&E.wait.upperQuartileMoreHours.join()==='9.4,8,8.8,11.9,12.8,13.8','wait figures at each stage');
      check(E.wait.typicalWaitHours[0]===Math.min(...E.wait.medianMoreHours)&&E.wait.typicalWaitHours[1]===Math.max(...E.wait.medianMoreHours)&&E.wait.typicalWaitHours.join()==='3.5,7'&&E.wait.oneInFourAtLeastHours===Math.min(...E.wait.upperQuartileMoreHours)&&E.wait.oneInFourAtLeastHours===8,'typical wait 3.5 to 7 hours; one rise in four needed 8 or more');
      check(E.aligned.rises===66&&E.aligned.falseAlertEpisodesAligned===29&&E.aligned.falseAlertEpisodesAsIssued===38&&E.aligned.warned12hEitherWay===36&&E.aligned.leadHours===12&&E.aligned.period==='October 2020 to September 2026','gauge-aligned: 29 against 38 false-alert episodes, 66 rises');
      check(E.noaaDry.rises===32&&E.noaaDry.shown12hAhead===25&&E.noaaDry.notShown===7&&E.noaaDry.shown12hAhead+E.noaaDry.notShown===E.noaaDry.rises&&E.noaaDry.notShownIncludes==='29 September 2026'&&E.noaaDry.leadHours===12,'NOAA in the dry season: 25 of 32, not 7');
      const C=E.rainContext;
      check(C.thresholdIn===0.75&&C.windowHours===24&&C.occasions===45&&C.followed===23&&C.followedWithinHours===36&&C.riseCfs===100&&C.perSeason===5&&C.perSeason===Math.round(C.occasions/C.seasons),'rain context: 45 occasions, 23 followed, about 5 a season');
      check(C.withNoNoaaRise===26&&C.withNoNoaaRiseFollowed===7&&C.aboutOneInWithNoNoaaRise===4&&C.aboutOneInWithNoNoaaRise===Math.round(26/7)&&C.risesNoaaDidNotShow===E.noaaDry.notShown&&C.ofThoseRainForecastAhead===4&&C.leadHours===12&&C.aheadYears==='2024 to 2026'&&C.aheadIncludes==='29 September 2026'&&C.risesWithForecast===32&&C.risesWithLessRain===10,'rain context: 7 of 26, 4 of the 7, 10 of 32');
      const A=E.afterNewHigh;
      check(A.readings===4027&&A.rises===172&&A.withinHours===2&&A.withinPercent===24.9&&A.atLeastHours===8&&A.atLeastPercent===26.6&&A.aboutOneInWithin===4&&A.aboutOneInAtLeast===4&&A.aboutOneInWithin===Math.round(100/A.withinPercent)&&A.aboutOneInAtLeast===Math.round(100/A.atLeastPercent),'after a new high: 4,027 readings in 172 rises; 24.9% within 2 hours, 26.6% at 8 hours or more');
      check(E.wait.lowerQuartileMoreHours.join()==='3.2,2,1.5,1.5,2,4'&&E.wait.lowerQuartileMoreHours.every((q,i)=>q<=E.wait.medianMoreHours[i]&&E.wait.medianMoreHours[i]<=E.wait.upperQuartileMoreHours[i]),'wait figures: the lower quarter at each stage, under the middle value');
      const RP=E.rainPause;
      check(RP.afterMinutes===R.peakMinutes&&RP.pausesWithRadar===62&&RP.rainingPauses===23&&RP.rainingRoseAgain===4&&RP.dryPauses===39&&RP.dryRoseAgain===2&&RP.rainingPauses+RP.dryPauses===RP.pausesWithRadar&&RP.radarWindowHours===3&&RP.radarAtLeastMm===0.5,'rain and a two-hour pause: 4 of 23 against 2 of 39');
      check(RP.storm==='29 September 2026'&&RP.rainEnded==='about 2 pm'&&RP.riverRoseUntil==='9 to 10 pm'&&RP.highestHourlyCfs===191,'the storm the rain sentence names');
      check(E.noaaDry.period==='May to October rises of July 2018 to early October 2026'&&E.rainContext.period==='dry seasons of July 2018 to early October 2026'&&E.noaaDry.source.includes('July 2018 to early October 2026')&&E.rainContext.source.includes('July 2018 to early October 2026'),'the two forecast look-backs cover July 2018 to early October 2026');
      check(Object.isFrozen(E.afterNewHigh)&&Object.isFrozen(E.rainPause)&&Object.isFrozen(E.wait.lowerQuartileMoreHours),'the new evidence entries are frozen');
      for(const key of ['pause','peak2h','falling','timing','wait','afterNewHigh','rainPause','aligned','noaaDry','rainContext']){const entry=E[key];check(typeof entry.period==='string'&&entry.period.length>3&&typeof entry.source==='string'&&entry.source.startsWith('Look-back')&&entry.source.length>60&&!['/',String.fromCharCode(92),'.txt','.py','.md','.json','C:'].some(piece=>entry.source.includes(piece)),'evidence entry names its look-back in plain words: '+key);}
      return count;
    }""", {'readings': sept29_readings(), 'tides': SEPT29_TIDES})
    assert page.locator('#flow').inner_text() == '101'
    assert page.locator('#rain-total').inner_text() == '0.80'
    assert 'not basin-wide rain' in page.locator('.context-grid .measurement-limit').inner_text()
    assert page.locator('#flow-chart svg').count() == 1
    assert page.locator('#rain-chart svg').count() == 1
    assert '139,116' in page.locator('#rain-points').inner_text()
    assert page.locator('#rain-forecast-table tbody tr').count() == 6
    assert page.locator('#observed-rain-table').get_by_text('0.00', exact=True).count() >= 1
    assert page.locator('#observed-rain-table').get_by_text('Unavailable', exact=True).count() >= 1
    assert page.locator('#radar-status').inner_text() in ('Animating retrieved frames', 'Latest retrieved frame')
    assert page.locator('#radar-loop').evaluate('img => img.complete && img.naturalWidth > 0')
    assert 'legend retrieved' in page.locator('#radar-legend-status').inner_text().lower()
    assert 'Capabilities retrieved' in page.locator('#radar-source-card').inner_text()
    assert page.locator('#radar-toggle').inner_text() == 'Pause animation'
    assert page.locator('#radar-toggle').evaluate('el => el.getBoundingClientRect().height >= 44')
    assert page.locator('#radar-overlay .basin-shape').count() == 1
    assert page.locator('#radar-overlay .gauge-marker').count() == 1
    assert page.locator('#radar-overlay .rain-marker').count() == 2
    assert page.locator('#radar-basin-note').is_hidden()
    assert page.locator('#radar-overlay .rain-marker text').evaluate_all("els => { const a=els[0].getBoundingClientRect(), b=els[1].getBoundingClientRect(); return a.bottom <= b.top || b.bottom <= a.top || a.right <= b.left || b.right <= a.left; }")
    assert 'valid' in page.locator('#radar-frame-time').inner_text()
    # Version 7: the River block replaces the strip's "River now" and "About 3-hour change" tiles.
    assert page.locator('#river-block #flow').inner_text() == '101'
    assert page.locator('#river-time').inner_text().startswith('at ') and page.locator('#river-time').inner_text().endswith(('PDT', 'PST'))
    assert re.fullmatch(r'\d+ minutes? old', page.locator('#river-age').inner_text())
    assert page.locator('#river-change').inner_text() == 'Last hour: +2 cfs (rising). About 3 hours: +4 cfs.'
    assert re.fullmatch(r'Rise above the 24-hour low: 25 cfs \(\d+% of the \d+ cfs \S+ number; low 76 cfs at .+ P[DS]T\)\.', page.locator('#river-rise').inner_text())
    for ident in ['river-state', 'river-wait', 'river-rain-note', 'river-past', 'river-high']:
        assert page.locator('#' + ident).is_hidden(), ident   # no rise in progress: no state and no "high" language
    assert page.locator('#river-announce').inner_text() == ''   # nothing is announced on a first load
    assert re.fullmatch(r'NOAA’s river forecast, issued .+ P[DS]T \(1 hour ago\), has 126 cfs for .+ P[DS]T\. The gauge read 101 cfs then: 25 cfs lower\.', page.locator('#noaa-compare').inner_text())
    assert page.locator('#noaa-flag').is_hidden()
    assert re.fullmatch(r'Low of 2\.0 ft was at .+ P[DS]T, 4 h [01] min before this check\. The tide is rising to a high of 8\.0 ft at .+ P[DS]T, then a low of -1\.0 ft at .+ P[DS]T\.', page.locator('#tide-now').inner_text())
    assert page.locator('#tide-list .tide-row').count() == 5 and 'passed' in page.locator('#tide-list .tide-row').first.inner_text()
    assert re.fullmatch(r'within the available path · issued .+ P[DS]T', page.locator('#ops-forecast-note').inner_text())
    assert page.locator('.ops-strip > div').count() == 3
    assert page.locator('#ops-threshold').inner_text().endswith('cfs')
    assert page.locator('#flow-chart').evaluate("el => el.getBoundingClientRect().top < document.getElementById('surprise-watch').getBoundingClientRect().top")
    assert page.locator('#radar-loop').evaluate("el => el.getBoundingClientRect().top < document.getElementById('surprise-watch').getBoundingClientRect().top")
    assert page.locator('#rise-title').inner_text().startswith('Largest relative rise:')
    assert 'largest rise relative to the seasonal reference' in page.locator('#rise-detail').inner_text().lower()
    assert page.locator('#saved-path-legend').is_hidden()
    assert page.locator('#flow-chart path[stroke="var(--saved)"]').count() == 0
    # ------------------------------------------------------------------------------------------------------
    # Version 7 page checks. The rise of 29 September 2026 is replayed through the page with the device clock
    # fixed, so each sentence asserted below is what a visitor would have read at that moment. The gauge
    # readings, the tide predictions and NOAA's river forecast issues are real (see REAL_NOAA_ISSUES above);
    # the rain and the radar are INVENTED. A page opened at 7:20 PM holds the 7:00 PM reading, 20 minutes old.
    # ------------------------------------------------------------------------------------------------------
    EVIDENCE = page.evaluate('SamishData.EVIDENCE')
    RULES = page.evaluate('SamishData.RIVER_RULES')
    half = lambda n: str(int(n)) if float(n).is_integer() else (str(int(n)) if int(n) else '') + '½'
    # The sentences that carry a count, rebuilt here from the evidence object. The page must print exactly these.
    E_WAIT, E_PAUSE, E_PEAK, E_FALL, E_DRY, E_RAIN, E_AFTER, E_RAINPAUSE = (EVIDENCE[key] for key in ['wait', 'pause', 'peak2h', 'falling', 'noaaDry', 'rainContext', 'afterNewHigh', 'rainPause'])
    AFTER_NEW_HIGH = (f"When a reading was a new high in past rises, the top of the rise came within the next {E_AFTER['withinHours']} hours about 1 time in {E_AFTER['aboutOneInWithin']} and was still "
                      f"{E_AFTER['atLeastHours']} hours or more away about 1 time in {E_AFTER['aboutOneInAtLeast']} ({E_AFTER['readings']:,} such readings in {E_AFTER['rises']} rises). "
                      "A new high can be the top; a long rise is not due to stop.")
    PAUSE = (f"A pause is not a peak: after a one-hour pause, {E_PAUSE['higherAgain']} of {E_PAUSE['rises']} past rises went higher again within a day, "
             f"{E_PAUSE['higherByMoreThan5Percent']} of them by more than 5%.")
    PEAK = (f"Of {E_PEAK['rises']} past rises that went 2 hours without a new high, counted from that 2-hour mark, the river later climbed more than 5% above that high within 12 hours in "
            f"{E_PEAK['within12h']} (about 1 in {E_PEAK['aboutOneIn12h']}) and within 24 hours in {E_PEAK['within24h']} (about 1 in {E_PEAK['aboutOneIn24h']}).")
    FALLING = (f"Of {E_FALL['rises']} past rises, counted from that point, the river later climbed more than 5% above that high within 12 hours in "
               f"{E_FALL['within12h']} (about 1 in {E_FALL['aboutOneIn12h']}) and within 24 hours in {E_FALL['within24h']} (about 1 in {E_FALL['aboutOneIn24h']}).")
    NOAA_DRY = (f"NOAA’s river forecast, read hour by hour, showed a closure-size rise {E_DRY['leadHours']} or more hours ahead for {E_DRY['shown12hAhead']} of "
                f"{E_DRY['rises']} {E_DRY['period']}, and not for {E_DRY['notShown']}, among them {E_DRY['notShownIncludes']}.")
    RAIN_CONTEXT = (f"In a look-back over the {E_RAIN['period']}, the river forecast centre’s rain forecast for this basin reached {E_RAIN['thresholdIn']} inch or more in "
                    f"{E_RAIN['windowHours']} hours about {E_RAIN['perSeason']} times a season. About half of those times ({E_RAIN['followed']} of {E_RAIN['occasions']}) the river "
                    f"then rose by {E_RAIN['riseCfs']} cubic feet per second or more within a day and a half. When NOAA’s river forecast showed no such rise and the rain "
                    f"forecast was that high, a rise followed about 1 time in {E_RAIN['aboutOneInWithNoNoaaRise']} ({E_RAIN['withNoNoaaRiseFollowed']} of {E_RAIN['withNoNoaaRise']}). "
                    f"Rain that high was in the forecast {E_RAIN['leadHours']} or more hours ahead of {E_RAIN['ofThoseRainForecastAhead']} of the {E_RAIN['risesNoaaDidNotShow']} "
                    f"dry-season rises that NOAA’s river forecast did not show, all four in {E_RAIN['aheadYears']}, including {E_RAIN['aheadIncludes']}. Less rain than this is "
                    f"not an all-clear: {E_RAIN['risesWithLessRain']} of {E_RAIN['risesWithForecast']} rises came with less. These counts are for a different rain forecast from "
                    "the two points shown here and have not been checked against them.")
    RAIN_BESIDE_PEAK = ('If rain is still falling over the basin on radar, a pause is less likely to be the peak. Rain stopping does not mean the river has peaked: '
                        f"on {E_RAINPAUSE['storm']} the rain ended {E_RAINPAUSE['rainEnded']} and the river kept rising until {E_RAINPAUSE['riverRoseUntil']}.")
    CAVEAT = EVIDENCE['caveat']
    # The same sentences with the numbers written out. If the evidence object drifted, these fail even though the
    # page and the object would still agree with each other.
    assert AFTER_NEW_HIGH == ('When a reading was a new high in past rises, the top of the rise came within the next 2 hours about 1 time in 4 and was still 8 hours or more away about 1 time in 4 '
                              '(4,027 such readings in 172 rises). A new high can be the top; a long rise is not due to stop.')
    assert PAUSE == 'A pause is not a peak: after a one-hour pause, 67 of 172 past rises went higher again within a day, 42 of them by more than 5%.'
    assert PEAK == 'Of 172 past rises that went 2 hours without a new high, counted from that 2-hour mark, the river later climbed more than 5% above that high within 12 hours in 19 (about 1 in 9) and within 24 hours in 30 (about 1 in 6).'
    assert FALLING == 'Of 172 past rises, counted from that point, the river later climbed more than 5% above that high within 12 hours in 10 (about 1 in 17) and within 24 hours in 21 (about 1 in 8).'
    assert NOAA_DRY == 'NOAA’s river forecast, read hour by hour, showed a closure-size rise 12 or more hours ahead for 25 of 32 May to October rises of July 2018 to early October 2026, and not for 7, among them 29 September 2026.'
    assert RAIN_CONTEXT == ('In a look-back over the dry seasons of July 2018 to early October 2026, the river forecast centre’s rain forecast for this basin reached 0.75 inch or more in 24 hours about 5 times a season. '
                            'About half of those times (23 of 45) the river then rose by 100 cubic feet per second or more within a day and a half. When NOAA’s river forecast showed no such rise '
                            'and the rain forecast was that high, a rise followed about 1 time in 4 (7 of 26). Rain that high was in the forecast 12 or more hours ahead of 4 of the 7 dry-season '
                            'rises that NOAA’s river forecast did not show, all four in 2024 to 2026, including 29 September 2026. Less rain than this is not an all-clear: 10 of 32 rises came '
                            'with less. These counts are for a different rain forecast from the two points shown here and have not been checked against them.')
    assert RAIN_BESIDE_PEAK == ('If rain is still falling over the basin on radar, a pause is less likely to be the peak. Rain stopping does not mean the river has peaked: '
                                'on 29 September 2026 the rain ended about 2 pm and the river kept rising until 9 to 10 pm.')
    assert CAVEAT == 'A look-back on past years, not a forecast.'
    NOT_TRACKING = 'NOAA’s forecast is not tracking this rise. Do not read a peak time from it.'
    NO_PEAK_ABOVE = 'No peak time is read from NOAA’s forecast while the gauge is above it.'
    NO_PEAK_UNCOMPARED = 'No peak time is read from NOAA’s forecast: it cannot be compared with the gauge right now.'
    RISE_UNTOLD = 'Whether a measured rise is in progress cannot be told from the gauge record. ' + NO_PEAK_ABOVE
    BUILT_ON_ABOVE = 'This forward look is built on NOAA’s forecast, which the gauge is currently above.'
    NOT_ALIGNED = 'The forecast cannot be aligned near the latest gauge reading'
    UNDER_AN_HOUR = ' Under an hour without a new high says nothing about the top of a rise.'
    past = lambda since: f'Past the 100 cfs May–October number since the {since} reading. This page’s arithmetic, not the Department of Health’s decision.'
    past_gap = lambda since: f'Past the 100 cfs number since at or before the {since} reading (a gap in the gauge record hides the exact time).'
    rise_line = lambda cfs, share, low: f'Rise above the 24-hour low: {cfs} cfs ({share}% of the 100 cfs May–October number; low {low}).'
    rise_at_least = lambda cfs, share, gap: f'Rise above the lowest reading held from the last 24 hours: at least {cfs} cfs ({share}% of the 100 cfs May–October number). The gauge record has a {gap}-minute gap in that time, so the rise may be larger.'
    # NOAA's value for the time of the reading (the reading lies inside NOAA's path) ...
    noaa_line = lambda issued, age, value, at, gauge, gap: f'NOAA’s river forecast, issued {issued} ({age} ago), has {value} cfs for {at}. The gauge read {gauge} cfs then: {gap} cfs higher.'
    # ... or, for the hours after an issue when NOAA's path has not started yet, its first and highest values.
    noaa_ahead = lambda issued, age, starts, first, top, top_at, gauge, at: f'NOAA’s river forecast, issued {issued} ({age} ago), starts at {starts} with {first} cfs; its highest value is {top} cfs at {top_at}. The gauge read {gauge} cfs at {at}.'
    above_highest = lambda by: f'The gauge is already {by} cfs above the highest value in NOAA’s forecast.'
    not_compared = lambda issued, age, why: f'NOAA’s river forecast, issued {issued} ({age} ago), is not compared with the gauge: {why}.'

    # No count that lives in the evidence object may be typed into the page's own files: the sentences are
    # assembled from the object, so these strings can appear only in data.js.
    page_sources = {name: (ROOT / name).read_text(encoding='utf-8') for name in ['index.html', 'app.js']}
    for name, text in page_sources.items():
        for typed in ['172', '67 of', '42 of', '23 of 45', '7 of 26', '25 of 32', '10 of 32', '4 of the 7', '29 false', 'in 19 (', 'in 30 (', 'in 10 (', 'in 21 (', '3½', '5½', '0.75 inch', '4,027', '4027', '24.9', '26.6', '29 September', 'about 2 pm']:
            assert typed not in text, (name, 'a look-back count is typed into the page instead of read from the evidence object', typed)
        assert 'backtest' not in text.lower(), (name, 'the removed data file is still mentioned')
    assert not (ROOT / 'backtest.js').exists(), 'backtest.js must not be published'
    assert 'backtest' not in (ROOT / 'README.md').read_text(encoding='utf-8').lower()
    # The page names no grower: the two places that did now use neutral wording.
    assert page.locator('.cross-check > strong').first.inner_text() == 'Other views used alongside this page'
    assert 'the kind of divergence a grower described.' in page_sources['index.html'] and ' uses</strong>' not in page_sources['index.html']
    assert page.locator('#outlook h1').inner_text() == 'What the river is doing, and what the sources say.'
    SEASONAL_NUMBERS_NOTE = ('The 100, 200 and 400 cfs numbers and the 24-hour period are as published in the Washington Department of Health’s growing-area map record for Samish Bay '
                             '(record dated 4 September 2026, read 13 October 2026). How the Department sets the starting flow, and its clock at a season boundary, are not published there.')
    assert page.locator('.rise-card div.note').inner_text() == SEASONAL_NUMBERS_NOTE and SEASONAL_NUMBERS_NOTE in ' '.join((ROOT / 'README.md').read_text(encoding='utf-8').split()), 'the same wording about the seasonal numbers on the page and in the README'
    assert 'numbers and 24-hour duration are confirmed' not in page.locator('#outlook').inner_text()

    # Words that must not appear on the Outlook tab. ALLOWED lists the exact phrases the page is meant to print
    # there that contain one, each a denial of the banned meaning: "may have peaked"; the rain sentence beside
    # it ("does not mean the river has peaked"); the dry-season rain paragraph ("is not an all-clear"); and two
    # version 6 disclaimers. Each is removed before the scan, so any other use of a banned word fails.
    BANNED = ['crested', 'final', 'all clear', 'safe', 'has not happened', 'wait', 'go now', 'peaked']
    ALLOWED = ['may have peaked',                              # the one permitted use of "peaked"
               'does not mean the river has peaked',           # the rain sentence printed beside "may have peaked"
               'is not an all-clear',                          # the dry-season rain context paragraph
               'not a closure, safety, or all-clear signal',   # version 6 disclaimer on the forecast-change check
               'closure, or all-clear recommendation']         # version 6 planning-limit disclaimer
    def banned_words(text):
        flat = lambda value: ' '.join(value.lower().replace('-', ' ').split())
        scan = flat(text)
        for phrase in ALLOWED:
            scan = scan.replace(flat(phrase), ' ')
        return [word for word in BANNED if re.search(r'\b' + re.escape(word) + r'\b', scan)]
    assert banned_words('The river crested at 9 PM and it is safe; all-clear, please wait, go now. The peak is final and has not happened.') == ['crested', 'final', 'all clear', 'safe', 'has not happened', 'wait', 'go now']
    assert banned_words('The river peaked at 191 cfs.') == ['peaked'] and banned_words('The river may have peaked at 191 cfs.') == []
    assert banned_words('Waiting for a gauge reading. Not a closure, safety, or all-clear signal.') == [] and banned_words('the typical wait to the top') == ['wait']

    def settle(target):
        target.wait_for_function("!document.getElementById('refresh').disabled")
        target.wait_for_function("['Latest retrieved frame','Animating retrieved frames','Unavailable'].includes(document.getElementById('radar-status').textContent)")

    def open_frame(check, width=1440, height=1000, scheme='light', feeds_payload=None, timezone_id=None, **feeds):
        """A first visit at `check`: a device with nothing saved, its clock fixed at that moment.

        timezone_id sets the device's own time zone; the page must print Pacific times whatever it is.
        """
        frame_context = browser.new_context(viewport={'width': width, 'height': height}, color_scheme=scheme, **({'timezone_id': timezone_id} if timezone_id else {}))
        frame_context.clock.set_fixed_time(check)
        source = {'payload': feeds_payload or replay_payload(check, **feeds), 'requests': []}
        frame = frame_context.new_page()
        frame.on('pageerror', lambda e: errors.append(str(e)))
        frame.route('**/*', lambda req: serve(req, source))
        frame.goto(URL)
        settle(frame)
        assert frame.evaluate('Date.now()') == int(check.timestamp() * 1000), 'the device clock must be fixed at the frame time'
        return frame_context, frame, source

    said = lambda target, ident: target.locator('#' + ident).inner_text()
    BLOCK_LINES = ['flow', 'river-time', 'river-age', 'river-change', 'river-older', 'river-state', 'river-past', 'river-high', 'river-new-high-note', 'river-rain-note', 'river-rise',
                   'noaa-compare', 'noaa-above', 'noaa-flag', 'tide-now']
    def river_lines(target):
        """The visible lines of the River, NOAA and Tide blocks, in page order; a hidden line is None."""
        return {ident: (None if target.locator('#' + ident).is_hidden() else said(target, ident)) for ident in BLOCK_LINES}
    assert page.evaluate("ids => ids.every((id, i) => !i || document.getElementById(ids[i - 1]).compareDocumentPosition(document.getElementById(id)) & Node.DOCUMENT_POSITION_FOLLOWING)", BLOCK_LINES), 'the lines of the three blocks are in the order listed'
    def block_style(target):
        """Every colour and class of the three blocks. It must be identical in every state."""
        return target.evaluate("""() => ['river-block','noaa-block','tide-block','flow','river-state','river-older','river-change','noaa-flag','noaa-above','noaa-compare','tide-now'].map(id => {
          const el = document.getElementById(id), s = getComputedStyle(el);
          return [id, el.className, s.color, s.backgroundColor, s.borderTopColor, s.borderLeftColor, s.fontWeight, s.textDecorationLine].join('|');
        })""")
    def first_screen(target, ids=('flow', 'river-time', 'river-age', 'river-change')):
        """Each element's box and type size, with the page not scrolled."""
        return target.evaluate("""ids => ({scrollY, innerWidth, innerHeight, overflow: document.documentElement.scrollWidth > innerWidth, boxes: ids.map(id => {
          const el = document.getElementById(id), r = el.getBoundingClientRect();
          return {id, top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height, size: parseFloat(getComputedStyle(el).fontSize)};
        })})""", list(ids))
    def assert_first_screen(target, label, ids=('flow', 'river-time', 'river-age', 'river-change')):
        view = first_screen(target, ids)
        assert view['scrollY'] == 0 and not view['overflow'], (label, 'scrolled or overflowing', view)
        for box in view['boxes']:
            assert box['height'] > 0 and box['top'] >= 0 and box['left'] >= 0 and box['bottom'] <= view['innerHeight'] and box['right'] <= view['innerWidth'], (label, 'not fully visible without scrolling', box, view['innerHeight'])
            assert box['size'] >= (32 if box['id'] == 'flow' else 15), (label, 'type too small', box)
    largest_type = """() => {
      const flow = parseFloat(getComputedStyle(document.getElementById('flow')).fontSize); let max = 0, who = '';
      for (const el of document.querySelectorAll('body *')) {
        if (el.id === 'flow' || !el.checkVisibility() || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
        const size = parseFloat(getComputedStyle(el).fontSize);
        if (size > max) { max = size; who = el.tagName + '#' + el.id + '.' + el.className; }
      }
      return {flow, max, who};
    }"""

    # ---- The replay frames: readings through the top of the hour, plus frames at 4:35 and 4:50 PM ----
    # NOAA issues in force: stamped 8:19 AM (path from 11:00 AM, highest 58.5 cfs), 2:36 PM (path from 5:00 PM,
    # highest 91.8 cfs) and, next morning, 8:10 AM (path from 11:00 AM, highest 100.3 cfs). The river reached 191 cfs.
    evening_tide = lambda since: f'High of 8.2 ft was at 6:46 PM PDT, {since} before this check. The tide is falling to a low of -1.2 ft at Sep 30, 1:56 AM PDT, then a high of 7.8 ft at Sep 30, 9:13 AM PDT.'
    afternoon_tide = lambda since: f'Low of 4.6 ft was at 1:21 PM PDT, {since} before this check. The tide is rising to a high of 8.2 ft at 6:46 PM PDT, then a low of -1.2 ft at Sep 30, 1:56 AM PDT.'
    low_at_1am = '15.9 cfs at 1:00 AM PDT'
    afternoon_issue = lambda age, gauge, at: noaa_ahead('2:36 PM PDT', age, '5:00 PM PDT', '91.8', '91.8', '5:00 PM PDT', gauge, at)
    FRAMES = [
        dict(name='1220pm', check=pacific(29, 12, 20), state_code='new-high', flow='119', time='at 12:00 PM PDT',
             change='Last hour: +21.5 cfs (rising). About 3 hours: +56.5 cfs.',
             state='Still rising as of 12:00 PM PDT (reading 20 minutes old): 119 cfs is the highest of this rise so far, up 21.5 cfs in the hour before. The top of this rise is at this reading or later.',
             since='12:00 PM PDT', rise=rise_line('103.1', 103, low_at_1am),
             noaa=noaa_line('8:19 AM PDT', '4 hours', '57', '12:00 PM PDT', '119', '62'), above='62', card='Largest relative rise: 103.1 cfs, or 103% of the 100 cfs May–October reference.',
             tide='High of 7.8 ft was at 8:08 AM PDT, 4 h 12 min before this check. The tide is falling to a low of 4.6 ft at 1:21 PM PDT, then a high of 8.2 ft at 6:46 PM PDT.'),
        # 3:20 PM: NOAA reissued at 2:36 PM and its path does not begin until 5:00 PM. Version 7 as first built printed
        # "no value for this hour" here. 163 cfs was first read at 2:45 PM; the 3:00 PM reading only equals it (a tie is not a new high).
        dict(name='0320pm', check=pacific(29, 15, 20), state_code='just-off-high', flow='163', time='at 3:00 PM PDT',
             change='Last hour: +6 cfs (rising). About 3 hours: +44 cfs.',
             state='Highest reading of this rise: 163 cfs at 2:45 PM PDT, 15 minutes of readings before the newest one.' + UNDER_AN_HOUR,
             since='12:00 PM PDT', rise=rise_line('147.1', 147, low_at_1am),
             noaa=afternoon_issue('44 minutes', '163', '3:00 PM PDT'), above='71.2', card=None, tide=afternoon_tide('1 h 59 min')),
        dict(name='0420pm', check=pacific(29, 16, 20), state_code='just-off-high', flow='164', time='at 4:00 PM PDT',
             change='Last hour: +1 cfs (about level). About 3 hours: +27 cfs.',
             state='Highest reading of this rise: 164 cfs at 3:15 PM PDT, 45 minutes of readings before the newest one.' + UNDER_AN_HOUR,
             since='12:00 PM PDT', rise=rise_line('148.1', 148, low_at_1am),
             noaa=afternoon_issue('2 hours', '164', '4:00 PM PDT'), above='72.2', card=None, tide=afternoon_tide('2 h 59 min')),
        # Opened at 4:35 PM holding the 4:15 PM reading, exactly 60 minutes of readings after the 3:15 PM high: a pause.
        # The river then went on from 164 to 191 cfs.
        dict(name='0435pm', check=pacific(29, 16, 35), newest=pacific(29, 16, 15), state_code='paused', flow='164', time='at 4:15 PM PDT',
             change='Last hour: 0 cfs (about level). About 3 hours: +22 cfs.',
             state='No new high since 3:15 PM PDT. ' + PAUSE, high='Highest reading since then: 164 cfs at 3:15 PM PDT.',
             since='12:00 PM PDT', rise=rise_line('148.1', 148, low_at_1am),
             noaa=afternoon_issue('2 hours', '164', '4:15 PM PDT'), above='72.2', card=None, tide=afternoon_tide('3 h 14 min')),
        # Opened at 4:50 PM holding the 4:30 PM reading: a new high (166 cfs) only 2 cfs and 1.2% above the reading an
        # hour before. The last-hour label is "about level", so the sentence says "New high", never "Still rising".
        dict(name='0450pm', check=pacific(29, 16, 50), newest=pacific(29, 16, 30), state_code='new-high', still_rising=False, flow='166', time='at 4:30 PM PDT',
             change='Last hour: +2 cfs (about level). About 3 hours: +19 cfs.',
             state='New high as of 4:30 PM PDT (reading 20 minutes old): 166 cfs is the highest of this rise so far, +2 cfs on the hour before. The top of this rise is at this reading or later.',
             since='12:00 PM PDT', rise=rise_line('150.1', 150, low_at_1am),
             noaa=afternoon_issue('2 hours', '166', '4:30 PM PDT'), above='74.2', card=None, tide=afternoon_tide('3 h 29 min')),
        # 5:20 PM: the 5:00 PM reading falls on the first point of NOAA's 2:36 PM path, so a value for that time exists again.
        dict(name='0520pm', check=pacific(29, 17, 20), state_code='new-high', flow='168', time='at 5:00 PM PDT',
             change='Last hour: +4 cfs (rising). About 3 hours: +11 cfs.',
             state='Still rising as of 5:00 PM PDT (reading 20 minutes old): 168 cfs is the highest of this rise so far, up 4 cfs in the hour before. The top of this rise is at this reading or later.',
             since='12:00 PM PDT', rise=rise_line('152.1', 152, low_at_1am),
             noaa=noaa_line('2:36 PM PDT', '3 hours', '91.8', '5:00 PM PDT', '168', '76.2'), above='76.2', card='Largest relative rise: 152.1 cfs, or 152% of the 100 cfs May–October reference.',
             tide=afternoon_tide('3 h 59 min')),
        dict(name='0720pm', check=pacific(29, 19, 20), state_code='new-high', flow='181', time='at 7:00 PM PDT',
             change='Last hour: +7 cfs (rising). About 3 hours: +17 cfs.',
             state='Still rising as of 7:00 PM PDT (reading 20 minutes old): 181 cfs is the highest of this rise so far, up 7 cfs in the hour before. The top of this rise is at this reading or later.',
             since='12:00 PM PDT', rise=rise_line('165.1', 165, low_at_1am),
             noaa=noaa_line('2:36 PM PDT', '5 hours', '76', '7:00 PM PDT', '181', '105'), above='105', card='Largest relative rise: 165.1 cfs, or 165% of the 100 cfs May–October reference.',
             tide=evening_tide('34 minutes')),   # the 6:46 PM high passed 34 minutes earlier and is still shown
        dict(name='1020pm', check=pacific(29, 22, 20), state_code='paused', flow='191', time='at 10:00 PM PDT',
             change='Last hour: 0 cfs (about level). About 3 hours: +10 cfs.',
             state='No new high since 9:00 PM PDT. ' + PAUSE, high='Highest reading since then: 191 cfs at 9:00 PM PDT.',
             since='12:00 PM PDT', rise=rise_line('175.1', 175, low_at_1am),
             noaa=noaa_line('2:36 PM PDT', '8 hours', '52.2', '10:00 PM PDT', '191', '138.8'), above='138.8', card='Largest relative rise: 175.1 cfs, or 175% of the 100 cfs May–October reference.',
             tide=evening_tide('3 h 34 min')),
        dict(name='1120pm', check=pacific(29, 23, 20), state_code='may-have-peaked', flow='189', time='at 11:00 PM PDT',
             change='Last hour: -2 cfs (about level). About 3 hours: +2 cfs.',
             state='No new high since 9:00 PM PDT (2 h 0 min of readings): the river may have peaked at 191 cfs. ' + PEAK,
             since='12:00 PM PDT', rise=rise_line('173.1', 173, low_at_1am),
             noaa=noaa_line('2:36 PM PDT', '9 hours', '44.2', '11:00 PM PDT', '189', '144.8'), above='144.8', card='Largest relative rise: 173.1 cfs, or 173% of the 100 cfs May–October reference.',
             tide=evening_tide('4 h 34 min')),
        # The next morning: the measured rise is back under 100 cfs, but the number was passed 20 hours earlier. NOAA
        # reissued at 8:10 AM and its path begins at 11:00 AM. The count is taken from the 12:30 AM reading (181 cfs),
        # the first at least 5% below the 191 cfs high.
        dict(name='0820am-next-day', check=pacific(30, 8, 20), state_code='falling', flow='125', time='at 8:00 AM PDT',
             change='Last hour: -7 cfs (falling). About 3 hours: -22 cfs.',
             state='Now at least 5% below the high of 191 cfs at Sep 29, 9:00 PM PDT; the river first read that far below it at 12:30 AM PDT. ' + FALLING,
             since='Sep 29, 12:00 PM PDT', rise=rise_line('79', 79, '46 cfs at Sep 29, 8:00 AM PDT'),
             noaa=noaa_ahead('8:10 AM PDT', '10 minutes', '11:00 AM PDT', '100.3', '100.3', '11:00 AM PDT', '125', '8:00 AM PDT'), above='24.7', card=None,
             tide='Low of -1.2 ft was at 1:56 AM PDT, 6 h 24 min before this check. The tide is rising to a high of 7.8 ft at 9:13 AM PDT, then a low of 5.4 ft at 2:07 PM PDT.'),
    ]
    replay_audits = 0
    styles_seen = {}
    frame_state = {spec['name']: spec['state'] for spec in FRAMES}
    frame_lines = {}
    for order, spec in enumerate(FRAMES, start=1):
        name, check = spec['name'], spec['check']
        shot = f'replay-{order:02d}-{name}'   # numbered so the screenshots sort in time order
        feeds = {'newest': spec['newest']} if 'newest' in spec else {}
        new_high, still_rising = spec['state_code'] == 'new-high', spec['state_code'] == 'new-high' and spec.get('still_rising', True)
        frame_context, frame, source = open_frame(check, **feeds)
        outlook_text = frame.locator('#outlook').inner_text()
        # Banned words first, so that a banned word is reported as one.
        assert banned_words(outlook_text) == [], (name, 'banned word on the Outlook tab', banned_words(outlook_text))
        lines = river_lines(frame)
        expected = {'flow': spec['flow'], 'river-time': spec['time'], 'river-age': '20 minutes old', 'river-change': spec['change'], 'river-older': None, 'river-state': spec['state'],
                    'river-past': past(spec['since']),
                    'river-high': spec.get('high'),                                      # its own line only where the state sentence does not name the high
                    'river-new-high-note': AFTER_NEW_HIGH if new_high else None,        # the two-sided sentence follows any new high
                    'river-rain-note': RAIN_BESIDE_PEAK if spec['state_code'] == 'may-have-peaked' else None,   # beside "may have peaked" only
                    'river-rise': spec['rise'], 'noaa-compare': spec['noaa'], 'noaa-above': above_highest(spec['above']), 'noaa-flag': NOT_TRACKING, 'tide-now': spec['tide']}
        assert list(expected) == BLOCK_LINES
        for ident, text in expected.items():
            assert lines[ident] == text, (name, ident, lines[ident], text)
        frame_lines[name] = lines
        assert (spec.get('high') is not None) == (spec['state_code'] == 'paused'), 'the separate high line is expected only beside a pause'
        assert frame.evaluate('feed => SamishData.riverState(SamishData.usgs(feed, Date.now()), Date.now()).state', source['payload']['usgs']) == spec['state_code'], (name, 'state code')
        # "May have peaked" is never printed before the 11:00 PM reading. "Still rising" needs a new high AND a last
        # hour that meets the "rising" test; any other new high reads "New high".
        assert ('may have peaked' in outlook_text) == (name == '1120pm'), (name, 'may-have-peaked wording')
        assert ('Still rising' in outlook_text) == still_rising and ('New high as of' in outlook_text) == (new_high and not still_rising), (name, 'still-rising and new-high wording')
        if name in ('1020pm', '1120pm'):
            assert 'rising' not in lines['river-change'] and 'rising' not in lines['river-state'] and 'rising' not in said(frame, 'watch-title'), (name, 'the river is not called rising after it stopped')
        if name == '0420pm':
            assert 'Last hour: +1 cfs' in lines['river-change'] and 'peak' not in frame.locator('#river-block').inner_text().lower(), (name, '+1 in the last hour and no peak wording')
        if name == '0435pm':
            assert '67 of 172' in lines['river-state'] and '42 of them' in lines['river-state'] and 'may have peaked' not in outlook_text
        # NOAA's current issue is set against the gauge on a first visit: nothing was saved on this device.
        assert said(frame, 'watch-state') == 'NO EARLIER FORECAST', (name, 'a replay frame is a first visit')
        # From 12:20 PM to the next morning the gauge is above NOAA's forecast: no forecast-to-fall sentence, no
        # forecast-high time and no tide pairing, whether or not NOAA's path has reached the reading yet.
        assert said(frame, 'forecast-time') == NO_PEAK_ABOVE and said(frame, 'crest-time') == NO_PEAK_ABOVE, name
        assert 'forecast to fall' not in outlook_text and 'Forecast high around' not in outlook_text and 'NOAA forecast high around' not in outlook_text and 'has no value for' not in outlook_text, name
        assert frame.locator('#crest-nearby .crest-tide').count() == 0 and frame.locator('#forecast-metric').is_hidden(), name
        assert said(frame, 'ops-forecast') == 'Only falls' and said(frame, 'ops-forecast-note').startswith('NOAA’s path falls from its first value · issued '), name
        # The NOAA-based card never says "below the numeric line" while the River block shows the number was passed.
        # It needs NOAA's path to reach the reading; until then it says so. When it is computed it says what it is built on.
        assert 'below the numeric line' not in outlook_text, (name, 'reassuring line after the number was passed')
        assert said(frame, 'rise-passed') == f'The measured rise passed the 100 cfs number at the {spec["since"]} reading (River block at the top). The figures on this card look forward from the newest reading and do not undo that.', name
        assert said(frame, 'rise-title') == (spec['card'] or NOT_ALIGNED), (name, said(frame, 'rise-title'))
        assert (said(frame, 'rise-noaa-basis') == BUILT_ON_ABOVE) if spec['card'] else frame.locator('#rise-noaa-basis').is_hidden(), name
        assert said(frame, 'rise-noaa-dry') == NOAA_DRY + ' ' + CAVEAT, name
        assert said(frame, 'rain-context-text') == RAIN_CONTEXT and frame.locator('#rain-context strong').inner_text() == 'Context, not an alert.', name
        assert frame.locator('#tide-heading').inner_text().endswith('Bellingham prediction, not Samish Bay water level or boat clearance'), name
        # No colour, icon or class in the three blocks changes with the state.
        assert frame.locator('.now-block .pill, .now-block img, .now-block svg, .now-block [class*="caution"], .now-block [class*="good"]').count() == 0, name
        for scheme in ['light', 'dark']:
            frame.emulate_media(color_scheme=scheme)
            frame.wait_for_timeout(150)
            assert styles_seen.setdefault(scheme, block_style(frame)) == block_style(frame), (name, scheme, 'block styling changed with the state')
            frame.screenshot(path=str(out / f'{shot}-desktop-1440-{scheme}.png'))
            if scheme == 'light':
                frame.screenshot(path=str(out / f'{shot}-desktop-1440-{scheme}-full.png'), full_page=True)
        if name == '0720pm':
            # The tide request starts 24 to 48 hours back (D.tideRequest), so the 6:46 PM high is in hand.
            tide_request = next(u for u in source['requests'] if 'tidesandcurrents' in u)
            assert 'begin_date=20260929' in tide_request and 'range=192' in tide_request and 'time_zone=gmt' in tide_request, tide_request
            assert frame.locator('#tide-list .tide-row').first.inner_text().replace('\n', ' ').endswith('Sep 29, 6:46 PM PDT · passed'), 'the tide list keeps the high that just passed'
            # The gauge request reaches back three days: the 48-hour memory needs a 24-hour low for each of its readings.
            gauge_request = next(u for u in source['requests'] if 'waterdata.usgs.gov' in u)
            assert 'time=P3D' in gauge_request and 'monitoring_location_id=USGS-12201500' in gauge_request and 'parameter_code=00060' in gauge_request, gauge_request
            sizes = frame.evaluate(largest_type)
            assert sizes['flow'] > sizes['max'], ('the flow figure must be the largest type on the Outlook tab (desktop)', sizes)
            # The copied snapshot carries the River, NOAA and Tide lines exactly as the screen shows them.
            frame.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject(Error('denied'))},configurable:true})")
            frame.locator('#copy-brief').click()
            frame.wait_for_function("!document.getElementById('brief-fallback').hidden")
            copied = frame.locator('#brief-fallback').input_value()
            assert 'RIVER, measured at the gauge: 181 cfs at 7:00 PM PDT, 20 minutes old\n' + '\n'.join(lines[ident] for ident in ['river-change', 'river-state', 'river-past', 'river-new-high-note', 'river-rise']) + '\n' in copied, copied[:900]
            assert 'NOAA RIVER FORECAST, current issue against the gauge\n' + '\n'.join(lines[ident] for ident in ['noaa-compare', 'noaa-above', 'noaa-flag']) + '\n' in copied and lines['tide-now'] in copied
            assert BUILT_ON_ABOVE in copied and NO_PEAK_ABOVE in copied and banned_words(copied.split('Official commercial status')[0]) == []
        replay_audits += audit_page(frame, 'replay-' + name)
        frame_context.close()
        # The same moment on a phone, 390 by 664: the reading, its time and age and the last-hour change without
        # scrolling; and at a new high the "Past the number" line too, ahead of the two-sided sentence.
        phone_context, phone, _ = open_frame(check, width=390, height=664, **feeds)
        assert river_lines(phone) == lines, (name, 'phone and desktop must print the same sentences')
        for scheme in ['light', 'dark']:
            phone.emulate_media(color_scheme=scheme)
            phone.wait_for_timeout(150)
            assert_first_screen(phone, (name, 390, 664, scheme), ids=('flow', 'river-time', 'river-age', 'river-change', 'river-state', 'river-past') if new_high else ('flow', 'river-time', 'river-age', 'river-change'))
            phone.screenshot(path=str(out / f'{shot}-phone-390x664-{scheme}.png'))
            if scheme == 'dark':
                phone.screenshot(path=str(out / f'{shot}-phone-390x664-{scheme}-full.png'), full_page=True)
        phone_context.close()
    axe_runs += replay_audits

    # ---- The device's own time zone must not matter: every time on the page is Pacific ----
    for zone, name in [('America/New_York', '0720pm'), ('Asia/Tokyo', '0820am-next-day'), ('Asia/Tokyo', '1120pm')]:
        spec = next(item for item in FRAMES if item['name'] == name)
        zone_context, zoned, _ = open_frame(spec['check'], timezone_id=zone)
        assert zoned.evaluate('Intl.DateTimeFormat().resolvedOptions().timeZone') == zone, 'the device zone was set'
        assert river_lines(zoned) == frame_lines[name], (zone, name, 'a device outside the Pacific zone must read the same sentences')
        assert said(zoned, 'update-status').startswith('Data checked ' + ('Sep 30, 8:20 AM PDT' if name == '0820am-next-day' else 'Sep 29, 7:20 PM PDT' if name == '0720pm' else 'Sep 29, 11:20 PM PDT')), said(zoned, 'update-status')
        assert said(zoned, 'rise-passed').startswith(f'The measured rise passed the 100 cfs number at the {spec["since"]} reading'), (zone, said(zoned, 'rise-passed'))
        ticks = zoned.locator('#flow-chart .tick-clock').evaluate_all('marks => marks.map(mark => mark.textContent)')
        assert ticks[2] == ('Wed 8:20 AM' if name == '0820am-next-day' else 'Tue 7:20 PM' if name == '0720pm' else 'Tue 11:20 PM'), (zone, ticks)
        assert 'PDT' in zoned.locator('#tide-list').inner_text() and 'EDT' not in zoned.locator('#outlook').inner_text() and 'GMT+9' not in zoned.locator('#outlook').inner_text() and 'JST' not in zoned.locator('#outlook').inner_text()
        zone_context.close()

    # ---- Phone windows 390 by 664 and 375 by 548, light and dark, at the 7:20 PM frame; and no sideways overflow at 320 pixels ----
    for width, height in [(390, 664), (375, 548), (320, 568)]:
        for scheme in ['light', 'dark']:
            phone_context, phone, _ = open_frame(pacific(29, 19, 20), width=width, height=height, scheme=scheme)
            assert_first_screen(phone, ('0720pm', width, height, scheme))
            sizes = phone.evaluate(largest_type)
            assert sizes['flow'] > sizes['max'], ('the flow figure must be the largest type on the Outlook tab (phone)', width, sizes)
            for tab in ['research', 'sources']:
                phone.locator('#tab-' + tab).click()
                tab_sizes = phone.evaluate(largest_type)
                assert tab_sizes['flow'] > tab_sizes['max'] and not phone.evaluate('document.documentElement.scrollWidth > innerWidth'), (tab, width, tab_sizes)
            phone.locator('#tab-outlook').click()
            phone.screenshot(path=str(out / f'phone-0720pm-{width}x{height}-{scheme}.png'))
            phone_context.close()

    # ---- A stalled feed is not a plateau ----
    # (a) Opened at 7:20 PM, newest reading 5:30 PM: 110 minutes behind. The reading keeps its own time and age.
    stalled_context, stalled, _ = open_frame(pacific(29, 19, 20), newest=pacific(29, 17, 30))
    lines = river_lines(stalled)
    assert lines['flow'] == '170' and lines['river-time'] == 'at 5:30 PM PDT' and lines['river-age'] == '110 minutes old', lines
    assert lines['river-state'] == 'Cannot tell whether the river is rising: the gauge feed is 110 minutes behind.', lines['river-state']
    for ident in ['river-change', 'river-older', 'river-past', 'river-high', 'river-new-high-note', 'river-rain-note', 'river-rise', 'noaa-above', 'noaa-flag']:
        assert lines[ident] is None, ('a stalled feed prints no change figure, no state and no comparison', ident, lines[ident])
    block_text = stalled.locator('#river-block').inner_text()
    assert not any(word in block_text for word in ['Last hour', 'About 3 hours', 'Still rising', 'New high', 'No new high', 'Highest reading', 'Past the', 'Rise above']), block_text
    # A refused reading is not set against NOAA's forecast, no peak time is read, and the NOAA-based card is withheld:
    # the page computes nothing from a reading the River block has refused.
    assert lines['noaa-compare'] == not_compared('2:36 PM PDT', '5 hours', 'the gauge feed is 110 minutes behind'), lines['noaa-compare']
    assert said(stalled, 'forecast-time') == NO_PEAK_UNCOMPARED and said(stalled, 'crest-time') == NO_PEAK_UNCOMPARED and 'forecast to fall' not in stalled.locator('#outlook').inner_text()
    assert said(stalled, 'feed-alert') == 'The newest gauge reading is 110 minutes old. Check the dated source details before planning.'
    assert said(stalled, 'rise-title') == 'Withheld: the gauge feed is 110 minutes behind.' and said(stalled, 'rise-status') == 'Unavailable' and said(stalled, 'rise-percent') == '—'
    assert 'Largest relative rise' not in stalled.locator('#outlook').inner_text() and 'numeric line at' not in stalled.locator('#outlook').inner_text() and stalled.locator('#rise-noaa-basis').is_hidden()
    assert banned_words(stalled.locator('#outlook').inner_text()) == []
    assert block_style(stalled) == styles_seen['light'], 'a stalled feed must not restyle the blocks'
    stalled.screenshot(path=str(out / 'state-stalled-feed-110min-desktop-1440.png'))
    axe_runs += audit_page(stalled, 'stalled-feed')
    stalled_context.close()
    stalled_context, stalled, _ = open_frame(pacific(29, 19, 20), width=390, height=664, scheme='dark', newest=pacific(29, 17, 30))
    assert_first_screen(stalled, 'stalled feed on a phone', ids=('flow', 'river-time', 'river-age', 'river-state'))
    stalled.screenshot(path=str(out / 'state-stalled-feed-110min-phone-390x664-dark.png'))
    stalled_context.close()
    # The same reading at exactly 90 minutes old is still read; at 91 and at 120 minutes it is refused and the card withheld.
    for minutes, refused in [(90, False), (91, True), (120, True)]:
        edge_context, edge, _ = open_frame(pacific(29, 17, 30) + timedelta(minutes=minutes), newest=pacific(29, 17, 30))
        assert said(edge, 'river-age') == f'{minutes} minutes old' and said(edge, 'flow') == '170', minutes
        if refused:
            assert said(edge, 'river-state') == f'Cannot tell whether the river is rising: the gauge feed is {minutes} minutes behind.', minutes
            assert said(edge, 'rise-title') == f'Withheld: the gauge feed is {minutes} minutes behind.' and said(edge, 'rise-percent') == '—' and edge.locator('#river-change').is_hidden(), minutes
            assert said(edge, 'crest-time') == NO_PEAK_UNCOMPARED, minutes
        else:
            assert said(edge, 'river-state') == 'Highest reading of this rise: 170 cfs at 5:15 PM PDT, 15 minutes of readings before the newest one.' + UNDER_AN_HOUR, said(edge, 'river-state')
            assert said(edge, 'rise-title') == 'Largest relative rise: 154.1 cfs, or 154% of the 100 cfs May–October reference.' and edge.locator('#river-change').is_visible(), said(edge, 'rise-title')
            assert said(edge, 'crest-time') == NO_PEAK_ABOVE and said(edge, 'noaa-flag') == NOT_TRACKING, minutes
        edge_context.close()
    # (b) The newest reading is 20 minutes old, but the readings from 5:45 to 6:45 PM never arrived: a 90-minute hole.
    hole_context, holed, _ = open_frame(pacific(29, 19, 20), hole=(pacific(29, 17, 45), pacific(29, 18, 45)))
    lines = river_lines(holed)
    assert lines['flow'] == '181' and lines['river-time'] == 'at 7:00 PM PDT' and lines['river-age'] == '20 minutes old', lines
    assert lines['river-state'] == 'Cannot tell whether the river is rising: there is a 90-minute hole in the gauge readings of the last hour.', lines['river-state']
    for ident in ['river-change', 'river-older', 'river-past', 'river-high', 'river-new-high-note', 'river-rain-note', 'river-rise', 'noaa-above', 'noaa-flag']:
        assert lines[ident] is None, ('a hole in the last hour prints no change figure, no state and no comparison', ident, lines[ident])
    assert lines['noaa-compare'] == not_compared('2:36 PM PDT', '5 hours', 'there is a 90-minute hole in the gauge readings of the last hour') and said(holed, 'feed-alert').startswith('Gauge readings are missing in the last hour.')
    assert said(holed, 'rise-title') == 'Withheld: there is a 90-minute hole in the gauge readings of the last hour.' and said(holed, 'rise-percent') == '—' and said(holed, 'crest-time') == NO_PEAK_UNCOMPARED
    holed.screenshot(path=str(out / 'state-hole-90min-desktop-1440.png'))
    hole_context.close()

    # ---- A device clock that is behind the gauge ----
    # True time 7:20 PM, the feed holds readings to 7:15 PM, the device believes it is 6:20 PM. The newest readings
    # must not be dropped in silence: the page says the clock is behind, with no age, no change figure and no state.
    CLOCK_BEHIND = 'this device’s clock is behind the gauge (the newest reading is stamped 55 minutes after this device’s time)'
    slow_context, slow, _ = open_frame(pacific(29, 18, 20), newest=pacific(29, 19, 15))
    lines = river_lines(slow)
    assert lines['river-state'] == 'Cannot tell: ' + CLOCK_BEHIND + '. Correct the device clock.', lines['river-state']
    assert lines['flow'] == '183' and lines['river-time'] == 'at 7:15 PM PDT' and lines['river-age'] in (None, ''), lines   # no age: none can be trusted
    for ident in ['river-change', 'river-older', 'river-past', 'river-high', 'river-new-high-note', 'river-rain-note', 'river-rise', 'noaa-above', 'noaa-flag']:
        assert lines[ident] is None, ('a device clock that is behind prints no change figure and no state', ident, lines[ident])
    assert said(slow, 'feed-alert') == lines['river-state'], 'the alert banner carries the same words'
    assert lines['noaa-compare'] == not_compared('2:36 PM PDT', '4 hours', CLOCK_BEHIND) and said(slow, 'rise-title') == 'Withheld: ' + CLOCK_BEHIND + '.'
    assert said(slow, 'crest-time') == NO_PEAK_UNCOMPARED and said(slow, 'watch-state') == 'CHECK UNAVAILABLE' and 'minutes old' not in slow.locator('#river-block').inner_text()
    slow.screenshot(path=str(out / 'state-device-clock-behind-desktop-1440.png'))
    axe_runs += audit_page(slow, 'device-clock-behind')
    slow_context.close()
    # A reading stamped 6 minutes ahead is past the 5-minute allowance; one stamped exactly 5 minutes ahead is simply
    # not used yet, and the page reads the 7:00 PM reading as usual.
    slow_context, slow, _ = open_frame(pacific(29, 19, 9), newest=pacific(29, 19, 15))
    assert said(slow, 'river-state') == 'Cannot tell: this device’s clock is behind the gauge (the newest reading is stamped 6 minutes after this device’s time). Correct the device clock.'
    slow_context.close()
    slow_context, slow, _ = open_frame(pacific(29, 19, 10), newest=pacific(29, 19, 15))
    assert said(slow, 'flow') == '181' and said(slow, 'river-time') == 'at 7:00 PM PDT' and said(slow, 'river-age') == '10 minutes old' and said(slow, 'river-state').startswith('Still rising as of 7:00 PM PDT (reading 10 minutes old): 181 cfs')
    assert slow.locator('#feed-alert').is_hidden()
    slow_context.close()

    # ---- A hole earlier in the last 24 hours: the rise is a lower bound, and the passing is "at or before" ----
    # The readings from 4:15 to 5:15 AM never arrived. The 24-hour low cannot be exact, but the lowest reading held
    # (15.9 cfs at 1:00 AM) bounds the rise from below, so one hole no longer blanks the measured rise for a day.
    gap_context, gapped, _ = open_frame(pacific(29, 19, 20), hole=(pacific(29, 4, 15), pacific(29, 5, 15)))
    lines = river_lines(gapped)
    assert lines['river-rise'] == rise_at_least('165.1', 165, 90), lines['river-rise']
    assert lines['river-past'] == past_gap('12:00 PM PDT') and lines['river-state'] == frame_state['0720pm'] and lines['river-new-high-note'] == AFTER_NEW_HIGH, lines
    assert lines['river-change'] == 'Last hour: +7 cfs (rising). About 3 hours: +17 cfs.' and lines['noaa-flag'] == NOT_TRACKING and said(gapped, 'crest-time') == NO_PEAK_ABOVE
    assert 'no rise' not in gapped.locator('#outlook').inner_text().lower() and 'Rise above the 24-hour low' not in gapped.locator('#outlook').inner_text()
    gapped.screenshot(path=str(out / 'state-rise-lower-bound-desktop-1440.png'))
    axe_runs += audit_page(gapped, 'rise-lower-bound')
    gap_context.close()
    # The feed was out from 10:45 AM to 1:15 PM, across the moment the number was passed. Opened at 2:50 PM.
    gap_context, gapped, _ = open_frame(pacific(29, 14, 50), newest=pacific(29, 14, 45), hole=(pacific(29, 10, 45), pacific(29, 13, 15)))
    lines = river_lines(gapped)
    assert lines['river-past'] == past_gap('1:30 PM PDT') and lines['river-rise'] == rise_at_least('147.1', 147, 180), lines
    assert lines['river-state'] == 'Still rising as of 2:45 PM PDT (reading 5 minutes old): 163 cfs is the highest of this rise so far, up 11 cfs in the hour before. The top of this rise is at this reading or later.', lines['river-state']
    assert lines['river-change'] == 'Last hour: +11 cfs (rising). About 3 hours: unavailable.' and lines['noaa-flag'] == NOT_TRACKING, lines
    assert lines['noaa-compare'] == afternoon_issue('14 minutes', '163', '2:45 PM PDT') and lines['noaa-above'] == above_highest('71.2'), lines
    gap_context.close()
    # A hole between the highest reading and the newest one still gives no state: the readings from 9:15 to 10:15 PM
    # are missing, the 9:00 PM reading (191 cfs) is the highest held, and the page is opened at 12:05 AM.
    gap_context, gapped, _ = open_frame(pacific(30, 0, 5), newest=pacific(29, 23, 45), hole=(pacific(29, 21, 15), pacific(29, 22, 15)))
    lines = river_lines(gapped)
    assert lines['river-state'] == 'Gauge readings are missing for 90 minutes between the highest reading held (191 cfs at Sep 29, 9:00 PM PDT) and the newest reading. No state is given for this rise.', lines['river-state']
    assert lines['river-high'] is None and lines['river-rain-note'] is None and lines['river-new-high-note'] is None and str(EVIDENCE['rises']['count']) not in gapped.locator('#river-block').inner_text()
    assert lines['river-past'] == past('Sep 29, 12:00 PM PDT') and lines['river-rise'].startswith('Rise above the lowest reading held from the last 24 hours: at least '), lines
    gap_context.close()

    # ---- Readings that do not reach back 24 hours: the rise is unavailable; it is never printed as "no rise" ----
    short_context, short, _ = open_frame(pacific(29, 19, 20), first=pacific(29, 6, 0))
    lines = river_lines(short)
    assert lines['river-change'] == 'Last hour: +7 cfs (rising). About 3 hours: +17 cfs.' and lines['river-rise'] == 'Measured rise unavailable: the gauge record has a gap in the last 24 hours.', lines
    assert lines['river-state'] is None and lines['river-past'] is None and lines['river-high'] is None and lines['river-older'] is None, lines
    assert 'no rise' not in short.locator('#outlook').inner_text().lower() and 'below the numeric line' not in short.locator('#outlook').inner_text()
    # The gauge is above NOAA's forecast and whether a rise is in progress cannot be told: the peak time stays withheld.
    assert lines['noaa-compare'] == noaa_line('2:36 PM PDT', '5 hours', '76', '7:00 PM PDT', '181', '105') and lines['noaa-above'] == above_highest('105') and lines['noaa-flag'] == RISE_UNTOLD, lines
    assert said(short, 'crest-time') == NO_PEAK_ABOVE and said(short, 'forecast-time') == NO_PEAK_ABOVE
    short.screenshot(path=str(out / 'state-rise-unavailable-desktop-1440.png'))
    axe_runs += audit_page(short, 'rise-unavailable')
    short_context.close()

    # ---- A rise older than the readings the page can compare ----
    # The readings start at 12:15 PM on 28 September, so the first one whose 24-hour rise can be worked out (12:15 PM
    # on 29 September) is already past the number. The newest reading is the highest held: the page must not say the
    # top of the rise is behind it. No pause, peak or falling line and no count; the highest reading held is named.
    old_context, old_rise, _ = open_frame(pacific(29, 19, 20), first=pacific(28, 12, 15))
    lines = river_lines(old_rise)
    assert lines['river-older'] == 'The measured rise passed the 100 cfs number at or before 12:15 PM PDT; this page’s readings do not reach back to where that rise began.', lines['river-older']
    assert lines['river-state'] == 'Still rising as of 7:00 PM PDT (reading 20 minutes old): 181 cfs is the highest reading this page holds from the last 48 hours, up 7 cfs in the hour before.', lines['river-state']
    assert lines['river-past'] is None and lines['river-high'] is None and lines['river-new-high-note'] is None and lines['river-rain-note'] is None, lines
    assert lines['river-rise'] == rise_line('165.1', 165, low_at_1am) and lines['river-change'] == 'Last hour: +7 cfs (rising). About 3 hours: +17 cfs.', lines
    block_text = old_rise.locator('#river-block').inner_text()
    assert 'older than the readings' not in block_text and 'The top of' not in block_text and str(EVIDENCE['rises']['count']) not in block_text and 'such readings' not in block_text, block_text
    assert lines['noaa-flag'] == NOT_TRACKING and 'below the numeric line' not in old_rise.locator('#outlook').inner_text()
    old_rise.screenshot(path=str(out / 'state-rise-at-or-before-desktop-1440.png'))
    axe_runs += audit_page(old_rise, 'rise-at-or-before')
    old_context.close()
    # The same device at 10:20 PM and 11:20 PM: 191 cfs at 9:00 PM is the highest held and the newest reading is not it.
    for check, clock in [(pacific(29, 22, 20), '10:00 PM'), (pacific(29, 23, 20), '11:00 PM')]:
        old_context, old_rise, _ = open_frame(check, first=pacific(28, 12, 15))
        lines = river_lines(old_rise)
        assert lines['river-state'] == 'Highest reading held from the last 48 hours: 191 cfs at 9:00 PM PDT.' and lines['river-older'].startswith('The measured rise passed the 100 cfs number at or before 12:15 PM PDT;'), (clock, lines)
        assert lines['river-rain-note'] is None and lines['river-high'] is None and 'may have peaked' not in old_rise.locator('#outlook').inner_text() and 'No new high' not in old_rise.locator('#river-block').inner_text(), clock
        old_context.close()

    # ---- A look-back count is printed only within the 24 hours of readings it was counted over ----
    # "Falling". The real record ends at 8:00 AM on 30 September, so the hourly readings from 9:00 AM on 30 September to
    # 1:00 AM on 1 October below are INVENTED (a steady fall from 120 to 88 cfs) only to carry the page past 24 hours.
    # The count is taken from the real 12:30 AM reading on 30 September, the first at least 5% below the 191 cfs high.
    invented_fall = [(pacific(30, 8) + timedelta(hours=step), 122 - 2 * step) for step in range(1, 18)]
    falling_lead = 'Now at least 5% below the high of 191 cfs at Sep 29, 9:00 PM PDT; the river first read that far below it at Sep 30, 12:30 AM PDT'
    for check, expected_state in [(pacific(30, 8) + timedelta(hours=16, minutes=20), falling_lead + '. ' + FALLING),            # newest reading midnight: 23 h 30 min after
                                  (pacific(30, 8) + timedelta(hours=17, minutes=20), falling_lead + ', more than 24 hours of readings ago.')]:   # 1:00 AM: 24 h 30 min after
        late_context, late, _ = open_frame(check, extra=invented_fall)
        assert said(late, 'river-state') == expected_state, (check, said(late, 'river-state'))
        assert (str(EVIDENCE['rises']['count']) in late.locator('#river-block').inner_text()) == expected_state.endswith(FALLING), 'no count once the newest reading is more than 24 hours past the point it is counted from'
        assert said(late, 'river-past') == past('Sep 29, 12:00 PM PDT') and banned_words(late.locator('#outlook').inner_text()) == []
        if not expected_state.endswith(FALLING):
            late.screenshot(path=str(out / 'state-falling-count-past-24-hours-desktop-1440.png'))
            axe_runs += audit_page(late, 'falling-count-past-24-hours')
        late_context.close()
    # The NOAA-based card on the same INVENTED afternoon (12:20 PM on 30 September, newest reading 114 cfs): NOAA's 8:10 AM
    # path now covers the reading, so the card is computed again, and its forward look is far under the number. It must
    # not say "below the numeric line": the measured rise passed the number 24 hours earlier.
    after_context, after, _ = open_frame(pacific(30, 12, 20), extra=invented_fall)
    assert said(after, 'rise-title') == 'Largest relative rise: 0 cfs, or 0% of the 100 cfs May–October reference.' and said(after, 'rise-percent') == '0', said(after, 'rise-title')
    assert said(after, 'rise-detail').startswith('Forward look from the newest reading; its largest relative rise is at the ') and 'below the numeric line' not in after.locator('#outlook').inner_text(), said(after, 'rise-detail')
    assert said(after, 'rise-passed').startswith('The measured rise passed the 100 cfs number at the Sep 29, 12:00 PM PDT reading') and said(after, 'rise-noaa-basis') == BUILT_ON_ABOVE
    assert after.locator('.rise-card .progress').is_hidden(), 'no bar filling toward a number the measured rise already passed'
    assert said(after, 'noaa-compare') == noaa_line('8:10 AM PDT', '4 hours', '95.4', '12:00 PM PDT', '114', '18.6') and said(after, 'noaa-flag') == NOT_TRACKING, said(after, 'noaa-compare')
    after_context.close()
    # "May have peaked". A SYNTHETIC gauge (nothing real): quiet at 50 cfs, a climb through 150 to a 200 cfs high, then 199 cfs
    # every hour. The count is taken from the 2-hour mark; once that mark is more than 24 hours of readings back it is dropped.
    plateau_check = datetime(2026, 7, 15, 19, 20, tzinfo=timezone.utc)   # 12:20 PM Pacific; the newest reading is 12:00 PM
    for hours_since_high, clock_of_high, counted in [(20, 'Jul 14, 4:00 PM PDT', True), (26, 'Jul 14, 10:00 AM PDT', True), (27, 'Jul 14, 9:00 AM PDT', False)]:
        hourly = [(plateau_check - timedelta(minutes=20, hours=back), 199 if back < hours_since_high else 200 if back == hours_since_high else 150 if back == hours_since_high + 1 else 50) for back in range(80, -1, -1)]
        flat_context, flat, _ = open_frame(plateau_check, feeds_payload=synthetic_gauge_payload(plateau_check, hourly))
        first_sentence = f'No new high since {clock_of_high} ({hours_since_high} h 0 min of readings): the river may have peaked at 200 cfs.'
        assert said(flat, 'river-state') == (first_sentence + ' ' + PEAK if counted else first_sentence), (hours_since_high, said(flat, 'river-state'))
        assert said(flat, 'river-rain-note') == RAIN_BESIDE_PEAK and (str(EVIDENCE['rises']['count']) in flat.locator('#river-block').inner_text()) == counted, hours_since_high
        if not counted:
            flat.screenshot(path=str(out / 'state-may-have-peaked-count-past-24-hours-desktop-1440.png'))
        flat_context.close()

    # ---- Climbing again below an earlier top (SYNTHETIC winter storm at the 400 cfs number; nothing real) ----
    # A first surge to 1,400 cfs, a fall to 820 cfs, then a slow second climb of 15 cfs an hour: under the 2% "rising"
    # test, so without the climb-back rule the page said "falling" with a count while the river rose for 12 hours.
    winter_storm = lambda day, hour, minute=0: datetime(2026, 1, day, hour, minute, tzinfo=timezone(timedelta(hours=-8)))
    knots = [(winter_storm(9, 0), 310), (winter_storm(12, 6), 300), (winter_storm(12, 9), 520), (winter_storm(12, 12), 980), (winter_storm(12, 15), 1400), (winter_storm(12, 21), 1250),
             (winter_storm(13, 6), 900), (winter_storm(13, 9), 820), (winter_storm(13, 21), 1000), (winter_storm(14, 1), 1060)]
    two_surges = []
    for (t0, q0), (t1, q1) in zip(knots, knots[1:]):
        moment = t0
        while moment < t1:
            value = q0 + (q1 - q0) * ((moment - t0) / (t1 - t0))
            two_surges.append((moment, round(value) if value < 1000 else int(value / 10 + 0.5) * 10))
            moment += timedelta(minutes=15)
    for check, expected_state in [
            (winter_storm(13, 12, 20), None),     # 865 cfs: 45 cfs above the low, under 5% of the high: still "falling"
            (winter_storm(13, 15, 20), 'Climbing again: 910 cfs is 90 cfs above the lowest reading since this rise’s high (820 cfs at 9:00 AM PST) and 490 cfs below that high of 1,400 cfs at Jan 12, 3:00 PM PST.'),
            (winter_storm(13, 20, 20), 'Climbing again: 985 cfs is 165 cfs above the lowest reading since this rise’s high (820 cfs at 9:00 AM PST) and 415 cfs below that high of 1,400 cfs at Jan 12, 3:00 PM PST.')]:
        newest = check.replace(minute=0)
        climb_context, climbing, _ = open_frame(check, feeds_payload=synthetic_gauge_payload(check, [row for row in two_surges if row[0] <= newest]))
        lines = river_lines(climbing)
        if expected_state is None:
            assert lines['river-state'].startswith('Now at least 5% below the high of 1,400 cfs at Jan 12, 3:00 PM PST; the river first read that far below it at '), lines['river-state']
        else:
            assert lines['river-state'] == expected_state, (check, lines['river-state'])
            assert 'about level' in lines['river-change'] and lines['river-high'] is None and lines['river-rain-note'] is None and str(EVIDENCE['rises']['count']) not in climbing.locator('#river-block').inner_text(), lines
            assert 'may have peaked' not in climbing.locator('#outlook').inner_text() and 'Now at least' not in climbing.locator('#river-block').inner_text()
        assert lines['river-past'] == 'Past the 400 cfs November–February number since the Jan 12, 10:15 AM PST reading. This page’s arithmetic, not the Department of Health’s decision.', lines['river-past']
        if check.hour == 15:
            climbing.screenshot(path=str(out / 'state-climbing-again-below-an-earlier-top-desktop-1440.png'))
            axe_runs += audit_page(climbing, 'climbing-again')
        climb_context.close()

    # ---- Before the number is passed (9:20 AM): no state and no "high" language ----
    # NOAA's 8:19 AM path starts at 11:00 AM with 58.5 cfs; the gauge reads 62.5 cfs, 4 cfs above it and inside the
    # 10 cfs line, so a comparison was made and NOAA's own words stand.
    early_context, early, _ = open_frame(pacific(29, 9, 20))
    lines = river_lines(early)
    assert lines['flow'] == '62.5' and lines['river-change'] == 'Last hour: +16.5 cfs (rising). About 3 hours: +32.6 cfs.' and lines['river-rise'] == rise_line('46.6', 46, low_at_1am), lines
    assert all(lines[ident] is None for ident in ['river-older', 'river-state', 'river-past', 'river-high', 'river-new-high-note', 'river-rain-note', 'noaa-above', 'noaa-flag']), lines
    assert lines['noaa-compare'] == noaa_ahead('8:19 AM PDT', '1 hour', '11:00 AM PDT', '58.5', '58.5', '11:00 AM PDT', '62.5', '9:00 AM PDT'), lines['noaa-compare']
    assert early.locator('#rise-passed').is_hidden() and early.locator('#rise-noaa-basis').is_hidden() and early.locator('.rise-card h2').inner_text() == 'What NOAA’s forecast adds' and said(early, 'rise-title') == NOT_ALIGNED
    assert said(early, 'crest-time') == 'Highest value is at the forecast’s start' and said(early, 'ops-forecast') == 'Only falls'
    assert said(early, 'forecast-time') == 'NOAA’s forecast path only falls from its first value (58.5 cfs at 11:00 AM PDT). That value is not a forecast high.'
    assert said(early, 'ops-forecast-note') == 'NOAA’s path falls from its first value · issued 8:19 AM PDT' and said(early, 'rise-noaa-dry') == NOAA_DRY + ' ' + CAVEAT
    assert banned_words(early.locator('#outlook').inner_text()) == []
    early.screenshot(path=str(out / 'replay-00-0920am-before-the-number-desktop-1440.png'))
    early_context.close()
    # 11:35 AM, holding the 11:15 AM reading: 103 cfs, 44.9 cfs above NOAA's value, the measured rise still under the
    # number. The gauge is above the line, so no peak time is read, but nothing says "not tracking a rise".
    early_context, early, _ = open_frame(pacific(29, 11, 35), newest=pacific(29, 11, 15))
    lines = river_lines(early)
    assert lines['noaa-compare'] == noaa_line('8:19 AM PDT', '3 hours', '58.1', '11:15 AM PDT', '103', '44.9') and lines['noaa-above'] == above_highest('44.9') and lines['noaa-flag'] is None, lines
    assert lines['river-state'] is None and lines['river-past'] is None and lines['river-rise'] == rise_line('87.1', 87, low_at_1am), lines
    assert said(early, 'crest-time') == NO_PEAK_ABOVE and said(early, 'forecast-time') == NO_PEAK_ABOVE and said(early, 'rise-noaa-basis') == BUILT_ON_ABOVE and 'forecast to fall' not in early.locator('#outlook').inner_text()
    early_context.close()

    # ---- One synthetic covered case: a first visit, a NOAA issue exactly 7 hours old whose path covers the reading ----
    # (INVENTED flat path at 81.5 cfs beginning before its issue stamp, a shape NOAA does not issue; kept so that the
    # covered comparison is tested with round numbers: the gauge at exactly twice NOAA's value.)
    flat_path = [((datetime(2026, 9, 29, 6, 0, tzinfo=timezone.utc) + timedelta(hours=6 * step)).isoformat(), 81.5) for step in range(19)]
    first_context, first_visit, _ = open_frame(pacific(29, 15, 20), noaa_path=flat_path, noaa_issue=pacific(29, 8, 20))
    assert said(first_visit, 'watch-state') == 'NO EARLIER FORECAST', 'no earlier forecast is saved on a first visit'
    assert said(first_visit, 'noaa-compare') == noaa_line('8:20 AM PDT', '7 hours', '81.5', '3:00 PM PDT', '163', '81.5') and said(first_visit, 'noaa-above') == above_highest('81.5') and said(first_visit, 'noaa-flag') == NOT_TRACKING
    assert said(first_visit, 'forecast-time') == NO_PEAK_ABOVE and said(first_visit, 'ops-forecast-note') == 'within the available path · issued 8:20 AM PDT'
    first_visit.screenshot(path=str(out / 'state-first-visit-noaa-mismatch-desktop-1440.png'))
    first_context.close()
    # A synthetic path that starts after the reading and later rises above the gauge: 163 cfs against a first value of
    # 120 cfs and a highest value of 300 cfs. Above the first value while the last hour is "rising" (+6 cfs).
    late_path = [((datetime(2026, 9, 30, 0, 0, tzinfo=timezone.utc) + timedelta(hours=6 * step)).isoformat(), 300 if step == 2 else 120) for step in range(16)]
    first_context, first_visit, _ = open_frame(pacific(29, 15, 20), noaa_path=late_path, noaa_issue=pacific(29, 14, 36))
    assert said(first_visit, 'noaa-compare') == noaa_ahead('2:36 PM PDT', '44 minutes', '5:00 PM PDT', '120', '300', 'Sep 30, 5:00 AM PDT', '163', '3:00 PM PDT'), said(first_visit, 'noaa-compare')
    assert said(first_visit, 'noaa-above') == 'The gauge is 43 cfs above NOAA’s first value and rose in the last hour.' and said(first_visit, 'noaa-flag') == NOT_TRACKING and said(first_visit, 'crest-time') == NO_PEAK_ABOVE
    first_context.close()
    # The same path an hour later: the last hour is only "about level" (+1 cfs), the gauge is below the path's highest
    # value, so it is not above the line; a comparison was made and NOAA's own forecast-high time stands.
    first_context, first_visit, _ = open_frame(pacific(29, 16, 20), noaa_path=late_path, noaa_issue=pacific(29, 14, 36))
    assert first_visit.locator('#noaa-above').is_hidden() and first_visit.locator('#noaa-flag').is_hidden() and said(first_visit, 'crest-time') == 'NOAA forecast high around Sep 30, 5:00 AM PDT'
    first_context.close()

    # ---- One device left open through the afternoon and evening: what a screen reader is told, and the earlier-forecast headline ----
    stay_context, stay, stay_source = open_frame(pacific(29, 12, 20))
    stay.evaluate("""() => { window.__told = []; const el = document.getElementById('river-announce');
      new MutationObserver(() => window.__told.push(el.textContent)).observe(el, {childList: true, characterData: true, subtree: true}); }""")
    assert stay.locator('#river-announce').get_attribute('aria-live') == 'polite' and stay.locator('#river-announce').get_attribute('role') == 'status'
    assert stay.locator('#river-block').get_attribute('aria-live') is None and said(stay, 'river-announce') == '', 'nothing is announced on a first load'
    def advance(check, **feeds):
        stay_context.clock.set_fixed_time(check)
        stay_source['payload'] = replay_payload(check, **feeds)
        stay.locator('#refresh').click()
        settle(stay)
        return stay.evaluate('window.__told')
    assert advance(pacific(29, 12, 25)) == [], 'a refresh with no change of state announces nothing'
    paused_at_415 = 'No new high since 3:15 PM PDT. ' + PAUSE
    assert advance(pacific(29, 16, 35), newest=pacific(29, 16, 15)) == [paused_at_415], 'the pause is announced once'
    # The forecast saved at the 12:20 PM visit is now 4 hours old: the earlier-forecast check runs, and its headline
    # takes its word from the last hour (level), not from the three-hour change (+22 cfs).
    assert said(stay, 'watch-state') == 'ABOVE EARLIER FORECAST' and said(stay, 'watch-title') == 'River is above the earlier NOAA forecast, but not rising in the last hour of readings'
    assert advance(pacific(29, 16, 40), newest=pacific(29, 16, 15)) == [paused_at_415], 'the same state is not announced again on the next refresh'
    told = advance(pacific(29, 19, 20))
    assert told == [paused_at_415, frame_state['0720pm']], told
    assert said(stay, 'watch-title') == 'River is above the earlier NOAA forecast and rising in the last hour of readings' and said(stay, 'watch-change') == '+17'
    told = advance(pacific(29, 22, 20))
    assert told[2:] == [frame_state['1020pm']], told
    # Version 6 said "still rising" here: the three-hour change is still +10 cfs. The last hour is level.
    assert said(stay, 'watch-state') == 'ABOVE EARLIER FORECAST' and said(stay, 'watch-change') == '+10'
    assert said(stay, 'watch-title') == 'River is above the earlier NOAA forecast, but not rising in the last hour of readings'
    assert 'Over the last hour of readings it was about level.' in said(stay, 'watch-detail') and 'still rising' not in stay.locator('#outlook').inner_text().lower()
    assert banned_words(stay.locator('#outlook').inner_text()) == []
    stay.screenshot(path=str(out / 'state-returning-device-1020pm-desktop-1440.png'), full_page=True)
    axe_runs += audit_page(stay, 'returning-device-1020pm')
    told = advance(pacific(29, 23, 20))
    assert told[3:] == [frame_state['1120pm']] and 'rising' not in said(stay, 'watch-title').replace('not rising', ''), told
    # The feed then stalls: the River block says it cannot tell, once.
    told = advance(pacific(30, 1, 20), newest=pacific(29, 23, 0))
    assert told[4:] == ['Cannot tell whether the river is rising: the gauge feed is 140 minutes behind.'], told
    assert said(stay, 'watch-state') == 'CHECK UNAVAILABLE', 'the earlier-forecast check does not run on a reading over 90 minutes old'
    stay_context.close()

    # ---- Rain: a block with no value against a block forecast at exactly zero (the +24 to 30 hour block) ----
    rain_shots = {}
    for label, amounts in [('missing', [2.54, 1.27, 0.51, 0, None, 0, 0]), ('zero', [2.54, 1.27, 0.51, 0, 0, 0, 0])]:
        rain_context, rainy, _ = open_frame(pacific(29, 19, 20), rain_mm=amounts)
        chart_text = rainy.locator('#rain-chart svg').evaluate("svg => [...svg.querySelectorAll('text')].map(t => t.childNodes[0].textContent)")
        rain_shots[label] = {'pixels': rainy.locator('#rain-chart').screenshot(path=str(out / f'rain-block-{label}-desktop-1440.png')), 'text': chart_text,
                             'missing': rainy.locator('#rain-chart svg rect.rain-missing').count(), 'bars': rainy.locator('#rain-chart svg rect.rain-a, #rain-chart svg rect.rain-b').count(),
                             'table': rainy.locator('#rain-forecast-table tbody tr').nth(4).evaluate('row => [...row.cells].slice(1).map(cell => cell.textContent)'), 'total': said(rainy, 'rain-total')}
        rain_context.close()
    assert rain_shots['missing']['pixels'] != rain_shots['zero']['pixels'], 'a missing rain block must not be drawn like zero rain'
    assert rain_shots['missing']['text'].count('no data') == 2 and 'No data (not zero)' in rain_shots['missing']['text'] and rain_shots['missing']['text'].count('0') == 4, rain_shots['missing']['text']
    assert 'no data' not in rain_shots['zero']['text'] and 'No data (not zero)' not in rain_shots['zero']['text'] and rain_shots['zero']['text'].count('0') == 6, rain_shots['zero']['text']
    assert rain_shots['missing']['missing'] == 3 and rain_shots['zero']['missing'] == 0, 'two hatched columns and their legend swatch, against none'
    assert rain_shots['missing']['bars'] == rain_shots['zero']['bars'] == 8, 'six real bars and the two legend swatches in both'
    assert rain_shots['missing']['table'] == ['Unavailable', 'Unavailable'] and rain_shots['zero']['table'] == ['0.00 in.', '0.00 in.'], (rain_shots['missing']['table'], rain_shots['zero']['table'])
    assert rain_shots['missing']['total'] == rain_shots['zero']['total'] == '0.17', 'the 24-hour headline is the same: the block lies beyond it'

    # ---- Observed rain: one gauge at 0.00 inch for 24 hours while both others report 0.25 inch or more ----
    suspect_context, suspect, _ = open_frame(pacific(29, 19, 20), rrm_rows=['Padilla Bay Farm 0.00 0.05 0.10 0.20 0.30 0.40 0.50', 'Burlington 0.00 0.03 0.08 0.15 0.25 0.35 0.45', 'Sedro Wooley RAWS 0.00 0.00 0.00 0.00 0.00 0.00 0.00'])
    assert suspect.locator('#observed-rain-table .suspect-note').count() == 1
    assert suspect.locator('#observed-rain-table tbody tr').nth(2).locator('th').inner_text().split('\n') == ['Sedro-Woolley RAWS', 'Reads zero while both other gauges report rain; treat as suspect.']
    suspect.locator('#observed-rain-table').screenshot(path=str(out / 'rain-suspect-zero-desktop-1440.png'))
    axe_runs += audit_page(suspect, 'suspect-zero-rain')
    suspect_context.close()
    suspect_context, suspect, _ = open_frame(pacific(29, 19, 20), rrm_rows=['Padilla Bay Farm 0.00 0.05 0.10 0.20 0.30 0.40 0.50', 'Burlington 0.00 0.03 0.08 0.15 0.24 0.35 0.45', 'Sedro Wooley RAWS 0.00 0.00 0.00 0.00 0.00 0.00 0.00'])
    assert suspect.locator('#observed-rain-table .suspect-note').count() == 0, 'no flag when one of the other gauges is under 0.25 inch'
    suspect_context.close()

    # ---- November to April: nothing rain-related is shown as context, and NOAA's dry-season record is not shown ----
    winter_check = datetime(2025, 11, 15, 20, 0, tzinfo=timezone.utc)   # synthetic feeds; noon Pacific in November
    winter_context, winter, _ = open_frame(winter_check, feeds_payload=fixtures(winter_check))
    assert winter.locator('#rain-context').is_hidden() and winter.locator('#rain-context').inner_text() == '' and winter.locator('#rise-noaa-dry').is_hidden()
    assert said(winter, 'ops-threshold') == '400 cfs' and said(winter, 'river-rise') == 'Rise above the 24-hour low: 25 cfs (6% of the 400 cfs November–February number; low 76 cfs at Nov 14, 12:00 PM PST).'
    winter_text = winter.locator('#outlook').inner_text().lower()
    assert 'dry season' not in winter_text and 'dry-season' not in winter_text and 'context, not an alert' not in winter_text and 'may to october rises' not in winter_text
    winter_context.close()

    # ---- Research tab: every count in the look-back section equals the evidence object ----
    page.locator('#tab-research').click()
    T_ALL, T_DRY, E_ALIGNED = EVIDENCE['timing']['all'], EVIDENCE['timing']['dry'], EVIDENCE['aligned']
    assert page.locator('#lookback-title').inner_text() == f"What {EVIDENCE['rises']['count']} past rises say about the peak" == 'What 172 past rises say about the peak'
    assert '13 OCTOBER 2026' in page.locator('.lookback .eyebrow').first.inner_text()
    lede = page.locator('#lookback-lede').inner_text()
    assert lede.startswith(f"Counts from {EVIDENCE['rises']['count']} rises at the {EVIDENCE['rises']['place']}, {EVIDENCE['rises']['period']}, read from {EVIDENCE['rises']['readings']},") and 'none is a forecast' in lede, lede
    span_of = lambda values: f"{values_text(min(values))} to {values_text(max(values))}"
    values_text = lambda value: half(value) if float(value * 2).is_integer() else f'{value:g}'
    expected_cards = {
        'timing': [f"Across {T_ALL['rises']} rises, the highest reading came a median of {half(T_ALL['medianHours'])} hours after the 24-hour rise passed the seasonal number (the middle value: half took less, half took more). "
                   f"Half of the rises took between {half(T_ALL['middleHalfHours'][0])} and {half(T_ALL['middleHalfHours'][1])} hours; {T_ALL['under2h']} took under 2 hours and {T_ALL['atLeast16h']} of {T_ALL['rises']} took 16 hours or more.",
                   f"In {T_DRY['months']} ({T_DRY['rises']} rises) the median was {half(T_DRY['medianHours'])} hours and half took between {half(T_DRY['middleHalfHours'][0])} and {half(T_DRY['middleHalfHours'][1])} hours; "
                   f"{T_DRY['over8h']} took more than 8 hours and {T_DRY['atLeast16h']} took 16 hours or more.",
                   'The spread is too wide for one clock time, so this page prints no time for the top of a rise.'],
        'afterNewHigh': [f"Of {E_AFTER['readings']:,} readings that were a new high for their rise ({E_AFTER['rises']} rises), the highest reading of the rise came within the next {E_AFTER['withinHours']} hours for "
                         f"{E_AFTER['withinPercent']}% (about 1 in {E_AFTER['aboutOneInWithin']}) and was still {E_AFTER['atLeastHours']} hours or more away for {E_AFTER['atLeastPercent']}% (about 1 in {E_AFTER['aboutOneInAtLeast']}).",
                         'The last new high of every rise is its top, so a new high can be the top; and a long rise is not due to stop.'],
        'wait': [f"For the rises whose highest reading had not yet come, the further time to it was wide at every stage checked: a quarter of them got there within {span_of(E_WAIT['lowerQuartileMoreHours'])} hours, "
                 f"the middle value was {span_of(E_WAIT['medianMoreHours'])} hours, and a quarter needed {span_of(E_WAIT['upperQuartileMoreHours'])} hours or more."],
        'pause': [f"The first time each rise went {E_PAUSE['afterMinutes']} minutes of readings with no new high, {E_PAUSE['higherAgain']} of {E_PAUSE['rises']} went higher again within a day, {E_PAUSE['higherByMoreThan5Percent']} of them by more than 5%."],
        'peak2h': [f"The first time each rise went 2 hours of readings with no new high, the river later climbed more than 5% above that high within 12 hours in {E_PEAK['within12h']} of {E_PEAK['rises']} rises "
                   f"(about 1 in {E_PEAK['aboutOneIn12h']}) and within 24 hours in {E_PEAK['within24h']} (about 1 in {E_PEAK['aboutOneIn24h']})."],
        'rainPause': [RAIN_BESIDE_PEAK],
        'falling': [f"The first time each rise read at least 5% below its highest reading so far, the river later climbed more than 5% above that high within 12 hours in {E_FALL['within12h']} of {E_FALL['rises']} rises "
                    f"(about 1 in {E_FALL['aboutOneIn12h']}) and within 24 hours in {E_FALL['within24h']} (about 1 in {E_FALL['aboutOneIn24h']})."],
        'aligned': [f"At the Samish over {E_ALIGNED['period']} ({E_ALIGNED['rises']} rises), NOAA’s river forecast shifted to start at the latest gauge reading gave {E_ALIGNED['falseAlertEpisodesAligned']} false-alert episodes "
                    f"against {E_ALIGNED['falseAlertEpisodesAsIssued']} for the forecast read as issued, with {E_ALIGNED['warned12hEitherWay']} rises warned {E_ALIGNED['leadHours']} hours or more ahead either way.",
                    'Limit: the shift does nothing for a rise NOAA’s river forecast does not show. This page does not draw the current forecast shifted to the gauge; it says when the gauge is above the forecast instead.'],
        'noaaDry': [NOAA_DRY, 'A closure-size rise is a 24-hour rise as large as the seasonal number.'],
        'rainContext': [RAIN_CONTEXT]}
    assert page.locator('#lookback-grid [data-evidence]').evaluate_all('cards => cards.map(card => card.dataset.evidence)') == list(expected_cards)
    for key, sentences in expected_cards.items():
        card = page.locator(f'#lookback-grid [data-evidence="{key}"]')
        assert card.locator('p:not(.eyebrow):not(.note):not(.meta)').all_inner_texts() == sentences, (key, card.locator('p').all_inner_texts())
        assert card.locator('p.note').inner_text() == f"Period: {EVIDENCE[key]['period']}. {CAVEAT}", key
        assert card.locator('p.meta').inner_text() == EVIDENCE[key]['source'], key
    assert page.locator('#lookback-grid [data-evidence="wait"] h3').inner_text() == 'How much longer past rises took'
    wait_rows = page.locator('#lookback-grid [data-evidence="wait"] tbody tr').evaluate_all("rows => rows.map(row => [...row.cells].map(cell => Number(cell.textContent)))")
    assert wait_rows == [list(row) for row in zip(E_WAIT['stagesHours'], E_WAIT['risesStillWaiting'], E_WAIT['lowerQuartileMoreHours'], E_WAIT['medianMoreHours'], E_WAIT['upperQuartileMoreHours'])], wait_rows
    assert wait_rows[0] == [0, 167, 3.2, 5.5, 9.4] and wait_rows[-1] == [12, 29, 4, 7, 13.8], wait_rows
    assert page.locator('#lookback-grid .lookback-table').evaluate('el => el.scrollHeight <= el.clientHeight'), 'every row of the look-back table is on screen without scrolling inside it'
    lookback_text = page.locator('#lookback-grid').inner_text()
    for literal in ['a median of 5½ hours', 'between 3 and 9 hours', '18 took under 2 hours', '22 of 172 took 16 hours or more', '(52 rises) the median was 6 hours', 'between 3½ and 8 hours', '13 took more than 8 hours',
                    '5 took 16 hours or more', 'within 1½ to 4 hours', 'the middle value was 3½ to 7 hours', 'a quarter needed 8 to 13.8 hours or more', 'Of 4,027 readings', 'for 24.9% (about 1 in 4)', 'for 26.6% (about 1 in 4)',
                    '67 of 172', '42 of them', 'in 19 of 172 rises (about 1 in 9)', 'in 30 (about 1 in 6)', 'in 10 of 172 rises (about 1 in 17)', 'in 21 (about 1 in 8)',
                    '(66 rises)', '29 false-alert episodes against 38', '36 rises warned 12 hours or more ahead', '25 of 32', 'not for 7', '(23 of 45)', '(7 of 26)', '4 of the 7', '10 of 32', 'July 2018 to early October 2026']:
        assert literal in lookback_text, ('look-back figure missing from the Research tab', literal)
    assert lookback_text.count(CAVEAT) == len(expected_cards) == 10 and '23 of 33' not in page.locator('#research').inner_text(), 'each entry says it is a look-back; the dry-season record is 25 of 32, never 23 of 33'
    assert 'kind of divergence a grower described' in page.locator('#research').inner_text() and 'RESEARCH UPDATE · OCTOBER 11, 2026' in page.locator('#research').inner_text()
    assert page.locator('#research .research-stat').count() == 2, 'the 11 October sections are kept'
    # Sources tab: the display rules are written from the rule constants.
    page.locator('#tab-sources').click()
    rules_text = page.locator('#river-rules').inner_text()
    assert page.locator('#river-rules li').count() == 14
    for literal in [f"recent for {RULES['freshMinutes']} minutes", 'recent for 90 minutes', 'more than 60 minutes of readings are missing inside the last hour', 'stamped more than 5 minutes after this device’s time',
                    'never against this device’s clock', 'within 20 minutes either way', '“rising” only at +2 cubic feet per second (cfs) and +2% or more', '“falling” only at −2 cfs and −2% or beyond',
                    'it is printed as “at least”, a lower bound above the lowest reading held', 'never as zero or as “no rise”', 'rounded down, here and on the rise card',
                    'first reading of the last 48 hours', 'remembered for 48 hours of readings', 'the page then says “since at or before”', 'its readings do not reach back to where that rise began',
                    'strictly higher than every earlier reading of this rise. An equal reading is not a new high.', 'otherwise the page says “New high”',
                    '60 minutes of readings with no new high is called a pause; 120 minutes or more is “may have peaked”', 'at least 5% below the high is “falling”',
                    'above the lowest reading since the high by at least 5% of the high and the about-three-hour change is positive',
                    'the count beside “may have peaked” from the 2-hour mark', 'more than 24 hours of readings past that point',
                    'A NOAA path starts some hours after it is issued', 'the highest value anywhere in the path, or against the path’s first value when the last-hour change is “rising”',
                    'at 10% of the seasonal number or more', 'so it works on a first visit', 'printed only when that comparison was made and the gauge is not above the line',
                    'the NOAA-based rise card (“What NOAA’s forecast adds”) is withheld for the same reason', 'look-backs on 172 Samish rises of 2011 to 2023 (15-minute readings)',
                    'keeps the last high or low after it passes', 'hatched “no data” column', 'report 0.25 inch or more is marked suspect', 'May to October only', 'beside “may have peaked” only']:
        assert literal in rules_text, ('display rule missing from the Sources tab', literal)
    assert 'more than 2 hours old are marked stale' not in page.locator('#sources').inner_text()
    page.locator('#tab-outlook').click()
    assert 'v7 / October 2026' in page.locator('footer').inner_text() and page.evaluate("[...document.querySelectorAll('link[rel=stylesheet], script[src]')].every(el => (el.href || el.src).endsWith('?v=7'))")
    # The flow figure is the largest type on every tab of the desktop page.
    for tab in ['outlook', 'research', 'sources']:
        page.locator('#tab-' + tab).click()
        sizes = page.evaluate(largest_type)
        assert sizes['flow'] > sizes['max'], ('the flow figure must be the largest type on the page', tab, sizes)
    page.locator('#tab-outlook').click()
    assert banned_words(page.locator('#outlook').inner_text()) == [], banned_words(page.locator('#outlook').inner_text())
    # A numerically available three-hour pair is not operationally current when
    # its latest endpoint is stale. All change displays must fail closed.
    original_observed = payload['nwps']['observed']
    original_usgs_time = payload['usgs']['features'][0]['properties']['time']
    payload['nwps']['observed'] = json.loads(json.dumps(original_observed))
    for index, row in enumerate(payload['nwps']['observed']['data']):
        row['validTime'] = ISO(index - 58)
    payload['usgs']['features'][0]['properties']['time'] = ISO(-10)
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    # Version 7: a reading over 90 minutes old gives "Cannot tell", its own time and age, and no change figure at all.
    assert re.fullmatch(r'Cannot tell whether the river is rising: the gauge feed is 6\d\d minutes behind\.', page.locator('#river-state').inner_text())
    assert re.fullmatch(r'6\d\d minutes old', page.locator('#river-age').inner_text())
    for ident in ['river-change', 'river-rise', 'river-past', 'river-high', 'river-wait', 'river-rain-note']:
        assert page.locator('#' + ident).is_hidden(), ident
    assert 'Last hour' not in page.locator('#river-block').inner_text() and 'About 3 hours' not in page.locator('#river-block').inner_text()
    assert re.match(r'The newest gauge reading is 6\d\d minutes old', page.locator('#feed-alert').inner_text())
    payload['nwps']['observed'] = original_observed
    payload['usgs']['features'][0]['properties']['time'] = original_usgs_time
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#river-change').inner_text() == 'Last hour: +2 cfs (rising). About 3 hours: +4 cfs.'
    assert page.locator('#river-state').is_hidden() and page.locator('#feed-alert').is_hidden()
    page.locator('#radar-toggle').click()
    page.wait_for_function("['Latest retrieved frame','Retrieved frame'].includes(document.getElementById('radar-status').textContent)")
    assert page.locator('#radar-toggle').inner_text() == 'Play animation'
    for product, layer in [('hourly', 'katx_boha'), ('storm', 'katx_bdsa'), ('reflectivity', 'katx_sr_bref')]:
        page.locator(f'[data-radar-product="{product}"]').click()
        page.wait_for_function("document.getElementById('radar-status').textContent === 'Latest retrieved frame'")
        assert page.locator(f'[data-radar-product="{product}"]').get_attribute('aria-pressed') == 'true'
        assert layer in page.locator('#radar-loop').get_attribute('src')
        assert page.locator('#radar-legend').evaluate('img => img.complete && img.naturalWidth > 0')
        page.screenshot(path=str(out / f'radar-{product}-1440.png'), full_page=False)
    # Mobile evidence preserves the provider's actual 500-by-30 horizontal
    # legend, exposes it in a keyboard-focusable scroll region below the map,
    # and keeps the safety-critical closure link at a 44-pixel touch target.
    for width in [320, 390]:
        page.set_viewport_size({'width': width, 'height': 960})
        closure_link = page.locator('.official-line .button-link')
        assert ' '.join(page.locator('.official-line').inner_text().split()) == 'Official status is separate. Check commercial closures ↗'
        assert closure_link.get_attribute('href') == 'https://doh.wa.gov/commercialshellfishmap'
        assert closure_link.evaluate('el => el.getBoundingClientRect().height >= 44')
        closure_link.focus()
        page.keyboard.press('Tab')
        page.keyboard.press('Shift+Tab')
        assert closure_link.evaluate('el => document.activeElement === el && getComputedStyle(el).outlineStyle !== "none"')
        for product, layer in [('reflectivity', 'katx_sr_bref'), ('hourly', 'katx_boha'), ('storm', 'katx_bdsa')]:
            page.locator(f'[data-radar-product="{product}"]').click()
            page.wait_for_function("document.getElementById('radar-status').textContent === 'Latest retrieved frame'")
            legend = page.locator('#radar-legend')
            legend_wrap = page.locator('#radar-legend-wrap')
            legend_box = page.locator('#radar-legend').bounding_box()
            assert legend.evaluate('img => img.naturalWidth === 500 && img.naturalHeight === 30'), (width, product, 'native legend geometry')
            assert legend_box and legend_box['width'] >= 499 and 29 <= legend_box['height'] <= 31, (width, product, legend_box)
            assert legend_wrap.evaluate('el => el.scrollWidth > el.clientWidth'), (width, product, 'legend must scroll')
            assert legend_wrap.evaluate("el => getComputedStyle(el).position === 'relative' && document.getElementById('radar-frame').getBoundingClientRect().bottom <= el.getBoundingClientRect().top"), (width, product, 'legend must sit below map')
            legend_wrap.focus()
            page.keyboard.press('Tab')
            page.keyboard.press('Shift+Tab')
            assert legend_wrap.evaluate('el => document.activeElement === el && getComputedStyle(el).outlineStyle !== "none"')
            assert layer in page.locator('#radar-loop').get_attribute('src')
            page.locator('.radar-card').screenshot(path=str(out / f'radar-{product}-{width}.png'))
    page.set_viewport_size({'width': 1440, 'height': 1000})
    # A failed official legend must be explicit without erasing a valid radar map
    # or claiming the combined radar source is fully retrieved.
    mode['radar_legend_fail'] = True
    page.locator('[data-radar-product="hourly"]').click()
    page.wait_for_function("document.getElementById('radar-legend-status').textContent.includes('unavailable')")
    page.wait_for_function("document.getElementById('radar-status').textContent === 'Latest retrieved frame'")
    assert page.locator('#radar-source-card .pill').inner_text() == 'Partial'
    assert page.locator('#radar-loop').evaluate('img => img.complete && img.naturalWidth > 0')
    page.screenshot(path=str(out / 'radar-legend-unavailable.png'), full_page=False)
    mode['radar_legend_fail'] = False
    page.locator('[data-radar-product="storm"]').click()
    page.wait_for_function("document.getElementById('radar-legend-status').textContent.includes('retrieved')")
    page.wait_for_function("document.getElementById('radar-status').textContent === 'Latest retrieved frame'")
    mode['radar_layer_fail'] = 'katx_boha'
    page.locator('[data-radar-product="hourly"]').click()
    page.wait_for_function("document.getElementById('radar-status').textContent === 'Unavailable'")
    assert page.locator('#flow').inner_text() == '101'
    assert not page.locator('#radar-overlay').is_visible()
    assert page.locator('#radar-legend-wrap').is_hidden()
    assert 'legend hidden' in page.locator('#radar-legend-status').inner_text().lower()
    failed_radar_alt = page.locator('#radar-loop').get_attribute('alt').lower()
    assert 'radar image unavailable' in failed_radar_alt and 'valid' not in failed_radar_alt
    # A later core-data render must not overwrite the failed image description
    # with the last successful radar time while map requests keep failing.
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    page.wait_for_function("document.getElementById('radar-status').textContent === 'Unavailable'")
    failed_radar_alt = page.locator('#radar-loop').get_attribute('alt').lower()
    assert 'radar image unavailable' in failed_radar_alt and 'valid' not in failed_radar_alt
    page.screenshot(path=str(out / 'radar-hourly-unavailable.png'), full_page=False)
    mode['radar_layer_fail'] = None
    page.locator('[data-radar-product="reflectivity"]').click()
    page.wait_for_function("document.getElementById('radar-status').textContent === 'Latest retrieved frame'")
    assert page.locator('#radar-overlay').is_visible()
    assert page.locator('#radar-legend-wrap').is_visible()
    assert 'valid' in page.locator('#radar-loop').get_attribute('alt').lower()
    assert page.locator('#watch-state').inner_text() == 'NO EARLIER FORECAST'
    assert page.locator('#watch-title').inner_text() == 'No earlier forecast to compare yet'
    assert 'dated panels above' in page.locator('#watch-detail').inner_text()
    assert page.locator('#watch-metrics').is_hidden()
    assert 'browser' not in page.locator('#outlook').inner_text().lower()
    assert 'profile' not in page.locator('#outlook').inner_text().lower()
    assert page.evaluate("Boolean(document.querySelector('.summary-grid').compareDocumentPosition(document.querySelector('.storm-log')) & Node.DOCUMENT_POSITION_FOLLOWING)")
    axe_runs += audit_state('learning')
    screenshot_state('learning')
    assert page.locator('#rise-status').inner_text() == 'Experimental'
    assert 'Not official status' in page.locator('#rise-detail').inner_text()
    assert page.locator('a[href="https://doh.wa.gov/commercialshellfishmap"]').count() >= 2
    assert page.locator('a[href="https://a.atmos.washington.edu/wrfrt/"]').count() == 1
    assert page.locator('a[href*="accuweather.com/en/us/burlington/98233/weather-forecast/336371"]').count() == 1
    assert page.locator('#update-status').evaluate("el => !el.closest('[role=tabpanel]')")
    assert page.locator('#feed-alert').evaluate("el => !el.closest('[role=tabpanel]')")
    page.locator('#tab-research').click()
    assert page.locator('#update-status').is_visible()
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#update-status').inner_text().startswith('Data checked')
    page.locator('#tab-outlook').click()
    assert 'NOAA forecast high around' in page.locator('#crest-time').inner_text()
    assert page.locator('#crest-nearby .crest-tide').count() >= 1

    # Manual storm log: no refresh creates entries; explicit saves persist,
    # export neutralizes spreadsheet formulas, and deletion/clear are local.
    assert page.locator('#storm-log-count').inner_text() == '0 saved'
    page.locator('#storm-log-tag').select_option(label='Before bed')
    page.locator('#storm-log-note').fill('=SUM(1,1) check')
    page.locator('#storm-log-save').click()
    assert page.locator('#storm-log-count').inner_text() == '1 saved'
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#storm-log-count').inner_text() == '1 saved'
    page.reload()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    page.wait_for_function("['Latest retrieved frame','Unavailable'].includes(document.getElementById('radar-status').textContent)")
    assert page.locator('#storm-log-count').inner_text() == '1 saved'
    assert page.locator('#radar-toggle').inner_text() == 'Play animation'
    with page.expect_download() as log_download_info:
        page.locator('#storm-log-export').click()
    log_text = Path(log_download_info.value.path()).read_text(encoding='utf-8-sig')
    assert "'=SUM(1,1) check" in log_text
    for field in ['feed_check_at', 'gauge_cfs', 'gauge_time', 'change_3h_cfs', 'noaa_forecast_high_cfs', 'noaa_forecast_issue', 'forecast_high_time', 'seasonal_rise_cfs', 'forecast_rain_24h_mean_in', 'rain_grid_136_114_updated', 'rain_grid_139_116_updated', 'observed_rain_report_issue', 'padilla_24h_in', 'burlington_24h_in', 'sedro_woolley_24h_in', 'radar_product', 'radar_valid_time']:
        assert field in log_text, field
    page.locator('#storm-log-tag').select_option(label='Morning check')
    page.locator('#storm-log-note').fill('Second manual check')
    page.locator('#storm-log-save').click()
    assert page.locator('#storm-log-count').inner_text() == '2 saved'
    page.locator('[data-delete-log]').first.click()
    assert page.locator('#storm-log-count').inner_text() == '1 saved'
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#storm-log-clear').click()
    assert page.locator('#storm-log-count').inner_text() == '0 saved'

    # Bank an older issue exactly as a returning browser would. The current reading
    # is 21 cfs above its saved path and has risen 4 cfs in the measured 3-hour span.
    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot())
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER FORECAST'
    assert 'not a closure, safety, or all-clear signal' in page.locator('#watch-detail').inner_text()
    assert page.locator('#watch-metrics').is_visible()
    assert page.locator('#watch-expected').inner_text() == '80'
    assert page.locator('#watch-observed').inner_text() == '101'
    assert page.locator('#watch-change').inner_text() == '+4'
    assert page.locator('#saved-path-legend').is_visible()
    assert page.locator('#flow-chart path[stroke="var(--saved)"]').count() >= 1

    first_history = page.evaluate("JSON.parse(localStorage.getItem('samish-river-outlook.forecast-snapshots.v1'))")
    current = max(first_history, key=lambda row: row['issueTime'])
    first_capture = current['capturedAt']
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    second_history = page.evaluate("JSON.parse(localStorage.getItem('samish-river-outlook.forecast-snapshots.v1'))")
    assert len(second_history) == len(first_history)
    assert next(row for row in second_history if row['issueTime'] == current['issueTime'])['capturedAt'] == first_capture

    with page.expect_download() as download_info:
        page.locator('#download-brief').click()
    download = download_info.value
    snapshot_text = Path(download.path()).read_text(encoding='utf-8')
    assert download.suggested_filename.startswith('samish-field-snapshot-')
    assert 'FORECAST CHANGE CHECK: ABOVE EARLIER FORECAST' in snapshot_text, repr(snapshot_text[:500])
    assert 'Official commercial status is not ingested' in snapshot_text
    # Version 7: the copied snapshot carries the same River, NOAA and Tide lines the screen shows, and nothing more.
    assert re.search(r'^RIVER, measured at the gauge: 101 cfs at .+ P[DS]T, \d+ minutes? old$', snapshot_text, re.M), snapshot_text[:400]
    assert 'Last hour: +2 cfs (rising). About 3 hours: +4 cfs.' in snapshot_text and 'Rise above the 24-hour low: 25 cfs' in snapshot_text
    assert 'NOAA RIVER FORECAST, current issue against the gauge\nNOAA’s river forecast, issued ' in snapshot_text and 'The gauge read 101 cfs then: 25 cfs lower.' in snapshot_text
    assert 'TIDE, Bellingham prediction, not Samish Bay water level or boat clearance\nLow of 2.0 ft was at ' in snapshot_text and ' · passed' in snapshot_text
    assert 'Still rising' not in snapshot_text and 'New high' not in snapshot_text and 'No new high' not in snapshot_text and banned_words(snapshot_text.split('Official commercial status')[0]) == []
    assert 'https://doh.wa.gov/commercialshellfishmap' in snapshot_text

    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot(95))
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'NOT ABOVE CHECK LINE'
    assert 'not a closure, safety, or all-clear signal' in page.locator('#watch-detail').inner_text()
    axe_runs += audit_state('tracking')
    screenshot_state('tracking')

    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot(250))
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'NOT ABOVE CHECK LINE'
    assert 'NEAR' not in page.locator('#watch-state').inner_text()

    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot())
    observed_minus_three = next(row for row in payload['nwps']['observed']['data'] if row['validTime'] == ISO(-3))
    original_minus_three = observed_minus_three['primary']
    observed_minus_three['primary'] = .110
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    # Version 7: the three-hour change is -9 cfs here, but the last hour is +2 cfs and +2%, so the
    # headline says rising. Under version 6 this state read "not rising now".
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER FORECAST'
    assert page.locator('#watch-change').inner_text() == '-9'
    assert page.locator('#watch-title').inner_text() == 'River is above the earlier NOAA forecast and rising in the last hour of readings'
    # With the last hour level (+0.5 cfs) the headline says "not rising", whatever the three-hour change is.
    observed_minus_one = next(row for row in payload['nwps']['observed']['data'] if row['validTime'] == ISO(-1))
    original_minus_one = observed_minus_one['primary']
    observed_minus_one['primary'] = .1005
    observed_minus_three['primary'] = original_minus_three
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER FORECAST'
    assert page.locator('#watch-change').inner_text() == '+4'
    assert page.locator('#watch-title').inner_text() == 'River is above the earlier NOAA forecast, but not rising in the last hour of readings'
    assert 'Over the last hour of readings it was about level.' in page.locator('#watch-detail').inner_text()
    axe_runs += audit_state('above-saved-path')
    screenshot_state('above-saved-path')
    observed_minus_one['primary'] = original_minus_one

    # Restore the earlier-path fixture so release screenshots include the neutral
    # comparison state rather than only the first-visit history-building state.
    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot())
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER FORECAST'
    page.locator('#tab-outlook').focus()
    page.keyboard.press('ArrowRight')
    assert page.locator('#research').is_visible()
    page.keyboard.press('End')
    assert page.locator('#sources').is_visible()
    page.keyboard.press('Home')
    assert page.locator('#outlook').is_visible()

    axe_runs += audit_state('outpacing', ('outlook', 'research', 'sources'))
    screenshot_state('outpacing')
    # Force clipboard denial to exercise a useful accessible fallback.
    page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject(Error('denied'))},configurable:true})")
    page.locator('#copy-brief').click()
    assert page.locator('#brief-fallback').is_visible()
    assert 'NOAA issued' in page.locator('#brief-fallback').input_value()
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#brief-fallback').is_hidden()
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER FORECAST'
    mode['radar_fail'] = True
    page.locator('#radar-toggle').click()
    page.wait_for_function("document.getElementById('radar-status').textContent === 'Unavailable'")
    assert page.locator('.radar-frame').evaluate("el => el.classList.contains('unavailable')")
    assert page.locator('#flow').inner_text() == '101'
    assert 'river and rain values remain independent' in page.locator('#radar-requested').inner_text().lower()
    failed_radar_alt = page.locator('#radar-loop').get_attribute('alt').lower()
    assert 'radar image unavailable' in failed_radar_alt and 'valid' not in failed_radar_alt
    page.screenshot(path=str(out / 'radar-unavailable.png'), full_page=False)
    mode['radar_fail'] = False
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    page.wait_for_function("['Animating retrieved frames','Latest retrieved frame'].includes(document.getElementById('radar-status').textContent)")
    assert page.locator('#radar-status').inner_text() in ('Animating retrieved frames', 'Latest retrieved frame')
    assert 'valid' in page.locator('#radar-loop').get_attribute('alt').lower()
    for scheme in ['light', 'dark']:
        page.emulate_media(color_scheme=scheme)
        for width in [320, 390, 768, 1024, 1440]:
            page.set_viewport_size({'width': width, 'height': 960})
            for tab in ['outlook', 'research', 'sources']:
                page.locator('#tab-' + tab).click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (scheme, width, tab, 'overflow')
                if width in [390, 1440]:
                    panel_text = page.locator('#' + tab).inner_text().lower()
                    assert 'browser' not in panel_text, (scheme, width, tab, 'browser language')
                    assert 'profile' not in panel_text, (scheme, width, tab, 'profile language')
                if width == 390 and tab == 'outlook':
                    assert page.locator('#river-block').evaluate('el => el.getBoundingClientRect().top < 650')
                    page.wait_for_function("Math.abs(document.querySelector('#rain-chart svg').viewBox.baseVal.width - document.querySelector('#rain-chart svg').getBoundingClientRect().width) <= 2")
                    assert page.locator('#rain-chart svg').evaluate("svg => Math.abs(svg.viewBox.baseVal.width - svg.getBoundingClientRect().width) <= 2")
                    assert page.locator('#rain-chart text').first.evaluate("el => parseFloat(getComputedStyle(el).fontSize) >= 11")
                    assert page.locator('[data-radar-product][aria-pressed="true"]').evaluate("el => getComputedStyle(el).boxShadow !== 'none'")
                if scheme == 'dark' and width in [320, 390] and tab == 'outlook':
                    legend_wrap = page.locator('#radar-legend-wrap')
                    legend_wrap.focus()
                    page.keyboard.press('Tab')
                    page.keyboard.press('Shift+Tab')
                    contrast = legend_wrap.evaluate("""el => {
                      const rgb = value => value.match(/[\\d.]+/g).slice(0, 3).map(Number);
                      const lum = value => rgb(value).map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
                      const a = lum(getComputedStyle(el).outlineColor), b = lum(getComputedStyle(el.closest('.radar-card')).backgroundColor);
                      return { ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05), outline: getComputedStyle(el).outlineColor, style: getComputedStyle(el).outlineStyle };
                    }""")
                    assert contrast['style'] != 'none' and contrast['ratio'] >= 3, (width, contrast)
                    page.locator('.radar-card').screenshot(path=str(out / f'dark-radar-legend-focus-{width}.png'))
                if width in [390, 1440]:
                    page.screenshot(path=str(out / f'{scheme}-{tab}-{width}.png'), full_page=True)
    # Nearby observed rain can fail without erasing the river or forecast rain.
    mode['rrm_fail'] = True
    page.locator('#tab-outlook').click()
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#observed-rain-status').inner_text() == 'Unavailable'
    assert page.locator('#flow').inner_text() == '101'
    assert page.locator('#rain-total').inner_text() == '0.80'
    page.screenshot(path=str(out / 'observed-rain-unavailable.png'), full_page=True)
    axe_runs += audit_state('observed-rain-unavailable')
    mode['rrm_fail'] = False
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    # Rain values are withheld if their official grid geometry cannot be checked.
    mode['grid_geometry_fail'] = True
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#rain-total').inner_text() == '—'
    assert page.locator('#radar-overlay .rain-marker').count() == 0
    assert 'geometry unavailable' in page.locator('#source-status').inner_text().lower()
    assert page.locator('#feed-alert').inner_text()[0].isupper()
    page.screenshot(path=str(out / 'rain-grid-geometry-unavailable.png'), full_page=True)
    mode['grid_geometry_fail'] = False
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#rain-total').inner_text() == '0.80'
    # A well-formed cell outside the displayed drainage reference is withheld.
    mode['grid_outside_basin'] = True
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#rain-total').inner_text() == '—'
    assert page.locator('#radar-overlay .rain-marker').count() == 1
    assert 'not fully inside' in page.locator('#source-status').inner_text().lower()
    assert 'shown only after' in page.locator('#rain-note').inner_text().lower()
    page.screenshot(path=str(out / 'rain-grid-outside-basin.png'), full_page=True)
    mode['grid_outside_basin'] = False
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#rain-total').inner_text() == '0.80'
    # Preserve NOAA observations when the direct feed fails, and label the source honestly.
    mode['direct_fail'] = True
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#flow').inner_text() == '100'
    assert 'NOAA copy' in page.locator('#observation-note').inner_text()
    assert 'No direct USGS reading' in page.locator('#source-status').inner_text()
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER FORECAST'
    payload['rain']['properties']['quantitativePrecipitation']['values'][0]['value'] = None
    payload['nwps']['forecast']['data'] = payload['nwps']['forecast']['data'][:4]
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#rain-total').inner_text() == '—'
    assert page.locator('#forecast-status').inner_text() == 'Shorter horizon'
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER FORECAST'
    payload['rain']['properties']['quantitativePrecipitation']['values'][0]['value'] = 0
    payload['rain']['properties']['updateTime'] = ISO(-25)
    payload['nwps']['forecast']['issuedTime'] = ISO(-49)
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#rain-total').inner_text() == '—'
    assert page.locator('#forecast-high').inner_text() == '—'
    assert page.locator('#rise-status').inner_text() == 'Unavailable'
    assert 'current usable NOAA forecast' in page.locator('#rise-title').inner_text()
    assert 'Stale' in page.locator('#rain-points').inner_text()
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER FORECAST'
    mode['fail'] = True
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    page.wait_for_function("document.getElementById('radar-status').textContent === 'Unavailable'")
    failed_radar_alt = page.locator('#radar-loop').get_attribute('alt').lower()
    assert 'radar image unavailable' in failed_radar_alt and 'valid' not in failed_radar_alt
    for ident in ['flow', 'forecast-high', 'rain-total']:
        assert page.locator('#' + ident).inner_text() == '—', ident
    assert page.locator('#watch-state').inner_text() == 'CHECK UNAVAILABLE'
    assert 'dated panels above' in page.locator('#watch-detail').inner_text()
    assert 'still work' not in page.locator('#watch-detail').inner_text()
    assert page.locator('#rise-status').inner_text() == 'Unavailable'
    assert page.locator('#flow-chart svg').count() == 0
    assert 'unavailable' in page.locator('#tide-list').inner_text().lower() or 'No upcoming' in page.locator('#tide-list').inner_text()
    assert page.locator('#feed-alert').is_visible()
    axe_runs += audit_state('all-feeds-unavailable')
    screenshot_state('all-feeds-unavailable')
    page.screenshot(path=str(out / 'feeds-unavailable.png'), full_page=True)
    mode['fail'] = False
    mode['direct_fail'] = False
    payload['rain']['properties']['updateTime'] = ISO(-1)
    payload['rain']['properties']['quantitativePrecipitation']['values'][0]['value'] = 5.08
    payload['nwps']['forecast'] = json.loads(json.dumps(original_forecast))

    # Without the reference basin, the page cannot substantiate containment, so
    # it keeps the river but withholds both forecast-rain points and their mean.
    mode['basin_fail'] = True
    basin_page = context.new_page()
    basin_page.route('**/*', route)
    basin_page.goto(URL)
    basin_page.wait_for_function("!document.getElementById('refresh').disabled")
    basin_page.wait_for_function("['Latest retrieved frame','Animating retrieved frames','Unavailable'].includes(document.getElementById('radar-status').textContent)")
    assert basin_page.locator('#radar-overlay .basin-shape').count() == 0
    assert basin_page.locator('#radar-overlay .gauge-marker').count() == 1
    assert 'outline unavailable' in basin_page.locator('#radar-overlay').get_attribute('aria-label').lower()
    assert 'outline is unavailable' in basin_page.locator('#radar-loop').get_attribute('alt').lower()
    assert basin_page.locator('#flow').inner_text() == '101'
    assert basin_page.locator('#rain-total').inner_text() == '—'
    assert basin_page.locator('#radar-overlay .rain-marker').count() == 0
    assert 'shown only after' in basin_page.locator('#rain-note').inner_text().lower()
    assert basin_page.locator('#radar-basin-note').is_visible()
    assert 'forecast-rain points were withheld' in basin_page.locator('#radar-basin-note').inner_text().lower()
    assert 'radar remains independent' in basin_page.locator('#radar-basin-note').inner_text().lower()
    assert basin_page.locator('#forecast-high').inner_text() != '—'
    basin_page.screenshot(path=str(out / 'basin-unavailable.png'), full_page=True)
    if axe_path:
        basin_page.add_script_tag(path=axe_path)
        audit = basin_page.evaluate("async () => await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})")
        assert not audit['violations'], ('basin-unavailable', audit['violations'])
        axe_runs += 1
    mode['basin_fail'] = False
    basin_page.locator('#refresh').click()
    basin_page.wait_for_function("!document.getElementById('refresh').disabled")
    assert basin_page.locator('#radar-overlay .basin-shape').count() == 1
    assert basin_page.locator('#radar-overlay .rain-marker').count() == 2
    assert basin_page.locator('#radar-basin-note').is_hidden()
    assert basin_page.locator('#rain-total').inner_text() == '0.80', basin_page.locator('#source-status').inner_text()
    basin_page.close()

    # A syntactically successful but malformed basin response is also retried.
    mode['basin_malformed_once'] = True
    basin_parse_page = context.new_page()
    basin_parse_page.route('**/*', route)
    basin_parse_page.goto(URL)
    basin_parse_page.wait_for_function("!document.getElementById('refresh').disabled")
    assert basin_parse_page.locator('#radar-overlay .basin-shape').count() == 0
    assert basin_parse_page.locator('#rain-total').inner_text() == '—'
    basin_parse_page.locator('#refresh').click()
    basin_parse_page.wait_for_function("!document.getElementById('refresh').disabled")
    assert basin_parse_page.locator('#radar-overlay .basin-shape').count() == 1
    assert basin_parse_page.locator('#rain-total').inner_text() == '0.80'
    basin_parse_page.close()

    # Device save denial disables only the local record and comparison tools.
    storage_context = browser.new_context(viewport={'width': 390, 'height': 960})
    storage_context.add_init_script("""(() => {
      for (const method of ['getItem','setItem','removeItem']) Object.defineProperty(Storage.prototype, method, {value(){throw new DOMException('blocked','SecurityError')}});
    })()""")
    storage_page = storage_context.new_page()
    storage_page.route('**/*', route)
    storage_page.emulate_media(color_scheme='dark')
    storage_page.goto(URL)
    storage_page.wait_for_function("!document.getElementById('refresh').disabled")
    assert storage_page.locator('#storm-log-count').inner_text() == 'SAVE UNAVAILABLE'
    assert storage_page.locator('#storm-log-save').is_disabled()
    assert storage_page.locator('#flow').inner_text() == '101'
    assert storage_page.locator('#watch-state').inner_text() == 'CHECK UNAVAILABLE'
    assert 'earlier-forecast check is unavailable' in storage_page.locator('#watch-detail').inner_text().lower()
    assert 'browser' not in storage_page.locator('#outlook').inner_text().lower()
    assert 'storage' not in storage_page.locator('#outlook').inner_text().lower()
    storage_page.screenshot(path=str(out / 'storage-unavailable-dark-390.png'), full_page=True)
    if axe_path:
        storage_page.add_script_tag(path=axe_path)
        audit = storage_page.evaluate("async () => await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})")
        assert not audit['violations'], ('storage-unavailable', audit['violations'])
        axe_runs += 1
    storage_context.close()

    malformed_context = browser.new_context(viewport={'width': 390, 'height': 960})
    malformed_context.add_init_script("localStorage.setItem('samish-river-outlook.storm-checks.v1', '{malformed')")
    malformed_page = malformed_context.new_page()
    malformed_page.route('**/*', route)
    malformed_page.goto(URL)
    malformed_page.wait_for_function("!document.getElementById('refresh').disabled")
    assert malformed_page.locator('#storm-log-count').inner_text() == 'SAVE UNAVAILABLE'
    assert 'left unchanged' in malformed_page.locator('#storm-log-status').inner_text()
    assert malformed_page.evaluate("localStorage.getItem('samish-river-outlook.storm-checks.v1')") == '{malformed'
    malformed_page.screenshot(path=str(out / 'storage-malformed-390.png'), full_page=True)
    malformed_context.close()

    motion_page = context.new_page()
    motion_page.route('**/*', route)
    motion_page.emulate_media(reduced_motion='reduce')
    motion_page.goto(URL)
    motion_page.wait_for_function("['Latest retrieved frame','Unavailable'].includes(document.getElementById('radar-status').textContent)")
    assert motion_page.locator('#radar-status').inner_text() == 'Latest retrieved frame'
    assert motion_page.locator('#radar-toggle').inner_text() == 'Play animation'
    motion_page.screenshot(path=str(out / 'reduced-motion.png'), full_page=True)
    motion_page.close()
    assert not errors, errors
    axe_note = f'; {axe_runs} axe-core panel audits' if axe_runs else ''
    print(f'PASS: {result + v7_result} numerical contracts ({result} from version 6 and earlier, {v7_result} for the version 7 river, forecast, tide, rain and look-back rules); '
          f'version 7 page replay of 29 September 2026 with the real NOAA issues ({len(FRAMES)} fixed-clock frames at desktop and phone sizes, every River, NOAA and Tide sentence exact), stalled feed, device clock, first visit, '
          f'phone type sizes, missing-against-zero rain, evidence object against rendered text, banned words and screen-reader announcements; '
          f'live UI fixtures, storage, failure isolation, keyboard, clipboard and 30 responsive/dark panel checks{axe_note}. Screenshots: {out}')
    browser.close()
if SERVER:
    SERVER.shutdown()
    SERVER.server_close()
