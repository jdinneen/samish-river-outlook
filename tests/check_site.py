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
            return req.fulfill(status=200, content_type='image/svg+xml', body=body, headers={'Access-Control-Allow-Origin': '*'})
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
      const gp=D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.4,48.5],[-122.2,48.5],[-122.2,48.7],[-122.4,48.7],[-122.4,48.5]]]}});check(Math.abs(gp.lon+122.3)<1e-8&&Math.abs(gp.lat-48.6)<1e-8,'forecast grid centroid');
      check(D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.4,48.5],[-122.2,48.5],[-122.2,48.7],[-122.4,48.7]]]}})===null,'open forecast grid rejected');
      check(D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.4,48.5],[-122.4,48.5],[-122.4,48.5],[-122.4,48.5]]]}})===null,'zero-area forecast grid rejected');
      check(D.gridPoint({geometry:{type:'Polygon',coordinates:[[[-122.5,48.5],[-122.3,48.7],[-122.5,48.7],[-122.4,48.5],[-122.5,48.5]]]}})===null,'self-intersecting forecast grid rejected');
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
    assert page.locator('#radar-overlay .rain-marker text').evaluate_all("els => { const a=els[0].getBoundingClientRect(), b=els[1].getBoundingClientRect(); return a.bottom <= b.top || b.bottom <= a.top || a.right <= b.left || b.right <= a.left; }")
    assert 'valid' in page.locator('#radar-frame-time').inner_text()
    assert page.locator('#ops-flow').inner_text() == '101'
    assert page.locator('#ops-threshold').inner_text().endswith('cfs')
    assert page.locator('#flow-chart').evaluate("el => el.getBoundingClientRect().top < document.getElementById('surprise-watch').getBoundingClientRect().top")
    assert page.locator('#radar-loop').evaluate("el => el.getBoundingClientRect().top < document.getElementById('surprise-watch').getBoundingClientRect().top")
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
    assert page.locator('#watch-state').inner_text() == 'BUILDING HISTORY'
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
    assert page.locator('#update-status').inner_text().startswith('Feed check completed')
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
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER PATH'
    assert 'This is not a risk or safety status' in page.locator('#watch-detail').inner_text()
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
    assert 'SAVED-FORECAST COMPARISON: ABOVE EARLIER PATH' in snapshot_text, repr(snapshot_text[:500])
    assert 'Official commercial status is not ingested' in snapshot_text
    assert 'https://doh.wa.gov/commercialshellfishmap' in snapshot_text

    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot(95))
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'NOT ABOVE COMPARISON LINE'
    assert 'not a risk or safety status' in page.locator('#watch-detail').inner_text()
    axe_runs += audit_state('tracking')
    screenshot_state('tracking')

    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot(250))
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'NOT ABOVE COMPARISON LINE'
    assert 'NEAR' not in page.locator('#watch-state').inner_text()

    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot())
    observed_minus_three = next(row for row in payload['nwps']['observed']['data'] if row['validTime'] == ISO(-3))
    original_minus_three = observed_minus_three['primary']
    observed_minus_three['primary'] = .110
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER PATH'
    assert 'not positive' in page.locator('#watch-title').inner_text()
    axe_runs += audit_state('above-saved-path')
    screenshot_state('above-saved-path')
    observed_minus_three['primary'] = original_minus_three

    # Restore the earlier-path fixture so release screenshots include the neutral
    # comparison state rather than only the first-visit history-building state.
    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot())
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER PATH'
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
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER PATH'
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
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER PATH'
    payload['rain']['properties']['quantitativePrecipitation']['values'][0]['value'] = None
    payload['nwps']['forecast']['data'] = payload['nwps']['forecast']['data'][:4]
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#rain-total').inner_text() == '—'
    assert page.locator('#forecast-status').inner_text() == 'Shorter horizon'
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER PATH'
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
    assert page.locator('#watch-state').inner_text() == 'ABOVE EARLIER PATH'
    mode['fail'] = True
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    page.wait_for_function("document.getElementById('radar-status').textContent === 'Unavailable'")
    failed_radar_alt = page.locator('#radar-loop').get_attribute('alt').lower()
    assert 'radar image unavailable' in failed_radar_alt and 'valid' not in failed_radar_alt
    for ident in ['flow', 'forecast-high', 'rain-total']:
        assert page.locator('#' + ident).inner_text() == '—', ident
    assert page.locator('#watch-state').inner_text() == 'COMPARISON UNAVAILABLE'
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

    # Browser storage denial disables only the local record and comparison tools.
    storage_context = browser.new_context(viewport={'width': 390, 'height': 960})
    storage_context.add_init_script("""(() => {
      for (const method of ['getItem','setItem','removeItem']) Object.defineProperty(Storage.prototype, method, {value(){throw new DOMException('blocked','SecurityError')}});
    })()""")
    storage_page = storage_context.new_page()
    storage_page.route('**/*', route)
    storage_page.emulate_media(color_scheme='dark')
    storage_page.goto(URL)
    storage_page.wait_for_function("!document.getElementById('refresh').disabled")
    assert storage_page.locator('#storm-log-count').inner_text() == 'Storage unavailable'
    assert storage_page.locator('#storm-log-save').is_disabled()
    assert storage_page.locator('#flow').inner_text() == '101'
    assert 'cannot build history until storage works' in storage_page.locator('#watch-detail').inner_text()
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
    assert malformed_page.locator('#storm-log-count').inner_text() == 'Storage unavailable'
    assert 'not overwritten' in malformed_page.locator('#storm-log-status').inner_text()
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
    print(f'PASS: {result} numerical contracts; live UI fixtures, storage, failure isolation, keyboard, clipboard and 30 responsive/dark panel checks{axe_note}. Screenshots: {out}')
    browser.close()
if SERVER:
    SERVER.shutdown()
    SERVER.server_close()
