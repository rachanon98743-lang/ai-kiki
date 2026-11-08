"""dashboard.py — หน้าเว็บดูสถานะบริษัท (เปิดได้เฉพาะเครื่องตัวเอง http://localhost:8080)"""

import hmac
import http.cookies
import json
import os
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from departments import RISK_PROFILES

PAGE = r"""<!DOCTYPE html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Trading Company</title>
<style>
body{margin:0;background:#0d1117;color:#e6edf3;font:14px/1.5 system-ui,Tahoma,sans-serif}
main{max-width:1100px;margin:auto;padding:12px}h1{font-size:18px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}
.s{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:8px}.s b{display:block;font-size:18px}.s span{color:#8b949e;font-size:12px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:5px;border-bottom:1px solid #30363d;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:#8b949e;font-weight:500}.sc{overflow:auto;max-height:360px}
.g{color:#3fb950}.r{color:#f85149}.m{color:#8b949e}.dept{color:#58a6ff}
button{padding:8px 14px;border-radius:8px;border:1px solid #30363d;background:#21262d;color:#e6edf3;cursor:pointer}
.live{background:#5a1010;padding:2px 8px;border-radius:6px}.org{display:flex;flex-wrap:wrap;gap:6px}
.org div{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:6px 10px;font-size:12px}
</style></head><body><main>
<h1>🏢 AI Trading Company <span id="mode"></span> <a href="/logout" style="float:right;font-size:13px;color:#8b949e">ออกจากระบบ</a></h1>
<div class="card org" id="org"></div>
<div class="card"><div class="grid">
<div class="s"><span>มูลค่าพอร์ต (<span id="q">USDT</span>)</span><b id="eq">-</b></div>
<div class="s"><span>กำไรที่ปิดแล้ว</span><b id="pnl">-</b></div>
<div class="s"><span>ชนะ / ทั้งหมด</span><b id="wr">-</b></div>
<div class="s"><span>ภาวะตลาด</span><b id="reg">-</b></div>
<div class="s"><span>ค่า AI วันนี้</span><b id="ai">-</b></div></div>
<p><button id="stop">⏸ หยุดเปิดไม้ใหม่</button> <span class="m" id="stopTxt"></span></p></div>
<div class="card"><h3>สถานะที่ถืออยู่</h3><div class="sc"><table><thead><tr><th>เหรียญ</th><th>จำนวน</th><th>ราคาซื้อ</th><th>ทุน</th><th>SL</th><th>TP</th><th>OCO</th><th>เหตุผล</th></tr></thead><tbody id="pos"></tbody></table></div></div>
<div class="card"><h3>ผลวิจัยล่าสุด</h3><div class="sc"><table><thead><tr><th>เหรียญ</th><th>ราคา</th><th>24ชม.</th><th>RSI</th><th>คะแนน</th><th>เหตุผล</th></tr></thead><tbody id="res"></tbody></table></div></div>
<div class="card"><h3>ประวัติการเทรด</h3><div class="sc"><table><thead><tr><th>เหรียญ</th><th>ซื้อ</th><th>ขาย</th><th>กำไร</th><th>เหตุผล</th><th>ปิดเมื่อ</th></tr></thead><tbody id="hist"></tbody></table></div></div>
<div class="card"><h3>บันทึกการทำงานของแต่ละแผนก</h3><div class="sc"><table><tbody id="logs"></tbody></table></div></div>
</main><script>
const f=(n,d=2)=>Number(n).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
const c=v=>v>0?'g':v<0?'r':'m';const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
async function load(){try{const res=await fetch('/api/status');if(res.status===401){location.reload();return;}const d=await res.json();
$('mode').innerHTML=d.mode.startsWith('live')?'<span class="live">เงินจริง'+d.mode.slice(4)+'</span>':'<span class="m">'+esc(d.mode)+'</span>';
$('org').innerHTML=d.org.map(o=>'<div>'+o+'</div>').join('');
$('eq').textContent=f(d.equity);$('q').textContent=d.quote||'USDT';$('pnl').innerHTML='<span class="'+c(d.summary.realized_pnl)+'">'+f(d.summary.realized_pnl)+'</span>';
$('wr').textContent=d.summary.wins+' / '+d.summary.trades+' ('+d.summary.win_rate+'%)';$('reg').textContent=d.regime;
$('ai').textContent='$'+f(d.ai_cost,4);$('stopTxt').textContent=d.stopped?'หยุดเปิดไม้ใหม่อยู่ (ไม้เดิมยังถูกเฝ้า)':'';
$('stop').textContent=d.stopped?'▶ กลับมาเปิดไม้ใหม่':'⏸ หยุดเปิดไม้ใหม่';
$('pos').innerHTML=d.positions.map(p=>`<tr><td>${esc(p.symbol)}</td><td>${f(p.qty,6)}</td><td>${f(p.entry,6)}</td><td>${f(p.cost)}</td><td>${f(p.sl,6)}</td><td>${f(p.tp,6)}</td><td>${p.oco_id?'✓':'-'}</td><td class="m">${esc(p.why)}</td></tr>`).join('')||'<tr><td class="m">ยังไม่มี</td></tr>';
$('res').innerHTML=d.research.map(r=>`<tr><td>${esc(r.symbol)}</td><td>${f(r.price,6)}</td><td class="${c(r.chg24)}">${f(r.chg24)}%</td><td>${f(r.rsi,0)}</td><td><b>${r.score}</b></td><td class="m">${esc(r.why.join(', '))}</td></tr>`).join('')||'<tr><td class="m">ยังไม่สแกน</td></tr>';
$('hist').innerHTML=d.closed.map(p=>`<tr><td>${esc(p.symbol)}</td><td>${f(p.entry,6)}</td><td>${f(p.exit,6)}</td><td class="${c(p.pnl)}">${f(p.pnl)}</td><td>${esc(p.reason)}</td><td class="m">${esc((p.closed||'').slice(5,16))}</td></tr>`).join('')||'<tr><td class="m">ยังไม่มี</td></tr>';
$('logs').innerHTML=d.logs.map(l=>`<tr><td class="m">${esc(l.t.slice(11,19))}</td><td class="dept">${esc(l.dept)}</td><td style="text-align:left;white-space:normal">${esc(l.msg)}</td></tr>`).join('');
}catch(e){}}
$('stop').onclick=async()=>{await fetch('/api/toggle-stop',{method:'POST'});load();};
load();setInterval(load,10000);
</script></body></html>"""

ORG = ["👔 CEO", "🔎 ฝ่ายวิจัยตลาด", "♟️ ฝ่ายกลยุทธ์", "🧠 ฝ่ายนักวิเคราะห์ AI", "🛡️ ฝ่ายบริหารความเสี่ยง", "⚡ ฝ่ายเทรด", "📒 ฝ่ายบัญชี"]


LOGIN_PAGE = r"""<!DOCTYPE html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>เข้าสู่ระบบ</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0d1117;color:#e6edf3;font:15px system-ui,Tahoma,sans-serif}
form{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;width:min(320px,90vw)}
input,button{width:100%;box-sizing:border-box;padding:12px;margin-top:10px;border-radius:8px;font-size:16px}
input{background:#0d1117;color:#e6edf3;border:1px solid #30363d}button{background:#58a6ff;border:0;font-weight:600}
p{color:#f85149;min-height:1em}</style></head><body>
<form method="post" action="/login"><h2>🏢 AI Trading Company</h2>
<input type="password" name="password" placeholder="รหัสผ่าน" autofocus required>
<button>เข้าสู่ระบบ</button><p>%MSG%</p></form></body></html>"""

MAX_FAILS, LOCK_SECONDS, SESSION_SECONDS = 5, 15 * 60, 7 * 24 * 3600


def serve(company, port, host="127.0.0.1"):
    password = os.environ.get("DASHBOARD_PASSWORD", "")
    if host != "127.0.0.1" and len(password) < 10:
        company.log("CEO", "ไม่เปิดแดชบอร์ดสู่เครือข่าย: ต้องตั้ง DASHBOARD_PASSWORD ยาวอย่างน้อย 10 ตัวอักษร")
        host = "127.0.0.1"
    sessions = {}          # token -> หมดอายุเมื่อไร
    fails = {}             # ip -> (จำนวนครั้งที่ผิด, เวลาที่เริ่มนับ)
    lock = threading.Lock()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype, headers=None):
            b = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)

        def _authed(self):
            if not password:
                return True
            c = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
            tok = c["sid"].value if "sid" in c else ""
            with lock:
                exp = sessions.get(tok)
                if exp and exp > time.time():
                    return True
                sessions.pop(tok, None)
            return False

        def _login_page(self, msg=""):
            self._send(200, LOGIN_PAGE.replace("%MSG%", msg), "text/html; charset=utf-8")

        def do_GET(self):
            if not self._authed():
                if self.path.startswith("/api/"):
                    return self._send(401, "{}", "application/json")
                return self._login_page()
            if self.path == "/logout":
                c = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
                with lock:
                    sessions.pop(c["sid"].value if "sid" in c else "", None)
                return self._send(302, "", "text/plain", {"Location": "/", "Set-Cookie": "sid=; Max-Age=0; Path=/"})
            if self.path == "/api/status":
                co = company
                try:
                    eq = co.equity()
                except Exception:
                    eq = 0
                data = {
                    "mode": co.mode + (" · Binance TH" if co.ex.th else ""), "quote": co.ex.quote, "risk": RISK_PROFILES[co.risk]["name"], "regime": co.regime,
                    "equity": eq, "summary": co.acct.summary(), "ai_cost": co.acct.ai_cost_today(),
                    "positions": co.acct.open_positions(), "closed": co.acct.closed_positions(50),
                    "research": co.last_research[:30], "logs": co.acct.recent_logs(80),
                    "stopped": os.path.exists("STOP"),
                    "org": [o + (" (Claude: %s)" % co.ai.model if "AI" in o and co.ai.enabled else " (ปิดอยู่)" if "AI" in o else "") for o in ORG],
                }
                self._send(200, json.dumps(data, ensure_ascii=False, default=str), "application/json; charset=utf-8")
            else:
                self._send(200, PAGE, "text/html; charset=utf-8")

        def do_POST(self):
            ip = self.client_address[0]
            if self.path == "/login":
                with lock:
                    n, t0 = fails.get(ip, (0, time.time()))
                    if time.time() - t0 > LOCK_SECONDS:
                        n, t0 = 0, time.time()
                    if n >= MAX_FAILS:
                        return self._login_page("ใส่รหัสผิดหลายครั้ง ล็อกไว้ 15 นาที")
                length = min(int(self.headers.get("Content-Length", 0) or 0), 2000)
                form = urllib.parse.parse_qs(self.rfile.read(length).decode(errors="replace"))
                given = (form.get("password") or [""])[0]
                if password and hmac.compare_digest(given.encode(), password.encode()):
                    tok = secrets.token_urlsafe(32)
                    with lock:
                        sessions[tok] = time.time() + SESSION_SECONDS
                        fails.pop(ip, None)
                    company.log("CEO", "เข้าสู่ระบบแดชบอร์ดจาก %s" % ip)
                    return self._send(302, "", "text/plain", {
                        "Location": "/",
                        "Set-Cookie": "sid=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=%d" % (tok, SESSION_SECONDS)})
                with lock:
                    fails[ip] = (n + 1, t0)
                company.log("CEO", "ใส่รหัสแดชบอร์ดผิดจาก %s (ครั้งที่ %d)" % (ip, n + 1))
                time.sleep(1)
                return self._login_page("รหัสผ่านไม่ถูกต้อง")
            if not self._authed():
                return self._send(401, "{}", "application/json")
            if self.path == "/api/toggle-stop":
                if os.path.exists("STOP"):
                    os.remove("STOP")
                    company.log("CEO", "กลับมาเปิดไม้ใหม่ (สั่งจากแดชบอร์ด)")
                else:
                    open("STOP", "w").close()
                    company.log("CEO", "หยุดเปิดไม้ใหม่ (สั่งจากแดชบอร์ด)")
                self._send(200, "{}", "application/json")
            else:
                self._send(404, "", "text/plain")

    company.log("CEO", "แดชบอร์ดเปิดที่ %s:%d %s" % (host, port, "(มีรหัสผ่าน)" if password else "(เฉพาะเครื่องนี้)"))
    ThreadingHTTPServer((host, port), H).serve_forever()
