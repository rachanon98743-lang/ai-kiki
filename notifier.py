"""
notifier.py — ส่งแจ้งเตือนเข้า LINE ผ่าน LINE Messaging API (LINE Notify ปิดบริการไปแล้ว)

ตั้งค่าใน /root/bot.env (ใช้ manage.sh ข้อ 11 ได้):
    LINE_CHANNEL_ACCESS_TOKEN=...   (Channel access token แบบ long-lived)
    LINE_USER_ID=U...               (Your user ID ในหน้า Basic settings ของ channel)

แพ็กเกจฟรีของ LINE OA ไทยส่งได้ 300 ข้อความ/เดือน จึงมี:
  - เพดานต่อเดือน (line_monthly_limit ใน config.json, เริ่มต้น 280) เกินแล้วส่งเฉพาะเรื่องด่วน
  - กันข้อความซ้ำ: ข้อความประเภทเดียวกันส่งไม่ถี่กว่าที่กำหนด (เช่น error ไม่เกินชั่วโมงละครั้ง)
ไม่ได้ตั้ง token = ไม่ส่งอะไร บอททำงานปกติ
"""

import json
import os
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "line_state.json")
API = "https://api.line.me/v2/bot/message/push"


class LineNotifier:
    def __init__(self, cfg=None, prefix="🤖 บอทเทรด"):
        cfg = cfg or {}
        self.token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
        self.to = os.environ.get("LINE_USER_ID", "").strip()
        self.monthly_limit = int(cfg.get("line_monthly_limit", 280))
        self.prefix = prefix
        self.lock = threading.Lock()

    @property
    def enabled(self):
        return bool(self.token and self.to)

    def _load(self):
        try:
            with open(STATE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self, st):
        try:
            with open(STATE, "w", encoding="utf-8") as f:
                json.dump(st, f)
        except Exception:
            pass

    def send(self, text, key=None, every_sec=0, urgent=False):
        """ส่งข้อความ คืน True ถ้าส่งได้
        key + every_sec: ข้อความ key เดียวกันจะไม่ส่งซ้ำภายใน every_sec วินาที
        urgent: ส่งได้แม้ใกล้เพดานรายเดือน (แต่ไม่เกินโควตาจริง 300)"""
        if not self.enabled:
            return False
        with self.lock:
            st = self._load()
            month = time.strftime("%Y-%m")
            if st.get("month") != month:
                st = {"month": month, "count": 0, "last": {}}
            limit = self.monthly_limit + (15 if urgent else 0)
            if st["count"] >= limit:
                return False
            now = time.time()
            if key and now - st["last"].get(key, 0) < every_sec:
                return False
            if st["count"] + 1 == self.monthly_limit:
                text += "\n\n⚠️ โควตา LINE เดือนนี้ใกล้หมด จากนี้จะส่งเฉพาะเรื่องด่วน (ขาดทุนหนัก/บอทมีปัญหา)"
            body = json.dumps({"to": self.to, "messages": [
                {"type": "text", "text": ("%s\n%s" % (self.prefix, text))[:4900]}]}).encode()
            req = urllib.request.Request(API, data=body, method="POST", headers={
                "Content-Type": "application/json", "Authorization": "Bearer " + self.token})
            try:
                urllib.request.urlopen(req, timeout=15).read()
            except Exception as e:
                print("ส่ง LINE ไม่สำเร็จ:", e, flush=True)
                return False
            st["count"] += 1
            if key:
                st["last"][key] = now
            self._save(st)
            return True
