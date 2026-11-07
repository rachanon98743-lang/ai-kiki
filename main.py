#!/usr/bin/env python3
"""
main.py — CEO ของบริษัท AI เทรดคริปโต: สั่งงานทุกแผนกเป็นรอบๆ + เปิดหน้าแดชบอร์ด

รัน:
    python main.py                 # ใช้ค่าใน config.json (เริ่มต้น = paper เงินจำลอง)
    python main.py --mode testnet  # เทรดจริงบน Binance Testnet (เงินปลอม)
    python main.py --mode live     # เงินจริง (ต้องยืนยันก่อน)
แดชบอร์ด: เปิด http://localhost:8080 ในเบราว์เซอร์
หยุดฉุกเฉิน: สร้างไฟล์ชื่อ STOP ในโฟลเดอร์นี้ (หยุดเปิดไม้ใหม่) หรือกด Ctrl+C
"""

import argparse
import json
import os
import sys
import threading
import time
import traceback

from binance_client import Binance, BinanceError
from departments import (RISK_PROFILES, AccountingDept, AIAnalystDept, ExecutionDept, ResearchDept,
                         RiskDept, StrategyDept, now_th)
import dashboard

HERE = os.path.dirname(os.path.abspath(__file__))


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Company:
    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = cfg["mode"]
        self.risk = cfg.get("risk", "mid")
        if self.risk not in RISK_PROFILES:
            sys.exit("risk ต้องเป็น low / mid / high")
        self.acct = AccountingDept(os.path.join(HERE, "company_%s.db" % self.mode))
        self.ex = Binance(self.mode, os.environ.get("BINANCE_API_KEY", ""), os.environ.get("BINANCE_API_SECRET", ""),
                          fee=cfg.get("fee", 0.001), paper_balance=cfg.get("paper_balance", 1000))
        if self.mode == "paper":
            saved = self.acct.get("paper_wallet")
            if saved:
                self.ex.paper = saved
        self.research = ResearchDept(self.ex, self.log)
        self.strategy = StrategyDept(self.log)
        self.ai = AIAnalystDept(cfg, self.acct, self.log)
        self.riskd = RiskDept(cfg, self.acct, self.log)
        self.exe = ExecutionDept(self.ex, self.acct, self.log)
        self.regime = "neutral"
        self.last_scan = 0
        self.last_research = []
        self.status = "starting"

    def log(self, dept, msg):
        line = "[%s] %-20s %s" % (now_th().strftime("%H:%M:%S"), dept, msg)
        print(line, flush=True)
        self.acct.log(dept, msg)

    def equity(self):
        pos = self.acct.open_positions()
        px = self.ex.prices([p["symbol"] for p in pos]) if pos else {}
        return self.ex.usdt_free() + sum(p["qty"] * px.get(p["symbol"], p["entry"]) for p in pos)

    def day_start_equity(self, eq):
        key = "day_start_" + now_th().date().isoformat()
        v = self.acct.get(key)
        if v is None:
            self.acct.set(key, eq)
            v = eq
        return v

    def save_paper(self):
        if self.mode == "paper":
            self.acct.set("paper_wallet", self.ex.paper)

    def start(self):
        self.log("CEO", "เปิดบริษัท โหมด %s ความเสี่ยง%s" % (self.mode.upper(), RISK_PROFILES[self.risk]["name"]))
        self.ex.sync_time()
        self.ex.load_filters()
        self.log("CEO", "โหลดข้อมูลเหรียญ USDT ที่เทรดได้ %d คู่" % len(self.ex.filters))
        if self.mode != "paper":
            self.log("CEO", "เงิน USDT ในบัญชี: %.2f" % self.ex.usdt_free())
        self.status = "running"

    def cycle(self):
        """1 รอบการทำงาน: เฝ้าสถานะ → (ถึงเวลา) สแกน → กลยุทธ์ → AI → ความเสี่ยง → ส่งคำสั่ง"""
        self.exe.monitor()
        eq = self.equity()
        self.acct.record_equity(eq)
        cfg = RISK_PROFILES[self.risk]
        if time.time() - self.last_scan < cfg["every_min"] * 60:
            self.save_paper()
            return
        self.last_scan = time.time()
        day0 = self.day_start_equity(eq)
        if not self.riskd.can_trade(eq, day0):
            return
        self.regime = self.research.market_regime()
        if self.regime == "bear" and self.cfg.get("skip_bear_market", True) and self.risk != "high":
            self.log("CEO", "ตลาดขาลง: งดเปิดไม้ใหม่รอบนี้ (ตั้ง skip_bear_market=false เพื่อปิด)")
            return
        held = {p["symbol"] for p in self.acct.open_positions()}
        self.last_research = self.research.scan(self.risk)
        props = self.strategy.proposals(self.last_research, self.risk, held)
        props = self.ai.review(props, self.regime)
        orders = self.riskd.approve(props, self.risk, self.regime, self.acct.open_positions(),
                                    self.ex.usdt_free(), eq, self.ex.filters)
        for o in orders:
            try:
                self.exe.buy(o, self.risk)
            except Exception as e:
                self.log("ฝ่ายเทรด", "ซื้อ %s ไม่สำเร็จ: %s" % (o["symbol"], e))
        self.save_paper()
        self.daily_report()

    def daily_report(self):
        today = now_th().date().isoformat()
        if self.acct.get("report_day") == today or now_th().hour < 21:
            return
        s = self.acct.summary()
        s["equity"] = round(self.equity(), 2)
        s["mode"], s["risk"], s["regime"] = self.mode, self.risk, self.regime
        letter = self.ai.daily_letter(s)
        self.log("CEO", "รายงานประจำวัน: " + json.dumps(s, ensure_ascii=False))
        if letter:
            self.log("CEO", "บทสรุปจาก AI: " + letter.replace("\n", " "))
        self.acct.set("report_day", today)

    def run_forever(self):
        self.start()
        while True:
            try:
                self.cycle()
            except BinanceError as e:
                self.log("CEO", "Binance ผิดพลาด: %s" % e)
                time.sleep(30)
            except Exception as e:
                self.log("CEO", "ผิดพลาด: %s" % e)
                traceback.print_exc()
                time.sleep(30)
            time.sleep(self.cfg.get("loop_seconds", 30))


def confirm_live(cfg):
    print("\n" + "=" * 60)
    print("⚠️  โหมด LIVE: บอทจะซื้อขายด้วยเงินจริงในบัญชี Binance ของคุณ")
    print("   ใช้ทุนไม่เกิน %.0f USDT, ขาดทุนต่อวันเกิน %s%% จะหยุดเปิดไม้ใหม่" % (
        cfg.get("max_capital_usdt", 100), cfg.get("max_daily_loss_pct", 5)))
    print("   ขาดทุนได้จริง ไม่มีอะไรรับประกันกำไร")
    print("=" * 60)
    # รันเป็น service บน VPS ไม่มีคนพิมพ์ยืนยัน: ให้ใส่ "live_confirmed": "ยืนยันเงินจริง" ใน config.json แทน
    if cfg.get("live_confirmed") == "ยืนยันเงินจริง":
        print("ยืนยันเงินจริงจาก config.json แล้ว")
        return
    try:
        ans = input('พิมพ์ "ยืนยันเงินจริง" เพื่อเริ่ม: ').strip()
    except EOFError:
        sys.exit('ไม่มีคนพิมพ์ยืนยัน: ใส่ "live_confirmed": "ยืนยันเงินจริง" ใน config.json')
    if ans != "ยืนยันเงินจริง":
        sys.exit("ยกเลิก")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--mode", choices=["paper", "testnet", "live"])
    ap.add_argument("--risk", choices=list(RISK_PROFILES))
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 = เปิดให้เครื่องอื่นเข้าได้ (ต้องตั้ง DASHBOARD_PASSWORD)")
    a = ap.parse_args()
    cfg = load_config(a.config)
    os.chdir(HERE)  # ไฟล์ STOP และฐานข้อมูลอยู่ในโฟลเดอร์โปรแกรมเสมอ
    if a.mode:
        cfg["mode"] = a.mode
    if a.risk:
        cfg["risk"] = a.risk
    if cfg["mode"] == "live":
        confirm_live(cfg)
    co = Company(cfg)
    threading.Thread(target=dashboard.serve, args=(co, a.port, a.host), daemon=True).start()
    print("แดชบอร์ด: http://localhost:%d" % a.port)
    try:
        co.run_forever()
    except KeyboardInterrupt:
        co.save_paper()
        print("\nปิดบริษัทแล้ว (สถานะที่ถืออยู่ยังอยู่ ถ้าตั้ง OCO ไว้ คำสั่งขายยังรออยู่บน Binance)")


if __name__ == "__main__":
    main()
