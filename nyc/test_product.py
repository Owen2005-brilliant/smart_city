import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE'),headless=True)
    page=b.new_page(viewport={'width':1280,'height':880})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(Path('FloodNet-街道积水升级检测器.html').resolve().as_uri())
    oracle=json.loads(Path('oracle.json').read_text())
    failures=page.evaluate('''rows=>rows.filter(r=>{
      const got=detectEpisode(r.p,480,r.tide,modelData).alarm;
      return (got===null?null:got/60)!==r.alarm;
    }).length''',oracle)
    assert failures==0,failures
    for case in range(3):
        page.select_option('#mode',str(case))
        for button in ['#nextstage','#nextstage','#finish']:page.click(button)
        assert '35:00' in page.locator('#clockText').inner_text()
    page.select_option('#mode','manual')
    for t,d in [(0,.5),(300,1),(480,2)]:
        page.fill('#stamp',str(t));page.fill('#depth',str(d));page.click('#append')
    assert '8:00' in page.locator('#clockText').inner_text()
    page.fill('#stamp','400');page.click('#append');assert page.locator('#err').inner_text()
    page.click('#clearRun');page.fill('#depth','.5');page.click('#append');page.click('#nextstage');assert '读数不足' in page.locator('#signal').inner_text()
    for tab,section in [('v0','replay'),('v1','summary'),('v2','instrument')]:
        page.click('#'+tab);assert page.locator('#'+section).is_visible()
    page.select_option('#mode','0');page.click('#nextstage');page.click('#nextstage')
    page.screenshot(path='product-preview.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors,errors
    print('Browser validation passed for',len(oracle),'event decisions, three replays, manual input, missing data, chronology, tabs and mobile.')
    b.close()
