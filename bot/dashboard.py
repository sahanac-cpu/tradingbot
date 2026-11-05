"""Tiny local web dashboard: http://localhost:8000 (no login, only on your computer)."""
from __future__ import annotations
import json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"equity": [], "positions": [], "trades": [], "log": [], "charts": {}, "tickers": [], "reviews": [], "stats": {}, "board": [], "history": [], "strategies": [], "status": "Starting", "broker": ""}
LOCK = threading.Lock()

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Trading Bot</title>
<style>
:root{--bg:#07090f;--card:rgba(255,255,255,.035);--line:rgba(255,255,255,.08);--txt:#e8ecf3;--mut:#7d8697;
--g:#22d39a;--r:#ff5c7a;--b:#6aa8ff;--y:#ffc861;--p:#a78bfa}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--txt);
font:14px/1.45 ui-sans-serif,-apple-system,"Segoe UI",Inter,Roboto,sans-serif;-webkit-font-smoothing:antialiased}
body:before{content:"";position:fixed;inset:-20%;z-index:-1;pointer-events:none;
background:radial-gradient(40% 35% at 15% 0%,rgba(106,168,255,.16),transparent 70%),
radial-gradient(35% 30% at 90% 10%,rgba(167,139,250,.14),transparent 70%),
radial-gradient(40% 40% at 60% 100%,rgba(34,211,154,.08),transparent 70%)}
.wrap{max-width:1400px;margin:0 auto;padding:20px 16px 40px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:18px}
.brand{display:flex;align-items:center;gap:12px}.logo{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;
background:linear-gradient(135deg,var(--b),var(--p));box-shadow:0 6px 24px rgba(106,168,255,.35)}
.brand h1{font-size:18px;margin:0;letter-spacing:-.01em}.brand small{color:var(--mut);font-size:12px}
.pill{display:inline-flex;align-items:center;gap:8px;padding:7px 12px;border-radius:999px;border:1px solid var(--line);
background:var(--card);font-size:12.5px;color:#cfd6e2}.dot{width:8px;height:8px;border-radius:50%;background:var(--g);
box-shadow:0 0 0 0 rgba(34,211,154,.6);animation:pulse 1.8s infinite}.dot.off{background:var(--mut);animation:none}
.dot.bad{background:var(--r);animation:none}@keyframes pulse{70%{box-shadow:0 0 0 9px rgba(34,211,154,0)}100%{box-shadow:0 0 0 0 rgba(34,211,154,0)}}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;backdrop-filter:blur(12px);min-width:0}
.card h2{font-size:12px;font-weight:600;color:var(--mut);text-transform:uppercase;letter-spacing:.08em;margin:0 0 12px;
display:flex;justify-content:space-between;align-items:center;gap:8px}
.kpis{display:grid;grid-template-columns:2fr repeat(4,1fr);gap:12px;margin-bottom:12px}
.big{font-size:34px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.mid{font-size:22px;font-weight:650;font-variant-numeric:tabular-nums}.sub{color:var(--mut);font-size:12px}
.g{color:var(--g)}.r{color:var(--r)}.bar{height:6px;border-radius:9px;background:rgba(255,255,255,.07);overflow:hidden;margin-top:10px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--b),var(--p));border-radius:9px;transition:width .4s}
.tick{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(170px,1fr);gap:10px;overflow-x:auto;margin-bottom:12px;padding-bottom:4px}
.tk{cursor:pointer;padding:12px 14px;transition:.15s}.tk:hover{border-color:rgba(255,255,255,.2)}
.tk.sel{border-color:var(--b);box-shadow:0 0 0 1px var(--b) inset,0 8px 30px rgba(106,168,255,.15)}
.tk .row{display:flex;justify-content:space-between;align-items:center}.sym{font-weight:700}
.badge{font-size:10px;padding:2px 6px;border-radius:6px;background:rgba(167,139,250,.15);color:var(--p);font-weight:600}
.badge.etf{background:rgba(106,168,255,.13);color:var(--b)}.tk svg{display:block;margin-top:6px}
.grid{display:grid;grid-template-columns:1.7fr 1fr;gap:12px}.stack{display:grid;gap:12px;align-content:start}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th{color:var(--mut);font-weight:500;font-size:11.5px;text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:8px;border-bottom:1px solid rgba(255,255,255,.04)}tr:last-child td{border-bottom:0}
.side{font-size:11px;font-weight:700;padding:3px 7px;border-radius:6px}.BUY{background:rgba(34,211,154,.14);color:var(--g)}
.SHORT{background:rgba(255,92,122,.14);color:var(--r)}.EXIT{background:rgba(255,200,97,.14);color:var(--y)}
.scroll{max-height:340px;overflow:auto}.log div{font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;padding:3px 0;color:#aeb6c4}
.log .entry{color:var(--b)}.log .win{color:var(--g)}.log .loss,.log .bad{color:var(--r)}.log .skip{color:var(--mut)}
.rv{display:grid;grid-template-columns:auto 1fr auto;gap:4px 14px;padding:12px 2px;border-bottom:1px solid rgba(255,255,255,.05)}
.rv:last-child{border-bottom:0}.vb{font-size:11px;font-weight:700;padding:3px 8px;border-radius:6px;text-transform:uppercase;align-self:start}
.v-good{background:rgba(34,211,154,.14);color:var(--g)}.v-ok{background:rgba(106,168,255,.14);color:var(--b)}
.v-loss{background:rgba(255,200,97,.14);color:var(--y)}.v-mistake{background:rgba(255,92,122,.16);color:var(--r)}
.q{grid-column:2/4;color:var(--mut);font-style:italic;font-size:12.5px;border-left:2px solid var(--line);padding-left:10px}
.empty{color:var(--mut);padding:18px 4px;text-align:center}.legend{display:flex;gap:14px;font-size:11.5px;color:var(--mut);text-transform:none;letter-spacing:0;font-weight:500}
.legend b{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
@media(max-width:1000px){.kpis{grid-template-columns:1fr 1fr}.kpis .card:first-child{grid-column:1/-1}.grid{grid-template-columns:1fr}}

.champ{display:flex;gap:14px;align-items:center;padding:14px 16px;margin-bottom:12px;background:linear-gradient(90deg,rgba(255,200,97,.12),rgba(167,139,250,.08));border:1px solid rgba(255,200,97,.25);border-radius:16px}
.champ .crown{font-size:26px}.champ b{font-size:16px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}.chip{cursor:pointer;padding:7px 12px;border-radius:999px;border:1px solid var(--line);background:var(--card);font-size:12.5px;color:#cfd6e2}
.chip.on{border-color:var(--b);background:rgba(106,168,255,.15);color:#fff}
.lb tr{cursor:pointer}.lb tr:hover td{background:rgba(255,255,255,.03)}.lb .me td{background:rgba(255,200,97,.06)}
.acct{font-size:10px;font-weight:700;padding:2px 6px;border-radius:5px}.real{background:rgba(34,211,154,.15);color:var(--g)}.simb{background:rgba(167,139,250,.15);color:var(--p)}
.why{color:var(--mut);font-size:12px;line-height:1.4;padding-top:3px;max-width:640px}
.hd{display:grid;grid-template-columns:96px 1fr auto;gap:6px 12px;padding:9px 4px;border-bottom:1px solid rgba(255,255,255,.05);cursor:pointer;font-size:13px}
.hd:hover{background:rgba(255,255,255,.03)}.viewing{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;margin-bottom:12px;border-radius:12px;background:rgba(106,168,255,.12);border:1px solid rgba(106,168,255,.3)}
button{font:inherit;cursor:pointer;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--txt);padding:6px 12px}
</style></head><body><div class="wrap">
<div class="top"><div class="brand"><div class="logo"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/></svg></div>
<div><h1>Strategy Arena</h1><small id="brk">-</small></div></div>
<div style="display:flex;gap:8px;flex-wrap:wrap"><span class="pill" id="guard">-</span><span class="pill"><span class="dot" id="dot"></span><span id="st">connecting...</span></span></div></div>
<div class="champ"><span class="crown">👑</span><div><div class="sub">Today's champion - the only strategy allowed to trade your real paper account</div><b id="champ">-</b> <span class="sub" id="cnote"></span></div></div>
<div class="kpis">
 <div class="card"><h2>Real account equity <span class="sub" id="tot"></span></h2><div class="big" id="eq">-</div><svg id="ec" viewBox="0 0 600 70" preserveAspectRatio="none" width="100%" height="70"></svg></div>
 <div class="card"><h2>Today (real)</h2><div class="mid" id="day">-</div><div class="sub" id="dayp"></div></div>
 <div class="card"><h2>Win rate (real)</h2><div class="mid" id="wr">-</div><div class="sub" id="nt"></div></div>
 <div class="card"><h2>Real trades today</h2><div class="mid" id="td">-</div><div class="bar"><i id="tdb" style="width:0"></i></div></div>
 <div class="card"><h2>Open positions</h2><div class="mid" id="op">-</div><div class="sub" id="opp"></div></div>
</div>
<div class="card" style="margin-bottom:12px"><h2>Leaderboard - every strategy trades every symbol in its own simulated $100k account <span class="legend">click a row to filter</span></h2><div id="lb"></div>
<div class="sub" style="margin-top:8px">Each morning the strategy with the best 10-day simulated P&L becomes champion (needs 5+ trades). Simulated results include crypto fees and slippage.</div></div>
<div class="tick" id="tick"></div>
<div class="chips" id="chips"></div>
<div id="viewbar"></div>
<div class="grid">
 <div class="stack">
  <div class="card"><h2><span id="ctitle">Chart</span><span class="legend"><span><b style="background:var(--g)"></b>Real buy</span><span><b style="background:var(--p)"></b>Sim buy</span><span><b style="background:var(--y)"></b>Exit</span></span></h2>
   <svg id="main" viewBox="0 0 800 300" preserveAspectRatio="none" width="100%" height="300"></svg></div>
  <div class="card"><h2>Open positions</h2><div id="pos"></div></div>
  <div class="card"><h2><span id="rvtitle">Trade reviews - what went right and wrong</span><span class="legend" id="rvsum"></span></h2><div class="scroll" style="max-height:520px" id="rv"></div></div>
  <div class="card"><h2><span id="trtitle">Trades today - and why each was taken</span></h2><div class="scroll" style="max-height:620px" id="tr"></div></div>
 </div>
 <div class="stack">
  <div class="card"><h2>History - every day so far <span class="legend">click a day</span></h2><div class="scroll" style="max-height:420px" id="hist"></div></div>
  <div class="card"><h2>Champion's brain (self-learning)</h2><div id="brain"></div></div>
  <div class="card"><h2>Live activity</h2><div class="scroll log" id="log" style="max-height:600px"></div></div>
 </div>
</div></div>
<script>
const $=id=>document.getElementById(id);
const money=(x,d=2)=>x==null?'-':(x<0?'-$':'$')+Math.abs(x).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d});
const sgn=x=>(x>=0?'+':'')+money(x);const cls=x=>x>=0?'g':'r';const px=v=>v==null?'-':v>=1000?v.toLocaleString(undefined,{maximumFractionDigits:2}):(+v).toFixed(2);
const esc=x=>String(x??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
let sel=null,filt='All',view=null,viewData=null,last=null;
const acct=a=>a=='real'?'<span class="acct real">REAL</span>':'<span class="acct simb">SIM</span>';
const pass=x=>filt=='All'||(filt=='Real account'?x.account=='real'||x.real:x.strategy==filt);
function area(a,W,H,col,id){if(a.length<2)return`<text x=8 y=${H/2} fill=#7d8697 font-size=12>collecting data...</text>`;
 const lo=Math.min(...a),hi=Math.max(...a),X=i=>i/(a.length-1)*W,Y=v=>H-3-(v-lo)/((hi-lo)||1)*(H-6);
 const pts=a.map((v,i)=>X(i).toFixed(1)+','+Y(v).toFixed(1)).join(' ');
 return`<defs><linearGradient id="${id}" x1=0 y1=0 x2=0 y2=1><stop offset=0 stop-color="${col}" stop-opacity=.35 /><stop offset=1 stop-color="${col}" stop-opacity=0 /></linearGradient></defs>
 <polygon points="0,${H} ${pts} ${W},${H}" fill="url(#${id})"/><polyline points="${pts}" fill=none stroke="${col}" stroke-width=2 vector-effect=non-scaling-stroke stroke-linejoin=round />`}
function mainChart(c){const W=800,H=300,el=$('main');const all=c.c.concat(c.hod,c.lod);
 if(c.c.length<2){el.innerHTML='<text x=20 y=150 fill=#7d8697 font-size=14>waiting for market data...</text>';return}
 const lo=Math.min(...all),hi=Math.max(...all),pad=(hi-lo)*.06||1,L=lo-pad,Hh=hi+pad,n=c.c.length-1;
 const X=i=>i/n*W,Y=v=>H-(v-L)/(Hh-L)*H,up=c.c.at(-1)>=c.c[0],col=up?'#22d39a':'#ff5c7a';
 const pl=a=>a.map((v,i)=>X(i).toFixed(1)+','+Y(v).toFixed(1)).join(' ');
 let g='';for(let k=1;k<4;k++){const y=H*k/4;g+=`<line x1=0 x2=${W} y1=${y} y2=${y} stroke="rgba(255,255,255,.05)"/><text x=${W-4} y=${y-4} text-anchor=end fill=#5d6676 font-size=11>${px(Hh-(Hh-L)*k/4)}</text>`}
 let m='';for(const k of c.marks){if(!pass(k))continue;const i=c.t.lastIndexOf(k.t);if(i<0)continue;const x=X(i),y=Y(k.px);
  m+=k.k=='exit'?`<circle cx=${x} cy=${y} r=5 fill=#ffc861 stroke=#07090f stroke-width=2 />`:
   `<path d="M${x-7},${y+11}L${x+7},${y+11}L${x},${y}Z" fill="${k.account=='real'?'#22d39a':'#a78bfa'}" stroke=#07090f stroke-width=1.5 />`}
 el.innerHTML=`<defs><linearGradient id=mg x1=0 y1=0 x2=0 y2=1><stop offset=0 stop-color="${col}" stop-opacity=.28 /><stop offset=1 stop-color="${col}" stop-opacity=0 /></linearGradient></defs>${g}
 <polyline points="${pl(c.hod)}" fill=none stroke="rgba(34,211,154,.45)" stroke-dasharray="5 5" vector-effect=non-scaling-stroke />
 <polyline points="${pl(c.lod)}" fill=none stroke="rgba(255,92,122,.45)" stroke-dasharray="5 5" vector-effect=non-scaling-stroke />
 <polygon points="0,${H} ${pl(c.c)} ${W},${H}" fill="url(#mg)"/><polyline points="${pl(c.c)}" fill=none stroke="${col}" stroke-width=2.2 vector-effect=non-scaling-stroke stroke-linejoin=round />${m}
 <text x=6 y=16 fill=#5d6676 font-size=11>${c.t[0]}</text><text x=6 y=${H-6} fill=#5d6676 font-size=11>${c.t.at(-1)}</text>`}
function tradesHtml(T){T=T.filter(pass);if(!T.length)return'<div class=empty>No trades for this filter yet</div>';
 return`<table><tr><th>Time</th><th>Symbol</th><th>Strategy</th><th></th><th>Qty</th><th>Price</th><th>P&L</th></tr>${T.slice().reverse().map(t=>
 `<tr><td class=sub>${t.t}</td><td><b>${esc(t.sym)}</b> ${acct(t.account)}</td><td class=sub>${esc(t.strategy)}</td><td><span class="side ${t.side}">${t.side}</span></td><td>${+(+t.qty).toFixed(6)}</td><td>${px(t.px)}</td><td class=${t.side=='EXIT'?cls(t.pnl):''}>${t.side=='EXIT'?sgn(t.pnl):''}</td></tr>
 <tr><td></td><td colspan=6 class=why>${t.side=='BUY'?'<b style="color:#cfd6e2">Why:</b> '+esc(t.why||t.reason):'<b style="color:#cfd6e2">Exit:</b> '+esc(t.reason)}</td></tr>`).join('')}</table>`}
function reviewsHtml(R){R=R.filter(pass);const lbl={good:'Worked',ok:'OK',loss:'Normal loss',mistake:'Mistake'};
 const cnt=k=>R.filter(r=>r.verdict==k).length;
 $('rvsum').innerHTML=R.length?`<span class=g>${cnt('good')} worked</span><span style="color:var(--b)">${cnt('ok')} ok</span><span style="color:var(--y)">${cnt('loss')} loss</span><span class=r>${cnt('mistake')} mistakes</span>`:'';
 return R.length?R.slice().reverse().map(r=>`<div class=rv><span class="vb v-${r.verdict}">${lbl[r.verdict]}</span>
  <div><b>${esc(r.sym)}</b> ${r.real?acct('real'):acct('sim')} <span class=sub>${esc(r.strategy||'Game Theory')} · ${r.t_in} → ${r.t_out} · exit: ${esc(r.why_out)}</span><br>${esc(r.lesson)}</div>
  <b class=${cls(r.pnl)}>${sgn(r.pnl)}</b>${r.quote?`<div class=q>"${esc(r.quote)}"</div>`:''}</div>`).join('')
  :'<div class=empty>Each trade is reviewed 15 minutes after it closes.</div>'}
async function openDay(d){view=d;viewData=await (await fetch('day/'+d,{cache:'no-store'})).json();render()}
function closeDay(){view=null;viewData=null;render()}
function render(){const s=last;if(!s)return;
 const e=s.equity.at(-1)||{v:0,day:0,tot:0},st=s.stats||{};
 $('eq').textContent=money(e.v);$('tot').innerHTML=`<span class=${cls(e.tot)}>${sgn(e.tot)} all time</span>`;
 $('day').innerHTML=`<span class=${cls(e.day)}>${sgn(e.day)}</span>`;$('dayp').textContent=e.v?((e.day/(e.v-e.day))*100).toFixed(2)+'% today':'';
 $('wr').textContent=st.win==null?'-':st.win+'%';$('nt').textContent=(st.n||0)+' closed real trades';
 $('td').textContent=`${st.trades_today||0} / ${st.max_trades||0}`;$('tdb').style.width=((st.trades_today||0)/(st.max_trades||1)*100)+'%';
 $('ec').innerHTML=area(s.equity.map(x=>x.v),600,70,'#6aa8ff','eg');
 $('brk').textContent=s.broker||'';$('st').textContent=s.status+(s.updated?' · updated '+s.updated:'');
 $('dot').className='dot'+(s.status.startsWith('Live')?'':s.status.startsWith('Halted')?' bad':' off');
 $('guard').innerHTML=st.halted?'<span class=r>Loss limit hit - no new real trades</span>':`Real: risk ${(st.risk*100).toFixed(2)}%/trade · stop day at -${(st.max_loss*100).toFixed(0)}%`;
 $('champ').textContent=s.champion?s.champion.name:'-';$('cnote').textContent=s.champion?'- '+s.champion.note:'';
 const P=s.positions.filter(pass),upl=s.positions.filter(p=>p.account=='real').reduce((a,p)=>a+p.pnl,0);
 $('op').textContent=s.positions.filter(p=>p.account=='real').length;$('opp').innerHTML=`<span class=${cls(upl)}>${sgn(upl)} real unrealized</span> · ${s.positions.filter(p=>p.account=='sim').length} sim`;
 $('lb').innerHTML=`<table class=lb><tr><th></th><th>Strategy</th><th>Today (sim)</th><th>Trades</th><th>Win</th><th>Open</th><th>10-day (sim)</th><th>Learned from</th></tr>${(s.board||[]).slice().sort((a,b)=>b.ten-a.ten).map(b=>
  `<tr class="${b.champion?'me':''}" onclick="filt='${b.name}';render()"><td>${b.champion?'👑':''}</td><td><b>${b.name}</b></td><td class=${cls(b.today)}><b>${sgn(b.today)}</b></td><td>${b.n}</td><td>${b.win==null?'-':b.win+'%'}</td><td>${b.open}</td><td class=${cls(b.ten)}>${sgn(b.ten)} <span class=sub>${b.ten_n} trades / ${b.days}d</span></td><td class=sub>${b.learned} trades</td></tr>`).join('')}</table>`;
 $('chips').innerHTML=['All','Real account',...(s.strategies||[])].map(x=>`<span class="chip ${x==filt?'on':''}" onclick="filt='${x}';render()">${x}</span>`).join('');
 if(!sel&&s.tickers.length)sel=s.tickers[0].sym;
 $('tick').innerHTML=s.tickers.map(t=>{const c=s.charts[t.sym]||{c:[]},ch=t.last&&t.open?(t.last/t.open-1)*100:null;
  return`<div class="card tk ${t.sym==sel?'sel':''}" onclick="sel='${t.sym}';render()"><div class=row><span class=sym>${t.sym}</span><span class="badge ${t.crypto?'':'etf'}">${t.sim?'CRYPTO · SIM':'ETF'}</span></div>
  <div class=row style="margin-top:4px"><span class=mid style="font-size:17px">${t.last?'$'+px(t.last):'-'}</span><span class="${ch==null?'sub':cls(ch)}" style="font-size:12.5px;font-weight:600">${ch==null?'':(ch>=0?'+':'')+ch.toFixed(2)+'%'}</span></div>
  <svg viewBox="0 0 160 34" preserveAspectRatio="none" width=100% height=34>${area(c.c.slice(-200),160,34,ch==null||ch>=0?'#22d39a':'#ff5c7a','s'+t.sym.replace('/',''))}</svg></div>`}).join('');
 if(sel&&s.charts[sel]){$('ctitle').textContent=sel+' · 1-minute'+(filt!='All'?' · '+filt:'');mainChart(s.charts[sel])}
 $('pos').innerHTML=P.length?`<table><tr><th>Symbol</th><th>Strategy</th><th>Qty</th><th>Entry</th><th>Last</th><th>P&L</th><th>Stop</th><th>Target</th></tr>${P.map(p=>
  `<tr><td><b>${p.sym}</b> ${acct(p.account)}</td><td class=sub>${p.strategy}</td><td>${+p.qty.toFixed(6)}</td><td>${px(p.entry)}</td><td>${px(p.last)}</td><td class=${cls(p.pnl)}><b>${sgn(p.pnl)}</b></td><td class=r>${px(p.stop)}</td><td class=g>${px(p.target)}</td></tr>`).join('')}</table>`
  :'<div class=empty>No open positions for this filter</div>';
 const D=view?viewData:s;
 $('viewbar').innerHTML=view?`<div class=viewing><span>Viewing <b>${view}</b>${viewData.source=='backfill'?' (back-filled from market data)':''} · champion: ${viewData.champion||'-'} · real P&L ${sgn((viewData.real||{}).pnl||0)}</span><button onclick="closeDay()">Back to today</button></div>`:'';
 $('trtitle').textContent=view?`Trades on ${view} - and why each was taken`:'Trades today - and why each was taken';
 $('rvtitle').textContent=view?`Reviews on ${view}`:'Trade reviews - what went right and wrong';
 $('tr').innerHTML=tradesHtml(D.trades||[]);$('rv').innerHTML=reviewsHtml(D.reviews||[]);
 $('hist').innerHTML=(s.history||[]).length?(s.history||[]).slice().reverse().map(h=>{const ar=h.arena||{},best=h.best;
  return`<div class=hd onclick="openDay('${h.date}')"><b>${h.date}</b><div>${Object.entries(ar).map(([k,v])=>`<span class=sub style="margin-right:10px">${k.split(' ')[0]} <span class=${cls(v.pnl)}>${sgn(v.pnl)}</span></span>`).join('')}<br><span class=sub>${h.source=='backfill'?'back-filled':'champion: '+(h.champion||'-')} · best: ${best||'-'}</span></div><span class=${cls((h.real||{}).pnl||0)}>${h.real&&h.real.n?sgn(h.real.pnl):''}</span></div>`}).join('')
  :'<div class=empty>Days appear here as they finish.</div>';
 const br=s.brain||{n:0,min:30,factors:[]};const nice={breakout:'Breakout setup',bounce:'Bounce setup',short:'Short trade',crypto:'Crypto',dist_extreme_atr:'Distance below day high',range_pos:'Position in day range',trend_30:'30-min trend',vol_ratio:'Volume picking up',atr_pct:'Market volatility',minutes_open:'Later in the day',bounce_n:'Bounce number',reward_risk:'Reward/risk'};
 $('brain').innerHTML=`<div style="display:flex;justify-content:space-between"><span class=mid style="font-size:18px">${br.name||''}: ${br.off?'Off':br.n<br.min?'Learning':'Filtering'}</span><span class=sub>${br.n} trades · ${br.n?Math.round(100*br.wins/br.n):0}% won</span></div>
 <div class=bar><i style="width:${Math.min(100,br.n/br.min*100)}%"></i></div><div class=sub style="margin:8px 0 6px">Each strategy has its own brain. It takes every setup until it has seen ${br.min} trades, then skips setups it predicts under 45% to win.</div>
 ${br.n?br.factors.map(([f,w])=>`<div style="display:flex;justify-content:space-between;font-size:12.5px;padding:3px 0"><span>${nice[f]||f}</span><span class=${w>=0?'g':'r'}>${w>=0?'helps':'hurts'} ${Math.abs(w).toFixed(2)}</span></div>`).join(''):''}`;
 $('log').innerHTML=s.log.slice().reverse().map(l=>`<div class="${l.k}">${esc(l.m)}</div>`).join('');
}
async function tick(){last=await (await fetch('state.json',{cache:'no-store'})).json();render()}
tick();setInterval(()=>tick().catch(()=>{$('st').textContent='Bot not running';$('dot').className='dot bad'}),3000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/day/"):
            import os, re
            d = self.path[5:15]
            f = os.path.join("history", d + ".json")
            body = open(f, "rb").read() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and os.path.exists(f) else b"{}"
            ctype = "application/json"
        elif self.path.startswith("/state.json"):
            with LOCK:
                body = json.dumps(STATE).encode()
            ctype = "application/json"
        else:
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def serve(port=8000):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
