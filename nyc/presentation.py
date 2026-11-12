"""Create an offline classroom replay from frozen non-tidal decisions."""
import base64,io,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

data=json.loads(Path('replay_non_tidal.json').read_text())
results=json.loads(Path('results.json').read_text())['main']
chosen=['SI-cassidy-pl-lafayette-ave-2z1750|2026-08-23T10:09:06','BK-hoyt-st-5th-st-007sk0|2026-07-18T16:16:26','SI-cassidy-pl-lafayette-ave-2z1750|2026-07-06T01:18:54']
def plot(r,minute):
    cut=r['cut']
    fig,ax=plt.subplots(figsize=(8.9,3.5),layout='constrained')
    fig.patch.set_facecolor('#ffffff')
    x=[(t-cut)/60 for t in r['t']]
    pts=[(u,v) for u,v in zip(x,r['depth']) if -5.01<=u<=minute]
    ax.plot(*zip(*pts),color='#075e62',marker='o',ms=4,lw=2)
    ax.axhline(4,color='#9b422d',linestyle='--',lw=1.4)
    ax.text(29.6,4.24,'4 in',ha='right',color='#9b422d')
    for v in [0,3]:
        if minute>=v:ax.axvline(v,color='#73858d',linestyle=':',lw=1)
    if minute<30: ax.axvspan(minute,30,color='#edefee',alpha=.9,zorder=-1)
    ax.set_xlim(-5.5,30.5);ax.set_ylim(-.4,12.9);ax.set_xticks([-5,0,3,10,20,30])
    ax.set_yticks([0,2,4,6,8,10,12])
    ax.grid(axis='y',alpha=.16);ax.spines[['top','right']].set_visible(False)
    for side in ['left','bottom']:ax.spines[side].set_color('#b6bfc0')
    ax.tick_params(colors='#445659',length=3)
    buf=io.BytesIO();fig.savefig(buf,format='png',dpi=120);plt.close(fig)
    return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
cases=[]
for key in chosen:
    r=next(v for v in data if v['key']==key)
    cases.append(dict(site=r['site'],date=key.split('|')[1].replace('T',' '),imgs=[plot(r,m) for m in [0,3,30]],
        slope=r['slope'],wait=r['wait_tail'],defer=r['defer'],band=[round(i,2) for i in r['band']],peak=r['peak'],lead=r['lead'],
        ordinary=[round(i,2) for i in r['ordinary_interval']]))
html="""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>街道积水预警｜课堂回放</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f3ee;font:16px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:#192f33}main{max-width:1060px;margin:auto;padding:28px 28px 60px}header{border-top:5px solid #08676b}h1{font-size:clamp(25px,4vw,44px);letter-spacing:-.04em;line-height:1.2;margin:18px 0 7px}h2{font-size:25px;margin:6px 0}p{margin:6px 0 12px}small{color:#4b6265}button,select{font:inherit;padding:6px 14px;border:1px solid #adbbba;background:white;color:#183235;border-radius:6px;cursor:pointer}button[aria-pressed=true]{background:#0b6265;color:white;border-color:#0b6265}nav, .controls{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:18px 0}article{background:white;border:1px solid #dbe2df;border-radius:12px;padding:20px 25px}img{display:block;width:100%;height:auto}#stage{font-weight:700;color:#075e62}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:12px 0}.cell{border-top:2px solid #acc8c7;padding:8px 0}.cell b{display:block;font-size:21px}.note{background:#eff4f1;padding:12px 16px}.legend{display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{text-align:left;border-bottom:1px solid #dde3e0;padding:8px 5px}footer{margin-top:15px;font-size:13px;color:#4e6162}a{color:#086065}button:focus-visible,select:focus-visible{outline:3px solid #cc8a28}@media(max-width:560px){main{padding:15px 10px}article{padding:12px}.grid{grid-template-columns:1fr}.cell b{font-size:17px}table{font-size:14px}}
</style></head><body><main><header><h1>街道积水告警，值得再等 3 分钟吗？</h1><p>纽约 FloodNet 实测回放 · 未来 30 分钟内达到 4 英寸 · 目标为至少提前 5 分钟</p></header>
<nav aria-label="查看内容"><button id="v0">事件回放</button><button id="v1">全样本与非潮汐站结果</button></nav>
<section id="replay"><div class="controls"><label for="case">非潮汐站案例</label><select id="case"></select></div>
<article><small id="meta"></small><h2 id="site"></h2><div class="controls" id="steps"><button>首次决策</button><button>3 分钟后</button><button>揭晓结果</button></div>
<div class="legend"><span id="stage"></span><small>纵轴为水深（英寸），横轴为距首次决策的分钟数</small></div><img id="plot" alt="随回放阶段逐步显示实际水深，横虚线为四英寸阈值">
<div class="grid"><div class="cell">简单涨速外推<b id="slope"></b></div><div class="cell">按区间决定是否复查<b id="policy"></b></div></div>
<p id="band"></p><p class="note" id="result"></p></article><footer>三个案例分别用于讨论等待的收益、时间成本和误报。采用非潮汐站过去时段选定的固定阈值。图中连线仅辅助读图，评分使用实际观测点。</footer></section>
<section id="summary" hidden><article><h2>每组给各方法相同数量的误报</h2><p>表中为至少提前 5 分钟命中的升级事件数。全样本有 192 次升级，允许 66 次误报；非潮汐站有 67 次升级，允许 26 次误报。</p><table><thead><tr><th>告警策略</th><th>全样本</th><th>非潮汐站</th></tr></thead><tbody id="alarms"></tbody></table>
<h2 style="margin-top:24px">升级事件是否落在预测区间内？</h2><table><thead><tr><th>首次决策时的区间</th><th>全样本</th><th>非潮汐站</th></tr></thead><tbody id="intervals"></tbody></table>
<p class="note" style="margin-top:18px">统一放宽与风险分组在校准期使用相同的平均加宽幅度。非潮汐站有 34/67 次升级在首次决策时已没有可确认的 5 分钟提前量。</p></article><footer>测试期 2026-07-01 至 10-26。统计限于已复核、满足数据质量要求的站点积水事件。相同误报数的回顾性比较用于评价排序能力，事件回放展示冻结阈值的实际决策。</footer></section>
<footer>数据来自 FloodNet（NYU、CUNY）和 NYC DEP。<a href="https://data.cityofnewyork.us/d/aq7i-eu5q">事件数据</a> · <a href="https://data.cityofnewyork.us/d/kb2e-tjy3">部署元数据</a></footer>
</main><script>
const cases=CASES,results=RESULTS;const el=id=>document.getElementById(id);let step=0;
function chooseView(i){el('replay').hidden=!!i;el('summary').hidden=!i;[0,1].forEach(j=>el('v'+j).setAttribute('aria-pressed',j===i))}
function render(){let c=cases[+el('case').value];el('meta').textContent=c.date+' GMT · 官方事件起点';el('site').textContent=c.site;
const steps=['首个湿读数后 5 分钟','首个湿读数后 8 分钟','30 分钟预测窗结束'];el('stage').textContent=steps[step];el('plot').src=c.imgs[step];[...el('steps').children].forEach((b,i)=>b.setAttribute('aria-pressed',i===step));
el('slope').textContent=c.slope===0?'首次决策即告警':'未发出告警';el('policy').textContent=c.wait===0?'首次决策即告警':step===0?(c.defer?'暂缓，等待下一次读数':'未发出告警'):(c.wait===3?'复查时发出告警':'未发出告警');
el('band').textContent='首次决策时，未来窗口最高水深的预测区间为 '+c.band.join(' 至 ')+' 英寸（普通校准为 '+c.ordinary.join(' 至 ')+' 英寸）。';
let outcome=c.lead<0?'本次未升级。':('本次升级。按越线前最后一个低读数，首次决策的保守提前量为 '+c.lead.toFixed(2)+' 分钟。');
if(c.lead>=0 && c.wait===3)outcome+='等 3 分钟后发报，保守提前量为 '+Math.max(0,c.lead-3).toFixed(2)+' 分钟。';
el('result').textContent=step===2?'窗内最高实测 '+c.peak.toFixed(2)+' 英寸。'+outcome:step===0?'此刻你会发出告警，还是再等 3 分钟？':'现在锁定判断，再揭晓 30 分钟内的实测结果。';}
cases.forEach((c,i)=>el('case').add(new Option((i+1)+' · '+c.site+' · '+c.date.slice(5,10),i)));el('case').onchange=()=>{step=0;render()};[...el('steps').children].forEach((b,i)=>b.onclick=()=>{step=i;render()});[0,1].forEach(i=>el('v'+i).onclick=()=>chooseView(i));
function table(id,arr,f){for(const [k,label] of arr){let r=el(id).insertRow();for(const v of [label,f(results.all,k),f(results.non_tidal,k)]) r.insertCell().textContent=v}}
table('alarms',[['slope','单次涨速外推'],['slope_recheck','涨速外推，可复查一次'],['rise_uniform_wait','仅涨速，首次告警要求更高'],['slope_plus_tide','单次涨速加潮汐属性'],['uniform_wait','多特征，两次决策、统一等待规则'],['wait_tail','多特征，两次决策、按风险区间复查']],(g,k)=>{let m=g.policies[k]['0.1'];return m.timely+'/'+m.pos+' ('+(100*m.recall).toFixed(1)+'%)'});
table('intervals',[['global','普通全局校准'],['tail','按风险分组放宽上界'],['uniform_width','统一放宽上界']],(g,k)=>{let m=g.intervals[k];return (100*m.positive).toFixed(1)+'% · 平均宽 '+m.width.toFixed(2)+' 英寸'});chooseView(0);render();
</script></body></html>"""
html=html.replace('CASES',json.dumps(cases)).replace('RESULTS',json.dumps(results))
Path('课堂回放.html').write_text(html,encoding='utf-8')
