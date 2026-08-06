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

def fetch_pe(ticker):
    """Fetch trailing P/E from Yahoo Finance quoteSummary. Returns None on failure."""
    try:
        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=summaryDetail"
        r = requests.get(url, headers=HEADERS, timeout=10)
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
    """Fundamental signal based on P/E."""
    if pe is None:
        return "HOLD"
    if pe < 20:
        return "BUY"
    if pe <= 35:
        return "HOLD"
    return "SELL"

def verdict_signal(tech, fund):
    """Combined verdict from tech + fund signals."""
    if tech == "SELL":
        return "SELL"
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

def generate_html(rows, indices, usd_ils, report_date, news_data=None):
    total_val     = sum(r["val_ils"]      for r in rows if r["val_ils"]      is not None)
    total_prev    = sum(r["prev_val_ils"] for r in rows if r["prev_val_ils"] is not None)
    port_day_pct  = (total_val - total_prev) / total_prev * 100 if total_prev else 0
    port_day_ils  = total_val - total_prev

    bearish_val   = sum(r["val_ils"] for r in rows if r["val_ils"] and r["pct_ma150"] is not None and r["pct_ma150"] < 0)
    bearish_pct   = bearish_val / total_val * 100 if total_val else 0

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

        if r["currency"] == "USD":
            price_str = f"${r['last_close']:.2f}"
        else:
            price_str = f"₪{r['last_close']/100:.2f}"

        table_rows_html += f"""
        <tr class="row-{sig_key}">
          <td class="center">{i}</td>
          <td class="ticker">{r['ticker'].replace('.TA','')}</td>
          <td class="name-col">{r['name']}</td>
          <td class="center">{r['shares']:g}</td>
          <td class="center mono">{price_str}</td>
          <td class="center {day_cls} mono">{fmt_pct(r.get('day_pct'))}</td>
          <td class="center {ma_cls} bold mono">{fmt_pct(r.get('pct_ma150'))}</td>
          <td class="center mono bold">{fmt_ils(r['val_ils'])}</td>
          <td class="center mono">{pct_val:.1f}%</td>
          <td class="center signal-cell">{sig_label}</td>
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

    table {{
      width: 100%;
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
    .mono {{ font-family: 'SF Mono', 'Fira Code', monospace; }}
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
  </div>
</div>

<!-- ═══ MARKET CARDS ═══════════════════════════════════════════════════════ -->
<div class="section" style="margin-bottom:20px;">
  <div class="section-header">🌍 מצב שווקים</div>
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

<!-- ═══ PORTFOLIO TABLE ════════════════════════════════════════════════════ -->
<div class="section">
  <div class="section-header">📋 לוח בקרה — תיק מלא</div>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>טיקר</th>
        <th>שם</th>
        <th>כמות</th>
        <th>מחיר</th>
        <th>יומי%</th>
        <th>MA150%</th>
        <th>שווי (₪)</th>
        <th>% תיק</th>
        <th>סיגנל מיכו</th>
      </tr>
    </thead>
    <tbody>
      {table_rows_html}
    </tbody>
    <tfoot>
      <tr style="background:#1c2333; font-weight:700;">
        <td colspan="7" style="text-align:left; padding-right:14px; color:var(--muted);">סה"כ</td>
        <td class="center mono bold">{fmt_ils(total_val)}</td>
        <td class="center">100%</td>
        <td></td>
      </tr>
    </tfoot>
  </table>
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
        elif sk in ("bearish", "warning") and abs(r.get("day_pct", 0)) >= 5:
            alerts.append(("yellow",
                f"🟠 {r['ticker']} — שינוי חד: {fmt_pct(r.get('day_pct'))} ביום"))
        elif sk == "bullish" and r.get("pct_ma150", 0) >= 20:
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
<div class="footer">
  נוצר: {report_date.strftime('%d/%m/%Y %H:%M')} |
  מקור: Yahoo Finance API (חינמי) |
  שיטת מיכו: מעל MA150 = בולישי | מתחת MA150 = סיגנל יציאה |
  USD/ILS: {usd_ils}
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
        "short_ma": [r["ticker"] for r in rows if r.get("ma_days", 150) < 150],
    }

# ─── Performance History ──────────────────────────────────────────────────────

def build_perf_history(rows, indices, usd_ils):
    """Build 90-day normalized performance history (base=100)."""
    n = 90

    # Portfolio daily values
    port_vals = []
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

    perf = {
        "dates": list(range(n)),
        "portfolio": normalize(port_vals),
    }

    for idx in indices:
        closes_90d = idx.get("closes_90d", [])
        key_map = {"S&P 500": "snp", "NDX": "ndx", "TA-35": "ta35", "TA-125": "ta125"}
        key = key_map.get(idx["name"], idx["name"].lower().replace("-", "").replace(" ", ""))
        if len(closes_90d) >= n:
            perf[key] = normalize(closes_90d[-n:])
        else:
            perf[key] = [100.0] * n

    return perf

# ─── data.json Generation ─────────────────────────────────────────────────────

def generate_data_json(rows, indices, usd_ils, report_date, news_data=None):
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
        }
        positions.append(pos)

    # perfHistory — 90-day normalized portfolio
    perf = build_perf_history(rows, indices, usd_ils)

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

    data = {
        "asOf": as_of,
        "fxRate": usd_ils,
        "cash": {"ils": 0, "usd": 0},
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

    # Generate HTML
    html, summary = generate_html(rows, indices, usd_ils, today, news_data)
    summary["failed"]   = failed
    summary["expected"] = len(PORTFOLIO)

    # Save HTML report
    out_path = Path(__file__).parent / f"report_{today.strftime('%Y-%m-%d')}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\n✅ דוח נשמר: {out_path}")
    print(f"   💰 שווי תיק: ₪{summary['total_val']:,.0f}")
    print(f"   📈 שינוי יומי: {summary['port_day_pct']:+.2f}% (₪{summary['port_day_ils']:+,.0f})")
    print(f"   ⚠️  מתחת MA150: {summary['bearish_pct']:.1f}% מהתיק")
    if failed:
        print(f"   ❌ נכשלו {len(failed)}/{len(PORTFOLIO)} מניות: {', '.join(failed)} "
              f"— השווי והשינוי היומי מחושבים על תיק חלקי!")
    if summary["short_ma"]:
        print(f"   ⚠️  היסטוריה חלקית (MA קצר מ-150): {', '.join(summary['short_ma'])}")

    # Generate data.json for Bloomberg Terminal viewer
    data_json_path = generate_data_json(rows, indices, usd_ils, today, news_data)

    summary["data_json_path"] = data_json_path
    return str(out_path), summary

if __name__ == "__main__":
    main()
