"""Tiny local web dashboard: http://localhost:8000 (no login, only on your computer)."""
from __future__ import annotations
import json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"equity": [], "positions": [], "trades": [], "log": [], "charts": {}, "tickers": [], "stats": {}, "status": "Starting", "broker": ""}
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
.empty{color:var(--mut);padding:18px 4px;text-align:center}.legend{display:flex;gap:14px;font-size:11.5px;color:var(--mut);text-transform:none;letter-spacing:0;font-weight:500}
.legend b{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
@media(max-width:1000px){.kpis{grid-template-columns:1fr 1fr}.kpis .card:first-child{grid-column:1/-1}.grid{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
<div class="top"><div class="brand"><div class="logo"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/></svg></div>
<div><h1>Game-Theory Bot</h1><small id="brk">-</small></div></div>
<div style="display:flex;gap:8px;flex-wrap:wrap"><span class="pill" id="guard">-</span><span class="pill"><span class="dot" id="dot"></span><span id="st">connecting...</span></span></div></div>
<div class="kpis">
 <div class="card"><h2>Account equity <span class="sub" id="tot"></span></h2><div class="big" id="eq">-</div><svg id="ec" viewBox="0 0 600 70" preserveAspectRatio="none" width="100%" height="70"></svg></div>
 <div class="card"><h2>Today</h2><div class="mid" id="day">-</div><div class="sub" id="dayp"></div></div>
 <div class="card"><h2>Win rate</h2><div class="mid" id="wr">-</div><div class="sub" id="nt"></div></div>
 <div class="card"><h2>Trades today</h2><div class="mid" id="td">-</div><div class="bar"><i id="tdb" style="width:0"></i></div></div>
 <div class="card"><h2>Open</h2><div class="mid" id="op">-</div><div class="sub" id="opp"></div></div>
</div>
<div class="tick" id="tick"></div>
<div class="grid">
 <div class="stack">
  <div class="card"><h2><span id="ctitle">Chart</span><span class="legend"><span><b style="background:var(--g)"></b>Buy</span><span><b style="background:var(--y)"></b>Exit</span><span><b style="background:transparent;border:1px dashed var(--mut)"></b>Day high / low</span></span></h2>
   <svg id="main" viewBox="0 0 800 300" preserveAspectRatio="none" width="100%" height="300"></svg></div>
  <div class="card"><h2>Open positions</h2><div id="pos"></div></div>
  <div class="card"><h2>Trade history</h2><div class="scroll" id="tr"></div></div>
 </div>
 <div class="stack"><div class="card"><h2>Bot brain (self-learning, runs on your computer)</h2><div id="brain"></div></div><div class="card"><h2>Live activity - why it does what it does</h2><div class="scroll log" id="log" style="max-height:700px"></div></div></div>
</div></div>
<script>
const $=id=>document.getElementById(id);
const money=(x,d=2)=>x==null?'-':(x<0?'-$':'$')+Math.abs(x).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d});
const sgn=x=>(x>=0?'+':'')+money(x);const cls=x=>x>=0?'g':'r';const px=v=>v==null?'-':v>=1000?v.toLocaleString(undefined,{maximumFractionDigits:2}):v.toFixed(2);
let sel=null;
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
 let m='';for(const k of c.marks){const i=c.t.lastIndexOf(k.t);if(i<0)continue;const x=X(i),y=Y(k.px);
  m+=k.k=='exit'?`<circle cx=${x} cy=${y} r=6 fill=#ffc861 stroke=#07090f stroke-width=2 />`:
   `<path d="M${x-7},${y+11}L${x+7},${y+11}L${x},${y}Z" fill="${k.k=='buy'?'#22d39a':'#ff5c7a'}" stroke=#07090f stroke-width=1.5 />`}
 el.innerHTML=`<defs><linearGradient id=mg x1=0 y1=0 x2=0 y2=1><stop offset=0 stop-color="${col}" stop-opacity=.28 /><stop offset=1 stop-color="${col}" stop-opacity=0 /></linearGradient></defs>${g}
 <polyline points="${pl(c.hod)}" fill=none stroke="rgba(34,211,154,.45)" stroke-dasharray="5 5" vector-effect=non-scaling-stroke />
 <polyline points="${pl(c.lod)}" fill=none stroke="rgba(255,92,122,.45)" stroke-dasharray="5 5" vector-effect=non-scaling-stroke />
 <polygon points="0,${H} ${pl(c.c)} ${W},${H}" fill="url(#mg)"/><polyline points="${pl(c.c)}" fill=none stroke="${col}" stroke-width=2.2 vector-effect=non-scaling-stroke stroke-linejoin=round />${m}
 <text x=6 y=16 fill=#5d6676 font-size=11>${c.t[0]}</text><text x=6 y=${H-6} fill=#5d6676 font-size=11>${c.t.at(-1)}</text>`}
async function tick(){
 const s=await (await fetch('state.json',{cache:'no-store'})).json();
 const e=s.equity.at(-1)||{v:0,day:0,tot:0},st=s.stats||{};
 $('eq').textContent=money(e.v);$('tot').innerHTML=`<span class=${cls(e.tot)}>${sgn(e.tot)} all time</span>`;
 $('day').innerHTML=`<span class=${cls(e.day)}>${sgn(e.day)}</span>`;$('dayp').textContent=e.v?((e.day/(e.v-e.day))*100).toFixed(2)+'% today':'';
 $('wr').textContent=st.win==null?'-':st.win+'%';$('nt').textContent=(st.n||0)+' closed trades';
 $('td').textContent=`${st.trades_today||0} / ${st.max_trades||0}`;$('tdb').style.width=((st.trades_today||0)/(st.max_trades||1)*100)+'%';
 $('ec').innerHTML=area(s.equity.map(x=>x.v),600,70,'#6aa8ff','eg');
 $('brk').textContent=s.broker||'';$('st').textContent=s.status;
 $('dot').className='dot'+(s.status.startsWith('Live')?'':s.status.startsWith('Halted')?' bad':' off');
 $('guard').innerHTML=st.halted?'<span class=r>Loss limit hit - no new trades</span>':`Risk ${(st.risk*100).toFixed(2)}%/trade · stop day at -${(st.max_loss*100).toFixed(0)}%`;
 const upl=s.positions.reduce((a,p)=>a+p.pnl,0);$('op').textContent=s.positions.length;$('opp').innerHTML=s.positions.length?`<span class=${cls(upl)}>${sgn(upl)} unrealized</span>`:'flat';
 if(!sel&&s.tickers.length)sel=s.tickers[0].sym;
 $('tick').innerHTML=s.tickers.map(t=>{const c=s.charts[t.sym]||{c:[]},ch=t.last&&t.open?(t.last/t.open-1)*100:null;
  return`<div class="card tk ${t.sym==sel?'sel':''}" onclick="sel='${t.sym}';tick()"><div class=row><span class=sym>${t.sym}</span><span class="badge ${t.crypto?'':'etf'}">${t.crypto?'CRYPTO 24/7':'ETF'}</span></div>
  <div class=row style="margin-top:4px"><span class=mid style="font-size:17px">${t.last?'$'+px(t.last):'-'}</span><span class="${ch==null?'sub':cls(ch)}" style="font-size:12.5px;font-weight:600">${ch==null?(t.live?'':'closed'):(ch>=0?'+':'')+ch.toFixed(2)+'%'}</span></div>
  <svg viewBox="0 0 160 34" preserveAspectRatio="none" width=100% height=34>${area(c.c.slice(-120),160,34,ch==null||ch>=0?'#22d39a':'#ff5c7a','s'+t.sym.replace('/',''))}</svg></div>`}).join('');
 if(sel&&s.charts[sel]){$('ctitle').textContent=sel+' · 1-minute';mainChart(s.charts[sel])}
 $('pos').innerHTML=s.positions.length?`<table><tr><th>Symbol</th><th>Qty</th><th>Entry</th><th>Last</th><th>P&L</th><th>Stop</th><th>Target</th><th>Setup</th></tr>${s.positions.map(p=>
  `<tr><td><b>${p.sym}</b></td><td>${+p.qty.toFixed(6)}</td><td>${px(p.entry)}</td><td>${px(p.last)}</td><td class=${cls(p.pnl)}><b>${sgn(p.pnl)}</b></td><td class=r>${px(p.stop)}</td><td class=g>${px(p.target)}</td><td class=sub>${p.reason}</td></tr>`).join('')}</table>`
  :'<div class=empty>No open positions - waiting for a setup</div>';
 $('tr').innerHTML=s.trades.length?`<table><tr><th>Time</th><th>Symbol</th><th></th><th>Qty</th><th>Price</th><th>P&L</th><th>Reason</th></tr>${s.trades.slice().reverse().map(t=>
  `<tr><td class=sub>${t.t}</td><td><b>${t.sym}</b></td><td><span class="side ${t.side}">${t.side}</span></td><td>${+(+t.qty).toFixed(6)}</td><td>${px(t.px)}</td><td class=${t.side=='EXIT'?cls(t.pnl):''}>${t.side=='EXIT'?sgn(t.pnl):''}</td><td class=sub>${t.reason}</td></tr>`).join('')}</table>`
  :'<div class=empty>No trades yet today</div>';
 const br=s.brain||{n:0,min:30,factors:[]};const nice={breakout:'Breakout setup',bounce:'Bounce setup',short:'Short trade',crypto:'Crypto',dist_extreme_atr:'Distance below day high',range_pos:'Position in day range',trend_30:'30-min trend',vol_ratio:'Volume picking up',atr_pct:'Market volatility',minutes_open:'Later in the day',bounce_n:'Bounce number',reward_risk:'Reward/risk'};
 $('brain').innerHTML=`<div class=row style="display:flex;justify-content:space-between"><span class=mid style="font-size:18px">${br.off?'Off':br.n<br.min?'Learning':'Filtering'}</span><span class=sub>${br.n} trades learned · ${br.n?Math.round(100*br.wins/br.n):0}% won</span></div>
 <div class=bar><i style="width:${Math.min(100,br.n/br.min*100)}%"></i></div><div class=sub style="margin:8px 0 6px">${br.n<br.min?`Takes every setup until it has seen ${br.min} trades, then skips ones it predicts will lose.`:'Skips setups with under 45% predicted win chance.'}</div>
 ${br.n?br.factors.map(([f,w])=>`<div style="display:flex;justify-content:space-between;font-size:12.5px;padding:3px 0"><span>${nice[f]||f}</span><span class=${w>=0?'g':'r'}>${w>=0?'helps':'hurts'} ${Math.abs(w).toFixed(2)}</span></div>`).join(''):''}`;
 $('log').innerHTML=s.log.slice().reverse().map(l=>`<div class="${l.k}">${l.m.replace(/</g,'&lt;')}</div>`).join('');
}
tick();setInterval(()=>tick().catch(()=>{$('st').textContent='Bot not running';$('dot').className='dot bad'}),3000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/state.json"):
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
