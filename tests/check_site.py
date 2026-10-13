"""Browser and numerical contract checks with synthetic feeds.

Run with its built-in local server: python tests/check_site.py
An explicit local URL remains supported as the first argument.
Nothing here calls scientific models or modifies provider data.
"""
import json
import os
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

def fixtures():
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
{NOW.strftime('%H%M %p %a %b %d %Y')}

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
        'tides': {'predictions': [{'t': (NOW + timedelta(hours=h)).strftime('%Y-%m-%d %H:%M'),
                  'v': str(v), 'type': typ} for h, v, typ in [(2, 8, 'H'), (8, -1, 'L'), (14, 9, 'H'), (20, 1, 'L')]]}}

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

    def route(req):
        u = req.request.url
        if '127.0.0.1' in u or 'localhost' in u:
            return req.continue_()
        parsed = urlparse(u)
        query = {key.lower(): value for key, value in parse_qs(parsed.query).items()}
        if 'opengeo.ncep.noaa.gov/geoserver/katx/ows' in u:
            request = query.get('request', [''])[0].lower()
            if mode['fail'] or mode['radar_fail']:
                return req.fulfill(status=503, body='Radar unavailable')
            if request == 'getcapabilities':
                return req.fulfill(status=200, content_type='application/xml', body=payload['capabilities'], headers={'Access-Control-Allow-Origin': '*'})
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
            return req.fulfill(status=200, content_type='application/json', body=json.dumps(payload['basin']), headers={'Access-Control-Allow-Origin': '*'})
        if 'api.weather.gov/products/types/RRM/locations/SEW' in u:
            if mode['fail'] or mode['rrm_fail']:
                return req.fulfill(status=503, body='Rain report unavailable')
            return req.fulfill(status=200, content_type='application/json', body=json.dumps(payload['rrm_index']), headers={'Access-Control-Allow-Origin': '*'})
        if 'api.weather.gov/products/123e4567-e89b-42d3-a456-426614174000' in u:
            if mode['fail'] or mode['rrm_fail']:
                return req.fulfill(status=503, body='Rain report unavailable')
            return req.fulfill(status=200, content_type='application/json', body=json.dumps(payload['rrm']), headers={'Access-Control-Allow-Origin': '*'})
        if mode['fail'] or mode['direct_fail'] and 'waterdata.usgs.gov' in u:
            return req.fulfill(status=503, body='Unavailable')
        if 'api.weather.gov/gridpoints/' in u and mode['grid_geometry_fail']:
            bad_grid = json.loads(json.dumps(payload['rain']))
            bad_grid.pop('geometry', None)
            return req.fulfill(status=200, content_type='application/json', body=json.dumps(bad_grid), headers={'Access-Control-Allow-Origin': '*'})
        if 'api.weather.gov/gridpoints/SEW/139,116' in u and mode['grid_outside_basin']:
            bad_grid = json.loads(json.dumps(payload['rain']))
            bad_grid['geometry'] = {'type': 'Polygon', 'coordinates': [[[-122.13, 48.58], [-122.09, 48.58], [-122.09, 48.61], [-122.13, 48.61], [-122.13, 48.58]]]}
            return req.fulfill(status=200, content_type='application/json', body=json.dumps(bad_grid), headers={'Access-Control-Allow-Origin': '*'})
        key = 'nwps' if '/nwps/' in u else 'usgs' if 'waterdata.usgs.gov' in u else 'rain' if 'api.weather.gov/gridpoints/' in u else 'tides'
        req.fulfill(status=200, content_type='application/json', body=json.dumps(payload[key]), headers={'Access-Control-Allow-Origin': '*'})

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

    def audit_state(label, tabs=('outlook',)):
        if not axe_path:
            return 0
        if not page.evaluate("typeof axe !== 'undefined'"):
            page.add_script_tag(path=axe_path)
        runs = 0
        for scheme in ['light', 'dark']:
            page.emulate_media(color_scheme=scheme)
            page.wait_for_timeout(250)
            for tab in tabs:
                page.locator('#tab-' + tab).click()
                audit = page.evaluate("""async () => await axe.run(document, {
                    runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']}
                })""")
                assert not audit['violations'], {
                    'state': label, 'scheme': scheme, 'tab': tab,
                    'violations': [(v['id'], v['impact'], [(n['target'], n['failureSummary']) for n in v['nodes']]) for v in audit['violations']]
                }
                runs += 1
        page.locator('#tab-outlook').click()
        return runs

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
      check(R.freshMinutes===90&&R.pauseMinutes===60&&R.peakMinutes===120&&R.fallingFraction===0.05&&R.risingCfs===2&&R.risingFraction===0.02&&R.riseMemoryHours===48&&R.lastHourToleranceMinutes===20&&R.maxGapMinutes===60,'river rule constants');
      check(Object.isFrozen(R)&&Object.keys(R).length===9,'river rule constants are one frozen object');
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
      s=D.riverState([...quiet,{t:T+30*M,q:999},{t:T-7*M,q:'oops'},{t:'x',q:5}],T);check(s.reading.t===T&&s.reading.q===50,'future-dated and malformed rows are ignored');

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
      check(s.riseStatus==='in-progress'&&s.riseStart.atOrBefore===true&&s.riseStart.t===T-6*H&&s.high.t===T-6*H&&s.state==='may-have-peaked','a rise older than the readable history is flagged at-or-before');

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

      // NOAA's current issue against the gauge. This NOAA path is INVENTED: six-hourly values that never show
      // the rise (91 cfs at 11 AM Pacific, then falling), issued 8:14 AM Pacific. Only its arithmetic is tested.
      const noaaPath=[['2026-09-29T06:00:00Z',17],['2026-09-29T12:00:00Z',26],['2026-09-29T18:00:00Z',91],['2026-09-30T00:00:00Z',78],['2026-09-30T06:00:00Z',61],['2026-09-30T12:00:00Z',49],['2026-09-30T18:00:00Z',42],['2026-10-01T00:00:00Z',37],['2026-10-01T06:00:00Z',33],['2026-10-01T12:00:00Z',30],['2026-10-01T18:00:00Z',28],['2026-10-02T00:00:00Z',26],['2026-10-02T06:00:00Z',25],['2026-10-02T12:00:00Z',24],['2026-10-02T18:00:00Z',23]].map(([t,q])=>({t:at(t),q}));
      const noaaIssue='2026-09-29T15:14:00Z';
      const against=(clock,delay=20)=>D.noaaAgainstGauge(frame(clock,delay),noaaPath,noaaIssue,P(clock)+delay*M);
      let n=against('19:00');
      check(n.code==='not-tracking'&&n.notTracking&&n.reason===null&&n.gaugeCfs===181&&n.readingTime===P('19:00')&&near(n.forecastCfs,78-17/3)&&near(n.difference,181-(78-17/3))&&n.line===10&&n.threshold.cfs===100&&n.aboveLine===true&&n.riseInProgress===true,'7:00 PM: gauge 181 against NOAA 72.3 for that time, not tracking');
      check(n.issued===at(noaaIssue)&&n.issueAgeMinutes===666&&n.pathOnlyFalls===true,'NOAA issue age and a path that only falls from the check time');
      check(D.noaaAgainstGauge(frame('19:00',20),noaaPath,at(noaaIssue),P('19:00')+20*M).code==='not-tracking','issue time accepted as epoch milliseconds');
      n=against('12:00');check(n.code==='not-tracking'&&near(n.forecastCfs,91-13/6)&&n.pathOnlyFalls===true,'12:00 PM: not tracking from the reading that passed the number');
      n=against('11:15');check(n.code==='above-line'&&!n.notTracking&&n.aboveLine===true&&n.riseInProgress===false&&n.difference>10,'11:15 AM: above NOAA by the line, but the measured rise has not passed the number');
      n=against('11:00');check(n.code==='within-line'&&n.aboveLine===false&&near(n.difference,6.5)&&!n.notTracking,'11:00 AM: 6.5 cfs above NOAA is inside the 10 cfs line');
      n=against('10:00');check(n.code==='within-line'&&n.difference<0&&n.pathOnlyFalls===false,'10:00 AM: gauge under NOAA, and the path still rises');
      const flat=(value,from=-12)=>Array.from({length:16},(_,i)=>({t:T+(from+i*6)*H,q:value}));
      n=D.noaaAgainstGauge(D.riverState(climb(0),T+20*M),flat(100),iso(T-7*H+20*M),T+20*M);
      check(n.code==='not-tracking'&&n.issueAgeMinutes===420&&n.forecastCfs===100&&n.difference===100&&n.pathOnlyFalls===false,'first visit: a 7-hour-old issue and the gauge at twice its value');
      check(D.noaaAgainstGauge(D.riverState(climb(0),T),flat(190),iso(T-H),T).code==='not-tracking','exactly at the 10% line counts as above it');
      check(D.noaaAgainstGauge(D.riverState(climb(0),T),flat(190.5),iso(T-H),T).code==='within-line','just under the 10% line is within it');
      n=D.noaaAgainstGauge(D.riverState(quiet,T),flat(30),iso(T-H),T);check(n.code==='above-line'&&!n.notTracking&&n.difference===20&&n.riseInProgress===false,'above NOAA with no rise in progress is not "not tracking"');
      n=D.noaaAgainstGauge(D.riverState(climb(0),T+110*M),flat(100),iso(T-H),T+110*M);
      check(n.code==='unknown'&&!n.notTracking&&n.aboveLine===true&&n.riseInProgress===null&&typeof n.reason==='string'&&n.difference===100,'gauge feed late: the comparison is stated but the code is unknown');
      n=D.noaaAgainstGauge(D.riverState(climb(0),T),flat(100,1),iso(T-H),T);check(n.code==='unknown'&&n.forecastCfs===null&&n.difference===null&&n.aboveLine===null&&n.gaugeCfs===200&&n.pathOnlyFalls===false&&typeof n.reason==='string','no value is invented before the first point of the NOAA path');
      n=D.noaaAgainstGauge(D.riverState(climb(0),T),[{t:T-8*H,q:100},...flat(100,1)],iso(T-H),T);check(n.forecastCfs===null&&n.code==='unknown','no value across forecast points more than 6 hours apart');
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
      for(const key of ['pause','peak2h','falling','timing','wait','aligned','noaaDry','rainContext']){const entry=E[key];check(typeof entry.period==='string'&&entry.period.length>3&&typeof entry.source==='string'&&entry.source.startsWith('Look-back')&&entry.source.length>60&&!['/',String.fromCharCode(92),'.txt','.py','.md','.json','C:'].some(piece=>entry.source.includes(piece)),'evidence entry names its look-back in plain words: '+key);}
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
    assert page.locator('#ops-flow').inner_text() == '101'
    assert page.locator('#ops-threshold').inner_text().endswith('cfs')
    assert page.locator('#flow-chart').evaluate("el => el.getBoundingClientRect().top < document.getElementById('surprise-watch').getBoundingClientRect().top")
    assert page.locator('#radar-loop').evaluate("el => el.getBoundingClientRect().top < document.getElementById('surprise-watch').getBoundingClientRect().top")
    assert page.locator('#rise-title').inner_text().startswith('Largest relative rise:')
    assert 'largest rise relative to the seasonal reference' in page.locator('#rise-detail').inner_text().lower()
    assert page.locator('#saved-path-legend').is_hidden()
    assert page.locator('#flow-chart path[stroke="var(--saved)"]').count() == 0
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
    assert page.locator('#gauge-status').inner_text() == 'Stale observation'
    assert page.locator('#change3').inner_text() == 'Unavailable'
    assert page.locator('#change24').inner_text() == 'Unavailable'
    assert page.locator('#ops-change').inner_text() == 'Unavailable'
    payload['nwps']['observed'] = original_observed
    payload['usgs']['features'][0]['properties']['time'] = original_usgs_time
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#gauge-status').inner_text() == 'Recent observation'
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
        closure_link = page.locator('.official-rail .button-link')
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
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER FORECAST'
    assert 'not rising now' in page.locator('#watch-title').inner_text()
    axe_runs += audit_state('above-saved-path')
    screenshot_state('above-saved-path')
    observed_minus_three['primary'] = original_minus_three

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
                    assert page.locator('#ops-strip, .ops-strip').first.evaluate('el => el.getBoundingClientRect().top < 650')
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
    print(f'PASS: {result + v7_result} numerical contracts ({result} from version 6 and earlier, {v7_result} for the version 7 river, forecast, tide, rain and look-back rules); live UI fixtures, storage, failure isolation, keyboard, clipboard and 30 responsive/dark panel checks{axe_note}. Screenshots: {out}')
    browser.close()
if SERVER:
    SERVER.shutdown()
    SERVER.server_close()
