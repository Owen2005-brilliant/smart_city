from pathlib import Path
import re
source=Path('课堂回放.html').read_text()
source=source.replace('<title>街道积水预警｜课堂回放</title>','<title>街道积水升级检测器</title>').replace('<nav aria-label="查看内容">','<nav aria-label="查看内容"><button id="v2">运行检测器</button><button id="v3">早判与晚判对照</button>').replace('<button id="v0">事件回放','<button id="v0">前期案例回放').replace('id="v1">全样本与非潮汐站结果','id="v1">前期策略对照')
source=re.sub(r'<h1>.*?</h1>','<h1>街道积水升级检测器</h1>',source,count=1)
source=source.replace('<section id="replay">',Path('panel.html').read_text()+Path('comparison.html').read_text()+'<section id="replay">')
source=source.replace('</style>','canvas{width:100%;height:auto}input{font:inherit;width:6em;padding:6px;border:1px solid #9bb1ae;border-radius:5px}details{margin:16px 0}summary{cursor:pointer}#err{color:#9b422d}button:disabled{opacity:.48}#decisions p{border-left:3px solid #9cbab7;padding-left:12px} #sitedata{font-size:14px}</style>')
source=source.replace('</style>',Path('compare.css').read_text()+'</style>')
source=source.replace('纽约 FloodNet 实测回放 · 未来 30 分钟内达到 4 英寸 · 目标为至少提前 5 分钟','纽约 FloodNet 实测回放 · 观察至首湿后第 35 分钟 · 目标为越线前至少 5 分钟告警')
js=Path('control.js').read_text().replace('EXAMPLES',Path('examples.json').read_text()).replace('MODEL',Path('model.json').read_text())
js+='\n'+Path('compare.js').read_text().replace('COMPARE_DATA',Path('result/compare.json').read_text())
source=source.replace('</body>','<script>'+Path('engine.js').read_text()+js+'</script></body>')
Path('FloodNet-街道积水升级检测器.html').write_text(source)
