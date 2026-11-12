const demoExamples=EXAMPLES, modelData=MODEL;
const get=id=>document.getElementById(id);
let input=[],clockSec=0,manual=false,current=0;
function timeMark(s){return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}
function graph(points,now){
  const ctx=get('chart').getContext('2d'),W=1000,H=220;
  ctx.clearRect(0,0,W,H);ctx.font='18px sans-serif';ctx.lineWidth=2;
  const xmax=Math.max(480,now),ymax=Math.max(5,...points.map(p=>p[1]+.5));
  const x=t=>54+(W-78)*t/xmax,y=d=>H-32-(H-53)*d/ymax;
  ctx.strokeStyle='#d5deda';ctx.beginPath();ctx.moveTo(54,14);ctx.lineTo(54,H-32);ctx.lineTo(W-20,H-32);ctx.stroke();
  ctx.fillStyle='#4d6464';ctx.fillText('0',22,H-26);ctx.fillText('0 分',54,H-5);ctx.fillText((xmax/60).toFixed(1)+' 分',W-87,H-5);
  ctx.strokeStyle='#a45336';ctx.setLineDash([7,5]);ctx.beginPath();ctx.moveTo(54,y(4));ctx.lineTo(W-20,y(4));ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#94442d';ctx.fillText('4 in',5,y(4)+5);
  ctx.strokeStyle='#146769';ctx.fillStyle='#146769';ctx.beginPath();
  points.forEach(([t,d],i)=>i?ctx.lineTo(x(t),y(d)):ctx.moveTo(x(t),y(d)));ctx.stroke();
  for(const [t,d] of points){ctx.beginPath();ctx.arc(x(t),y(d),3,0,2*Math.PI);ctx.fill();}
}
function draw(){
  const ex=demoExamples[current];
  const pts=manual?input:ex.points.filter(([t])=>t<=clockSec);
  const tidal=manual?get('tide').value==='1':ex.tide;
  const state=detectEpisode(pts,clockSec,tidal,modelData);
  const latest=pts.at(-1);get('clockText').textContent=timeMark(clockSec);
  get('signal').textContent=state.status;get('sampleInfo').textContent=latest?'已接收 '+pts.length+' 条读数 · 最近一次 '+timeMark(latest[0])+'，水深 '+latest[1].toFixed(2)+' 英寸。':'尚未录入读数。';
  get('sitedata').textContent=manual?'单站输入 · 时间从 0 秒起算':ex.date+' · '+(tidal?'潮汐影响站':'非潮汐站');
  get('custom').hidden=!manual;get('packet').hidden=manual;get('finish').hidden=manual;
  get('tide').disabled=input.length>0;
  const wet=pts.find(p=>p[1]>10/25.4),start=wet?wet[0]:null;
  get('nextstage').hidden=!manual && start!==null && clockSec>=start+480;
  get('nextstage').disabled=start===null||clockSec>=start+2100;
  get('nextstage').textContent=start!==null && clockSec>=start+480?'推进到观察窗结束':'推进到下一决策时刻';
  get('packet').disabled=!manual && !ex.points.some(p=>p[0]>clockSec);
  get('finish').disabled=clockSec>=2100;
  get('decisions').replaceChildren();
  for(const e of state.log){let p=document.createElement('p');let b=document.createElement('strong');b.textContent=timeMark(e.time)+'　'+e.state+'　';p.append(b,e.reason);get('decisions').append(p);}
  if(!state.log.length)get('decisions').textContent='首个超过 10 mm 的读数将启动判断。';
  graph(pts,clockSec);
}
function reset(){input=[];clockSec=0;get('stamp').value='0';get('err').textContent='';draw();}
demoExamples.forEach((x,i)=>get('mode').add(new Option(x.site+' · '+x.date.slice(5),i)));
get('mode').add(new Option('自填观测数据','manual'));
get('mode').onchange=()=>{manual=get('mode').value==='manual';current=manual?0:Number(get('mode').value);reset();};
get('packet').onclick=()=>{const row=demoExamples[current].points.find(p=>p[0]>clockSec);if(row){clockSec=row[0];draw();}};
get('nextstage').onclick=()=>{const pts=manual?input:demoExamples[current].points.filter(p=>p[0]<=clockSec);
 const start=pts.find(p=>p[1]>10/25.4)[0];clockSec=[300,480,2100].map(k=>k+start).find(k=>k>clockSec);get('stamp').value=clockSec+60;draw();};
get('finish').onclick=()=>{clockSec=2100;draw();};get('clearRun').onclick=reset;get('tide').onchange=draw;
get('append').onclick=()=>{const t=get('stamp').valueAsNumber,d=get('depth').valueAsNumber;const wet=input.find(p=>p[1]>10/25.4);
 if(!Number.isSafeInteger(t)||t<0||!Number.isFinite(d)||d<0||(input.length && t<=clockSec)||(wet && t>wet[0]+2100)){get('err').textContent='请输入非负水深和递增的整数秒数，且时间在本次观察窗内。';return;}
 input.push([t,d]);clockSec=t;get('stamp').value=t+60;get('err').textContent='';draw();};
get('validation').textContent=Object.entries(modelData.stats).map(([k,m])=>k+'共 '+m.n+' 场，升级 '+m.pos+' 场，至少提前 5 分钟捕获 '+m.timely+' 场，未升级事件中误报 '+m.fp+' 场。').join(' ');
function selectTab(id){['instrument','replay','summary'].forEach((n,i)=>{get(n).hidden=id!==n;get(['v2','v0','v1'][i]).setAttribute('aria-pressed',id===n);});}
get('v2').onclick=()=>selectTab('instrument');get('v0').onclick=()=>selectTab('replay');get('v1').onclick=()=>selectTab('summary');selectTab('instrument');reset();
