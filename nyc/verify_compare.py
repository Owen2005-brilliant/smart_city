"""Check actual browser decisions against the original benchmark at each decision time."""
import argparse,csv,json,os
from pathlib import Path
from playwright.sync_api import sync_playwright
from first_look import load_events

args=argparse.ArgumentParser();args.add_argument('--data-dir',type=Path,default=Path('.'));conf=args.parse_args()
traces,_=load_events(conf.data_dir)
expected={(r['key'],r['policy']):None if r['time']=='' else int(r['time'])*60 for r in csv.DictReader(open('result/decisions.csv')) if r['period']=='main' and r['mode']=='frozen' and r['policy'] in ('2+3','5+3')}
cases=[dict(tide=r['tidal'],p=list(zip(r['t'],r['d'])),answers={k:expected[(r['key'],k)] for k in ('2+3','5+3')},key=r['key']) for r in traces if (r['key'],'2+3') in expected]
assert len(cases)==985
with sync_playwright() as playwright:
    browser=playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE'),headless=True)
    page=browser.new_page(viewport={'width':1240,'height':850},offline=True)
    errors=[];page.on('pageerror',lambda ex:errors.append(str(ex)))
    page.goto(Path('FloodNet-街道积水升级检测器.html').resolve().as_uri()+'#compare')
    assert page.locator('#comparison').is_visible()
    errors_in_scores=page.evaluate('''rows=>{
      const mismatches=[];
      for(const row of rows)for(const [key,answer] of Object.entries(row.answers)){
        for(const t of [0,119,120,299,300,479,480,2100]){
          const expected=answer!==null && answer<=t?answer:null;
          const actual=detectEpisode(row.p,t,row.tide,experiment.models[key]).alarm;
          if(actual!==expected){mismatches.push([row.key,key,t,expected,actual]);break;}
        }
      }
      return mismatches;}''',cases)
    assert not errors_in_scores,errors_in_scores[:5]
    for i,final in [(0,'早判保守提前 6 分钟（及时），晚判保守提前 0 分钟（不足 5 分钟）'),(1,'早判为误报，晚判正确未报')]:
        page.select_option('#compareCase',str(i))
        assert '尚未观测' in page.locator('#compareResult').inner_text()
        page.click('#comparePacket')
        page.click('#compareStep');assert '2:00' in page.locator('#compareTime').inner_text()
        assert '已在 2:00 发警' in page.locator('#compareCards').inner_text()
        page.select_option('#compareView','2+3');assert page.locator('#compareCards section').count()==1
        page.select_option('#compareView','both')
        page.click('#compareEnd');assert final in page.locator('#compareResult').inner_text()
        page.locator('#compareSlider').fill('300');assert '尚未观测' in page.locator('#compareResult').inner_text()
        page.click('#compareReset');assert '0:00' in page.locator('#compareTime').inner_text()
    for nav in ['v0','v1','v2','v3']:page.click('#'+nav)
    page.select_option('#compareCase','0');page.click('#compareEnd')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    browser.close()
print('985 test episodes × 2 policies × 8 prefix times matched. Offline replay, tab switching, rewinding and mobile verified.')
