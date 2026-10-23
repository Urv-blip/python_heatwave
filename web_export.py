"""web_export.py - builds website/index.html (interactive, Apple-style) from SQLite.
Run:  python web_export.py   then open website/index.html in a browser.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import database as db
import live_data
import predictor as pr

OUT = Path(__file__).with_name("website") / "index.html"

TEMPLATE = r'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Heatwave Guard</title>
<style>
:root{--bg:#f5f5f7;--card:#fff;--ink:#1d1d1f;--mute:#6e6e73;--line:#d2d2d7;--blue:#0071e3;--shadow:0 4px 24px rgba(0,0,0,.06)}
@media(prefers-color-scheme:dark){:root{--bg:#000;--card:#1c1c1e;--ink:#f5f5f7;--mute:#98989d;--line:#38383a;--blue:#2997ff;--shadow:none}}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
nav{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:18px;padding:12px 5vw;background:color-mix(in srgb,var(--bg) 78%,transparent);backdrop-filter:saturate(180%) blur(20px);-webkit-backdrop-filter:saturate(180%) blur(20px);border-bottom:1px solid var(--line)}
.logo{font-weight:600;white-space:nowrap}.seg{display:flex;gap:2px;padding:3px;border-radius:10px;background:color-mix(in srgb,var(--mute) 18%,transparent);overflow-x:auto;margin-left:auto}
.seg button{border:0;background:none;color:var(--ink);font:500 13px inherit;font-family:inherit;padding:7px 14px;border-radius:8px;cursor:pointer;white-space:nowrap;transition:.2s}
.seg button.on{background:var(--card);box-shadow:0 1px 4px rgba(0,0,0,.18)}
main{max-width:1080px;margin:auto;padding:30px 5vw 60px}.panel{display:none;animation:in .45s ease}.panel.on{display:block}
@keyframes in{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
h1{font-size:clamp(38px,8vw,72px);line-height:1.04;letter-spacing:-.03em;margin:30px 0 14px;font-weight:700}
h1 span{background:linear-gradient(90deg,#ff9f0a,#ff375f);-webkit-background-clip:text;background-clip:text;color:transparent}
h2{font-size:28px;letter-spacing:-.02em;margin:0 0 6px}.sub{color:var(--mute);font-size:19px;max-width:640px;margin:0 0 28px}
.card{background:var(--card);border-radius:22px;padding:22px;box-shadow:var(--shadow)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
.stat{cursor:pointer;transition:transform .25s}.stat:hover,.city:hover{transform:scale(1.025)}
.stat b{font-size:54px;font-weight:700;letter-spacing:-.03em;display:block}.stat i{font-style:normal;color:var(--mute);font-size:15px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px}
.bar{display:flex;height:14px;border-radius:99px;overflow:hidden;margin:26px 0 8px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:7px 15px;border-radius:99px;font:500 14px inherit;font-family:inherit;cursor:pointer;transition:.2s}
.chip.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
input[type=search]{width:100%;padding:12px 16px;border-radius:12px;border:1px solid var(--line);background:var(--card);color:var(--ink);font:16px inherit;font-family:inherit;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
.city{cursor:pointer;transition:transform .25s}.city h3{margin:0;font-size:20px}.city small{color:var(--mute)}
.temp{font-size:46px;font-weight:700;letter-spacing:-.03em;margin:10px 0 4px}
.pill{display:inline-block;padding:3px 11px;border-radius:99px;font-size:12px;font-weight:600;color:#fff}
.two{display:grid;grid-template-columns:1.6fr 1fr;gap:14px}@media(max-width:760px){.two{grid-template-columns:1fr}}
svg{width:100%;height:auto;display:block;overflow:visible}
#tip{position:absolute;pointer-events:none;background:var(--ink);color:var(--bg);padding:6px 10px;border-radius:8px;font-size:12px;opacity:0;transition:opacity .15s;white-space:nowrap}
table{width:100%;border-collapse:collapse}td,th{padding:11px 6px;text-align:left;border-bottom:1px solid var(--line);font-size:15px}th{color:var(--mute);font-weight:500;font-size:13px}
.big{font-size:64px;font-weight:700;letter-spacing:-.03em;line-height:1}
label{display:flex;justify-content:space-between;font-size:15px;margin:18px 0 6px}label b{font-weight:600}
input[type=range]{width:100%;accent-color:var(--blue)}
.alert{display:flex;gap:14px;align-items:flex-start;margin-bottom:12px;border-left:6px solid var(--c)}.alert p{margin:4px 0 0;color:var(--mute);font-size:15px}
footer{text-align:center;color:var(--mute);font-size:12px;padding:24px 5vw;border-top:1px solid var(--line)}
.f label{display:block;margin:14px 0 6px;font-size:14px;color:var(--mute)}
input[type=number],input[type=date],select{width:100%;padding:12px 14px;border-radius:12px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font:16px inherit;font-family:inherit}
input:focus,select:focus{outline:3px solid color-mix(in srgb,var(--blue) 35%,transparent);border-color:var(--blue)}
.btn{border:0;background:var(--blue);color:#fff;padding:11px 22px;border-radius:99px;font:600 15px inherit;font-family:inherit;cursor:pointer;transition:.2s}.btn:hover{filter:brightness(1.1);transform:scale(1.03)}
.btn.ghost{background:color-mix(in srgb,var(--mute) 18%,transparent);color:var(--ink)}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}
.err{color:#ff3b30;font-size:14px;min-height:18px;margin:10px 0 0}.prev{font-size:15px;color:var(--mute);min-height:24px}
.row{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--line);font-size:15px}
.x{border:0;background:none;color:var(--mute);font-size:24px;cursor:pointer;line-height:1}.x:hover{color:#ff3b30}
#toast{position:fixed;left:50%;bottom:28px;transform:translate(-50%,30px);background:var(--ink);color:var(--bg);padding:12px 22px;border-radius:99px;font-size:14px;opacity:0;transition:.3s;pointer-events:none;z-index:20}#toast.on{opacity:1;transform:translate(-50%,0)}
</style></head><body>
<nav><div class="logo">&#9728;&#65039; Heatwave Guard</div>
<div class="seg" id="seg"><button data-t="overview">Overview</button><button data-t="cities">Cities</button><button data-t="forecast">Forecast</button><button data-t="add">Add Reading</button><button data-t="check">Risk Check</button><button data-t="alerts">Alerts</button></div></nav>
<main>
<section class="panel" id="overview"><h1>Heat, <span>understood.</span></h1>
<p class="sub">Climate intelligence for heatwave monitoring, prediction and early warning. Tap any tile to explore.</p>
<div class="stats" id="stats"></div><div class="bar" id="bar"></div><small style="color:var(--mute)">Share of monitored cities by risk level</small></section>
<section class="panel" id="cities"><h2>Cities</h2><p class="sub">Live status from the SQLite database. Select a city for its forecast.</p>
<input type="search" id="q" placeholder="Search city or state"><div class="chips" id="chips"></div><div class="grid" id="grid"></div></section>
<section class="panel" id="forecast"><h2>Forecast</h2><p class="sub">Observed readings and a 3-day trend forecast. Hover the chart for values.</p>
<div class="chips" id="fchips"></div><div class="two"><div class="card" style="position:relative"><div id="chart"></div><div id="tip"></div></div>
<div class="card"><div id="fhead"></div><table id="ftable"></table></div></div><div class="card" id="fadv" style="margin-top:14px"></div><div class="actions"><button class="btn" id="issue">Issue early warning</button><button class="btn ghost" id="fadd">Add a reading for this city</button></div></section>
<section class="panel" id="check"><h2>Risk Check</h2><p class="sub">Move the sliders and see the heat index and risk level update instantly.</p>
<div class="two"><div class="card"><label>Maximum temperature <b id="vt"></b></label><input type="range" id="rt" min="20" max="52" step=".5" value="42">
<label>Relative humidity <b id="vh"></b></label><input type="range" id="rh" min="5" max="100" value="40">
<label>Normal maximum for the city <b id="vn"></b></label><input type="range" id="rn" min="25" max="45" step=".5" value="38"></div>
<div class="card" id="res" style="text-align:center"><div class="big" id="hi"></div><small style="color:var(--mute)">heat index &deg;C</small><p><span class="pill" id="lv" style="font-size:16px;padding:6px 18px"></span></p><p id="adv" style="color:var(--mute)"></p></div></div></section>
<section class="panel" id="add"><h2>Add Reading</h2><p class="sub">Record a new daily observation. Every city card, forecast, chart and alert updates immediately. Entries are saved in this browser.</p>
<div class="two"><form class="card f" id="aform" novalidate><label>City</label><select id="acity"></select><label>Date</label><input type="date" id="aday">
<label>Maximum temperature (&deg;C)</label><input type="number" step="0.1" id="amax" placeholder="e.g. 43.5"><label>Minimum temperature (&deg;C)</label><input type="number" step="0.1" id="amin" placeholder="e.g. 29">
<label>Relative humidity (%)</label><input type="number" step="1" id="ahum" placeholder="e.g. 35"><p id="aerr" class="err"></p><div id="aprev" class="prev"></div>
<div class="actions"><button class="btn" type="submit">Save reading</button></div></form>
<div class="card"><h3 style="margin:0 0 10px">Your entries</h3><div id="alog"></div><div class="actions"><button class="btn ghost" id="csv" type="button">Download all data (CSV)</button><button class="btn ghost" id="reset" type="button">Reset to demo data</button></div></div></div></section>
<section class="panel" id="alerts"><h2>Early warnings</h2><p class="sub">Generated from the 3-day forecast, most severe first, plus alerts saved in the app.</p><div id="alist"></div></section>
</main><div id="toast"></div><footer>__SRC__ &middot; generated __DATE__ &middot; IMD-style rule + heat index &middot; forecast = 7-day linear trend</footer>
<script>
const D=__DATA__,$=s=>document.querySelector(s),L=D.levels,C=D.colors,KEY='hg_user_v1',r1=v=>Math.round(v*10)/10;
let U={readings:[],alerts:[]},M=[],sel=0,filt='All';try{U=JSON.parse(localStorage.getItem(KEY))||U}catch(e){}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(U))}catch(e){}},today=()=>new Date().toISOString().slice(0,10);
function hi(t,r){let f=t*9/5+32;if(f<80)return t;let h=-42.379+2.04901523*f+10.14333127*r-.22475541*f*r-6.83783e-3*f*f-5.481717e-2*r*r+1.22874e-3*f*f*r+8.5282e-4*f*r*r-1.99e-6*f*f*r*r;
if(r<13&&f<=112)h-=((13-r)/4)*Math.sqrt((17-Math.abs(f-95))/17);else if(r>85&&f<=87)h+=((r-85)/10)*((87-f)/5);return Math.round((h-32)*50/9)/10}
function cls(t,n,r){let d=t-n,l=0;if(t>=47||d>=6.5)l=3;else if(t>=40&&d>=4.5)l=2;else if(t>=37&&d>=2)l=1;
let h=hi(t,r);if(h>=54&&t>=37)l=Math.max(l,2);else if(h>=41)l=Math.max(l,1);return L[l]}
function fit(ys){const n=ys.length;if(n<2)return[ys[0]||0,0];const mx=(n-1)/2,my=ys.reduce((a,b)=>a+b)/n;let sxx=0,sxy=0;ys.forEach((y,i)=>{sxx+=(i-mx)**2;sxy+=(i-mx)*(y-my)});const b=sxy/sxx;return[my-b*mx,b]}
function fcast(h,n){const w=h.slice(-7),ts=w.map(x=>x.t),hm=Math.round(w.reduce((a,x)=>a+x.h,0)/w.length),[a,b]=fit(ts),fc=[];
for(let k=1;k<=3;k++){const t=r1(a+b*(ts.length-1+k));fc.push({day:new Date(Date.parse(w[w.length-1].day)+864e5*k).toISOString().slice(0,10),t,hi:hi(t,hm),level:cls(t,n,hm)})}return{fc,slope:b}}
function warn(name,fc){let w=fc[0];fc.forEach(f=>{if(L.indexOf(f.level)>L.indexOf(w.level))w=f});
return w.level==='Normal'?['Normal',`${name}: no heatwave expected in the next 3 days.`]:[w.level,`${name}: ${w.level} likely on ${w.day} (max ${w.t} °C, heat index ${w.hi} °C). ${D.advice[w.level]}`]}
function model(){M=D.cities.map(c=>{const h=c.hist.map(x=>({...x}));U.readings.filter(r=>r.city===c.name).forEach(r=>{const i=h.findIndex(x=>x.day===r.day);i>=0?h[i]=r:h.push(r)});
h.sort((a,b)=>a.day<b.day?-1:1);const l=h[h.length-1],{fc,slope}=fcast(h,c.normal),[wl,wm]=warn(c.name,fc);
return{...c,hist:h,tmax:l.t,hum:l.h,day:l.day,hi:hi(l.t,l.h),level:cls(l.t,c.normal,l.h),fc,slope,wl,wm}})}
const pill=l=>`<span class="pill" style="background:${C[l]}">${l}</span>`;
const toast=m=>{const t=$('#toast');t.textContent=m;t.classList.add('on');clearTimeout(toast.t);toast.t=setTimeout(()=>t.classList.remove('on'),2800)};
function show(t){document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('on',p.id===t));
document.querySelectorAll('#seg button').forEach(b=>b.classList.toggle('on',b.dataset.t===t));history.replaceState(0,'','#'+t);scrollTo(0,0)}
document.querySelectorAll('#seg button').forEach(b=>b.onclick=()=>show(b.dataset.t));
// overview
function drawO(){const cnt=Object.fromEntries(L.map(l=>[l,M.filter(c=>c.level===l).length]));
$('#stats').innerHTML=L.map(l=>`<div class="card stat" data-l="${l}"><b style="color:${C[l]}">${cnt[l]}</b><i><span class="dot" style="background:${C[l]}"></span>${l}</i></div>`).join('');
$('#bar').innerHTML=L.map(l=>`<div style="width:${cnt[l]/M.length*100}%;background:${C[l]}"></div>`).join('');
document.querySelectorAll('.stat').forEach(s=>s.onclick=()=>{filt=s.dataset.l;drawC();show('cities')})}
// cities
$('#chips').innerHTML=['All',...L].map(l=>`<button class="chip" data-l="${l}">${l}</button>`).join('');
document.querySelectorAll('#chips .chip').forEach(b=>b.onclick=()=>{filt=b.dataset.l;drawC()});$('#q').oninput=()=>drawC();
function drawC(){const q=$('#q').value.toLowerCase();document.querySelectorAll('#chips .chip').forEach(b=>b.classList.toggle('on',b.dataset.l===filt));
$('#grid').innerHTML=M.map((c,i)=>({c,i})).filter(({c})=>(filt==='All'||c.level===filt)&&(c.name+c.state).toLowerCase().includes(q)).map(({c,i})=>
`<div class="card city" data-i="${i}"><h3>${c.name}</h3><small>${c.state} &middot; ${c.day}</small><div class="temp">${c.tmax}&deg;</div>${pill(c.level)}<p><small>Heat index ${c.hi}&deg; &middot; Humidity ${c.hum}% &middot; Normal ${c.normal}&deg;</small></p></div>`).join('')||'<p class="sub">No cities match.</p>';
document.querySelectorAll('.city').forEach(e=>e.onclick=()=>{sel=+e.dataset.i;drawF();show('forecast')})}
// forecast
$('#fchips').innerHTML=D.cities.map((c,i)=>`<button class="chip" data-i="${i}">${c.name}</button>`).join('');
document.querySelectorAll('#fchips .chip').forEach(b=>b.onclick=()=>{sel=+b.dataset.i;drawF()});
function drawF(){const c=M[sel];document.querySelectorAll('#fchips .chip').forEach(b=>b.classList.toggle('on',+b.dataset.i===sel));
const hh=c.hist.slice(-14),pts=[...hh.map(h=>({d:h.day,t:h.t,f:0})),...c.fc.map(h=>({d:h.day,t:h.t,f:1,l:h.level}))],W=600,H=300,p=34,k=hh.length;pts.forEach((q,i)=>q.i=i);
const lo=Math.min(...pts.map(a=>a.t),c.normal)-2,hi_=Math.max(...pts.map(a=>a.t),c.normal)+2,x=i=>p+i*(W-2*p)/(pts.length-1),y=t=>H-p-(t-lo)/(hi_-lo)*(H-2*p);
const path=a=>a.map((q,i)=>(i?'L':'M')+x(q.i).toFixed(1)+','+y(q.t).toFixed(1)).join('');
let g='';for(let t=Math.ceil(lo/2)*2;t<=hi_;t+=2)g+=`<line x1="${p}" x2="${W-p}" y1="${y(t)}" y2="${y(t)}" stroke="var(--line)"/><text x="${p-6}" y="${y(t)+4}" font-size="11" text-anchor="end" fill="var(--mute)">${t}</text>`;
$('#chart').innerHTML=`<svg viewBox="0 0 ${W} ${H}">${g}<line x1="${p}" x2="${W-p}" y1="${y(c.normal)}" y2="${y(c.normal)}" stroke="#ff3b30" stroke-dasharray="5 4"/>
<path d="${path(pts.slice(0,k))}" fill="none" stroke="var(--blue)" stroke-width="3" stroke-linecap="round"/><path d="${path(pts.slice(k-1))}" fill="none" stroke="#ff9f0a" stroke-width="3" stroke-dasharray="7 6" stroke-linecap="round"/>
${pts.map(q=>`<circle cx="${x(q.i)}" cy="${y(q.t)}" r="${q.f?6:4}" fill="${q.f?C[q.l]:'var(--blue)'}" data-i="${q.i}"/>`).join('')}</svg>`;
const tip=$('#tip');document.querySelectorAll('#chart circle').forEach(e=>{e.onmouseenter=()=>{const q=pts[e.dataset.i],r=e.getBoundingClientRect(),b=$('#chart').parentNode.getBoundingClientRect();
tip.textContent=`${q.d}: ${q.t}°C${q.f?' (forecast)':''}`;tip.style.left=r.left-b.left-30+'px';tip.style.top=r.top-b.top-34+'px';tip.style.opacity=1};e.onmouseleave=()=>tip.style.opacity=0});
$('#fhead').innerHTML=`<h2 style="font-size:24px">${c.name}</h2><p class="sub" style="font-size:15px;margin-bottom:10px">Trend ${c.slope>=0?'+':''}${c.slope.toFixed(2)} °C per day</p>`;
$('#ftable').innerHTML='<tr><th>Date</th><th>Max</th><th>HI</th><th>Status</th></tr>'+c.fc.map(f=>`<tr><td>${f.day.slice(5)}</td><td>${f.t}°</td><td>${f.hi}°</td><td>${pill(f.level)}</td></tr>`).join('');
$('#fadv').innerHTML=`${pill(c.wl)} <span style="margin-left:6px">${c.wm}</span>`}
$('#issue').onclick=()=>{const c=M[sel];U.alerts.push({city:c.name,day:today(),level:c.wl,message:c.wm});save();drawA();toast('Early warning saved to the Alerts tab')};
$('#fadd').onclick=()=>{$('#acity').value=M[sel].name;prev();show('add')};
// add reading
$('#acity').innerHTML=D.cities.map(c=>`<option>${c.name}</option>`).join('');$('#aday').value=today();
function prev(){const t=parseFloat($('#amax').value),h=parseFloat($('#ahum').value),c=D.cities.find(x=>x.name===$('#acity').value)||D.cities[0];
$('#aprev').innerHTML=isNaN(t)||isNaN(h)?'Enter a maximum temperature and humidity to preview the risk level.':`${pill(cls(t,c.normal,h))} &nbsp; heat index <b>${hi(t,h)}°C</b> &middot; normal for ${c.name} is ${c.normal}°C`}
['acity','amax','amin','ahum'].forEach(i=>$('#'+i).oninput=prev);
$('#aform').onsubmit=e=>{e.preventDefault();const city=$('#acity').value,day=$('#aday').value,t=parseFloat($('#amax').value),n=parseFloat($('#amin').value),h=parseFloat($('#ahum').value);let err='';
if(!day||isNaN(t)||isNaN(n)||isNaN(h))err='Please fill in every field with valid numbers.';else if(!(n>=-10&&n<=t&&t<=60))err='Temperatures must satisfy -10 \u2264 min \u2264 max \u2264 60 \u00b0C.';else if(h<0||h>100)err='Humidity must be between 0 and 100 %.';
$('#aerr').textContent=err;if(err)return;
U.readings=U.readings.filter(r=>!(r.city===city&&r.day===day));U.readings.push({city,day,t,tn:n,h});save();refresh();sel=D.cities.findIndex(c=>c.name===city);drawF();
toast(`Saved. ${city} is now ${M[sel].level}. Forecast updated.`);e.target.reset();$('#aday').value=today();$('#acity').value=city;prev()};
function drawL(){$('#alog').innerHTML=U.readings.length?U.readings.map((r,i)=>({r,i})).reverse().map(({r,i})=>`<div class="row"><span><b>${r.city}</b> &middot; ${r.day}<br><small>max ${r.t}° &middot; min ${r.tn}° &middot; ${r.h}%</small></span><button class="x" data-i="${i}" title="Delete">&times;</button></div>`).join(''):'<p style="color:var(--mute)">No readings added yet. Entries you save appear here.</p>';
document.querySelectorAll('#alog .x').forEach(b=>b.onclick=()=>{U.readings.splice(+b.dataset.i,1);save();refresh()})}
$('#reset').onclick=()=>{if(confirm('Remove all readings and alerts you added and go back to the demo data?')){U={readings:[],alerts:[]};save();refresh();toast('Demo data restored')}};
$('#csv').onclick=()=>{let s='city,date,max_temp,min_temp,humidity\n';M.forEach(c=>c.hist.forEach(h=>s+=`${c.name},${h.day},${h.t},${h.tn},${h.h}\n`));
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([s],{type:'text/csv'}));a.download='heatwave_readings.csv';a.click()};
// risk check
function calc(){const t=+$('#rt').value,r=+$('#rh').value,n=+$('#rn').value;$('#vt').textContent=t+'°C';$('#vh').textContent=r+'%';$('#vn').textContent=n+'°C';
const l=cls(t,n,r);$('#hi').textContent=hi(t,r)+'°';$('#hi').style.color=C[l];$('#lv').textContent=l;$('#lv').style.background=C[l];$('#adv').textContent=D.advice[l]}
['rt','rh','rn'].forEach(i=>$('#'+i).oninput=calc);
// alerts
function drawA(){const al=[...M.map(c=>({lv:c.wl,m:c.wm,w:'Forecast'})),...D.saved.map(a=>({lv:a.level,m:a.message,w:'From the desktop app, '+a.day})),...U.alerts.map((a,i)=>({lv:a.level,m:a.message,w:'Saved by you, '+a.day,i}))].sort((a,b)=>L.indexOf(b.lv)-L.indexOf(a.lv));
$('#alist').innerHTML=al.map(a=>`<div class="card alert" style="--c:${C[a.lv]}"><div style="flex:1">${pill(a.lv)}<p>${a.m}</p><small style="color:var(--mute)">${a.w}</small></div>${a.i!==undefined?`<button class="x" data-i="${a.i}" title="Delete">&times;</button>`:''}</div>`).join('');
document.querySelectorAll('#alist .x').forEach(b=>b.onclick=()=>{U.alerts.splice(+b.dataset.i,1);save();drawA()})}
function refresh(){model();drawO();drawC();drawF();drawA();drawL()}
refresh();prev();calc();show(location.hash.slice(1)&&$('#'+location.hash.slice(1))?location.hash.slice(1):'overview');
</script></body></html>'''


def build(live=False):
    """Default: SIMULATED demo data in its own file (heatwave_demo.db).
    live=True (python web_export.py --live): fetch real data into heatwave.db instead."""
    if live:
        db.init_db()
        print("Fetching live data from Open-Meteo...")
        ok, errs = live_data.refresh()
        if errs:
            print(f"Warning: {len(errs)} cities failed; using stored data for them.")
        src = 'Live data: <a href="https://open-meteo.com" style="color:inherit">Open-Meteo</a> (CC BY 4.0)'
    else:
        demo = Path(__file__).with_name("heatwave_demo.db")
        demo.unlink(missing_ok=True)          # fresh simulated data every build
        db.DB_PATH = demo
        db.init_db(seed=True)
        src = "Simulated demo data"
    latest = db.latest_per_city()
    if not latest:
        raise SystemExit("No weather data yet. Connect to the internet and run with --live.")
    cities = []
    for r in latest:
        hist = db.get_history(r["city_id"])
        cities.append({"name": r["name"], "state": r["state"], "normal": r["normal_max"],
                       "hist": [{"day": h["day"], "t": h["max_temp"], "tn": h["min_temp"], "h": int(h["humidity"])} for h in hist]})
    saved = [{"level": a["level"], "message": a["message"], "day": a["day"]} for a in db.get_alerts(20)] if live else []
    data = {"cities": cities, "saved": saved, "levels": pr.LEVELS, "colors": pr.COLORS, "advice": pr.ADVICE}
    page = (TEMPLATE.replace("__DATA__", json.dumps(data)).replace("__SRC__", src)
            .replace("__DATE__", datetime.now().strftime("%d %b %Y, %H:%M")))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print("Website written to", OUT, "(live data)" if live else "(simulated data)")


if __name__ == "__main__":
    build(live="--live" in sys.argv)
