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
main{max-width:1100px;margin:auto;padding:12px}h1{font-size:18px}h3{margin:0 0 8px;font-size:15px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}
.s{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:8px}.s b{display:block;font-size:18px}.s span{color:#8b949e;font-size:12px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:5px;border-bottom:1px solid #30363d;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:#8b949e;font-weight:500}.sc{overflow:auto;max-height:360px}
.g{color:#3fb950}.r{color:#f85149}.a{color:#d29922}.m{color:#8b949e}.dept{color:#58a6ff}
button{padding:8px 14px;border-radius:8px;border:1px solid #30363d;background:#21262d;color:#e6edf3;cursor:pointer;font-size:14px}
button.pri{background:#58a6ff;color:#000;border:0;font-weight:600}
.live{background:#5a1010;padding:2px 8px;border-radius:6px}
.depts{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px}
.dp{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:8px;cursor:pointer}
.dp.on{border-color:#58a6ff;background:#13233a}.dp b{font-size:14px}.dp .last{font-size:12px;color:#8b949e;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;background:#30363d}.dot.act{background:#3fb950}
.bar{height:8px;background:#21262d;border-radius:4px;overflow:hidden;margin:4px 0 10px}.bar i{display:block;height:100%;background:#3fb950}
.bar i.w{background:#d29922}.bar i.x{background:#f85149}
label{display:block;color:#8b949e;font-size:12px;margin-top:8px}
input,select{width:100%;box-sizing:border-box;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:8px;font-size:15px}
.form{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:4px 10px}
details summary{cursor:pointer;color:#58a6ff}pre{white-space:pre-wrap;font-size:12px;color:#c9d1d9;margin:4px 0}
</style></head><body><main>
<h1>🏢 AI Trading Company <span id="mode"></span> <a href="/logout" style="float:right;font-size:13px;color:#8b949e">ออกจากระบบ</a></h1>

<div class="card"><h3>แผนกต่างๆ <span class="m" style="font-weight:400;font-size:12px">แตะเพื่อดูงานของแผนกนั้น</span></h3><div class="depts" id="depts"></div></div>

<div class="card"><div class="grid">
<div class="s"><span>มูลค่าพอร์ต (<span id="q">USDT</span>)</span><b id="eq">-</b></div>
<div class="s"><span>กำไรที่ปิดแล้ว</span><b id="pnl">-</b></div>
<div class="s"><span>ชนะ / ทั้งหมด</span><b id="wr">-</b></div>
<div class="s"><span>ภาวะตลาด</span><b id="reg">-</b></div></div>
<p><button id="stop">⏸ หยุดเปิดไม้ใหม่</button> <span class="m" id="stopTxt"></span></p></div>

<div class="card"><h3>🧠 ฝ่ายนักวิเคราะห์ AI · งบและการใช้ token</h3>
<div id="aiState" class="m"></div>
<div id="bars"></div>
<details><summary>⚙️ ตั้งงบ / เพดาน token</summary>
<div class="form">
<div><label>เปิดใช้ AI</label><select id="f_en"><option value="1">เปิด</option><option value="0">ปิด</option></select></div>
<div><label>รุ่น AI</label><select id="f_model"><option value="claude-haiku-5-5">Haiku 5.5 (ถูกสุด)</option><option value="claude-sonnet-5-5">Sonnet 5.5</option><option value="claude-opus-5-5">Opus 5.5 (แพงสุด)</option></select></div>
<div><label>งบต่อวัน (USD)</label><input id="f_day" type="number" step="0.01" min="0" max="100"></div>
<div><label>งบต่อเดือน (USD)</label><input id="f_month" type="number" step="0.1" min="0" max="1000"></div>
<div><label>token สูงสุดต่อวัน</label><input id="f_tok" type="number" step="1000" min="0" max="50000000"></div>
<div><label>token ตอบสูงสุดต่อครั้ง</label><input id="f_call" type="number" step="50" min="100" max="4000"></div>
</div>
<p><button class="pri" id="save">บันทึก</button> <span id="saveMsg" class="m"></span></p>
<p class="m" style="font-size:12px">ถึงเพดานไหนก่อน AI จะหยุดทันที บอทยังเทรดต่อตามกฎ ไม่ใช้ AI จนกว่าจะขึ้นวัน/เดือนใหม่</p>
</details>
<h3 style="margin-top:12px">ประวัติการเรียก AI</h3>
<div class="sc"><table><thead><tr><th>เวลา</th><th>งาน</th><th>token เข้า/ออก</th><th>ค่าใช้จ่าย</th></tr></thead><tbody id="calls"></tbody></table></div>
</div>

<div class="card"><h3>สถานะที่ถืออยู่</h3><div class="sc"><table><thead><tr><th>เหรียญ</th><th>จำนวน</th><th>ราคาซื้อ</th><th>ทุน</th><th>SL</th><th>TP</th><th>เหตุผล</th></tr></thead><tbody id="pos"></tbody></table></div></div>
<div class="card"><h3>ผลวิจัยล่าสุด</h3><div class="sc"><table><thead><tr><th>เหรียญ</th><th>ราคา</th><th>24ชม.</th><th>RSI</th><th>คะแนน</th><th>เหตุผล</th></tr></thead><tbody id="res"></tbody></table></div></div>
<div class="card"><h3>ประวัติการเทรด</h3><div class="sc"><table><thead><tr><th>เหรียญ</th><th>ซื้อ</th><th>ขาย</th><th>กำไร</th><th>เหตุผล</th><th>ปิดเมื่อ</th></tr></thead><tbody id="hist"></tbody></table></div></div>
<div class="card"><h3>บันทึกการทำงาน <span id="logTitle" class="m" style="font-weight:400"></span></h3><div class="sc"><table><tbody id="logs"></tbody></table></div></div>
</main><script>
const f=(n,d=2)=>Number(n).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
const c=v=>v>0?'g':v<0?'r':'m';const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
let sel=null, D=null, formLoaded=false;
const ago=t=>{if(!t)return'ยังไม่ทำงานวันนี้';const s=(Date.now()-new Date(t).getTime())/1000;return s<60?'เมื่อสักครู่':s<3600?Math.floor(s/60)+' นาทีที่แล้ว':Math.floor(s/3600)+' ชม.ที่แล้ว';};
function bar(label,used,lim,fmt){const p=lim>0?Math.min(100,used/lim*100):100;const cl=p>=100?'x':p>=80?'w':'';
 return `<div class="m" style="font-size:12px">${label}: <b style="color:#e6edf3">${fmt(used)}</b> / ${fmt(lim)}</div><div class="bar"><i class="${cl}" style="width:${p}%"></i></div>`;}
function renderLogs(){const L=D.logs.filter(l=>!sel||l.dept===sel);$('logTitle').textContent=sel?'· '+sel+' (แตะแผนกเดิมเพื่อดูทั้งหมด)':'· ทุกแผนก';
 $('logs').innerHTML=L.map(l=>`<tr><td class="m">${esc(l.t.slice(11,19))}</td><td class="dept">${esc(l.dept)}</td><td style="text-align:left;white-space:normal">${esc(l.msg)}</td></tr>`).join('')||'<tr><td class="m">ยังไม่มี</td></tr>';}
function renderDepts(){$('depts').innerHTML=D.depts.map(d=>{const a=D.activity[d.name]||{};const act=a.t&&(Date.now()-new Date(a.t).getTime())<20*60000;
 return `<div class="dp ${sel===d.name?'on':''}" data-n="${esc(d.name)}"><b><span class="dot ${act?'act':''}"></span>${d.icon} ${esc(d.name)}</b>
 <div class="m" style="font-size:12px">${ago(a.t)}${a.today?' · วันนี้ '+a.today+' งาน':''}${d.note?' · '+esc(d.note):''}</div><div class="last">${esc(a.last||'')}</div></div>`;}).join('');
 document.querySelectorAll('.dp').forEach(e=>e.onclick=()=>{sel=sel===e.dataset.n?null:e.dataset.n;renderDepts();renderLogs();});}
async function load(){try{const res=await fetch('/api/status');if(res.status===401){location.reload();return;}D=await res.json();
$('mode').innerHTML=D.mode.startsWith('live')?'<span class="live">เงินจริง'+esc(D.mode.slice(4))+'</span>':'<span class="m">'+esc(D.mode)+'</span>';
$('eq').textContent=f(D.equity);$('q').textContent=D.quote||'USDT';$('pnl').innerHTML='<span class="'+c(D.summary.realized_pnl)+'">'+f(D.summary.realized_pnl)+'</span>';
$('wr').textContent=D.summary.wins+' / '+D.summary.trades+' ('+D.summary.win_rate+'%)';$('reg').textContent=D.regime;
$('stopTxt').textContent=D.stopped?'หยุดเปิดไม้ใหม่อยู่ (ไม้เดิมยังถูกเฝ้า)':'';$('stop').textContent=D.stopped?'▶ กลับมาเปิดไม้ใหม่':'⏸ หยุดเปิดไม้ใหม่';
const A=D.ai,u=A.usage,l=A.limits;
$('aiState').innerHTML=!A.has_key?'⚪ ยังไม่ได้ใส่ Claude API key (เมนู manage.sh ข้อ 2) บอทใช้กฎอย่างเดียว':!A.enabled?'⚪ ปิด AI อยู่':A.over.length?'🔴 ถึงเพดานแล้ว: '+esc(A.over.join(', '))+' (AI หยุดชั่วคราว)':'🟢 ทำงานอยู่ · รุ่น '+esc(A.model)+' · วันนี้เรียก '+u.day_calls+' ครั้ง';
$('bars').innerHTML=bar('ค่าใช้จ่ายวันนี้',u.day_usd,l.day_usd,v=>'$'+f(v,4))+bar('ค่าใช้จ่ายเดือนนี้',u.month_usd,l.month_usd,v=>'$'+f(v,4))+bar('token วันนี้',u.day_tokens,l.day_tokens,v=>f(v,0));
if(!formLoaded){$('f_en').value=A.enabled_setting?'1':'0';$('f_model').value=A.model;$('f_day').value=l.day_usd;$('f_month').value=l.month_usd;$('f_tok').value=l.day_tokens;$('f_call').value=l.max_tokens_per_call;formLoaded=true;}
$('calls').innerHTML=A.calls.map(x=>`<tr><td class="m">${esc(x.t.slice(5,16).replace('T',' '))}</td><td style="text-align:left;white-space:normal"><details><summary>${esc(x.purpose)}</summary><pre>${esc(x.result)}</pre></details></td><td>${f(x.tin,0)} / ${f(x.tout,0)}</td><td>$${f(x.usd,5)}</td></tr>`).join('')||'<tr><td class="m">ยังไม่มี</td></tr>';
$('pos').innerHTML=D.positions.map(p=>`<tr><td>${esc(p.symbol)}</td><td>${f(p.qty,6)}</td><td>${f(p.entry,6)}</td><td>${f(p.cost)}</td><td>${f(p.sl,6)}</td><td>${f(p.tp,6)}</td><td class="m">${esc(p.why)}</td></tr>`).join('')||'<tr><td class="m">ยังไม่มี</td></tr>';
$('res').innerHTML=D.research.map(r=>`<tr><td>${esc(r.symbol)}</td><td>${f(r.price,6)}</td><td class="${c(r.chg24)}">${f(r.chg24)}%</td><td>${f(r.rsi,0)}</td><td><b>${r.score}</b></td><td class="m">${esc(r.why.join(', '))}</td></tr>`).join('')||'<tr><td class="m">ยังไม่สแกน</td></tr>';
$('hist').innerHTML=D.closed.map(p=>`<tr><td>${esc(p.symbol)}</td><td>${f(p.entry,6)}</td><td>${f(p.exit,6)}</td><td class="${c(p.pnl)}">${f(p.pnl)}</td><td>${esc(p.reason)}</td><td class="m">${esc((p.closed||'').slice(5,16))}</td></tr>`).join('')||'<tr><td class="m">ยังไม่มี</td></tr>';
renderDepts();renderLogs();
}catch(e){}}
$('stop').onclick=async()=>{await fetch('/api/toggle-stop',{method:'POST'});load();};
$('save').onclick=async()=>{const body={ai_enabled:$('f_en').value==='1',ai_model:$('f_model').value,ai_daily_budget_usd:+$('f_day').value,ai_monthly_budget_usd:+$('f_month').value,ai_daily_token_limit:+$('f_tok').value,ai_max_tokens_per_call:+$('f_call').value};
 const r=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json().catch(()=>({}));
 $('saveMsg').textContent=r.ok?'✅ บันทึกแล้ว':'❌ '+(j.error||'บันทึกไม่ได้');formLoaded=false;load();};
load();setInterval(load,10000);
</script></body></html>"""

DEPTS = [("👔", "CEO"), ("🔎", "ฝ่ายวิจัยตลาด"), ("♟️", "ฝ่ายกลยุทธ์"), ("🧠", "ฝ่ายนักวิเคราะห์ AI"),
         ("🛡️", "ฝ่ายบริหารความเสี่ยง"), ("⚡", "ฝ่ายเทรด"), ("📒", "ฝ่ายบัญชี")]
SETTINGS = {  # ชื่อ: (ชนิด, ต่ำสุด, สูงสุด)
    "ai_enabled": (bool, None, None), "ai_model": (str, None, None),
    "ai_daily_budget_usd": (float, 0, 100), "ai_monthly_budget_usd": (float, 0, 1000),
    "ai_daily_token_limit": (int, 0, 50_000_000), "ai_max_tokens_per_call": (int, 100, 4000),
}
MODELS = {"claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"}


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
                }
                usage, limits, over = co.ai.budget_status()
                data["ai"] = {"has_key": bool(co.ai.key), "enabled": co.ai.enabled,
                              "enabled_setting": bool(co.ai.setting("ai_enabled", True)), "model": co.ai.model,
                              "usage": usage, "limits": limits, "over": over, "calls": co.acct.recent_ai_calls(30)}
                data["activity"] = co.acct.dept_activity()
                data["depts"] = [{"icon": i, "name": n, "note": ("Claude " + co.ai.model.split("-")[1].title()) if "AI" in n and co.ai.enabled else ("ปิดอยู่" if "AI" in n else "")} for i, n in DEPTS]
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
            if self.path == "/api/settings":
                length = min(int(self.headers.get("Content-Length", 0) or 0), 5000)
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                    clean = {}
                    for k, v in body.items():
                        if k not in SETTINGS:
                            continue
                        typ, lo, hi = SETTINGS[k]
                        v = typ(v)
                        if typ in (int, float) and not (lo <= v <= hi):
                            raise ValueError("%s ต้องอยู่ระหว่าง %s ถึง %s" % (k, lo, hi))
                        if k == "ai_model" and v not in MODELS:
                            raise ValueError("รุ่นไม่ถูกต้อง")
                        clean[k] = v
                except (ValueError, TypeError) as e:
                    return self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8")
                for k, v in clean.items():
                    company.acct.set("set_" + k, v)
                company.log("CEO", "ปรับงบ AI จากแดชบอร์ด: " + ", ".join("%s=%s" % kv for kv in clean.items()))
                return self._send(200, "{}", "application/json")
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
