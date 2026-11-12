const experiment = COMPARE_DATA;
const compareKeys = ['2+3','5+3'];
const palette = {'2+3':'#08735f','5+3':'#875299'};
const milestones = [120,300,480,720,2100];
let compareSeconds=0;

function currentComparison(){
  return experiment.cases[Number(get('compareCase').value)];
}
function selectedKeys(){
  const selected=get('compareView').value;
  return selected==='both'?compareKeys:[selected];
}
function drawComparisonChart(visible,states,keys) {
  const canvas=get('comparePlot');
  const bounds=canvas.getBoundingClientRect();
  if(!bounds.width || !bounds.height)return;
  const width=bounds.width,height=bounds.height,dpr=window.devicePixelRatio||1;
  canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
  const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);
  const left=34,right=width-24,top=14,bottom=height-29;
  const maxDepth=Math.max(5,Math.ceil(Math.max(...visible.map(p=>p[1]),0)/2)*2+1);
  const x=t=>left+(right-left)*t/2100;
  const y=d=>bottom-(bottom-top)*d/maxDepth;
  function line(x1,y1,x2,y2,color,dash=[]){
    ctx.beginPath();ctx.setLineDash(dash);ctx.strokeStyle=color;ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();ctx.setLineDash([]);
  }
  ctx.font='12px sans-serif';ctx.lineWidth=1;
  ctx.fillStyle='#eff2ee';ctx.fillRect(x(compareSeconds),top,right-x(compareSeconds),bottom-top);
  line(left,top,left,bottom,'#99adab');line(left,bottom,right,bottom,'#99adab');
  ctx.fillStyle='#4c6465';ctx.textAlign='right';ctx.fillText('0',left-8,bottom+3);ctx.fillText('4',left-8,y(4)+4);
  ctx.textAlign='left';ctx.fillText('英寸',0,top);
  for (let tick=8;tick<maxDepth;tick+=4) {
    line(left,y(tick),right,y(tick),'#d8e0dc',[2,4]);ctx.textAlign='right';
    ctx.fillStyle='#4c6465';ctx.fillText(String(tick),left-8,y(tick)+4);
  }
  line(left,y(4),right,y(4),'#a64d30',[5,4]);
  ctx.fillStyle='#a64d30';ctx.textAlign='right';ctx.fillText('升级阈值',right-4,y(4)-5);
  ctx.textAlign='center';ctx.fillStyle='#4c6465';
  for(const m of [0,5,10,20,35])ctx.fillText(m===35?'35 分':String(m),x(m*60),bottom+19);
  ctx.lineWidth=2;ctx.strokeStyle='#193f45';ctx.beginPath();
  visible.forEach(([t,d],i)=>i?ctx.lineTo(x(t),y(d)):ctx.moveTo(x(t),y(d)));ctx.stroke();
  ctx.fillStyle='#193f45';for(const [t,d] of visible){ctx.beginPath();ctx.arc(x(t),y(d),2.6,0,2*Math.PI);ctx.fill();}
  for(const [i,key] of keys.entries()){
    const alarm=states[key].alarm;
    if(alarm===null)continue;
    const same=keys.length===2 && states[keys[0]].alarm===states[keys[1]].alarm;
    const xx=x(alarm)+(same?(i===0?-1.5:1.5):0);
    line(xx,top,xx,bottom,palette[key],i===0?[3,2]:[7,3]);
    ctx.textAlign='left';ctx.fillStyle=palette[key];ctx.fillText((key==='2+3'?'早判':'晚判')+'发警',xx+3,top+10+(same?i*16:0));
  }
}
function comparisonCard(key,state){
  const first=experiment.models[key].schedule[0];
  const panel=document.createElement('section');panel.style.setProperty('--tone',palette[key]);
  const title=document.createElement('h3');title.textContent='第 '+first+' 分钟首判 · 第 '+(first+3)+' 分钟可复查';
  const status=document.createElement('strong');
  status.textContent=state.alarm!==null?'已在 '+timeMark(state.alarm)+' 发警':state.status;
  panel.append(title,status);
  const decisions=state.log.filter(e=>e.state!=='检出积水' && e.state!=='已实测达到 4 英寸');
  if(!decisions.length){
    const p=document.createElement('p');p.textContent=state.observed===null?'尚未到达本策略的首次决策时刻。':'实测已越线，提前告警机会已结束。';panel.append(p);
  }
  for(const e of decisions){
    const text=document.createElement('p');text.textContent=timeMark(e.time)+'　'+e.state+'。'+e.reason;panel.append(text);
  }
  return panel;
}
function renderComparison(){
  const row=currentComparison(),keys=selectedKeys();
  const visible=row.points.filter(([t])=>t<=compareSeconds);
  const states=Object.fromEntries(keys.map(k=>[k,detectEpisode(visible,compareSeconds,row.tidal,experiment.models[k])]));
  const clock=timeMark(compareSeconds),last=visible.at(-1);
  get('compareSlider').value=compareSeconds;get('compareSlider').setAttribute('aria-valuetext',clock);
  get('compareTime').textContent='首湿后 '+clock;
  get('compareLatest').textContent='非潮汐站 · 最近读数 '+last[1].toFixed(2)+' 英寸（'+timeMark(last[0])+'）';
  get('compareCards').replaceChildren(...keys.map(k=>comparisonCard(k,states[k])));
  drawComparisonChart(visible,states,keys);
  const step=milestones.find(t=>t>compareSeconds);
  get('compareStep').disabled=step===undefined;
  get('compareStep').textContent=step===undefined?'已到窗末':'推进到第 '+step/60+' 分钟';
  get('compareEnd').disabled=compareSeconds===2100;get('compareReset').disabled=!compareSeconds;
  get('comparePacket').disabled=!row.points.some(([t])=>t>compareSeconds);
  const crossing=visible.findIndex(([,d])=>d>=4);
  const outcome=get('compareResult');
  if(crossing>=0){
    const low=visible[Math.max(0,crossing-1)][0];
    const scores=keys.map(k=>{
      const alarm=states[k].alarm;
      const name=k==='2+3'?'早判':'晚判';
      if(alarm===null)return name+'未提前告警';
      const lead=Math.max(0,low-alarm);
      return name+'保守提前 '+Number((lead/60).toFixed(2))+' 分钟（'+(lead>=300?'及时':'不足 5 分钟')+'）';
    });
    outcome.textContent='首次实测越线 '+timeMark(visible[crossing][0])+'。'+scores.join('，')+'。';
  } else if(compareSeconds===2100){
    outcome.textContent='观察窗内最高实测 '+Math.max(...visible.map(p=>p[1])).toFixed(2)+' 英寸，未升级。'+keys.map(k=>(k==='2+3'?'早判':'晚判')+(states[k].alarm===null?'正确未报':'为误报')).join('，')+'。';
  }else{
    outcome.textContent='截至 '+clock+' 尚未观测到 4 英寸。灰色区域为尚未揭晓的时间。';
  }
}
function advanceComparison(to){
  compareSeconds=Math.max(0,Math.min(2100,to));renderComparison();
}
experiment.cases.forEach((r,i)=>get('compareCase').add(new Option(r.date.slice(5)+' · '+r.site,i)));
get('compareCase').onchange=()=>advanceComparison(0);
get('compareView').onchange=renderComparison;
get('compareSlider').oninput=e=>advanceComparison(Number(e.target.value));
get('compareStep').onclick=()=>advanceComparison(milestones.find(t=>t>compareSeconds)??2100);
get('comparePacket').onclick=()=>{
  const next=currentComparison().points.find(([t])=>t>compareSeconds);
  if(next)advanceComparison(next[0]);
};
get('compareReset').onclick=()=>advanceComparison(0);
get('compareEnd').onclick=()=>advanceComparison(2100);
get('v3').onclick=()=>{selectTab('comparison');renderComparison();};
new ResizeObserver(()=>{if(!get('comparison').hidden)renderComparison();}).observe(get('comparePlot'));
renderComparison();
