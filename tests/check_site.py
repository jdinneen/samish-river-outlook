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
    out = Path(tempfile.mkdtemp(prefix='samish-browser-review-'))
    axe_path = os.environ.get('AXE_PATH')
    if os.environ.get('REQUIRE_AXE') == '1' and not axe_path:
        raise RuntimeError('REQUIRE_AXE=1 but AXE_PATH was not supplied')
    axe_runs = 0
    if axe_path:
        page.add_script_tag(path=axe_path)

    def audit_state(label, tabs=('outlook',)):
        if not axe_path:
            return 0
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
      check(screen.usable&&screen.projectedRise===120&&screen.baselineTime<screen.pointTime,'complete rise screen and strict earlier baseline');
      check(screen.threshold.cfs===D.thresholdAt(screen.pointTime).cfs,'candidate-time seasonal rule');
      check(!D.planningScreen(obs.slice(1),future,now).usable,'rise screen requires full 24-hour history');
      check(!D.planningScreen(obs.filter(r=>r.t!==now-12*H),future,now).usable,'rise screen rejects gauge gap');
      check(!D.planningScreen(obs.slice(0,-3),future,now).usable,'rise screen rejects stale gauge');
      check(!D.planningScreen(obs,future.filter(r=>r.t<=now+54*H),now).usable,'rise screen rejects short reach');
      check(!D.planningScreen(obs,future.filter(r=>r.t!==now+30*H),now).usable,'rise screen rejects forecast gap');
      const lowObs=obs.map(r=>({...r,q:10})), falling=Array.from({length:13},(_,i)=>({t:now+i*6*H,q:200-i*20}));
      check(!D.planningScreen(lowObs,falling,now).usable,'rise screen rejects negative aligned flow');
      const changed=D.recentChange([{t:now-3.25*H,q:90},{t:now,q:101}],{t:now,q:101},3);
      check(changed.change===11&&changed.spanHours===3.25,'recent change reports actual span');
      const nearest=D.recentChange([{t:now-3.4*H,q:90},{t:now-2.9*H,q:110},{t:now,q:101}],{t:now,q:101},3);
      check(nearest.change===-9&&Math.abs(nearest.spanHours-2.9)<1e-8,'recent change uses nearest eligible reading');
      const tied=D.recentChange([{t:now-3.5*H,q:90},{t:now-2.5*H,q:110},{t:now,q:101}],{t:now,q:101},3);
      check(tied.change===-9&&tied.spanHours===2.5,'recent change tie uses more recent reading');

      const snapshot=(age=6,value=80,gap=6)=>{
        const start=now-age*H,times=[];
        for(let t=start;t<=now+72*H;t+=gap*H)times.push(t);
        return {issueTime:iso(now+(-age-1)*H),capturedAt:iso(start),gaugeTime:iso(start),gaugeCfs:70,adjustment:-20,
          alignedPath:times.map((t,i)=>({t,q:i?value:70})),rawPath:times.map((t,i)=>({t,q:i?value+20:90}))};
      };
      const observation={t:now,q:101,change3:4,span3:3,fresh:true};
      let watch=D.surpriseWatch(observation,[snapshot()]);
      check(watch.code==='outpacing'&&watch.expected===80&&watch.difference===21&&watch.line===10,'saved path outpacing');
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
    assert page.locator('.measurement-limit').inner_text() == 'Forecast only. Actual basin rain is not measured here.'
    assert page.locator('#flow-chart svg').count() == 1
    assert page.locator('#watch-state').inner_text() == 'LEARNING'
    axe_runs += audit_state('learning')
    screenshot_state('learning')
    assert page.locator('#rise-status').inner_text() == 'Lab screen'
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

    # Bank an older issue exactly as a returning browser would. The current reading
    # is 21 cfs above its saved path and has risen 4 cfs in the measured 3-hour span.
    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot())
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'CHECK — OUTPACING'
    assert 'This is not a risk or safety status' in page.locator('#watch-detail').inner_text()
    assert page.locator('#watch-expected').inner_text() == '80'
    assert page.locator('#watch-observed').inner_text() == '101'
    assert page.locator('#watch-change').inner_text() == '+4'

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
    assert 'SAVED-FORECAST CHECK: CHECK — OUTPACING' in snapshot_text, repr(snapshot_text[:500])
    assert 'Official commercial status is not ingested' in snapshot_text
    assert 'https://doh.wa.gov/commercialshellfishmap' in snapshot_text

    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot(95))
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'BELOW WATCH LINE'
    assert 'not a risk or safety status' in page.locator('#watch-detail').inner_text()
    axe_runs += audit_state('tracking')
    screenshot_state('tracking')

    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot())
    observed_minus_three = next(row for row in payload['nwps']['observed']['data'] if row['validTime'] == ISO(-3))
    original_minus_three = observed_minus_three['primary']
    observed_minus_three['primary'] = .110
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'ABOVE SAVED PATH'
    axe_runs += audit_state('above-saved-path')
    screenshot_state('above-saved-path')
    observed_minus_three['primary'] = original_minus_three

    # Restore the outpacing fixture so release screenshots include the actionably
    # conservative state rather than only the first-visit learning state.
    page.evaluate("value => localStorage.setItem('samish-river-outlook.forecast-snapshots.v1', JSON.stringify([value]))", saved_snapshot())
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#watch-state').inner_text() == 'CHECK — OUTPACING'
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
    assert page.locator('#watch-state').inner_text() == 'CHECK — OUTPACING'
    for scheme in ['light', 'dark']:
        page.emulate_media(color_scheme=scheme)
        for width in [320, 390, 768, 1440]:
            page.set_viewport_size({'width': width, 'height': 960})
            for tab in ['outlook', 'research', 'sources']:
                page.locator('#tab-' + tab).click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (scheme, width, tab, 'overflow')
                if width in [390, 1440]:
                    page.screenshot(path=str(out / f'{scheme}-{tab}-{width}.png'), full_page=True)
    # Preserve NOAA observations when the direct feed fails, and label the source honestly.
    mode['direct_fail'] = True
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#flow').inner_text() == '100'
    assert 'NOAA copy' in page.locator('#observation-note').inner_text()
    assert 'No direct USGS reading' in page.locator('#source-status').inner_text()
    assert page.locator('#watch-state').inner_text() == 'CHECK — OUTPACING'
    payload['rain']['properties']['quantitativePrecipitation']['values'][0]['value'] = None
    payload['nwps']['forecast']['data'] = payload['nwps']['forecast']['data'][:4]
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    assert page.locator('#rain-total').inner_text() == '—'
    assert page.locator('#forecast-status').inner_text() == 'Shorter horizon'
    assert page.locator('#watch-state').inner_text() == 'CHECK — OUTPACING'
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
    assert page.locator('#watch-state').inner_text() == 'CHECK — OUTPACING'
    mode['fail'] = True
    page.locator('#refresh').click()
    page.wait_for_function("!document.getElementById('refresh').disabled")
    for ident in ['flow', 'forecast-high', 'rain-total']:
        assert page.locator('#' + ident).inner_text() == '—', ident
    assert page.locator('#watch-state').inner_text() == 'UNKNOWN'
    assert page.locator('#rise-status').inner_text() == 'Unavailable'
    assert page.locator('#flow-chart svg').count() == 0
    assert 'unavailable' in page.locator('#tide-list').inner_text().lower() or 'No upcoming' in page.locator('#tide-list').inner_text()
    assert page.locator('#feed-alert').is_visible()
    axe_runs += audit_state('all-feeds-unavailable')
    screenshot_state('all-feeds-unavailable')
    page.screenshot(path=str(out / 'feeds-unavailable.png'), full_page=True)
    assert not errors, errors
    axe_note = f'; {axe_runs} axe-core panel audits' if axe_runs else ''
    print(f'PASS: {result} numerical contracts; live UI fixtures, fallback, all-feed failure, keyboard, clipboard and 24 responsive/dark panel checks{axe_note}. Screenshots: {out}')
    browser.close()
if SERVER:
    SERVER.shutdown()
    SERVER.server_close()
