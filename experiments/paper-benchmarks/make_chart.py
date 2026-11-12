"""Optional presentation figure. Requires matplotlib and a font containing Chinese."""
import argparse
import csv
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

parser=argparse.ArgumentParser()
parser.add_argument('metrics',type=Path)
parser.add_argument('out',type=Path)
parser.add_argument('--font',type=Path,required=True)
args=parser.parse_args()
font=FontProperties(fname=str(args.font))
with args.metrics.open() as f:
    data=[r for r in csv.DictReader(f) if r['period']=='main' and r['mode']=='matched']
labels=[('ours','本项目两阶段规则'),('EFAS_any','EFAS 式 · 任一次达标'),('EFAS_both','EFAS 式 · 连续两次达标'),
        ('TEASER','TEASER · 公开实现适配'),('Taiwan_single_site_proxy','彰化研究 · 单站替代版')]
fig,axes=plt.subplots(1,2,figsize=(10.6,4.15))
fig.subplots_adjust(left=.23,right=.96,bottom=.19,top=.77,wspace=.21)
fig.suptitle('同样的误报数下，有多少升级事件能提前至少 5 分钟报出？',fontproperties=font,fontsize=18,y=.95)
for ax,(group,title) in zip(axes,[('all','全网 · 192 场升级 / 66 次误报'),('non_tidal','非潮汐站 · 67 场升级 / 26 次误报')]):
    rows={r['method']:r for r in data if r['group']==group}
    vals=[int(rows[key]['timely']) for key,_ in labels]
    ax.barh(range(len(vals)),vals,color=['#09675A','#85A6AA','#85A6AA','#5B81AC','#5B81AC'],height=.58)
    ax.set_yticks(range(len(vals)),[name for _,name in labels] if group=='all' else ['']*len(vals),fontproperties=font)
    ax.set_title(title,fontproperties=font,fontsize=13)
    for i,v in enumerate(vals):ax.text(v+max(vals)*.016,i,str(v),va='center',fontsize=11)
    ax.invert_yaxis()
    ax.set_xlim(0,max(vals)*1.16)
    ax.spines[['top','right','left']].set_visible(False)
    ax.tick_params(axis='y',length=0)
    ax.grid(axis='x',alpha=.16)
    ax.set_axisbelow(True)
fig.text(.03,.04,'纽约历史回测，2026 年 7–10 月。数字为及时命中场数；两组分别匹配误报，横轴各自缩放。',fontproperties=font,fontsize=10)
fig.savefig(args.out,dpi=180,facecolor='white')
