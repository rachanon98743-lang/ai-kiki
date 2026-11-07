"""
binance_client.py — ตัวเชื่อม Binance Spot (ใช้แค่ไลบรารีมาตรฐานของ Python)

3 โหมด:
  paper   : ใช้ราคาจริง แต่ซื้อขายจำลองในเครื่อง ไม่ต้องมี API key
  testnet : ส่งคำสั่งจริงไปที่ testnet.binance.vision (เงินปลอม) ต้องมี testnet key
  live    : ส่งคำสั่งจริงไปที่ Binance เงินจริง
"""

import hashlib
import hmac
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

LIVE_URL = "https://api.binance.com"
TESTNET_URL = "https://testnet.binance.vision"
DATA_URL = "https://data-api.binance.vision"  # ข้อมูลราคาสาธารณะ


class BinanceError(Exception):
    pass


def _round_down(x, step):
    if step <= 0:
        return x
    decimals = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    return round(math.floor(x / step + 1e-9) * step, decimals)


class Binance:
    def __init__(self, mode="paper", api_key="", api_secret="", fee=0.001, paper_balance=1000.0):
        self.mode = mode
        self.key, self.secret = api_key, api_secret
        self.base = {"live": LIVE_URL, "testnet": TESTNET_URL}.get(mode, LIVE_URL)
        self.data_base = TESTNET_URL if mode == "testnet" else DATA_URL
        self.fee = fee
        self.time_offset = 0
        self.filters = {}
        # สมุดบัญชีจำลองสำหรับโหมด paper
        self.paper = {"USDT": paper_balance}
        self._oid = 0
        if mode in ("live", "testnet") and not (api_key and api_secret):
            raise BinanceError("โหมด %s ต้องตั้ง BINANCE_API_KEY และ BINANCE_API_SECRET" % mode)

    # ------------------------------------------------------------ http
    def _request(self, method, path, params=None, signed=False, base=None):
        params = dict(params or {})
        headers = {"User-Agent": "ai-trading-company/1.0"}
        if signed:
            params["timestamp"] = int(time.time() * 1000) + self.time_offset
            params["recvWindow"] = 10000
            q = urllib.parse.urlencode(params)
            sig = hmac.new(self.secret.encode(), q.encode(), hashlib.sha256).hexdigest()
            q += "&signature=" + sig
            headers["X-MBX-APIKEY"] = self.key
        else:
            q = urllib.parse.urlencode(params)
        url = (base or self.base) + path
        data = None
        if method == "GET" or method == "DELETE":
            url += ("?" + q) if q else ""
        else:
            data = q.encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        for attempt in range(3):
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")
                if e.code in (429, 418):
                    time.sleep(10 * (attempt + 1))
                    continue
                if e.code == 451:
                    raise BinanceError("Binance ปฏิเสธเพราะตำแหน่ง IP (451) ต้องรันจากประเทศที่ Binance อนุญาต")
                raise BinanceError("HTTP %s %s: %s" % (e.code, path, body))
            except urllib.error.URLError as e:
                if attempt == 2:
                    raise BinanceError("เชื่อมต่อไม่ได้: %s" % e)
                time.sleep(3)
        raise BinanceError("ถูกจำกัดความถี่ (rate limit) ซ้ำหลายครั้ง")

    def public(self, path, params=None):
        try:
            return self._request("GET", path, params, base=self.data_base)
        except BinanceError:
            if self.mode == "testnet":
                raise
            return self._request("GET", path, params, base=LIVE_URL)

    # ------------------------------------------------------------ market data
    def sync_time(self):
        t = self.public("/api/v3/time")["serverTime"]
        self.time_offset = t - int(time.time() * 1000)

    def load_filters(self):
        info = self.public("/api/v3/exchangeInfo")
        for s in info["symbols"]:
            if s.get("status") != "TRADING" or s.get("quoteAsset") != "USDT":
                continue
            f = {x["filterType"]: x for x in s["filters"]}
            lot = f.get("LOT_SIZE", {})
            notional = f.get("NOTIONAL") or f.get("MIN_NOTIONAL") or {}
            price = f.get("PRICE_FILTER", {})
            self.filters[s["symbol"]] = {
                "base": s["baseAsset"],
                "step": float(lot.get("stepSize", 0) or 0),
                "min_qty": float(lot.get("minQty", 0) or 0),
                "tick": float(price.get("tickSize", 0) or 0),
                "min_notional": float(notional.get("minNotional", 5) or 5),
                "oco": bool(s.get("ocoAllowed")),
            }
        return self.filters

    def tickers_24h(self):
        return self.public("/api/v3/ticker/24hr")

    def klines(self, symbol, interval, limit=250):
        return self.public("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})

    def prices(self, symbols=None):
        if symbols:
            data = self.public("/api/v3/ticker/price", {"symbols": json.dumps(list(symbols), separators=(",", ":"))})
        else:
            data = self.public("/api/v3/ticker/price")
        return {d["symbol"]: float(d["price"]) for d in data}

    # ------------------------------------------------------------ account
    def balances(self):
        if self.mode == "paper":
            return dict(self.paper)
        acc = self._request("GET", "/api/v3/account", signed=True)
        return {b["asset"]: float(b["free"]) for b in acc["balances"] if float(b["free"]) > 0}

    def usdt_free(self):
        return self.balances().get("USDT", 0.0)

    # ------------------------------------------------------------ orders
    def market_buy(self, symbol, usdt):
        """ซื้อด้วยจำนวน USDT คืนค่า (จำนวนเหรียญสุทธิหลังหักค่าธรรมเนียม, ราคาเฉลี่ย, order id)"""
        f = self.filters[symbol]
        if self.mode == "paper":
            px = self.prices([symbol])[symbol]
            if self.paper.get("USDT", 0) < usdt:
                raise BinanceError("เงิน USDT จำลองไม่พอ")
            qty = _round_down(usdt / px * (1 - self.fee), f["step"])
            self.paper["USDT"] -= usdt
            self.paper[f["base"]] = self.paper.get(f["base"], 0) + qty
            self._oid += 1
            return qty, px, "paper-%d" % self._oid
        usdt = math.floor(usdt * 100) / 100
        r = self._request("POST", "/api/v3/order", {
            "symbol": symbol, "side": "BUY", "type": "MARKET",
            "quoteOrderQty": "%.2f" % usdt, "newOrderRespType": "FULL"}, signed=True)
        qty = float(r["executedQty"])
        spent = float(r["cummulativeQuoteQty"])
        fee_in_base = sum(float(x["commission"]) for x in r.get("fills", []) if x["commissionAsset"] == f["base"])
        net = _round_down(qty - fee_in_base, f["step"])
        return net, (spent / qty if qty else 0), str(r["orderId"])

    def market_sell(self, symbol, qty):
        f = self.filters[symbol]
        qty = _round_down(qty, f["step"])
        if self.mode == "paper":
            px = self.prices([symbol])[symbol]
            have = self.paper.get(f["base"], 0)
            qty = min(qty, have)
            self.paper[f["base"]] = have - qty
            got = qty * px * (1 - self.fee)
            self.paper["USDT"] = self.paper.get("USDT", 0) + got
            return got, px
        r = self._request("POST", "/api/v3/order", {
            "symbol": symbol, "side": "SELL", "type": "MARKET",
            "quantity": self._fmt(qty, f["step"]), "newOrderRespType": "FULL"}, signed=True)
        got = float(r["cummulativeQuoteQty"])
        q = float(r["executedQty"]) or 1
        fee_usdt = sum(float(x["commission"]) for x in r.get("fills", []) if x["commissionAsset"] == "USDT")
        return got - fee_usdt, got / q

    def place_oco_exit(self, symbol, qty, tp_price, sl_price):
        """ตั้งคำสั่งขายล่วงหน้าบนกระดาน: ทำกำไร (LIMIT_MAKER) + ตัดขาดทุน (STOP_LOSS_LIMIT)
        ข้อดี: ถึงโปรแกรมปิด/เน็ตหลุด คำสั่งก็ยังอยู่บน Binance"""
        if self.mode == "paper":
            return None
        f = self.filters[symbol]
        if not f["oco"]:
            return None
        qty = _round_down(qty, f["step"])
        tp = _round_down(tp_price, f["tick"])
        sl_stop = _round_down(sl_price, f["tick"])
        sl_limit = _round_down(sl_price * 0.995, f["tick"])  # เผื่อราคาไหลตอนหลุด stop
        r = self._request("POST", "/api/v3/orderList/oco", {
            "symbol": symbol, "side": "SELL", "quantity": self._fmt(qty, f["step"]),
            "aboveType": "LIMIT_MAKER", "abovePrice": self._fmt(tp, f["tick"]),
            "belowType": "STOP_LOSS_LIMIT", "belowStopPrice": self._fmt(sl_stop, f["tick"]),
            "belowPrice": self._fmt(sl_limit, f["tick"]), "belowTimeInForce": "GTC"}, signed=True)
        return str(r["orderListId"])

    def oco_status(self, list_id):
        """คืน 'open' ถ้ายังรออยู่, 'done' ถ้าขายไปแล้ว (โดน TP หรือ SL)"""
        r = self._request("GET", "/api/v3/orderList", {"orderListId": list_id}, signed=True)
        return "done" if r.get("listOrderStatus") == "ALL_DONE" else "open"

    def oco_fill(self, list_id):
        """ราคาและเงินที่ได้จริงจากคำสั่ง OCO ที่ขายไปแล้ว"""
        r = self._request("GET", "/api/v3/orderList", {"orderListId": list_id}, signed=True)
        sym = r["symbol"]
        for o in r["orders"]:
            od = self._request("GET", "/api/v3/order", {"symbol": sym, "orderId": o["orderId"]}, signed=True)
            if od["status"] == "FILLED":
                got = float(od["cummulativeQuoteQty"])
                q = float(od["executedQty"]) or 1
                return got * (1 - self.fee), got / q, od["type"]
        return 0.0, 0.0, "UNKNOWN"

    def cancel_oco(self, symbol, list_id):
        if self.mode == "paper" or not list_id:
            return
        self._request("DELETE", "/api/v3/orderList", {"symbol": symbol, "orderListId": list_id}, signed=True)

    @staticmethod
    def _fmt(x, step):
        if step <= 0 or step >= 1:
            return ("%f" % x).rstrip("0").rstrip(".")
        d = max(0, -int(math.floor(math.log10(step))))
        return ("%.*f" % (d, x))
