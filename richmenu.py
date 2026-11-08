#!/usr/bin/env python3
"""richmenu.py — ติดตั้งริชเมนู 6 ปุ่มให้ LINE OA (รันครั้งเดียว หรือรันซ้ำเพื่อแทนของเดิม)

    python3 richmenu.py          # ใช้ LINE_CHANNEL_ACCESS_TOKEN จาก environment
"""

import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.line.me/v2/bot"
DATA_API = "https://api-data.line.me/v2/bot"
NAME = "kiki-bot-menu"
W, H = 2500, 1686
BUTTONS = ["สถานะ", "ไม้ที่ถือ", "สรุปวันนี้", "หยุด", "เริ่ม", "ช่วยเหลือ"]


def call(method, url, token, body=None, ctype="application/json"):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token, "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        sys.exit("❌ LINE ตอบ HTTP %s: %s" % (e.code, e.read().decode(errors="replace")[:300]))


def main():
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token:
        sys.exit("❌ ยังไม่ได้ตั้ง LINE_CHANNEL_ACCESS_TOKEN (manage.sh ข้อ 11)")
    # ลบเมนูเก่าของบอทนี้ (ถ้ามี) ก่อน
    for m in call("GET", API + "/richmenu/list", token).get("richmenus", []):
        if m.get("name") == NAME:
            call("DELETE", API + "/richmenu/" + m["richMenuId"], token)
    cw, ch = W // 3, H // 2
    areas = [{"bounds": {"x": (i % 3) * cw, "y": (i // 3) * ch, "width": cw, "height": ch},
              "action": {"type": "message", "text": t}} for i, t in enumerate(BUTTONS)]
    menu = {"size": {"width": W, "height": H}, "selected": True, "name": NAME,
            "chatBarText": "เมนูบอทเทรด", "areas": areas}
    rid = call("POST", API + "/richmenu", token, menu)["richMenuId"]
    with open(os.path.join(HERE, "richmenu.png"), "rb") as f:
        call("POST", DATA_API + "/richmenu/%s/content" % rid, token, f.read(), "image/png")
    call("POST", API + "/user/all/richmenu/" + rid, token)
    print("✅ ติดตั้งริชเมนูแล้ว ปิดแชท OA แล้วเปิดใหม่จะเห็นเมนูด้านล่าง")


if __name__ == "__main__":
    main()
