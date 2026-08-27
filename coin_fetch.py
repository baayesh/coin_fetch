#!/usr/bin/env python3
"""
coin_fetch.py — market + account snapshot for the ladder review.

Public data needs nothing. Account data (balances, open orders, fills) needs a
Binance API key with READ PERMISSION ONLY:

    Binance -> API Management -> Create API
      [x] Enable Reading
      [ ] Enable Spot & Margin Trading   <-- LEAVE OFF
      [ ] Enable Withdrawals             <-- LEAVE OFF
    Restrict access to your IP address.

    export BINANCE_KEY="..."      # never paste these into a chat
    export BINANCE_SECRET="..."

Without those env vars the script still runs and just skips the account section.

Drawn levels live in levels.json next to this file, e.g.:
    {"BTCUSDT": {"82896.24": "resistance", "62701.39": "support"},
     "DOGEUSDT": {"0.10103": "resistance"},
     "SOLUSDT": {"96.46": "breaking point"}}

Usage:  python3 coin_fetch.py > report.md
"""

import os, json, time, hmac, hashlib, pathlib
from urllib.parse import urlencode

import requests
import pandas as pd

BASE = "https://api.binance.com"
PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "TRXUSDT", "DOGEUSDT", "ADAUSDT"]
BTC_PAIRS = ["ETHBTC", "SOLBTC", "XRPBTC", "TRXBTC", "DOGEBTC", "ADABTC"]
TFS = ["1m", "1w", "1d", "4h", "1h"]
HERE = pathlib.Path(__file__).parent


# ---------------------------------------------------------------- indicators

def rsi(close, n=14):
    """Wilder's RSI — matches TradingView's RSI(14)."""
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss)


def atr(high, low, close, n=14):
    """Wilder's ATR — typical move size per candle."""
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


# ------------------------------------------------------------------ fetching

def klines(symbol, interval, limit=250):
    r = requests.get(f"{BASE}/api/v3/klines",
                     params={"symbol": symbol, "interval": interval, "limit": limit},
                     timeout=20)
    r.raise_for_status()
    df = pd.DataFrame(r.json()).iloc[:, :6]
    df.columns = ["t", "o", "h", "l", "c", "v"]
    return df.astype(float)


def signed(path, params=None):
    """Signed GET. Returns None if no credentials are configured."""
    key, secret = os.environ.get("BINANCE_KEY"), os.environ.get("BINANCE_SECRET")
    if not key or not secret:
        return None
    p = dict(params or {})
    p["timestamp"] = int(time.time() * 1000)
    p["recvWindow"] = 10000
    q = urlencode(p)
    p["signature"] = hmac.new(secret.encode(), q.encode(), hashlib.sha256).hexdigest()
    r = requests.get(f"{BASE}{path}", params=p, headers={"X-MBX-APIKEY": key}, timeout=20)
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------- report

def market_table():
    rows, spot = [], {}
    for pair in PAIRS:
        for tf in TFS:
            k = klines(pair, tf)
            o, h, l, c, v = (k[x] for x in "ohlcv")
            last = c.iloc[-1]
            if tf == "1h":
                spot[pair] = last
            ma = {p: c.rolling(p).mean().iloc[-1] for p in (7, 25, 99, 200)}
            a = atr(h, l, c).iloc[-1]
            rows.append({
                "Pair": pair, "TF": tf,
                "O": o.iloc[-1], "H": h.iloc[-1], "L": l.iloc[-1], "C": last,
                "MA7": ma[7], "MA25": ma[25], "MA99": ma[99], "MA200": ma[200],
                "RSI": round(rsi(c).iloc[-1], 2),
                "Chg%": round(100 * (last / c.iloc[-2] - 1), 2),
                "Vol": v.iloc[-1],
                "VolRatio": round(v.iloc[-1] / v.tail(20).mean(), 2),
                "ATR": round(a, 8),
                "ATR%": round(100 * a / last, 2),
                "SwingH30": h.tail(30).max(), "SwingL30": l.tail(30).min(),
                "SwingH90": h.tail(90).max(), "SwingL90": l.tail(90).min(),
            })
    return pd.DataFrame(rows), spot


def btc_ratio_table():
    """Alt priced in BTC — shows rotation directly, not by comparing percentages."""
    rows = []
    for pair in BTC_PAIRS:
        k = klines(pair, "1d", limit=40)
        c = k["c"]
        rows.append({
            "Pair": pair, "Close": c.iloc[-1],
            "1d%": round(100 * (c.iloc[-1] / c.iloc[-2] - 1), 2),
            "7d%": round(100 * (c.iloc[-1] / c.iloc[-8] - 1), 2),
            "30d%": round(100 * (c.iloc[-1] / c.iloc[-31] - 1), 2),
        })
    return pd.DataFrame(rows)


def account_section(spot):
    acct = signed("/api/v3/account")
    if acct is None:
        return "\n## Account\n\n_No API credentials set — balances and orders skipped._\n"

    out = ["\n## Balances\n", "| Asset | Free | Locked | Total | USD |", "|---|---|---|---|---|"]
    total_usd = 0.0
    for b in acct["balances"]:
        free, locked = float(b["free"]), float(b["locked"])
        if free + locked <= 0:
            continue
        asset = b["asset"]
        px = 1.0 if asset in ("USDT", "FDUSD", "USDC") else spot.get(asset + "USDT")
        usd = (free + locked) * px if px else None
        if usd is not None:
            total_usd += usd
        out.append(f"| {asset} | {free:.8f} | {locked:.8f} | {free+locked:.8f} | "
                   f"{'%.2f' % usd if usd is not None else '?'} |")
    out.append(f"\n**Total: ${total_usd:.2f}**\n")

    orders = signed("/api/v3/openOrders") or []
    out += ["\n## Open orders\n",
            "| Pair | Side | Price | Qty | Total | Spot | Distance |", "|---|---|---|---|---|---|---|"]
    for o in sorted(orders, key=lambda x: (x["symbol"], x["side"])):
        price, qty = float(o["price"]), float(o["origQty"])
        s = spot.get(o["symbol"])
        dist = f"{100*(price/s-1):+.2f}%" if s else "?"
        out.append(f"| {o['symbol']} | {o['side']} | {price:g} | {qty:g} | "
                   f"{price*qty:.2f} | {s if s else '?'} | {dist} |")
    out.append(f"\n**{len(orders)} open orders**\n")

    since = int((time.time() - 3 * 86400) * 1000)
    out += ["\n## Fills, last 3 days\n",
            "| Time | Pair | Side | Price | Qty | Total | Fee |", "|---|---|---|---|---|---|---|"]
    for pair in PAIRS:
        for t in (signed("/api/v3/myTrades", {"symbol": pair, "startTime": since}) or []):
            ts = time.strftime("%m-%d %H:%M", time.localtime(t["time"] / 1000))
            side = "BUY" if t["isBuyer"] else "SELL"
            out.append(f"| {ts} | {pair} | {side} | {float(t['price']):g} | "
                       f"{float(t['qty']):g} | {float(t['quoteQty']):.2f} | "
                       f"{float(t['commission']):g} {t['commissionAsset']} |")
    return "\n".join(out)


def levels_section():
    f = HERE / "levels.json"
    if not f.exists():
        return "\n## Drawn levels\n\n_No levels.json found._\n"
    data = json.loads(f.read_text())
    out = ["\n## Drawn levels\n", "| Pair | Level | Note |", "|---|---|---|"]
    for pair, levels in data.items():
        for price, note in levels.items():
            out.append(f"| {pair} | {price} | {note} |")
    return "\n".join(out)


if __name__ == "__main__":
    stamp = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"# Coin Fetch Report\n\nGenerated: {stamp}\n")
    mkt, spot = market_table()
    print("## Market\n")
    print(mkt.to_markdown(index=False, floatfmt=".8g"))
    print("\n## Alt / BTC ratios\n")
    print(btc_ratio_table().to_markdown(index=False, floatfmt=".8g"))
    print(levels_section())
    print(account_section(spot))
