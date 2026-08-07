#!/usr/bin/env python3
"""
Daily Portfolio Report Generator — Meir
Micho Method: MA150-based technical signals
Free data: Yahoo Finance API (no API key required)
"""

import requests
import json
import time
import datetime
import sys
import re
from pathlib import Path

# ─── Portfolio Definition ────────────────────────────────────────────────────

PORTFOLIO = [
    {"ticker": "AMZN",    "name": "Amazon",           "shares": 62,    "currency": "USD", "avg": 178.40},
    {"ticker": "TSLA",    "name": "Tesla",             "shares": 14,    "currency": "USD", "avg": 242.10},
    {"ticker": "JOBY",    "name": "Joby Aviation",     "shares": 840,   "currency": "USD", "avg": 5.80},
    {"ticker": "NASA",    "name": "TEMA Space Innovators ETF", "shares": 190, "currency": "USD", "avg": 41.57},
    {"ticker": "BMNR",    "name": "Bitmine Immersion", "shares": 234,   "currency": "USD", "avg": 52.80},
    {"ticker": "QCOM",    "name": "Qualcomm",          "shares": 8,     "currency": "USD", "avg": 168.20},
    {"ticker": "META",    "name": "Meta Platforms",    "shares": 1,     "currency": "USD", "avg": 482.00},
    {"ticker": "ORCL",    "name": "Oracle",            "shares": 0.8,   "currency": "USD", "avg": 138.40},
    {"ticker": "MARA",    "name": "MARA Holdings",     "shares": 9,     "currency": "USD", "avg": 22.40},
    {"ticker": "PLTR",    "name": "Palantir",          "shares": 0.49,  "currency": "USD", "avg": 24.80},
    {"ticker": "ACCL.TA", "name": "אקסל סולושנס",     "shares": 14789, "currency": "ILS", "avg": 4.20},
    {"ticker": "MLSR.TA", "name": "מליסרון",          "shares": 37,    "currency": "ILS", "avg": 248.00},
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

# ─── Helper / Signal Functions ────────────────────────────────────────────────

def calc_rsi(closes, period=14):
    """RSI 14-day Wilder smoothing."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100
    return round(100 - 100 / (1 + avg_gain / avg_loss), 1)

_YF_SESSION = None

def _yahoo_session():
    """Session carrying the cookie + crumb that quoteSummary now requires.

    Yahoo started rejecting unauthenticated quoteSummary calls with
    401 "Invalid Crumb", which fetch_pe swallowed — every P/E silently became
    None. Built once and reused; returns (session, crumb) or (None, None).
    """
    global _YF_SESSION
    if _YF_SESSION is None:
        try:
            s = requests.Session()
            s.headers.update(HEADERS)
            try:
                s.get("https://fc.yahoo.com", timeout=10)   # sets the cookie
            except requests.RequestException:
                pass                                        # cookie may already be set
            crumb = s.get("https://query1.finance.yahoo.com/v1/test/getcrumb",
                          timeout=10).text.strip()
            _YF_SESSION = (s, crumb) if crumb and "<" not in crumb else (None, None)
        except Exception:
            _YF_SESSION = (None, None)
    return _YF_SESSION

def fetch_pe(ticker):
    """Fetch trailing P/E from Yahoo Finance quoteSummary. Returns None on failure."""
    session, crumb = _yahoo_session()
    if not session:
        return None
    try:
        url = (f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
               f"?modules=summaryDetail&crumb={crumb}")
        r = session.get(url, timeout=10)
        res = r.json().get("quoteSummary", {}).get("result", [{}])
        pe = res[0].get("summaryDetail", {}).get("trailingPE", {}).get("raw") if res else None
        return round(pe, 1) if pe else None
    except Exception:
        return None

def tech_signal(price, ma150, rsi):
    """שיטת מיכו: MA150 + RSI."""
    if price is None or ma150 is None:
        return "HOLD"
    if price < ma150:
        return "SELL"
    if rsi is not None and rsi > 70:
        return "HOLD"  # overbought
    return "BUY"

def fund_signal(pe):
    """Fundamental signal based on P/E.

    Returns "N/A" — not "HOLD" — when there is no P/E. ETFs and unprofitable
    companies legitimately have none, and reporting "HOLD" there manufactures a
    fundamental opinion out of missing data.
    """
    if pe is None:
        return "N/A"
    if pe < 20:
        return "BUY"
    if pe <= 35:
        return "HOLD"
    return "SELL"

def verdict_signal(tech, fund):
    """Combined verdict from tech + fund signals."""
    if tech == "SELL":
        return "SELL"
    if fund == "N/A":
        return tech          # technical-only; caller labels it as such
    if tech == "BUY" and fund in ("BUY", "HOLD"):
        return "BUY"
    if tech == "BUY" and fund == "SELL":
        return "HOLD"
    return "HOLD"

def fmt_vol(vol_list):
    """Format volume as string like '32.4M' or '2.4M'."""
    if not vol_list:
        return "—"
    recent = [v for v in vol_list if v]
    if not recent:
        return "—"
    recent = recent[-1]
    if recent >= 1_000_000:
        return f"{recent/1_000_000:.1f}M"
    if recent >= 1_000:
        return f"{recent/1_000:.0f}K"
    return str(int(recent))

def fmt_avg_vol(vol_list, days=20):
    """Average volume over last N days."""
    vals = [v for v in vol_list if v][-days:]
    if not vals:
        return "—"
    avg = sum(vals) / len(vals)
    if avg >= 1_000_000:
        return f"{avg/1_000_000:.1f}M"
    if avg >= 1_000:
        return f"{avg/1_000:.0f}K"
    return str(int(avg))

# ─── Data Fetching ────────────────────────────────────────────────────────────

def fetch_usd_ils():
    """Fetch live USD/ILS rate from Yahoo Finance. USDILS=X returns ILS per USD directly."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/USDILS=X?interval=1d&range=5d"
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json()
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        return round(closes[-1], 4)
    except Exception:
        return 3.65  # fallback

def fetch_index(ticker, name_he):
    """Fetch index close, daily change, week/month/ytd, and 90-day closes."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y"
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json()
        result = data["chart"]["result"][0]
        closes_raw = result["indicators"]["quote"][0]["close"]
        timestamps = result.get("timestamp", [])
        closes = [c for c in closes_raw if c is not None]
        if len(closes) < 5:
            return {"name": name_he, "value": None, "day_pct": None, "week_pct": None,
                    "month_pct": None, "ytd_pct": None, "closes_90d": []}

        last = closes[-1]
        prev = closes[-2]
        day_pct = (last - prev) / prev * 100

        week_pct = (last / closes[-6] - 1) * 100 if len(closes) >= 6 else None
        month_pct = (last / closes[-22] - 1) * 100 if len(closes) >= 22 else None

        # YTD: find first close of current year
        current_year = datetime.datetime.now().year
        ytd_pct = None
        if timestamps:
            for i, ts in enumerate(timestamps):
                if closes_raw[i] is not None:
                    dt = datetime.datetime.fromtimestamp(ts)
                    if dt.year == current_year:
                        ytd_base = closes_raw[i]
                        ytd_pct = (last / ytd_base - 1) * 100
                        break

        closes_90d = closes[-90:] if len(closes) >= 90 else closes

        return {
            "name": name_he,
            "value": last,
            "day_pct": day_pct,
            "week_pct": week_pct,
            "month_pct": month_pct,
            "ytd_pct": ytd_pct,
            "closes_90d": closes_90d,
        }
    except Exception:
        return {"name": name_he, "value": None, "day_pct": None, "week_pct": None,
                "month_pct": None, "ytd_pct": None, "closes_90d": []}

def fetch_stock(ticker, shares, currency, usd_ils):
    """Fetch stock data, calculate MA150 and extended metrics."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        result = data["chart"]["result"][0]
        quotes = result["indicators"]["quote"][0]
        closes_raw = quotes["close"]
        volumes_raw = quotes.get("volume", [])

        closes = [c for c in closes_raw if c is not None]
        if len(closes) < 5:
            return None

        last_close  = closes[-1]
        prev_close  = closes[-2]
        day_pct     = (last_close - prev_close) / prev_close * 100
        n           = min(len(closes), 150)
        ma150       = sum(closes[-n:]) / n
        pct_ma150   = (last_close - ma150) / ma150 * 100

        # Week/month/year pct
        week_pct  = (last_close / closes[-6]  - 1) * 100 if len(closes) >= 6  else None
        month_pct = (last_close / closes[-22] - 1) * 100 if len(closes) >= 22 else None
        year_pct  = (last_close / closes[0]   - 1) * 100 if len(closes) >= 2  else None

        # RSI
        rsi = calc_rsi(closes)

        # Volume
        volumes = [v for v in volumes_raw if v is not None]
        vol_raw_90 = volumes[-90:] if len(volumes) >= 90 else volumes

        # Support/resistance (last 20 closes, raw price units)
        last_20 = closes[-20:]
        support    = min(last_20) if last_20 else None
        resistance = max(last_20) if last_20 else None

        # 90-day closes (raw, agorot for TASE)
        closes_90d = closes[-90:] if len(closes) >= 90 else closes

        # Value in ILS
        if currency == "USD":
            price_ils = last_close * usd_ils
            prev_ils  = prev_close * usd_ils
        else:
            # TASE prices returned in agorot by Yahoo → divide by 100
            price_ils = last_close / 100
            prev_ils  = prev_close / 100

        val_ils      = price_ils * shares
        prev_val_ils = prev_ils  * shares

        return {
            "last_close":   last_close,
            "prev_close":   prev_close,
            "day_pct":      day_pct,
            "week_pct":     week_pct,
            "month_pct":    month_pct,
            "year_pct":     year_pct,
            "ma150":        ma150,
            "ma_days":      n,   # actual window used; < 150 means not a true MA150
            "pct_ma150":    pct_ma150,
            "rsi":          rsi,
            "price_ils":    price_ils,
            "val_ils":      val_ils,
            "prev_val_ils": prev_val_ils,
            "vol_raw":      vol_raw_90,
            "support":      support,
            "resistance":   resistance,
            "closes_90d":   closes_90d,
        }
    except Exception as e:
        return None

# ─── Translation ─────────────────────────────────────────────────────────────

def translate_he(text):
    """Translate English text to Hebrew via Google Translate (no API key)."""
    if not text:
        return text
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "en", "tl": "he", "dt": "t", "q": text}
        r = requests.get(url, params=params, headers=HEADERS, timeout=8)
        result = r.json()
        return "".join(part[0] for part in result[0] if part[0])
    except Exception:
        return text

# ─── News Fetching ───────────────────────────────────────────────────────────

def fetch_news(ticker):
    """Fetch recent news headlines (last 48h) from Yahoo Finance search."""
    try:
        search_q = ticker.replace('.TA', '')
        url = (f"https://query1.finance.yahoo.com/v1/finance/search"
               f"?q={search_q}&newsCount=6&quotesCount=0&enableFuzzyQuery=false")
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        items = r.json().get("news", [])
        cutoff = datetime.datetime.now().timestamp() - 48 * 3600
        results = []
        for item in items:
            if item.get("providerPublishTime", 0) >= cutoff:
                title_en = item.get("title", "")
                results.append({
                    "title":     translate_he(title_en),
                    "link":      item.get("link", "#"),
                    "publisher": item.get("publisher", ""),
                    "ts":        item.get("providerPublishTime", 0),
                })
        return results[:4]
    except Exception:
        return []

# ─── Signal Logic (Micho Method) ─────────────────────────────────────────────

def signal(pct_ma150):
    if pct_ma150 is None:
        return "neutral", "לא ידוע", "⚪"
    if pct_ma150 >= 10:
        return "bullish",  "BULLISH 🟢", "🟢"
    elif pct_ma150 >= 0:
        return "neutral",  "NEUTRAL 🟡", "🟡"
    elif pct_ma150 >= -10:
        return "warning",  "WATCH 🟠",   "🟠"
    else:
        return "bearish",  "BEARISH 🔴", "🔴"

# ─── HTML Generation ──────────────────────────────────────────────────────────

def fmt_ils(val):
    return f"₪{val:,.0f}"

def fmt_pct(val, plus=True):
    if val is None:
        return "—"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"

def display_units(r):
    """Prices in the units a human reads them in.

    Yahoo returns TASE prices in agorot while PORTFOLIO stores `avg` in shekels,
    so the two are only comparable after dividing by 100. Getting this wrong
    silently inflates every Israeli position 100x, so it lives in one place.
    """
    div = 100 if r["currency"] == "ILS" else 1
    scale = lambda v: v / div if v is not None else None
    return {
        "price":      scale(r.get("last_close")),
        "avg":        r.get("avg"),          # already in display units
        "ma150":      scale(r.get("ma150")),
        "support":    scale(r.get("support")),
        "resistance": scale(r.get("resistance")),
        "symbol":     "₪" if r["currency"] == "ILS" else "$",
    }

def position_pnl(r):
    """Unrealized P&L for one holding, in ILS and in percent.

    Returns (pnl_ils, pnl_pct, cost_ils) — or (None, None, None) when there is
    no usable cost basis, so callers render — instead of a fabricated 0.
    """
    d = display_units(r)
    avg, price = d["avg"], d["price"]
    if not avg or price is None:
        return None, None, None
    # val_ils is already the ILS market value; derive cost with the same FX path.
    fx = (r["val_ils"] / (price * r["shares"])) if price and r["shares"] else 1
    cost_ils = avg * r["shares"] * fx
    return r["val_ils"] - cost_ils, (price / avg - 1) * 100, cost_ils

def generate_html(rows, indices, usd_ils, report_date, news_data=None, failed=None,
                  events=None):
    total_val     = sum(r["val_ils"]      for r in rows if r["val_ils"]      is not None)
    total_prev    = sum(r["prev_val_ils"] for r in rows if r["prev_val_ils"] is not None)
    port_day_pct  = (total_val - total_prev) / total_prev * 100 if total_prev else 0
    port_day_ils  = total_val - total_prev

    bearish_val   = sum(r["val_ils"] for r in rows if r["val_ils"] and r["pct_ma150"] is not None and r["pct_ma150"] < 0)
    bearish_pct   = bearish_val / total_val * 100 if total_val else 0

    # Unrealized P&L. Positions without a usable cost basis are excluded from both
    # sides of the ratio so the percentage stays honest rather than diluted.
    _pnl = [(r, *position_pnl(r)) for r in rows]
    total_cost    = sum(c for _, _, _, c in _pnl if c is not None)
    total_pnl     = sum(p for _, p, _, c in _pnl if c is not None)
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
    pnl_cls       = "up" if total_pnl >= 0 else "dn"
    pnl_arrow     = "▲" if total_pnl >= 0 else "▼"
    no_basis      = [r["ticker"] for r, _, _, c in _pnl if c is None]

    # Caveats belong in the report, not only in the covering email — whoever opens
    # the Pages URL directly should see the same warnings.
    short_ma = [r["ticker"] for r in rows if r.get("ma_days", 150) < 150]
    caveats  = []
    if failed:
        caveats.append(f"<b>{len(failed)} מניות לא נמשכו ({', '.join(failed)})</b> — "
                       f"שווי התיק, הרווח/הפסד והשינוי היומי מחושבים על תיק חלקי.")
    if short_ma:
        days = {r["ticker"]: r.get("ma_days") for r in rows if r["ticker"] in short_ma}
        detail = ", ".join(f"{t} ({days[t]} ימים)" for t in short_ma)
        caveats.append(f"היסטוריה קצרה מ-150 ימי מסחר: {detail} — "
                       f"ה-MA שלהן מחושב על חלון קצר יותר ומסומן ב-* בטבלה.")
    if no_basis:
        caveats.append(f"אין מחיר קנייה ל-{', '.join(no_basis)} — "
                       f"הן לא נכללות בחישוב הרווח/הפסד.")

    # "What changed" — the crossings are the actual Micho trigger, and a daily
    # snapshot on its own can never report them.
    events_html = ""
    if events is not None:
        colours = {"cross_down": "#f85149", "cross_up": "#3fb950", "qty": "#58a6ff",
                   "streak": "#d29922", "aging": "#d29922", "new": "#58a6ff"}
        if events:
            items = "".join(
                f'<li style="margin:5px 0; color:{colours.get(k, "#e6edf3")};">{t}</li>'
                for k, t in events)
            body = f'<ul style="margin:0; padding-right:18px; line-height:1.8;">{items}</ul>'
        else:
            body = '<div style="color:var(--muted); font-size:13px;">אין שינויים מהותיים מאז הדוח הקודם.</div>'
        events_html = f"""
<div class="section">
  <div class="section-header">🔄 מה השתנה מאז הדוח הקודם</div>
  <div style="padding:14px 16px;">{body}</div>
</div>"""

    trust_banner = ""
    if caveats:
        items = "".join(f"<li style='margin:3px 0;'>{c}</li>" for c in caveats)
        trust_banner = f"""
<div class="section" style="margin-bottom:20px; background:#3a2d00; border-color:#d29922;">
  <div style="padding:12px 16px;">
    <div style="font-weight:700; color:#e3b341; margin-bottom:6px;">⚠️ הסתייגויות נתונים</div>
    <ul style="margin:0; padding-right:18px; color:#e3b341; font-size:13px; line-height:1.7;">{items}</ul>
  </div>
</div>"""

    sp500  = next((i for i in indices if "S&P"    in i["name"]), None)
    ndx    = next((i for i in indices if "NDX"    in i["name"]), None)
    ta35   = next((i for i in indices if i["name"] == "TA-35"),  None)
    ta125  = next((i for i in indices if "TA-125" in i["name"]), None)

    today_str = report_date.strftime("%-d ב%B %Y").replace(
        "January","ינואר").replace("February","פברואר").replace("March","מרץ"
        ).replace("April","אפריל").replace("May","מאי").replace("June","יוני"
        ).replace("July","יולי").replace("August","אוגוסט").replace("September","ספטמבר"
        ).replace("October","אוקטובר").replace("November","נובמבר").replace("December","דצמבר")

    def idx_row(idx, label):
        """One market-table row: value + day/week/month/YTD, all real numbers.

        A missing value renders as — rather than 0%, which would read as a flat market.
        """
        if not idx or idx["value"] is None:
            return (f'<td class="bold">{label}</td>'
                    f'<td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>')

        def cell(v, small=False):
            if v is None:
                return '<td style="color:var(--muted);">—</td>'
            style = ' style="font-size:12px;"' if small else ""
            return f'<td class="{"up" if v >= 0 else "dn"}"{style}>{fmt_pct(v)}</td>'

        return (f'<td class="bold">{label}</td>'
                f'<td>{idx["value"]:,.0f}</td>'
                + cell(idx["day_pct"])
                + cell(idx.get("week_pct"), small=True)
                + cell(idx.get("month_pct"), small=True)
                + cell(idx.get("ytd_pct"), small=True))

    port_cls  = "up" if port_day_pct >= 0 else "dn"

    # Build portfolio table rows
    table_rows_html = ""
    for i, r in enumerate(rows, 1):
        sig_key, sig_label, sig_icon = signal(r.get("pct_ma150"))
        pct_val = r.get("val_ils", 0) / total_val * 100 if total_val else 0
        day_cls = "up" if (r.get("day_pct") or 0) >= 0 else "dn"
        ma_cls  = sig_key

        d = display_units(r)
        price_str = f"{d['symbol']}{d['price']:.2f}"
        avg_str   = f"{d['symbol']}{d['avg']:.2f}" if d["avg"] else "—"

        pnl_ils, pnl_pct, _ = position_pnl(r)
        if pnl_ils is None:
            pnl_cell = '<td class="center mono" colspan="1">—</td>'
        else:
            pc = "up" if pnl_ils >= 0 else "dn"
            pnl_cell = (f'<td class="center mono {pc}">{fmt_ils(pnl_ils)}'
                        f'<br><span style="font-size:11px;">{fmt_pct(pnl_pct)}</span></td>')

        # NASA-style short history must not silently pass as a real MA150.
        ma_txt = fmt_pct(r.get("pct_ma150"))
        if r.get("ma_days", 150) < 150:
            ma_txt += f'<span style="font-size:10px;color:var(--muted);">*</span>'

        table_rows_html += f"""
        <tr class="row-{sig_key}">
          <td class="center">{i}</td>
          <td class="ticker">{r['ticker'].replace('.TA','')}</td>
          <td class="name-col">{r['name']}</td>
          <td class="center">{r['shares']:g}</td>
          <td class="center mono">{price_str}</td>
          <td class="center mono" style="color:var(--muted);">{avg_str}</td>
          <td class="center {day_cls} mono">{fmt_pct(r.get('day_pct'))}</td>
          <td class="center {ma_cls} bold mono">{ma_txt}</td>
          <td class="center mono bold">{fmt_ils(r['val_ils'])}</td>
          {pnl_cell}
          <td class="center mono">{pct_val:.1f}%</td>
          <td class="center signal-cell">{sig_label}</td>
        </tr>"""

    # Indicators live in their own section: bolting five more columns onto the
    # dashboard makes it unreadable in RTL on a phone, which is where it's read.
    perf_rows_html = ""
    for r in rows:
        d = display_units(r)
        rsi, pe = r.get("rsi"), r.get("pe")

        if rsi is None:
            rsi_cell = '<td class="center mono">—</td>'
        else:
            rsi_cls = "dn" if rsi > 70 else ("up" if rsi < 30 else "")
            tag = " 🔥" if rsi > 70 else (" 🧊" if rsi < 30 else "")
            rsi_cell = f'<td class="center mono {rsi_cls}">{rsi:.0f}{tag}</td>'

        # Distance to the last-20-day extremes is actionable; the raw levels aren't.
        def dist(level):
            if not level or not d["price"]:
                return "—"
            return f"{(d['price'] / level - 1) * 100:+.1f}%"

        perf_rows_html += f"""
        <tr>
          <td class="ticker">{r['ticker'].replace('.TA','')}</td>
          <td class="center mono {'up' if (r.get('week_pct') or 0) >= 0 else 'dn'}">{fmt_pct(r.get('week_pct'))}</td>
          <td class="center mono {'up' if (r.get('month_pct') or 0) >= 0 else 'dn'}">{fmt_pct(r.get('month_pct'))}</td>
          <td class="center mono {'up' if (r.get('year_pct') or 0) >= 0 else 'dn'}">{fmt_pct(r.get('year_pct'))}</td>
          {rsi_cell}
          <td class="center mono">{f'{pe:.1f}' if pe else '—'}</td>
          <td class="center mono">{d['symbol']}{d['ma150']:.2f}</td>
          <td class="center mono" style="font-size:12px;">{dist(d['support'])}</td>
          <td class="center mono" style="font-size:12px;">{dist(d['resistance'])}</td>
          <td class="center mono" style="font-size:12px;">{fmt_vol(r.get('vol_raw'))} / {fmt_avg_vol(r.get('vol_raw'))}</td>
        </tr>"""

    # Build market rows
    port_arrow = "▲" if port_day_pct >= 0 else "▼"

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>דוח תיק — {today_str}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700;800&display=swap');

    :root {{
      --bg:        #0d1117;
      --card:      #161b22;
      --border:    #30363d;
      --text:      #e6edf3;
      --muted:     #8b949e;
      --green:     #3fb950;
      --green-bg:  #0d2818;
      --red:       #f85149;
      --red-bg:    #2d0a0a;
      --yellow:    #d29922;
      --yellow-bg: #271d07;
      --orange:    #e3963e;
      --orange-bg: #271807;
      --blue:      #58a6ff;
      --accent:    #1f6feb;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: 'Heebo', Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      direction: rtl;
      text-align: right;
      padding: 20px;
      font-size: 14px;
      line-height: 1.6;
    }}

    /* Header */
    .header {{
      background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px 28px;
      margin-bottom: 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .header-title h1 {{
      font-size: 22px;
      font-weight: 800;
      color: var(--text);
      letter-spacing: 0.5px;
    }}
    .header-title p {{
      color: var(--muted);
      font-size: 13px;
      margin-top: 4px;
    }}
    .header-value {{
      text-align: left;
    }}
    .header-value .total {{
      font-size: 28px;
      font-weight: 800;
      color: var(--text);
      direction: ltr;
      unicode-bidi: embed;
    }}
    .header-value .change {{
      font-size: 15px;
      font-weight: 600;
      direction: ltr;
      unicode-bidi: embed;
    }}

    /* Cards row */
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 14px;
      margin-bottom: 20px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
    }}
    .card .label {{
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 6px;
    }}
    .card .value {{
      font-size: 20px;
      font-weight: 700;
      direction: ltr;
      unicode-bidi: embed;
    }}
    .card .sub {{
      font-size: 12px;
      color: var(--muted);
      margin-top: 4px;
      direction: ltr;
      unicode-bidi: embed;
    }}

    /* Tables */
    .section {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 0;
      margin-bottom: 20px;
      overflow: hidden;
    }}
    .section-header {{
      padding: 14px 20px;
      font-size: 15px;
      font-weight: 700;
      border-bottom: 1px solid var(--border);
      background: #1c2333;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    /* .section has overflow:hidden for its rounded corners, which silently CLIPS
       any table wider than the viewport — on a phone most columns became
       unreachable rather than scrollable. Tables get their own scroll context. */
    .table-scroll {{
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }}
    table {{
      width: 100%;
      min-width: 620px;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th {{
      padding: 10px 14px;
      background: #1c2333;
      color: var(--muted);
      font-weight: 600;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }}
    td {{
      padding: 10px 14px;
      border-bottom: 1px solid #21262d;
      white-space: nowrap;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #1c2333; }}

    .center {{ text-align: center; }}
    /* Numbers are LTR runs inside an RTL document; without isolation a leading
       "-" or "₪" reorders and "₪-28,912" reads as "28,912-₪". */
    .mono {{ font-family: 'SF Mono', 'Fira Code', monospace;
             direction: ltr; unicode-bidi: isolate; }}
    .bold {{ font-weight: 700; }}

    .ticker {{
      font-weight: 700;
      font-size: 14px;
      color: var(--blue);
      font-family: monospace;
    }}
    .name-col {{ color: var(--text); }}

    /* Signal colors */
    .up      {{ color: var(--green) !important; }}
    .dn      {{ color: var(--red)   !important; }}
    .bullish {{ color: var(--green) !important; }}
    .neutral {{ color: var(--yellow)!important; }}
    .warning {{ color: var(--orange)!important; }}
    .bearish {{ color: var(--red)   !important; }}

    .row-bullish {{ border-right: 3px solid var(--green); }}
    .row-neutral {{ border-right: 3px solid var(--yellow); }}
    .row-warning {{ border-right: 3px solid var(--orange); }}
    .row-bearish {{ border-right: 3px solid var(--red); }}

    .signal-cell {{ font-size: 12px; font-weight: 600; }}

    /* Market table */
    .market-table td:first-child {{ font-weight: 700; }}
    .port-row td {{
      background: #1a2332 !important;
      font-weight: 700;
    }}

    /* Alert box */
    .alert {{
      border-radius: 8px;
      padding: 14px 18px;
      margin-bottom: 12px;
      font-size: 13px;
      border-right: 4px solid;
    }}
    .alert-red    {{ background: var(--red-bg);    border-color: var(--red);    color: #ff7b72; }}
    .alert-yellow {{ background: var(--yellow-bg); border-color: var(--yellow); color: #e3b341; }}
    .alert-green  {{ background: var(--green-bg);  border-color: var(--green);  color: #56d364; }}

    /* Bar chart */
    .bar-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 6px;
      font-size: 12px;
    }}
    .bar-label {{ width: 60px; font-family: monospace; color: var(--blue); }}
    .bar-track {{ flex: 1; background: #21262d; border-radius: 4px; height: 16px; overflow: hidden; }}
    .bar-fill  {{ height: 100%; border-radius: 4px; display: flex; align-items: center; padding: 0 6px;
                  font-size: 10px; font-weight: 600; color: #fff; white-space: nowrap; }}
    .bar-pct   {{ width: 48px; text-align: left; color: var(--muted); font-size: 11px; direction: ltr; unicode-bidi: embed; }}

    /* News section */
    .news-stock-header {{
      font-weight: 700;
      font-size: 13px;
      margin: 16px 0 8px 0;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .news-stock-header:first-child {{ margin-top: 0; }}
    .news-list {{ list-style: none; padding: 0; margin: 0 0 4px 0; }}
    .news-list li {{
      padding: 7px 0;
      border-bottom: 1px solid #21262d;
      display: flex;
      flex-direction: column;
      gap: 3px;
    }}
    .news-list li:last-child {{ border-bottom: none; }}
    .news-link {{ color: var(--text); text-decoration: none; font-size: 13px; line-height: 1.4; }}
    .news-link:hover {{ color: var(--blue); text-decoration: underline; }}
    .news-meta {{ color: var(--muted); font-size: 11px; direction: ltr; unicode-bidi: embed; }}
    .no-news {{ color: var(--muted); font-size: 13px; font-style: italic; }}

    /* Footer */
    .footer {{
      text-align: center;
      color: var(--muted);
      font-size: 11px;
      margin-top: 20px;
      padding: 14px;
      border-top: 1px solid var(--border);
    }}

    /* Responsive */
    @media (max-width: 768px) {{
      body {{ padding: 10px; font-size: 12px; }}
      .header {{ flex-direction: column; }}
      .header-value {{ text-align: right; }}
    }}
  </style>
</head>
<body>

<!-- ═══ HEADER ═══════════════════════════════════════════════════════════ -->
<div class="header">
  <div class="header-title">
    <h1>📊 דוח תיק — מאיר</h1>
    <p>שיטת מיכו | MA150 | נתונים: Yahoo Finance</p>
    <p style="margin-top:6px; color:#8b949e;">📅 {today_str} | מחירי סגירה: יום קודם</p>
  </div>
  <div class="header-value">
    <div class="total">{fmt_ils(total_val)}</div>
    <div class="change {'up' if port_day_pct >= 0 else 'dn'}">
      {port_arrow} {fmt_pct(port_day_pct)} ({fmt_ils(abs(port_day_ils))}) ביום
    </div>
    <div style="margin-top:8px; font-size:13px; color:#8b949e;">
      מושקע: {fmt_ils(total_cost)} ·
      <span class="{pnl_cls}" style="font-weight:700;">
        רווח/הפסד: {pnl_arrow} {fmt_ils(abs(total_pnl))} ({fmt_pct(total_pnl_pct)})
      </span>
    </div>
  </div>
</div>

{trust_banner}
{events_html}
<!-- ═══ MARKET CARDS ═══════════════════════════════════════════════════════ -->
<div class="section" style="margin-bottom:20px;">
  <div class="section-header">🌍 מצב שווקים</div>
  <div class="table-scroll">
  <table class="market-table">
    <thead>
      <tr>
        <th>מדד</th>
        <th>ערך</th>
        <th>יומי</th>
        <th>שבוע</th>
        <th>חודש</th>
        <th>מתחילת השנה</th>
      </tr>
    </thead>
    <tbody>
      <tr>{idx_row(sp500, "S&P 500")}</tr>
      <tr>{idx_row(ndx,   "NDX")}</tr>
      <tr>{idx_row(ta35,  "TA-35")}</tr>
      <tr>{idx_row(ta125, "TA-125")}</tr>
      <tr class="port-row">
        <td>🗂️ תיק מאיר</td>
        <td>{fmt_ils(total_val)}</td>
        <td class="{port_cls}">{fmt_pct(port_day_pct)}</td>
        <td colspan="3" style="color:var(--muted); font-size:12px;">{fmt_ils(port_day_ils)} ביום</td>
      </tr>
      <tr>
        <td class="bold">USD/ILS</td>
        <td class="mono">{usd_ils:.4f}</td>
        <td colspan="4" style="color:var(--muted); font-size:12px;">שער המרה לחישוב פוזיציות דולריות</td>
      </tr>
    </tbody>
  </table>
  </div>
</div>

<!-- ═══ PORTFOLIO TABLE ════════════════════════════════════════════════════ -->
<div class="section">
  <div class="section-header">📋 לוח בקרה — תיק מלא</div>
  <div class="table-scroll">
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>טיקר</th>
        <th>שם</th>
        <th>כמות</th>
        <th>מחיר</th>
        <th>מחיר קנייה</th>
        <th>יומי%</th>
        <th>MA150%</th>
        <th>שווי (₪)</th>
        <th>רווח/הפסד</th>
        <th>% תיק</th>
        <th>סיגנל מיכו</th>
      </tr>
    </thead>
    <tbody>
      {table_rows_html}
    </tbody>
    <tfoot>
      <tr style="background:#1c2333; font-weight:700;">
        <td colspan="8" style="text-align:left; padding-right:14px; color:var(--muted);">סה"כ</td>
        <td class="center mono bold">{fmt_ils(total_val)}</td>
        <td class="center mono {pnl_cls}">{fmt_ils(total_pnl)}<br><span style="font-size:11px;">{fmt_pct(total_pnl_pct)}</span></td>
        <td class="center">100%</td>
        <td></td>
      </tr>
    </tfoot>
  </table>
  </div>
</div>

<!-- ═══ PERFORMANCE & INDICATORS ═══════════════════════════════════════════ -->
<div class="section">
  <div class="section-header">📈 ביצועים ואינדיקטורים</div>
  <div class="table-scroll">
  <table>
    <thead>
      <tr>
        <th>טיקר</th>
        <th>שבוע</th>
        <th>חודש</th>
        <th>שנה</th>
        <th>RSI</th>
        <th>P/E</th>
        <th>MA150</th>
        <th>מתמיכה</th>
        <th>מהתנגדות</th>
        <th>נפח / ממוצע 20י'</th>
      </tr>
    </thead>
    <tbody>
      {perf_rows_html}
    </tbody>
  </table>
  </div>
  <div style="padding:8px 14px; color:var(--muted); font-size:11px; line-height:1.6;">
    RSI: 🔥 מעל 70 (קניית יתר) · 🧊 מתחת 30 (מכירת יתר) ·
    "מתמיכה"/"מהתנגדות" = מרחק המחיר מהשפל/שיא של 20 ימי המסחר האחרונים.
  </div>
</div>

<!-- ═══ SIGNAL SUMMARY ════════════════════════════════════════════════════ -->
<div class="section">
  <div class="section-header">🎯 פיזור סיגנלים — שיטת מיכו</div>
  <div style="padding: 16px 20px;">
"""

    # Build bar chart
    bar_colors = {
        "bullish": ("#3fb950", "🟢"),
        "neutral": ("#d29922", "🟡"),
        "warning": ("#e3963e", "🟠"),
        "bearish": ("#f85149", "🔴"),
    }
    signal_buckets = {"bullish": 0.0, "neutral": 0.0, "warning": 0.0, "bearish": 0.0}
    for r in rows:
        sk, _, _ = signal(r.get("pct_ma150"))
        signal_buckets[sk] += r.get("val_ils", 0)

    for sk, color_tuple in bar_colors.items():
        color, icon = color_tuple
        val = signal_buckets[sk]
        pct = val / total_val * 100 if total_val else 0
        label_map = {"bullish": "BULLISH", "neutral": "NEUTRAL", "warning": "WATCH", "bearish": "BEARISH"}
        html += f"""
    <div class="bar-row">
      <div class="bar-label">{icon} {label_map[sk]}</div>
      <div class="bar-track">
        <div class="bar-fill" style="width:{pct:.0f}%; background:{color};">{fmt_ils(val)}</div>
      </div>
      <div class="bar-pct">{pct:.1f}%</div>
    </div>"""

    html += f"""
    <div style="margin-top:14px; font-size:12px; color:var(--muted);">
      ⚠️ <strong style="color:{('#f85149' if bearish_pct > 25 else '#d29922')}">
      {bearish_pct:.1f}% מהתיק בסיגנל שלילי (מתחת ל-MA150)
      </strong>
    </div>
  </div>
</div>
"""

    # Alerts
    html += """<div class="section">
  <div class="section-header">⚡ התראות</div>
  <div style="padding: 16px 20px;">
"""
    alerts = []
    for r in rows:
        sk, _, _ = signal(r.get("pct_ma150"))
        pct_val = r.get("val_ils", 0) / total_val * 100 if total_val else 0
        if sk == "bearish" and pct_val >= 5:
            alerts.append(("red",
                f"🔴 {r['ticker']} ({r['name']}) — מתחת MA150 ב-{abs(r.get('pct_ma150') or 0):.1f}% | "
                f"חשיפה: {pct_val:.1f}% מהתיק ({fmt_ils(r['val_ils'])})"))
        elif sk in ("bearish", "warning") and abs(r.get("day_pct") or 0) >= 5:
            alerts.append(("yellow",
                f"🟠 {r['ticker']} — שינוי חד: {fmt_pct(r.get('day_pct'))} ביום"))
        elif sk == "bullish" and (r.get("pct_ma150") or 0) >= 20:
            alerts.append(("green",
                f"🟢 {r['ticker']} ({r['name']}) — {fmt_pct(r.get('pct_ma150'))} מעל MA150 | ביצוע חזק"))

    if not alerts:
        alerts.append(("green", "✅ אין התראות מיוחדות היום"))

    for alert_type, msg in alerts:
        html += f'    <div class="alert alert-{alert_type}">{msg}</div>\n'

    html += f"""  </div>
</div>

<!-- ═══ NEWS ══════════════════════════════════════════════════════════════ -->
"""
    nd = news_data or {}
    stocks_with_news = [(r, nd.get(r['ticker'], [])) for r in rows if nd.get(r['ticker'])]

    html += '<div class="section">\n'
    html += '  <div class="section-header">📰 חדשות עדכניות — 48 שעות אחרונות</div>\n'
    html += '  <div style="padding: 16px 20px;">\n'

    if not stocks_with_news:
        html += '    <div class="no-news">לא נמצאו חדשות עדכניות</div>\n'
    else:
        for r, items in stocks_with_news:
            ticker_display = r['ticker'].replace('.TA', '')
            sig_key, _, sig_icon = signal(r.get('pct_ma150'))
            html += f'    <div class="news-stock-header">{sig_icon} <span class="ticker">{ticker_display}</span> &nbsp;{r["name"]}</div>\n'
            html += '    <ul class="news-list">\n'
            now_ts = datetime.datetime.now().timestamp()
            for item in items:
                hours_ago = max(0, int((now_ts - item['ts']) / 3600))
                time_str = f"{hours_ago}ש' לפני" if hours_ago > 0 else "עכשיו"
                html += (f'      <li>'
                         f'<a href="{item["link"]}" target="_blank" class="news-link">{item["title"]}</a>'
                         f'<span class="news-meta">{item["publisher"]} · {time_str}</span>'
                         f'</li>\n')
            html += '    </ul>\n'

    html += '  </div>\n</div>\n\n'

    html += f"""<!-- ═══ FOOTER ════════════════════════════════════════════════════════════ -->
<div style="text-align:center; margin:24px 0;">
  <a href="Portfolio%20Terminal.html"
     style="display:inline-block; padding:12px 28px; border:1px solid #30363d; border-radius:9px;
            color:#e6edf3; text-decoration:none; font-weight:700;">
    🖥️ פתח טרמינל אינטראקטיבי
  </a>
</div>

<div class="footer">
  נוצר: {report_date.strftime('%d/%m/%Y %H:%M')} |
  מקור: Yahoo Finance API (חינמי) |
  שיטת מיכו: מעל MA150 = בולישי | מתחת MA150 = סיגנל יציאה |
  USD/ILS: {usd_ils}
  <br><span style="opacity:0.7;">אינדיקטורים בלבד — לא ייעוץ השקעות.</span>
</div>

</body>
</html>"""

    return html, {
        "total_val": total_val,
        "port_day_pct": port_day_pct,
        "port_day_ils": port_day_ils,
        "bearish_pct": bearish_pct,
        "usd_ils": usd_ils,
        "rows": rows,
        "short_ma": short_ma,
        "total_cost": total_cost,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "no_basis": no_basis,
    }

# ─── Performance History ──────────────────────────────────────────────────────

def build_perf_history(rows, indices, usd_ils, history=None):
    """Build 90-day normalized performance history (base=100).

    The portfolio line prefers recorded NAV from history.json. The fallback
    backcast reprices today's share counts at today's FX all the way back, and
    drops any holding with under 90 days of closes — NASA silently left the
    basket, which made the line jump. It is only used before enough history
    accumulates, and the result is flagged so the viewer can label it.
    """
    n = 90
    synthetic = True
    port_vals = []

    recorded = [h for h in (history or []) if h.get("total_val")]
    if len(recorded) >= 30:
        port_vals = [h["total_val"] for h in recorded[-n:]]
        synthetic = False
    else:
        for d in range(n):
            day_val = 0
            for r in rows:
                closes_90d = r.get("closes_90d", [])
                if len(closes_90d) < n:
                    continue
                c = closes_90d[-(n - d)]
                if r["currency"] == "ILS":
                    day_val += (c / 100) * r["shares"]
                else:
                    day_val += c * r["shares"] * usd_ils
            port_vals.append(day_val)

    def normalize(vals):
        if not vals or vals[0] == 0:
            return [100.0] * len(vals)
        base = vals[0]
        return [round(v / base * 100, 2) for v in vals]

    days = len(port_vals)
    perf = {
        "dates": list(range(days)),
        "portfolio": normalize(port_vals),
        "portfolioSynthetic": synthetic,
    }

    for idx in indices:
        closes_90d = idx.get("closes_90d", [])
        key_map = {"S&P 500": "snp", "NDX": "ndx", "TA-35": "ta35", "TA-125": "ta125"}
        key = key_map.get(idx["name"], idx["name"].lower().replace("-", "").replace(" ", ""))
        # Align the benchmarks to however many portfolio points we actually have.
        perf[key] = normalize(closes_90d[-days:]) if len(closes_90d) >= days else [100.0] * days

    return perf

# ─── data.json Generation ─────────────────────────────────────────────────────

def generate_data_json(rows, indices, usd_ils, report_date, news_data=None, history=None):
    now = datetime.datetime.now()
    months_he = ["ינואר","פברואר","מרץ","אפריל","מאי","יוני","יולי","אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"]
    as_of = f"{now.day} ב{months_he[now.month-1]} {now.year}, {now.strftime('%H:%M')} IDT"

    # benchmarks
    benchmarks = []
    for idx in indices:
        benchmarks.append({
            "sym": idx["name"],
            "value": round(idx["value"], 2) if idx["value"] else None,
            "day": round(idx.get("day_pct") or 0, 2),
            "week": round(idx.get("week_pct") or 0, 2),
            "month": round(idx.get("month_pct") or 0, 2),
            "ytd": round(idx.get("ytd_pct") or 0, 2),
        })

    # positions
    positions = []
    nav = sum(r["val_ils"] for r in rows if r.get("val_ils") is not None)
    for r in rows:
        sym = r["ticker"].replace(".TA", "")
        market = "IL" if r["currency"] == "ILS" else "US"

        # price in display units (ILS for TASE, USD for US)
        if r["currency"] == "ILS":
            price_disp = r["last_close"] / 100  # agorot → ILS
            avg_disp = r["avg"]  # already ILS
            support_disp = r.get("support") / 100 if r.get("support") else None
            resistance_disp = r.get("resistance") / 100 if r.get("resistance") else None
            vol_prefix = "₪"
        else:
            price_disp = r["last_close"]
            avg_disp = r["avg"]
            support_disp = r.get("support")
            resistance_disp = r.get("resistance")
            vol_prefix = ""

        rsi = r.get("rsi")
        pe = r.get("pe")
        pnl_ils, pnl_pct, _ = position_pnl(r)
        tech = tech_signal(r["last_close"], r["ma150"], rsi)
        fund = fund_signal(pe)
        verd = verdict_signal(tech, fund)

        # notes based on signals
        ma_pct = r.get("pct_ma150", 0) or 0
        if tech == "BUY":
            notes = f"מעל MA150 ב-{ma_pct:+.1f}%."
        elif tech == "SELL":
            notes = f"מתחת MA150 ב-{abs(ma_pct):.1f}%."
        else:
            notes = f"MA150: {ma_pct:+.1f}%."
        if rsi and rsi > 70:
            notes += " RSI גבוה — overbought."
        elif rsi and rsi < 30:
            notes += " RSI נמוך — oversold."

        news_titles = []
        if news_data and r["ticker"] in news_data:
            news_titles = [item["title"] for item in news_data[r["ticker"]][:2]]

        pos = {
            "sym": sym,
            "name": r["name"],
            "market": market,
            "qty": r["shares"],
            "avg": round(avg_disp, 2),
            "price": round(price_disp, 4) if price_disp < 10 else round(price_disp, 2),
            "day": round(r.get("day_pct") or 0, 2),
            "week": round(r.get("week_pct") or 0, 2),
            "month": round(r.get("month_pct") or 0, 2),
            "year": round(r.get("year_pct") or 0, 2),
            "ma150": round(r["ma150"] / 100 if r["currency"] == "ILS" else r["ma150"], 2),
            "rsi": rsi,
            "vol": vol_prefix + fmt_vol(r.get("vol_raw", [])),
            "avgVol": vol_prefix + fmt_avg_vol(r.get("vol_raw", [])),
            "pe": pe,
            "support": round(support_disp, 2) if support_disp else None,
            "resistance": round(resistance_disp, 2) if resistance_disp else None,
            "tech": tech,
            "fund": fund,
            "verdict": verd,
            "notes": notes,
            "events": news_titles,
            # app.jsx reads these on every position; without them the terminal
            # threw on load and rendered nothing.
            "value":    round(price_disp * r["shares"], 2),   # in the position's own currency
            "valueILS": round(r["val_ils"], 2) if r.get("val_ils") is not None else 0,
            "weight":   round(r["val_ils"] / nav * 100, 2) if nav and r.get("val_ils") else 0,
            "aboveMA":  (r.get("pct_ma150") or 0) >= 0,
            "maDelta":  round(r.get("pct_ma150") or 0, 2),
            "pl":       round(pnl_ils, 2) if pnl_ils is not None else 0,
            "plPct":    round(pnl_pct, 2) if pnl_pct is not None else 0,
        }
        positions.append(pos)

    # perfHistory — 90-day normalized portfolio
    perf = build_perf_history(rows, indices, usd_ils, history=history)

    # alerts
    alerts = []
    total_val = sum(r.get("val_ils", 0) for r in rows)
    for r in rows:
        sym = r["ticker"].replace(".TA", "")
        pct_val = r.get("val_ils", 0) / total_val * 100 if total_val else 0
        rsi_val = r.get("rsi")
        ma_pct = r.get("pct_ma150", 0) or 0
        if ma_pct < -10 and pct_val >= 5:
            alerts.append({"level": "high", "sym": sym,
                          "msg": f"מתחת MA150 ב-{abs(ma_pct):.1f}% | {pct_val:.1f}% מהתיק", "flag": "🔴"})
        elif rsi_val and rsi_val > 70:
            alerts.append({"level": "med", "sym": sym,
                          "msg": f"RSI={rsi_val:.0f} — אזור overbought", "flag": "🟡"})
        elif rsi_val and rsi_val < 30:
            alerts.append({"level": "med", "sym": sym,
                          "msg": f"RSI={rsi_val:.0f} — אזור oversold", "flag": "🔵"})

    # The terminal reads D.totals in four places; its absence was a hard crash.
    prev_nav = sum(r["prev_val_ils"] for r in rows if r.get("prev_val_ils") is not None)
    pl_ils   = sum(p["pl"] for p in positions)
    cost     = nav - pl_ils

    data = {
        "asOf": as_of,
        "fxRate": usd_ils,
        "cash": {"ils": 0, "usd": 0},
        "totals": {
            "valueILS":   round(nav, 2),
            "dayPctILS":  round((nav - prev_nav) / prev_nav * 100, 2) if prev_nav else 0,
            "plILS":      round(pl_ils, 2),
            "plPct":      round(pl_ils / cost * 100, 2) if cost else 0,
        },
        "benchmarks": benchmarks,
        "positions": positions,
        "perfHistory": perf,
        "trades": [],
        "alerts": alerts,
        "notes": "מעקב יומי — שיטת מיכו. MA150 = קו החלטה.",
    }

    out_path = Path(__file__).parent / "data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ data.json נשמר: {out_path}")
    return str(out_path)

# ─── Day-over-day history ─────────────────────────────────────────────────────

HISTORY_PATH = Path(__file__).parent / "history.json"
HISTORY_KEEP = 250


def load_history():
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def history_record(rows, usd_ils, report_date, total_val, day_pct):
    """One compact snapshot per run.

    qty is stored alongside price on purpose: without it a purchase looks
    identical to a gain when the series is read back.
    """
    positions = {}
    for r in rows:
        d = display_units(r)
        band, _, _ = signal(r.get("pct_ma150"))
        positions[r["ticker"]] = {
            "qty":       r["shares"],
            "price":     round(d["price"], 4) if d["price"] is not None else None,
            "pct_ma150": round(r["pct_ma150"], 2) if r.get("pct_ma150") is not None else None,
            "band":      band,
            "rsi":       r.get("rsi"),
            "val_ils":   round(r["val_ils"], 2) if r.get("val_ils") is not None else None,
        }
    return {
        "date":      report_date.strftime("%Y-%m-%d"),
        "total_val": round(total_val, 2),
        "day_pct":   round(day_pct, 2),
        "fx":        usd_ils,
        "positions": positions,
    }


def save_history(record):
    """Append today's record, replacing any existing one for the same date."""
    hist = [h for h in load_history() if h.get("date") != record["date"]]
    hist.append(record)
    hist.sort(key=lambda h: h["date"])
    hist = hist[-HISTORY_KEEP:]
    HISTORY_PATH.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ history.json נשמר: {len(hist)} ימים")
    return hist


def build_events(rows, history, today_record):
    """What changed since the previous run — the part a daily snapshot can't say.

    Returns a list of (kind, html) where kind drives the colour.
    """
    past = [h for h in history if h["date"] < today_record["date"]]
    if not past:
        return [], None
    prev = past[-1]
    events = []

    name_of = {r["ticker"]: r["name"] for r in rows}
    # The previous run is not necessarily yesterday — weekends, holidays and
    # skipped runs all leave gaps, so name the date instead of saying "אתמול".
    d = prev["date"].split("-")
    since = f"{d[2]}/{d[1]}"
    oldest = past[0]["date"]

    for tic, now in today_record["positions"].items():
        before = prev["positions"].get(tic)
        if not before:
            events.append(("new", f"🆕 <b>{tic}</b> — פוזיציה חדשה בדוח"))
            continue

        n_ma, p_ma = now.get("pct_ma150"), before.get("pct_ma150")
        if n_ma is None or p_ma is None:
            continue

        # The Micho trigger: the moment price crosses its MA150.
        if p_ma >= 0 > n_ma:
            events.append(("cross_down",
                f"🔴 <b>{tic}</b> ({name_of.get(tic,'')}) ירדה מתחת ל-MA150 — "
                f"ב-{since} {p_ma:+.1f}%, היום {n_ma:+.1f}%"))
        elif p_ma < 0 <= n_ma:
            events.append(("cross_up",
                f"🟢 <b>{tic}</b> ({name_of.get(tic,'')}) חצתה מעל ל-MA150 — "
                f"ב-{since} {p_ma:+.1f}%, היום {n_ma:+.1f}%"))

        # Quantity changes mean a trade happened; flag it so it isn't read as return.
        if before.get("qty") != now.get("qty"):
            events.append(("qty",
                f"📦 <b>{tic}</b> — הכמות השתנתה: {before['qty']:g} → {now['qty']:g}"))

    # Portfolio direction streak.
    streak, direction = 0, None
    for h in reversed(past + [today_record]):
        dp = h.get("day_pct") or 0
        d = "up" if dp > 0 else ("down" if dp < 0 else None)
        if d is None:
            break
        if direction is None:
            direction = d
        if d != direction:
            break
        streak += 1
    if streak >= 3:
        word = "עולה" if direction == "up" else "יורד"
        icon = "📈" if direction == "up" else "📉"
        events.append(("streak", f"{icon} התיק {word} <b>{streak} ימי מסחר ברציפות</b>"))

    # How long each position has been below its MA150. Listing every one of these
    # every day is how an alert box becomes wallpaper, so heavy positions get a
    # line each and the rest are collapsed into a single tail.
    nav = today_record.get("total_val") or 0
    aging = []
    for tic, now in today_record["positions"].items():
        if (now.get("pct_ma150") or 0) >= 0:
            continue
        days = 0
        for h in reversed(past):
            p = h["positions"].get(tic)
            if not p or (p.get("pct_ma150") is None) or p["pct_ma150"] >= 0:
                break
            days += 1
        if days < 5:
            continue
        capped = days + 1 >= len(past)     # streak runs past the start of history
        weight = (now.get("val_ils") or 0) / nav * 100 if nav else 0
        aging.append((tic, days + 1, capped, weight))

    aging.sort(key=lambda a: -a[3])
    for tic, days, capped, weight in aging[:3]:
        if weight < 5:
            break
        events.append(("aging",
            f"⏳ <b>{tic}</b> מתחת ל-MA150 כבר <b>{days}{'+' if capped else ''}</b> "
            f"ימי מסחר ({weight:.0f}% מהתיק)"))
    rest = [a for a in aging if a not in aging[:3] or a[3] < 5]
    if rest:
        names = ", ".join(f"{t} ({d}{'+' if c else ''})" for t, d, c, _ in rest)
        events.append(("aging", f"⏳ מתחת ל-MA150 זמן ממושך גם: {names}"))

    if any(a[2] for a in aging):
        events.append(("aging",
            f'<span style="font-size:12px; opacity:0.75;">'
            f'"+" = הרצף נמשך אל מעבר לתחילת ההיסטוריה ({oldest})</span>'))

    return events, prev


# ─── Landing page ─────────────────────────────────────────────────────────────

def generate_index(report_filename, summary, report_date):
    """Write index.html — the site root, which was a 404.

    Regenerated every run so it always points at the newest report, and links the
    terminal, which has been updating daily with nothing pointing at it.
    """
    total_val = summary["total_val"]
    day_pct   = summary["port_day_pct"]
    pnl       = summary.get("total_pnl", 0)
    pnl_pct   = summary.get("total_pnl_pct", 0)

    day_col = "#3fb950" if day_pct >= 0 else "#f85149"
    pnl_col = "#3fb950" if pnl     >= 0 else "#f85149"

    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>דוח תיק — מאיר</title>
<style>
  body {{ margin:0; background:#0d1117; color:#e6edf3; direction:rtl;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
         display:flex; align-items:center; justify-content:center; min-height:100vh; }}
  .card {{ background:#161b22; border:1px solid #30363d; border-radius:14px;
           padding:32px; max-width:460px; width:calc(100% - 32px); }}
  h1 {{ margin:0 0 4px; font-size:22px; }}
  .sub {{ color:#8b949e; font-size:13px; margin-bottom:22px; }}
  .val {{ font-size:34px; font-weight:800; letter-spacing:-0.5px; }}
  .line {{ font-size:15px; margin-top:6px; }}
  .btn {{ display:block; text-align:center; padding:14px; border-radius:9px;
          text-decoration:none; font-weight:700; margin-top:10px; }}
  .primary {{ background:#1f6feb; color:#fff; }}
  .ghost {{ border:1px solid #30363d; color:#e6edf3; }}
  .foot {{ color:#6e7681; font-size:11px; margin-top:20px; text-align:center; }}
</style>
</head>
<body>
  <div class="card">
    <h1>📊 דוח תיק — מאיר</h1>
    <div class="sub">שיטת מיכו · MA150 · {report_date.strftime('%d/%m/%Y')}</div>

    <div class="val">₪{total_val:,.0f}</div>
    <div class="line" style="color:{day_col};">
      <span style="direction:ltr; display:inline-block;">{'▲' if day_pct >= 0 else '▼'} {day_pct:+.2f}%</span> ביום
    </div>
    <div class="line" style="color:{pnl_col};">רווח/הפסד כולל:
      <span style="direction:ltr; display:inline-block;">{'▲' if pnl >= 0 else '▼'} ₪{abs(pnl):,.0f} ({pnl_pct:+.1f}%)</span>
    </div>

    <a class="btn primary" href="{report_filename}">📈 הדוח המלא של היום</a>
    <a class="btn ghost" href="Portfolio%20Terminal.html">🖥️ טרמינל אינטראקטיבי</a>

    <div class="foot">נוצר אוטומטית · Yahoo Finance · אינדיקטורים בלבד, לא ייעוץ השקעות</div>
  </div>
</body>
</html>"""

    out_path = Path(__file__).parent / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"✅ index.html נשמר: {out_path}")
    return str(out_path)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("📊 מייצר דוח תיק...", flush=True)

    today = datetime.date.today()
    usd_ils = fetch_usd_ils()
    print(f"   💱 USD/ILS: {usd_ils}", flush=True)

    # Fetch indices (all 4)
    indices = [
        fetch_index("^GSPC",     "S&P 500"),
        fetch_index("^NDX",      "NDX"),
        fetch_index("TA35.TA",   "TA-35"),   # no caret — "^TA35.TA" returns null

        fetch_index("^TA125.TA", "TA-125"),
    ]
    time.sleep(0.3)

    # Fetch all stocks
    rows = []
    failed = []
    for stock in PORTFOLIO:
        print(f"   ⏳ {stock['ticker']}...", end=" ", flush=True)
        data = fetch_stock(stock["ticker"], stock["shares"], stock["currency"], usd_ils)
        if data:
            data.update({
                "ticker":   stock["ticker"],
                "name":     stock["name"],
                "shares":   stock["shares"],
                "currency": stock["currency"],
                "avg":      stock.get("avg", 0),
            })
            rows.append(data)
            pma = data.get("pct_ma150")
            print(f"MA150: {pma:+.1f}%" if pma is not None else "ok", flush=True)
        else:
            failed.append(stock["ticker"])
            print("ERROR", flush=True)
        time.sleep(0.25)

    # Sort by portfolio weight
    rows.sort(key=lambda r: r.get("val_ils", 0), reverse=True)

    # Fetch P/E for each stock
    print("📈 מביא P/E...", flush=True)
    for r in rows:
        r["pe"] = fetch_pe(r["ticker"])
        time.sleep(0.2)

    # Fetch news for each stock
    print("📰 מביא חדשות...", flush=True)
    news_data = {}
    for stock in PORTFOLIO:
        items = fetch_news(stock["ticker"])
        if items:
            news_data[stock["ticker"]] = items
            print(f"   📄 {stock['ticker']}: {len(items)} כתבות", flush=True)
        time.sleep(0.2)

    # Day-over-day: compare against the previous run before recording this one.
    # A first pass is needed for the totals the history record stores.
    _, pre = generate_html(rows, indices, usd_ils, today, news_data, failed=failed)
    history = load_history()
    record  = history_record(rows, usd_ils, today,
                             pre["total_val"], pre["port_day_pct"])
    events, prev = build_events(rows, history, record)

    # Generate HTML
    html, summary = generate_html(rows, indices, usd_ils, today, news_data,
                                  failed=failed, events=events)
    summary["failed"]   = failed
    summary["expected"] = len(PORTFOLIO)
    summary["events"]   = events

    # Save HTML report
    out_path = Path(__file__).parent / f"report_{today.strftime('%Y-%m-%d')}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\n✅ דוח נשמר: {out_path}")
    print(f"   💰 שווי תיק: ₪{summary['total_val']:,.0f}")
    print(f"   📈 שינוי יומי: {summary['port_day_pct']:+.2f}% (₪{summary['port_day_ils']:+,.0f})")
    print(f"   💵 רווח/הפסד: ₪{summary['total_pnl']:+,.0f} ({summary['total_pnl_pct']:+.1f}%) "
          f"על ₪{summary['total_cost']:,.0f} מושקע")
    print(f"   ⚠️  מתחת MA150: {summary['bearish_pct']:.1f}% מהתיק")
    if failed:
        print(f"   ❌ נכשלו {len(failed)}/{len(PORTFOLIO)} מניות: {', '.join(failed)} "
              f"— השווי והשינוי היומי מחושבים על תיק חלקי!")
    if summary["short_ma"]:
        print(f"   ⚠️  היסטוריה חלקית (MA קצר מ-150): {', '.join(summary['short_ma'])}")

    # Record today only after the report is written, so a mid-run failure doesn't
    # poison tomorrow's comparison with a half-built snapshot.
    hist = save_history(record)
    if events:
        print(f"   🔄 {len(events)} שינויים מאז {prev['date'] if prev else '—'}:")
        for _, text in events:
            print("      • " + re.sub(r"<[^>]+>", "", text))

    # Landing page — the site root used to 404
    generate_index(out_path.name, summary, today)

    # Generate data.json for Bloomberg Terminal viewer
    data_json_path = generate_data_json(rows, indices, usd_ils, today, news_data,
                                        history=hist)

    summary["data_json_path"] = data_json_path
    return str(out_path), summary

if __name__ == "__main__":
    main()
