// A single site and single wet episode. Times are seconds, depths are inches.
// The supplied clock may advance independently of packets. No later readings
// participate in a scheduled decision, even when replay jumps several minutes.
function detectEpisode(readings, now, tidal, model) {
  const wetDepth = 10 / 25.4;
  const seen = readings.filter(([s]) => s <= now);
  const wet = seen.find(([,d]) => d > wetDepth);
  const log = [];
  let alarm = null;
  if (!wet) return {status:'等待积水读数',log,alarm,observed:null};
  const start = wet[0], end = start+2100;
  const active = seen.filter(([t])=>t>=start && t<=end);
  const crossed = active.find(([,d])=>d>=4);
  let status = '积水已检出，收集初始读数';
  const event = (time,state,reason) => log.push({time,state,reason});
  event(start,'检出积水','首个水深超过 10 mm 的读数启动时钟。');
  for (const stage of [0,1]) {
    const at=start+(stage===0?300:480);
    if(now<at || (crossed && crossed[0]<=at)) break;
    const past=active.filter(([s])=>s<=at);
    const last=past[past.length-1];
    if (at-last[0]>180 || last[1]<=wetDepth || (stage===1 && last[0]<=start+300)) {
      status='结束判断：读数不足或积水已退';
      event(at,status,'需要仍湿且最近 3 分钟内的有效观测；复查还需要首次决策之后的新读数。');
      break;
    }
    const elapsed=(last[0]-start)/60;
    const slope=elapsed>0?(last[1]-wet[1])/elapsed:0;
    const horizon=stage===0?30:27;
    const projection=last[1]+horizon*Math.max(0,slope);
    const p=model.params[stage], flag=Number(tidal);
    const trigger=(model.cutoffs[flag]-p.bias-p.tide*flag)/p.depth;
    const fires=projection>=trigger;
    status=fires?'发出升级预警':stage===0?'暂缓，3 分钟后复查':'结束判断：未触发预警';
    event(at,status,'平均涨速 '+slope.toFixed(2)+' 英寸/分，按正涨速外推 '+horizon+' 分钟得 '+projection.toFixed(2)+' 英寸，本阶段评分等价的外推触发线为 '+trigger.toFixed(2)+' 英寸。');
    if(fires){alarm=at;break;}
  }
  if(crossed){
    let message='实测水深 '+crossed[1].toFixed(2)+' 英寸。';
    if(alarm!==null){
      const prior=active[active.indexOf(crossed)-1];
      const seconds=prior?Math.max(0,prior[0]-alarm):0;
      message+='按越线前最后一个低读数，可确认提前 '+(seconds/60).toFixed(2)+' 分钟，'+(seconds>=300?'达到':'未达到')+' 5 分钟目标。';
    }
    event(crossed[0],'已实测达到 4 英寸',message);
    status=alarm===null?'已实测越线，未提前告警':'预警后已实测越线';
  } else if(now>=end) {
    status=alarm===null?'观察窗结束':'观察窗结束，曾发出预警';
  }
  return {status,log,alarm,observed:crossed?crossed[0]:null};
}
