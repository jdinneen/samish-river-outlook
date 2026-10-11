"""Browser contract checks with synthetic feeds. Requires QA-only playwright.

Run against a local static server: python tests/check_site.py http://127.0.0.1:8769
Nothing here calls scientific models or modifies provider data.
"""
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8769'
NOW = datetime.now(timezone.utc).replace(microsecond=0)
ISO = lambda h=0: (NOW + timedelta(hours=h)).isoformat()

def fixtures():
    def series(rows):
        return {'primaryName': 'River Discharge', 'primaryUnits': 'kcfs',
                'secondaryName': 'Stage', 'secondaryUnits': 'ft',
                'issuedTime': ISO(-1), 'data': [
                    {'validTime': ISO(h), 'primary': q / 1000, 'secondary': 4}
                    for h, q in rows]}
    return {
        'nwps': {'observed': series([(h, 100 + h) for h in range(-48, 1)]),
                 'forecast': series([(h, 150 - abs(h - 24)) for h in range(-6, 79, 6)])},
        'usgs': {'features': [{'properties': {'monitoring_location_id': 'USGS-12201500',
                 'parameter_code': '00060', 'time': ISO(), 'value': '101', 'unit_of_measure': 'ft^3/s'}}]},
        'rain': {'properties': {'updateTime': ISO(-1), 'quantitativePrecipitation': {
                 'uom': 'wmoUnit:mm', 'values': [{'validTime': ISO(-1) + '/PT30H', 'value': 25.4}]}}},
        'tides': {'predictions': [{'t': (NOW + timedelta(hours=h)).strftime('%Y-%m-%d %H:%M'),
                  'v': str(v), 'type': typ} for h, v, typ in [(2, 8, 'H'), (8, -1, 'L'), (14, 9, 'H'), (20, 1, 'L')]]}}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    payload = fixtures()
    mode = {'fail': False, 'direct_fail': False}

    def route(req):
        u = req.request.url
        if '127.0.0.1' in u or 'localhost' in u:
            return req.continue_()
        if mode['fail'] or mode['direct_fail'] and 'waterdata.usgs.gov' in u:
            return req.fulfill(status=503, body='Unavailable')
        key = 'nwps' if '/nwps/' in u else 'usgs' if 'waterdata.usgs.gov' in u else 'rain' if 'weather.gov' in u else 'tides'
        req.fulfill(status=200, content_type='application/json', body=json.dumps(payload[key]), headers={'Access-Control-Allow-Origin': '*'})

    page.route('**/*', route)
    page.goto(URL)
    page.wait_for_function("!document.getElementById('refresh').disabled")
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
      for(const unit of ['constructor','__proto__']){threw=false;try{D.nwpsSeries({...series,secondaryUnits:unit},now,true)}catch{threw=true}check(threw,'inherited flow units');}
      check(D.nwpsSeries({...series,data:[{validTime:iso(now),secondary:1e308}]},now,true).length===0,'scaled flow overflow');
      const prop={monitoring_location_id:'USGS-12201500',parameter_code:'00060',unit_of_measure:'ft^3/s',time:iso(now),value:'0'};
      check(D.usgs({features:[{properties:prop},{properties:{...prop,value:null}},{properties:{...prop,monitoring_location_id:'other',value:5}}]},now).length===1,'USGS zero null station');
      for(const unit of ['constructor','__proto__'])check(D.usgs({features:[{properties:{...prop,unit_of_measure:unit}}]},now).length===0,'inherited USGS units');
      check(D.duration('PT90M')===1.5*H&&D.duration('P1DT6H')===30*H&&D.duration('PT30S')===30000,'duration units');
      check(D.duration('P')===null&&D.duration('PT')===null&&D.duration('P1DT')===null&&D.duration('oops')===null&&D.duration('P'+'9'.repeat(310)+'D')===null,'malformed duration');
      const makeRain=(values,updated=iso(now-H))=>D.rain({properties:{updateTime:updated,quantitativePrecipitation:{uom:'wmoUnit:mm',values}}},now);
      const native=v=>[{validTime:iso(now-H)+'/PT30H',value:v}];
      for(const uom of ['constructor','__proto__']){threw=false;try{D.rain({properties:{updateTime:iso(now-H),quantitativePrecipitation:{uom,values:native(2)}}},now)}catch{threw=true}check(threw,'inherited rain units');}
      check(Math.abs(D.rainWindow(makeRain(native(30)),now,24).mm-24)<1e-8,'partial interval mass');
      check(D.rainWindow(makeRain(native(0)),now,24).complete,'real zero coverage');
      check(!D.rainWindow(makeRain(native(null)),now,24).complete,'null no coverage');
      check(!D.rainWindow(makeRain([{validTime:iso(now)+'/PT12H',value:0}]),now,24).complete,'partial day');
      threw=false;try{makeRain([...native(2),...native(3)])}catch{threw=true}check(threw,'rain overlap rejected');
      threw=false;try{makeRain(native(2),iso(now+H))}catch{threw=true}check(threw,'future rain clock');
      const rr=[{t:now-H,q:100},{t:now+5*H,q:200},{t:now+11*H,q:100}];
      let f=D.forecast(rr,iso(now-H),now);check(f.usable&&!f.complete&&f.hours===11&&f.max===200,'short actual forecast');
      check(D.interpolate(rr,now+12*H)===null,'no extrapolation');
      check(!D.forecast(rr,iso(now-49*H),now).usable,'wall-clock forecast stale');
      check(!D.forecast(rr,iso(now+H),now).usable,'future forecast issue');
      check(!D.forecast([{t:now-H,q:1},{t:now+8*H,q:2}],iso(now-H),now).usable,'large gap');
      f=D.forecast([{t:now,q:100},{t:now+3*H,q:50},{t:now+6*H,q:100}],iso(now-H),now);check(f.atStart&&f.atEnd&&f.rows[1].q===50,'separated maxima');
      check(D.atBefore([{t:now-H,q:1}],now)===null,'distant baseline');
      const tide=D.tides({predictions:[{t:'2026-11-01 09:30',v:'-1',type:'L'},{t:'bad',v:'4',type:'H'}]});check(tide.length===1&&tide[0].t===Date.parse('2026-11-01T09:30:00Z')&&tide[0].v===-1,'UTC tide and negative height');
      return count;
    }""")
    assert page.locator('#flow').inner_text() == '101'
    assert page.locator('#rain-total').inner_text() == '0.80'
    assert page.locator('#flow-chart svg').count() == 1
    page.locator('#tab-outlook').focus()
    page.keyboard.press('ArrowRight')
    assert page.locator('#research').is_visible()
    page.keyboard.press('End')
    assert page.locator('#sources').is_visible()
    page.keyboard.press('Home')
    assert page.locator('#outlook').is_visible()
    # Force clipboard denial to exercise a useful accessible fallback.
    page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject(Error('denied'))},configurable:true})")
    page.locator('#copy-brief').click()
    assert page.locator('#brief-fallback').is_visible()
    assert 'NOAA issued' in page.locator('#brief-fallback').input_value()
    out = Path(tempfile.mkdtemp(prefix='samish-browser-review-'))
    for scheme in ['light', 'dark']:
        page.emulate_media(color_scheme=scheme)
        for width in [320, 390, 768, 1440]:
            page.set_viewport_size({'width': width, 'height': 960})
            for tab in ['outlook', 'research', 'sources']:
                page.locator('#tab-' + tab).click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (scheme, width, tab, 'overflow')
            page.locator('#tab-outlook').click()
            page.screenshot(path=str(out / f'{scheme}-{width}.png'), full_page=True)
    # Preserve NOAA observations when the direct feed fails, and label the source honestly.
    mode['direct_fail'] = True
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#flow').inner_text() == '100'
    assert 'NOAA copy' in page.locator('#observation-note').inner_text()
    assert 'No direct USGS reading' in page.locator('#source-status').inner_text()
    payload['rain']['properties']['quantitativePrecipitation']['values'][0]['value'] = None
    payload['nwps']['forecast']['data'] = payload['nwps']['forecast']['data'][:4]
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#rain-total').inner_text() == '—'
    assert page.locator('#forecast-status').inner_text() == 'Shorter horizon'
    payload['rain']['properties']['quantitativePrecipitation']['values'][0]['value'] = 0
    payload['rain']['properties']['updateTime'] = ISO(-25)
    payload['nwps']['forecast']['issuedTime'] = ISO(-49)
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#rain-total').inner_text() == '—'
    assert page.locator('#forecast-high').inner_text() == '—'
    assert 'Stale' in page.locator('#rain-points').inner_text()
    mode['fail'] = True
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    for ident in ['flow', 'forecast-high', 'rain-total']:
        assert page.locator('#' + ident).inner_text() == '—', ident
    assert page.locator('#flow-chart svg').count() == 0
    assert 'unavailable' in page.locator('#tide-list').inner_text().lower() or 'No upcoming' in page.locator('#tide-list').inner_text()
    page.screenshot(path=str(out / 'feeds-unavailable.png'), full_page=True)
    assert not errors, errors
    print(f'PASS: {result} numerical contracts; live UI fixtures, fallback, all-feed failure, keyboard, clipboard and 24 responsive/dark panel checks. Screenshots: {out}')
    browser.close()
