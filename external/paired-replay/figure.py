from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from run import load

font=FontProperties(fname='/System/Library/Fonts/STHeiti Medium.ttc')
cases=[(Path('inputs'),'2021-08-07T13:59:23','屏东林边邮局','两版均在第 8 分钟报，保守提前量 3 分 19 秒'),
       (Path('extension'),'2023-08-04T01:29:11','兴桐村福天宫','第 8 分钟复查报中，保守提前量 11 分 09 秒')]
fig,axes=plt.subplots(1,2,figsize=(10.4,4.25),sharey=True)
fig.subplots_adjust(left=.075,right=.98,bottom=.23,top=.72,wspace=.15)
fig.suptitle('同样等三分钟，结果可以不同',fontproperties=font,fontsize=18,y=.97)
for ax,(path,start,name,subtitle) in zip(axes,cases):
    e=next(e for e in load(path,'TW',False).values() if e['start']==start)
    pts=[(t/60,d) for t,d in e['points'] if t<=max(e['cross']+90,900)]
    mins,depths=zip(*pts)
    ax.plot(mins,depths,'o--',ms=5,color='#17685e',lw=1.4)
    ax.axhline(10.16,color='#bb553b',ls=':',lw=1.3)
    for at in [5,8]:ax.axvline(at,color='#777777',ls=':',lw=1)
    ax.set_xlim(0,max(mins)+1)
    ax.set_ylim(0,max(16,max(depths)+1))
    ax.set_title(name+' · '+start[:10]+'\n'+subtitle,fontproperties=font,fontsize=11)
    ax.set_xlabel('首湿后经过的分钟',fontproperties=font)
    ax.spines[['right','top']].set_visible(False)
axes[0].set_ylabel('实测水深（厘米）',fontproperties=font)
fig.text(.08,.045,'圆点为实测；虚线连接仅供读图。竖线为第 5、8 分钟，水平线为升级阈值 10.16 厘米。提前量计到首次越线前最后一个低读数。',fontproperties=font,fontsize=9)
fig.savefig('cases.png',dpi=180)
