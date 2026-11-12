"""Plot two historical examples with the alarms from past-period fixed thresholds."""
import argparse,csv
from pathlib import Path
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from first_look import load_events

p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,default=Path('.'));p.add_argument('--out',type=Path,default=Path('result'));args=p.parse_args()
fontfile=Path('/System/Library/Fonts/Hiragino Sans GB.ttc')
if fontfile.exists():
    font_manager.fontManager.addfont(str(fontfile));mpl.rcParams['font.family']=font_manager.FontProperties(fname=str(fontfile)).get_name()
else:mpl.rcParams['font.sans-serif']=['Noto Sans CJK SC','Microsoft YaHei','SimHei','DejaVu Sans']
mpl.rcParams['axes.unicode_minus']=False
data={r['key']:r for r in load_events(args.data_dir)[0]}
decisions={(r['key'],r['policy']):r['time'] for r in csv.DictReader((args.out/'decisions.csv').open()) if r['mode']=='frozen' and r['period']=='main'}
keys=['Q-188th-st-58th-ave-1zbc0d|2026-07-18T16:30:35','BK-dewitt-ave-williams-ave-215zzc|2026-07-15T22:39:07']
assert [(decisions[k,'2+3'],decisions[k,'5+3']) for k in keys]==[('2','8'),('2','')]
fig,axes=plt.subplots(1,2,figsize=(12.8,5.95))
fig.patch.set_facecolor('#f6f5f0');fig.subplots_adjust(left=.07,right=.967,top=.70,bottom=.24,wspace=.19)
fig.text(.063,.90,'把首判提前 3 分钟：一次及时命中，一次误报',fontsize=25,weight='bold',color='#173638')
fig.text(.065,.81,'非潮汐站真实读数。两套规则均使用历史期锁定的门槛，曲线只用于事后核验。',fontsize=13,color='#486363')
for ax,k,title in zip(axes,keys,['7 月 18 日　Queens · 188th St / 58th Ave','7 月 15 日　Brooklyn · DeWitt Ave / Williams Ave']):
    r=data[k];x=[a/60 for a in r['t']];d=r['d']
    ax.set_facecolor('#fff');ax.plot(x,d,'-o',lw=2,ms=3,color='#1a545c')
    ax.axhline(4,color='#a04530',ls='--',lw=1.4);ax.text(34.8,4.1,'升级阈值',ha='right',fontsize=10,color='#a04530')
    for name,color in [('2+3','#047b64'),('5+3','#8e58a0')]:
        alarm=decisions[k,name]
        if alarm:
            ax.axvline(int(alarm),color=color,ls=':',lw=2)
    ax.set(xlim=(-.3,35.3),ylim=(0,max(5.2,max(d)*1.15)),xlabel='首个湿读数后（分钟）')
    ax.set_title(title,fontsize=13,loc='left',pad=10,color='#173638');ax.spines[['top','right']].set_visible(False)
    ax.grid(axis='y',alpha=.12)
axes[0].set_ylabel('测点水深（英寸）')
fig.text(.068,.104,'第 2 分钟发警可确认提前 6 分钟；第 8 分钟发警已不及时。',fontsize=11.7,color='#173638')
fig.text(.559,.104,'早判策略第 2 分钟发警，窗内峰值仅 2.05 英寸。',fontsize=11.7,color='#173638')
fig.text(.065,.035,'绿竖线：第 2 分钟首判策略的告警时刻。紫竖线：第 5 分钟首判策略的告警时刻。两者均允许 3 分钟后复查。',fontsize=10,color='#486363')
fig.savefig(args.out/'首判实验案例.png',dpi=170);plt.close(fig)
