"""Tiny local web dashboard: http://localhost:8000 (no login, only on your computer)."""
import json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"equity": [], "positions": [], "trades": [], "log": [], "charts": {}, "status": "starting"}
LOCK = threading.Lock()

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Paper Trading Bot</title>
<style>
body{margin:0;font:14px system-ui,sans-serif;background:#0f1115;color:#e6e6e6}
header{padding:14px 20px;border-bottom:1px solid #222;display:flex;gap:28px;flex-wrap:wrap;align-items:baseline}
h1{font-size:18px;margin:0}.k{color:#888;font-size:12px}.v{font-size:22px;font-weight:600}
.g{color:#3fb950}.r{color:#f85149}main{padding:16px 20px;display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(420px,1fr))}
.card{background:#161a21;border:1px solid #222;border-radius:8px;padding:12px}.card h2{font-size:14px;margin:0 0 8px;color:#aaa}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:4px 6px;text-align:left;border-bottom:1px solid #222}
#log{font:12px ui-monospace,monospace;max-height:300px;overflow:auto;white-space:pre-wrap}
</style></head><body>
<header><h1>Paper Trading Bot</h1>
<div><div class="k">Equity</div><div class="v" id="eq">-</div></div>
<div><div class="k">Today</div><div class="v" id="day">-</div></div>
<div><div class="k">Total</div><div class="v" id="tot">-</div></div>
<div><div class="k">Status</div><div id="st">-</div></div></header>
<main>
<div class="card"><h2>Equity</h2><svg id="ec" viewBox="0 0 600 180" width="100%"></svg></div>
<div class="card"><h2>Open positions</h2><table id="pos"></table></div>
<div id="charts" style="display:contents"></div>
<div class="card"><h2>Trades</h2><div style="max-height:300px;overflow:auto"><table id="tr"></table></div></div>
<div class="card"><h2>Bot log (why it's doing what it's doing)</h2><div id="log"></div></div>
</main>
<script>
const money=x=>(x<0?'-$':'$')+Math.abs(x).toLocaleString(undefined,{maximumFractionDigits:2});
const cls=x=>x>=0?'g':'r';let charts={};
function line(a,col){if(a.length<2)return '<text x=10 y=20 fill=#888>collecting data</text>';const lo=Math.min(...a),hi=Math.max(...a);
 return `<polyline fill=none stroke="${col}" stroke-width=2 points="${a.map((v,i)=>i/(a.length-1)*600+','+(172-(v-lo)/((hi-lo)||1)*164)).join(' ')}"/><text x=4 y=14 fill=#888 font-size=11>${money(hi)}</text><text x=4 y=178 fill=#888 font-size=11>${money(lo)}</text>`}
async function tick(){
 const s=await (await fetch('state.json')).json();
 const e=s.equity.at(-1)||{v:0,day:0,tot:0};
 eq.textContent=money(e.v);day.innerHTML=`<span class=${cls(e.day)}>${money(e.day)}</span>`;
 tot.innerHTML=`<span class=${cls(e.tot)}>${money(e.tot)}</span>`;st.textContent=s.status;
 ec.innerHTML=line(s.equity.map(x=>x.v),'#58a6ff');
 pos.innerHTML='<tr><th>Sym</th><th>Qty</th><th>Entry</th><th>Last</th><th>P&L</th><th>Stop</th><th>Target</th><th>Why</th></tr>'+
  (s.positions.map(p=>`<tr><td>${p.sym}</td><td>${p.qty}</td><td>${p.entry.toFixed(2)}</td><td>${p.last.toFixed(2)}</td><td class=${cls(p.pnl)}>${money(p.pnl)}</td><td>${p.stop.toFixed(2)}</td><td>${p.target.toFixed(2)}</td><td>${p.reason}</td></tr>`).join('')||'<tr><td colspan=8>Flat - waiting for a setup</td></tr>');
 tr.innerHTML='<tr><th>Time</th><th>Sym</th><th>Side</th><th>Qty</th><th>Price</th><th>P&L</th><th>Reason</th></tr>'+
  s.trades.slice().reverse().map(t=>`<tr><td>${t.t}</td><td>${t.sym}</td><td>${t.side}</td><td>${t.qty}</td><td>${t.px.toFixed(2)}</td><td class=${cls(t.pnl)}>${t.side=='EXIT'?money(t.pnl):''}</td><td>${t.reason}</td></tr>`).join('');
 log.textContent=s.log.slice().reverse().join('\n');
 for(const [sym,c] of Object.entries(s.charts)){
  if(!charts[sym]){const d=document.createElement('div');d.className='card';d.innerHTML=`<h2>${sym} - price, high/low of day (dashed), <span class=g>▲ buy</span> <span class=r>▼ short</span> <span style=color:#d29922>● exit</span></h2><svg viewBox="0 0 600 220" width="100%"></svg>`;
   document.getElementById('charts').appendChild(d);charts[sym]=d.querySelector('svg');}
  const all=c.c.concat(c.hod,c.lod);if(!all.length){charts[sym].innerHTML='<text x=10 y=20 fill=#888>waiting for bars</text>';continue}
  const lo=Math.min(...all),hi=Math.max(...all),W=600,H=220,n=Math.max(c.c.length-1,1);
  const X=i=>i/n*W,Y=v=>H-8-(v-lo)/((hi-lo)||1)*(H-16);
  const pl=(a,col,dash)=>`<polyline fill=none stroke="${col}" stroke-width=1.5 ${dash?'stroke-dasharray="4 4"':''} points="${a.map((v,i)=>X(i)+','+Y(v)).join(' ')}"/>`;
  let m='';for(const k of c.marks){const i=c.t.lastIndexOf(k.t);if(i<0)continue;const x=X(i),y=Y(k.px);
   m+=k.k=='exit'?`<circle cx=${x} cy=${y} r=5 fill=#d29922 />`:k.k=='buy'?`<path d="M${x-6},${y+8}L${x+6},${y+8}L${x},${y-2}Z" fill=#3fb950 />`:`<path d="M${x-6},${y-8}L${x+6},${y-8}L${x},${y+2}Z" fill=#f85149 />`}
  charts[sym].innerHTML=pl(c.hod,'#3fb95088',1)+pl(c.lod,'#f8514988',1)+pl(c.c,'#e6e6e6')+m+
   `<text x=4 y=14 fill=#888 font-size=11>${hi.toFixed(2)}</text><text x=4 y=${H-2} fill=#888 font-size=11>${lo.toFixed(2)}</text>`;}
}
tick();setInterval(()=>tick().catch(()=>st.textContent='bot not running'),3000);
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
