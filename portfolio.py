"""Holdings derived from a trade log.

The portfolio used to be a Python literal inside generate_report.py, so every
buy or sell meant editing code — and `avg` was maintained by hand, which made
the P&L in the report only as correct as the last time someone remembered.

trades.json is a plain list of transactions. Share counts and average cost are
computed from it, so recording a trade is the only thing to remember:

    {"date": "2026-05-28", "ticker": "NASA", "side": "buy",
     "qty": 190, "price": 41.57}

- `price` is per share, in the security's own currency (USD, or ILS for .TA).
- A "sell" reduces the quantity and leaves the average cost untouched, which is
  the standard weighted-average treatment: realised gains are not cost basis.
- Selling the whole position drops it from the report; buying back starts a
  fresh average.

Ticker metadata (display name, currency) lives in `meta` alongside the trades.
"""

import json
from pathlib import Path

TRADES_PATH = Path(__file__).parent / "trades.json"


def load_portfolio(path=None):
    """Return the PORTFOLIO list the report expects, derived from trades.

    Raises FileNotFoundError if trades.json is missing — silently reporting an
    empty portfolio would look like a total loss.
    """
    path = Path(path) if path else TRADES_PATH
    doc = json.loads(path.read_text(encoding="utf-8"))
    meta = doc.get("meta", {})

    # Chronological order matters: a sell must not be applied before its buy.
    trades = sorted(doc.get("trades", []), key=lambda t: (t["date"], t.get("seq", 0)))

    books = {}
    for t in trades:
        tic = t["ticker"]
        b = books.setdefault(tic, {"qty": 0.0, "cost": 0.0})
        qty, price = float(t["qty"]), float(t["price"])

        if t["side"] == "buy":
            b["qty"] += qty
            b["cost"] += qty * price
        elif t["side"] == "sell":
            if b["qty"] <= 0:
                continue
            sold = min(qty, b["qty"])
            # Remove cost proportionally so the average per share is unchanged.
            b["cost"] -= b["cost"] * (sold / b["qty"])
            b["qty"] -= sold
            if b["qty"] <= 1e-9:
                b["qty"], b["cost"] = 0.0, 0.0
        else:
            raise ValueError(f"{tic} {t['date']}: side must be buy or sell, got {t['side']!r}")

    portfolio = []
    for tic, b in books.items():
        if b["qty"] <= 0:
            continue                      # fully exited — no longer a holding
        m = meta.get(tic, {})
        qty = round(b["qty"], 6)
        portfolio.append({
            "ticker":   tic,
            "name":     m.get("name", tic),
            "shares":   int(qty) if abs(qty - round(qty)) < 1e-9 else qty,
            "currency": m.get("currency", "ILS" if tic.endswith(".TA") else "USD"),
            "avg":      round(b["cost"] / b["qty"], 4),
            # "etf" or "stock" — an ETF having no ticker-specific news is normal,
            # and no trailing P/E is expected rather than a gap.
            "type":     m.get("type", "stock"),
        })

    portfolio.sort(key=lambda p: p["ticker"])
    return portfolio


def recent_trades(limit=10, path=None):
    """Most recent trades, newest first, shaped for the terminal's TradeLog."""
    path = Path(path) if path else TRADES_PATH
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    trades = sorted(doc.get("trades", []),
                    key=lambda t: (t["date"], t.get("seq", 0)), reverse=True)
    return [{
        "date":  t["date"],
        "sym":   t["ticker"].replace(".TA", ""),
        "side":  t["side"],
        "qty":   t["qty"],
        "price": t["price"],
        "note":  t.get("note", ""),
    } for t in trades[:limit]]


if __name__ == "__main__":
    for p in load_portfolio():
        print(f"{p['ticker']:<9} {p['shares']:>10g}  @ {p['avg']:>9.2f} {p['currency']}  {p['name']}")
